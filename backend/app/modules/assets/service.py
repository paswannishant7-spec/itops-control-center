from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.access.repository import AccessRepository
from app.modules.assets.models import Asset, AssetAssignment, AssetEvent, AssetStatus
from app.modules.assets.repository import (
    AssetAccess,
    AssetRecord,
    AssetRepository,
    AssignmentRecord,
    EventRecord,
)
from app.modules.directory.models import DirectoryStatus
from app.modules.directory.repository import DirectoryRepository
from app.modules.identity.models import UserStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


def asset_state(asset: Asset) -> dict[str, object]:
    return {
        "asset_tag": asset.asset_tag,
        "serial_number": asset.serial_number,
        "hostname": asset.hostname,
        "asset_type": asset.asset_type,
        "owner_id": str(asset.owner_id) if asset.owner_id else None,
        "department_id": str(asset.department_id) if asset.department_id else None,
        "location_id": str(asset.location_id) if asset.location_id else None,
        "status": asset.status,
        "health_status": asset.health_status,
    }


class AssetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = AssetRepository(session)

    async def access(self, user_id: UUID, required: str | None = None) -> AssetAccess:
        _, grants = await AccessRepository(self.session).grants(user_id)
        permissions = frozenset(grants)
        if required and required not in permissions:
            raise HTTPException(403, "Permission denied")
        team_ids = (
            await DirectoryRepository(self.session).active_team_ids(user_id)
            if "asset:view_team" in permissions
            else frozenset()
        )
        return AssetAccess(
            user_id=user_id,
            permissions=permissions,
            team_department_ids=await self.repository.team_departments(team_ids),
        )

    async def _visible(
        self, user_id: UUID, asset_id: UUID, *, required: str | None = None, lock: bool = False
    ) -> tuple[AssetRecord, AssetAccess]:
        access = await self.access(user_id, required)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        record = await self.repository.visible_asset(asset_id, access, for_update=lock)
        if record is None:
            raise HTTPException(404, "Asset not found")
        return record, access

    def _event(
        self,
        asset: Asset,
        actor_id: UUID,
        action: str,
        before: dict[str, object] | None,
        reason: str,
        request_id: str,
    ) -> None:
        self.session.add(
            AssetEvent(
                asset_id=asset.id,
                actor_id=actor_id,
                action=action,
                before_state=before,
                after_state=asset_state(asset),
                reason=reason,
                request_id=request_id[:128],
                created_at=utc_now(),
            )
        )

    async def _commit(self, conflict: str) -> None:
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, conflict) from None

    async def _validate_assignment_refs(
        self, owner_id: UUID | None, department_id: UUID | None, location_id: UUID | None
    ) -> None:
        repository = DirectoryRepository(self.session)
        if owner_id:
            owner = await repository.user(owner_id)
            if owner is None or owner.status != UserStatus.ACTIVE:
                raise HTTPException(422, "Owner does not exist or is inactive")
        if department_id:
            department = await repository.department(department_id)
            if department is None or department.status != DirectoryStatus.ACTIVE:
                raise HTTPException(422, "Department does not exist or is inactive")
        if location_id:
            location = await repository.location(location_id)
            if location is None or location.status != DirectoryStatus.ACTIVE:
                raise HTTPException(422, "Location does not exist or is inactive")

    async def list_assets(self, actor_id: UUID, **filters: object) -> tuple[list[AssetRecord], int]:
        access = await self.access(actor_id)
        if not access.can_view_any:
            raise HTTPException(403, "Permission denied")
        return await self.repository.assets(access, **filters)  # type: ignore[arg-type]

    async def get_asset(self, actor_id: UUID, asset_id: UUID) -> AssetRecord:
        record, _ = await self._visible(actor_id, asset_id)
        return record

    async def require_linkable(self, actor_id: UUID, asset_id: UUID) -> Asset:
        record, _ = await self._visible(actor_id, asset_id)
        if record.asset.status in {AssetStatus.RETIRED, AssetStatus.DISPOSED}:
            raise HTTPException(409, "Retired or disposed assets cannot be linked")
        return record.asset

    async def create_asset(
        self, actor_id: UUID, values: dict[str, object], reason: str, request_id: str
    ) -> Asset:
        await self.access(actor_id, "asset:create")
        owner_id = values.get("owner_id")
        department_id = values.get("department_id")
        location_id = values.get("location_id")
        await self._validate_assignment_refs(
            owner_id if isinstance(owner_id, UUID) else None,
            department_id if isinstance(department_id, UUID) else None,
            location_id if isinstance(location_id, UUID) else None,
        )
        asset = Asset(id=uuid4(), **values)
        self.session.add(asset)
        if owner_id or department_id or location_id:
            self.session.add(
                AssetAssignment(
                    asset_id=asset.id,
                    owner_id=owner_id,
                    department_id=department_id,
                    location_id=location_id,
                    assigned_by_id=actor_id,
                    reason=reason,
                    started_at=utc_now(),
                )
            )
        self._event(asset, actor_id, "asset.created", None, reason, request_id)
        await self._commit("Asset tag or serial number already exists")
        return asset

    async def update_asset(
        self,
        actor_id: UUID,
        asset_id: UUID,
        values: dict[str, object],
        reason: str,
        request_id: str,
    ) -> Asset:
        record, _ = await self._visible(actor_id, asset_id, required="asset:update", lock=True)
        asset = record.asset
        if asset.status in {AssetStatus.RETIRED, AssetStatus.DISPOSED}:
            raise HTTPException(409, "Retired or disposed assets cannot be edited")
        purchase_date = values.get("purchase_date", asset.purchase_date)
        warranty_end = values.get("warranty_end", asset.warranty_end)
        if purchase_date and warranty_end and warranty_end < purchase_date:  # type: ignore[operator]
            raise HTTPException(422, "Warranty end cannot precede purchase date")
        before = asset_state(asset)
        for key, value in values.items():
            setattr(asset, key, value)
        self._event(asset, actor_id, "asset.updated", before, reason, request_id)
        await self._commit("Asset tag or serial number already exists")
        return asset

    async def assign(
        self,
        actor_id: UUID,
        asset_id: UUID,
        owner_id: UUID | None,
        department_id: UUID | None,
        location_id: UUID | None,
        clear: bool,
        reason: str,
        request_id: str,
    ) -> Asset:
        record, _ = await self._visible(actor_id, asset_id, required="asset:update", lock=True)
        asset = record.asset
        if asset.status in {AssetStatus.RETIRED, AssetStatus.DISPOSED}:
            raise HTTPException(409, "Retired or disposed assets cannot be assigned")
        if not clear:
            await self._validate_assignment_refs(owner_id, department_id, location_id)
        before = asset_state(asset)
        active = await self.repository.active_assignment(asset_id)
        now = utc_now()
        if active:
            active.ended_at = now
        asset.owner_id = None if clear else owner_id
        asset.department_id = None if clear else department_id
        asset.location_id = None if clear else location_id
        if not clear:
            self.session.add(
                AssetAssignment(
                    asset_id=asset_id,
                    owner_id=owner_id,
                    department_id=department_id,
                    location_id=location_id,
                    assigned_by_id=actor_id,
                    reason=reason,
                    started_at=now,
                )
            )
        self._event(
            asset,
            actor_id,
            "asset.unassigned" if clear else "asset.assigned",
            before,
            reason,
            request_id,
        )
        await self._commit("Asset assignment conflicted with another update")
        return asset

    async def retire(self, actor_id: UUID, asset_id: UUID, reason: str, request_id: str) -> Asset:
        record, _ = await self._visible(actor_id, asset_id, required="asset:retire", lock=True)
        asset = record.asset
        if asset.status == AssetStatus.RETIRED:
            return asset
        if asset.status == AssetStatus.DISPOSED:
            raise HTTPException(409, "Disposed assets cannot be retired")
        before = asset_state(asset)
        active = await self.repository.active_assignment(asset_id)
        if active:
            active.ended_at = utc_now()
        asset.owner_id = None
        asset.department_id = None
        asset.location_id = None
        asset.status = AssetStatus.RETIRED
        self._event(asset, actor_id, "asset.retired", before, reason, request_id)
        await self._commit("Asset retirement conflicted with another update")
        return asset

    async def history(
        self, actor_id: UUID, asset_id: UUID
    ) -> tuple[list[AssignmentRecord], list[EventRecord]]:
        await self._visible(actor_id, asset_id)
        return (
            await self.repository.assignments(asset_id),
            await self.repository.events(asset_id),
        )
