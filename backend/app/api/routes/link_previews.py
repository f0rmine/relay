from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.services.link_previews import get_or_fetch_preview, serialize_preview

router = APIRouter(prefix="/link-previews", tags=["link-previews"])


@router.get("")
async def get_link_preview(
    current_user: CurrentUser,
    db: DbSession,
    url: str = Query(min_length=1, max_length=2000),
) -> dict:
    preview = await get_or_fetch_preview(db, url)
    serialized = serialize_preview(preview)
    if serialized is None:
        return {"url": url, "title": None, "description": None, "image_url": None}
    return serialized
