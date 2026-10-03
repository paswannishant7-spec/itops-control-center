from datetime import datetime
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.realtime.models import RealtimeCursor, RealtimeEvent


class RealtimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish_pending(self, limit: int) -> int:
        pending = await self.session.scalar(
            select(RealtimeEvent.id).where(RealtimeEvent.sequence.is_(None)).limit(1)
        )
        if pending is None:
            await self.session.rollback()
            return 0
        cursor = await self.session.get(RealtimeCursor, 1, with_for_update=True)
        if cursor is None:
            cursor = RealtimeCursor(id=1, value=0)
            self.session.add(cursor)
            await self.session.flush()
        events = list(
            await self.session.scalars(
                select(RealtimeEvent)
                .where(RealtimeEvent.sequence.is_(None))
                .order_by(RealtimeEvent.created_at, RealtimeEvent.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for value in events:
            cursor.value += 1
            value.sequence = cursor.value
        await self.session.commit()
        return len(events)

    async def latest_sequence(self) -> int:
        return int(
            cast(
                int | None,
                await self.session.scalar(select(func.max(RealtimeEvent.sequence))),
            )
            or 0
        )

    async def first_sequence(self) -> int | None:
        value = cast(
            int | None,
            await self.session.scalar(select(func.min(RealtimeEvent.sequence))),
        )
        return int(value) if value is not None else None

    async def events_after(self, cursor: int, limit: int) -> list[RealtimeEvent]:
        return list(
            await self.session.scalars(
                select(RealtimeEvent)
                .where(
                    RealtimeEvent.sequence.is_not(None),
                    RealtimeEvent.sequence > cursor,
                )
                .order_by(RealtimeEvent.sequence)
                .limit(limit)
            )
        )

    async def prune(self, before: datetime) -> int:
        result = await self.session.execute(
            delete(RealtimeEvent)
            .where(RealtimeEvent.sequence.is_not(None), RealtimeEvent.created_at < before)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
