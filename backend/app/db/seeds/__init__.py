"""Deterministic, idempotent database seed registry."""

from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.directory.seeds import seed_enterprise_directory
from app.modules.identity.seeds import seed_initial_admin

Seed = Callable[[AsyncSession], Awaitable[None]]


def seed_registry() -> Sequence[Seed]:
    """Return seeds in dependency order. Domain phases append explicit seed functions."""
    return (seed_enterprise_directory, seed_initial_admin)


async def run_seeds(session: AsyncSession) -> None:
    for seed in seed_registry():
        await seed(session)
