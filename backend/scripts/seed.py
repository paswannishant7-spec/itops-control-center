import asyncio

from app.db.seeds import run_seeds
from app.db.session import transaction


async def main() -> None:
    async with transaction() as session:
        await run_seeds(session)


if __name__ == "__main__":
    asyncio.run(main())
