"""Run once when upgrading an existing Phase 3 administrator."""

import asyncio

from app.core.config import get_settings
from app.db.session import dispose_engine, transaction
from app.modules.access.bootstrap import bootstrap_existing


async def main() -> None:
    try:
        async with transaction() as session:
            await bootstrap_existing(session, get_settings())
        print("Administrator role assigned and audited.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
