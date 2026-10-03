from datetime import UTC, datetime, time, timedelta
from typing import TypedDict, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sla.models import (
    BusinessCalendar,
    BusinessHoliday,
    BusinessWindow,
    PriorityMatrix,
    SlaEvent,
    SlaInstance,
    SlaPause,
    SlaPolicy,
    SlaState,
)
from app.modules.sla.repository import CalendarBundle, SlaRepository
from app.modules.tickets.models import Ticket, TicketStatus


class Measurement(TypedDict):
    state: SlaState
    active_target: str
    response_target_seconds: int
    resolution_target_seconds: int
    response_elapsed_seconds: int
    resolution_elapsed_seconds: int
    elapsed_seconds: int
    remaining_seconds: int
    percentage: float
    is_paused: bool


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def calendar_intervals(
    bundle: CalendarBundle, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    if end <= start:
        return []
    zone = ZoneInfo(bundle.calendar.timezone)
    local_start, local_end = aware(start).astimezone(zone), aware(end).astimezone(zone)
    first_day = local_start.date() - timedelta(days=1)
    intervals: list[tuple[datetime, datetime]] = []
    for offset in range((local_end.date() - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        if day in bundle.holidays:
            continue
        for window in bundle.windows:
            if window.weekday != day.weekday():
                continue
            begins = datetime.combine(day, time(), zone) + timedelta(minutes=window.start_minute)
            finishes = datetime.combine(day, time(), zone) + timedelta(minutes=window.end_minute)
            clipped = (
                max(aware(start), begins.astimezone(UTC)),
                min(aware(end), finishes.astimezone(UTC)),
            )
            if clipped[1] > clipped[0]:
                intervals.append(clipped)
    intervals.sort()
    merged: list[tuple[datetime, datetime]] = []
    for begins, finishes in intervals:
        if merged and begins <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], finishes))
        else:
            merged.append((begins, finishes))
    return merged


def business_seconds(bundle: CalendarBundle, start: datetime, end: datetime) -> int:
    return int(
        sum(
            (finish - begin).total_seconds()
            for begin, finish in calendar_intervals(bundle, start, end)
        )
    )


def elapsed_business_seconds(
    bundle: CalendarBundle,
    start: datetime,
    end: datetime,
    pauses: list[SlaPause],
) -> int:
    elapsed = business_seconds(bundle, start, end)
    for pause in pauses:
        pause_end = min(end, aware(pause.ended_at) if pause.ended_at else end)
        pause_start = max(start, aware(pause.started_at))
        if pause_end > pause_start:
            elapsed -= business_seconds(bundle, pause_start, pause_end)
    return max(0, elapsed)


class SlaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = SlaRepository(session)

    async def resolve_priority(self, impact: str, urgency: str) -> str:
        priority = await self.repository.priority(impact, urgency)
        if priority is None:
            raise HTTPException(503, "Priority matrix is not configured")
        return priority

    async def initialize(self, ticket: Ticket) -> SlaInstance:
        policy = await self.repository.active_policy(ticket.priority)
        if policy is None:
            raise HTTPException(503, f"No active SLA policy exists for {ticket.priority}")
        instance = SlaInstance(
            ticket_id=ticket.id,
            policy_id=policy.id,
            calendar_id=policy.calendar_id,
            state=SlaState.ON_TRACK,
            response_target_seconds=policy.response_target_minutes * 60,
            resolution_target_seconds=policy.resolution_target_minutes * 60,
            at_risk_percent=policy.at_risk_percent,
        )
        self.session.add(instance)
        await self.session.flush()
        await self._event(instance, "sla.created", "created", {"priority": ticket.priority})
        return instance

    async def reconfigure(self, ticket: Ticket) -> None:
        instance = await self.repository.instance(ticket.id, lock=True)
        if instance is None:
            await self.initialize(ticket)
            return
        policy = await self.repository.active_policy(ticket.priority)
        if policy is None:
            raise HTTPException(503, f"No active SLA policy exists for {ticket.priority}")
        if instance.policy_id == policy.id:
            return
        instance.policy_id = policy.id
        instance.calendar_id = policy.calendar_id
        instance.response_target_seconds = policy.response_target_minutes * 60
        instance.resolution_target_seconds = policy.resolution_target_minutes * 60
        instance.at_risk_percent = policy.at_risk_percent
        await self._event(
            instance, "sla.policy_changed", f"policy:{policy.id}", {"priority": ticket.priority}
        )

    async def on_first_response(self, ticket_id: UUID, occurred_at: datetime) -> None:
        instance = await self.repository.instance(ticket_id, lock=True)
        if instance and instance.response_completed_at is None:
            instance.response_completed_at = occurred_at
            await self._event(instance, "sla.response_completed", "response:completed", {})

    async def on_transition(
        self, ticket_id: UUID, current: TicketStatus, target: TicketStatus, occurred_at: datetime
    ) -> None:
        instance = await self.repository.instance(ticket_id, lock=True)
        if instance is None:
            return
        pending = {TicketStatus.PENDING_USER, TicketStatus.PENDING_VENDOR}
        active_pause = await self.repository.active_pause(instance.id)
        if target in pending and active_pause is None:
            pause = SlaPause(instance_id=instance.id, reason=target, started_at=occurred_at)
            self.session.add(pause)
            await self.session.flush()
            instance.state = SlaState.PAUSED
            await self._event(instance, "sla.paused", f"pause:{pause.id}", {"reason": target})
        elif current in pending and active_pause:
            active_pause.ended_at = occurred_at
            await self._event(
                instance, "sla.resumed", f"resume:{active_pause.id}", {"status": target}
            )
        if target in {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED}:
            instance.resolution_completed_at = occurred_at
        elif current == TicketStatus.RESOLVED and target == TicketStatus.OPEN:
            instance.resolution_completed_at = None
            instance.state = SlaState.ON_TRACK

    async def snapshot(
        self, ticket: Ticket, now: datetime | None = None
    ) -> dict[str, object] | None:
        instance = await self.repository.instance(ticket.id)
        if instance is None:
            return None
        policy = await self.repository.policy(instance.policy_id)
        bundle = await self.repository.calendar_bundle(instance.calendar_id)
        if policy is None or bundle is None:
            raise HTTPException(409, "SLA configuration is unavailable")
        values = await self._measure(instance, ticket, bundle, aware(now or datetime.now(UTC)))
        return {
            "instance_id": instance.id,
            "policy_name": policy.name,
            "calendar_name": bundle.calendar.name,
            "calendar_timezone": bundle.calendar.timezone,
            **values,
            "response_breached_at": instance.response_breached_at,
            "resolution_breached_at": instance.resolution_breached_at,
            "escalated_at": instance.escalated_at,
            "last_evaluated_at": instance.last_evaluated_at,
        }

    async def _measure(
        self, instance: SlaInstance, ticket: Ticket, bundle: CalendarBundle, now: datetime
    ) -> Measurement:
        pauses = await self.repository.pauses(instance.id)
        created = aware(ticket.created_at)
        response_end = aware(ticket.first_response_at) if ticket.first_response_at else now
        resolution_end = aware(ticket.resolved_at) if ticket.resolved_at else now
        response_elapsed = elapsed_business_seconds(bundle, created, response_end, pauses)
        resolution_elapsed = elapsed_business_seconds(bundle, created, resolution_end, pauses)
        active_target = "RESPONSE" if ticket.first_response_at is None else "RESOLUTION"
        elapsed = response_elapsed if active_target == "RESPONSE" else resolution_elapsed
        target = (
            instance.response_target_seconds
            if active_target == "RESPONSE"
            else instance.resolution_target_seconds
        )
        percentage = min(100.0, round(elapsed * 100 / target, 2))
        is_paused = any(pause.ended_at is None for pause in pauses)
        is_complete = ticket.status in {
            TicketStatus.RESOLVED,
            TicketStatus.CLOSED,
            TicketStatus.CANCELLED,
        }
        breached = elapsed >= target or bool(
            instance.response_breached_at or instance.resolution_breached_at
        )
        state = (
            SlaState.COMPLETED
            if is_complete
            else SlaState.PAUSED
            if is_paused
            else SlaState.BREACHED
            if breached
            else SlaState.AT_RISK
            if percentage >= instance.at_risk_percent
            else SlaState.ON_TRACK
        )
        return Measurement(
            state=state,
            active_target=active_target,
            response_target_seconds=instance.response_target_seconds,
            resolution_target_seconds=instance.resolution_target_seconds,
            response_elapsed_seconds=response_elapsed,
            resolution_elapsed_seconds=resolution_elapsed,
            elapsed_seconds=elapsed,
            remaining_seconds=max(0, target - elapsed),
            percentage=percentage,
            is_paused=is_paused,
        )

    async def evaluate(self, instance: SlaInstance, ticket: Ticket, now: datetime) -> bool:
        bundle = await self.repository.calendar_bundle(instance.calendar_id)
        if bundle is None:
            raise HTTPException(409, "SLA calendar is unavailable")
        before = instance.state
        measured = await self._measure(instance, ticket, bundle, aware(now))
        instance.state = str(measured["state"])
        instance.response_elapsed_seconds = int(measured["response_elapsed_seconds"])
        instance.resolution_elapsed_seconds = int(measured["resolution_elapsed_seconds"])
        instance.last_evaluated_at = aware(now)
        active = str(measured["active_target"]).lower()
        elapsed = int(measured["elapsed_seconds"])
        target = (
            instance.response_target_seconds
            if active == "response"
            else instance.resolution_target_seconds
        )
        if elapsed * 100 >= target * instance.at_risk_percent:
            await self._event(instance, "sla.at_risk", f"{active}:at-risk", {"target": active})
        if elapsed >= target:
            breach_field = f"{active}_breached_at"
            if getattr(instance, breach_field) is None:
                setattr(instance, breach_field, aware(now))
                await self._event(
                    instance, "sla.breached", f"{active}:breached", {"target": active}, True
                )
            if active == "resolution" and instance.escalated_at is None:
                instance.escalated_at = aware(now)
                await self._event(instance, "sla.escalated", "resolution:escalated", {}, True)
        if measured["state"] == SlaState.COMPLETED:
            await self._event(instance, "sla.completed", "completed", {})
        return before != instance.state

    async def run_once(self, now: datetime | None = None, limit: int = 100) -> tuple[int, int]:
        records = await self.repository.active_instances(limit)
        changed = sum(
            [
                await self.evaluate(instance, ticket, aware(now or datetime.now(UTC)))
                for instance, ticket in records
            ]
        )
        await self.session.commit()
        return len(records), changed

    async def _event(
        self,
        instance: SlaInstance,
        event_type: str,
        suffix: str,
        payload: dict[str, object],
        notify: bool = False,
    ) -> None:
        key = f"{instance.id}:{suffix}"
        if not await self.repository.has_event(key):
            self.session.add(
                SlaEvent(
                    instance_id=instance.id,
                    event_type=event_type,
                    idempotency_key=key,
                    payload=payload,
                    notification_required=notify,
                )
            )

    async def set_matrix(self, impact: str, urgency: str, priority: str) -> PriorityMatrix:
        record = await self.session.get(PriorityMatrix, (impact, urgency), with_for_update=True)
        if record is None:
            record = PriorityMatrix(impact=impact, urgency=urgency, priority=priority)
            self.session.add(record)
        else:
            record.priority = priority
        await self._commit("Priority matrix update conflicted")
        return record

    async def save_calendar(
        self, values: dict[str, object], calendar_id: UUID | None = None
    ) -> BusinessCalendar:
        try:
            ZoneInfo(str(values["timezone"]))
        except ZoneInfoNotFoundError:
            raise HTTPException(422, "Timezone is not recognized") from None
        windows = cast(list[dict[str, int]], values.pop("windows"))
        holidays = cast(list[dict[str, object]], values.pop("holidays"))
        make_default = bool(values.pop("is_default"))
        if calendar_id:
            calendar = await self.session.get(BusinessCalendar, calendar_id, with_for_update=True)
            if calendar is None:
                raise HTTPException(404, "Business calendar not found")
            await self.repository.replace_calendar_children(calendar_id)
            for key, value in values.items():
                setattr(calendar, key, value)
        else:
            calendar = BusinessCalendar(**values, is_default=False)
            self.session.add(calendar)
            await self.session.flush()
        if make_default:
            await self.session.execute(
                update(BusinessCalendar)
                .where(BusinessCalendar.id != calendar.id)
                .values(is_default=False)
            )
        calendar.is_default = make_default
        self.session.add_all([BusinessWindow(calendar_id=calendar.id, **item) for item in windows])
        self.session.add_all(
            [BusinessHoliday(calendar_id=calendar.id, **item) for item in holidays]
        )
        await self._commit("Business calendar conflicts with existing configuration")
        await self.session.refresh(calendar)
        return calendar

    async def save_policy(
        self, values: dict[str, object], policy_id: UUID | None = None
    ) -> SlaPolicy:
        calendar = await self.session.get(BusinessCalendar, values["calendar_id"])
        if calendar is None or not calendar.is_active:
            raise HTTPException(422, "An active business calendar is required")
        if values.get("is_active"):
            existing = await self.repository.active_policy(str(values["priority"]))
            if existing and existing.id != policy_id:
                existing.is_active = False
        if policy_id:
            policy = await self.repository.policy(policy_id, lock=True)
            if policy is None:
                raise HTTPException(404, "SLA policy not found")
            for key, value in values.items():
                setattr(policy, key, value)
        else:
            policy = SlaPolicy(**values)
            self.session.add(policy)
        await self._commit("SLA policy conflicts with existing configuration")
        await self.session.refresh(policy)
        return policy

    async def _commit(self, detail: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, detail) from None
