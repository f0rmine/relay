import asyncio
import os

from fastapi import HTTPException, status

from app.core.database import AsyncSessionLocal
from app.services.auth import register_user


def get_seed_password() -> str:
    password = os.environ.get("RELAY_SEED_PASSWORD")
    if not password or len(password) < 8:
        raise RuntimeError("RELAY_SEED_PASSWORD must contain at least 8 characters")
    return password


async def main() -> None:
    password = get_seed_password()
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
            "serhiy": "Сергій",
        }
        for username, display_name in ukrainian_users.items():
            try:
                await register_user(
                    db,
                    username=username,
                    display_name=display_name,
                    email=f"{username}@example.com",
                    password=password,
                )
                print(f"created {username}@example.com ({display_name})")
            except HTTPException as exc:
                if exc.status_code != status.HTTP_409_CONFLICT:
                    raise
                print(f"skipped existing user {username}")


if __name__ == "__main__":
    asyncio.run(main())
