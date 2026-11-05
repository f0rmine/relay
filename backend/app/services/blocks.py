"""Blocking users: either-direction checks and listing."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_block import UserBlock


async def is_blocked(db: AsyncSession, user_a: str, user_b: str) -> bool:
    """True if either user blocks the other."""
    found = await db.scalar(
        select(UserBlock.id)
        .where(
            or_(
                (UserBlock.blocker_id == user_a) & (UserBlock.blocked_id == user_b),
                (UserBlock.blocker_id == user_b) & (UserBlock.blocked_id == user_a),
            )
        )
        .limit(1)
    )
    return found is not None


async def list_blocked(db: AsyncSession, user_id: str) -> list[User]:
    rows = (
        await db.scalars(
            select(User)
            .join(UserBlock, UserBlock.blocked_id == User.id)
            .where(UserBlock.blocker_id == user_id)
            .order_by(User.username.asc())
        )
    ).all()
    return list(rows)


async def blocked_ids_union(db: AsyncSession, user_id: str) -> list[str]:
    """Ids of users blocked in either direction (for search exclusion)."""
    blocked_by_me = (
        await db.scalars(select(UserBlock.blocked_id).where(UserBlock.blocker_id == user_id))
    ).all()
    blocking_me = (
        await db.scalars(select(UserBlock.blocker_id).where(UserBlock.blocked_id == user_id))
    ).all()
    return list(dict.fromkeys([*blocked_by_me, *blocking_me]))
