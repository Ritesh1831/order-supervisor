import asyncio

from app import db
from app.supervisors.templates import TEMPLATES


async def main() -> None:
    await db.init_schema()
    for t in TEMPLATES:
        await db.upsert_supervisor(t)
        print(f"seeded supervisor: {t['id']} ({t['name']})")
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
