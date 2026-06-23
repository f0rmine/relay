import asyncio

from app.core.database import AsyncSessionLocal
from app.services.auth import register_user


async def main() -> None:
    async with AsyncSessionLocal() as db:
        ukrainian_users = {
            "olena": "Олена",
            "taras": "Тарас",
            "oksana": "Оксана",
            "mykola": "Микола",
            "andriy": "Андрій",
            "svitlana": "Світлана",
            "dmytro": "Дмитро",
            "natalia": "Наталя",
            "viktor": "Віктор",
            "tetiana": "Тетяна",
            "iryna": "Ірина",
            "oleksandr": "Олександр",
            "kateryna": "Катерина",
            "yuriy": "Юрій",
            "nadiya": "Надія",
            "maksym": "Максим",
            "yuliya": "Юлія",
            "bogdan": "Богдан",
            "valeriya": "Валерія",
            "serhiy": "Сергій"
        }
        for username, display_name in ukrainian_users.items():
            try:
                await register_user(
                    db,
                    username=username,
                    display_name=display_name,
                    email=f"{username}@example.com",
                    password="password123",
                )
                print(f"created {username}@example.com ({display_name}) / password123")
            except Exception as exc:
                print(f"skipped {username}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
