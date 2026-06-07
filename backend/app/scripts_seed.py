import asyncio

from app.core.database import AsyncSessionLocal
from app.services.auth import register_user


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for username in ["alice", "bob", "carol"]:
            try:
                await register_user(
                    db,
                    username=username,
                    display_name=username.title(),
                    email=f"{username}@example.com",
                    password="password123",
                )
                print(f"created {username}@example.com / password123")
            except Exception as exc:
                print(f"skipped {username}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
