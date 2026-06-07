from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    detail: str


class PaginationMeta(BaseModel):
    next_cursor: datetime | None = None
    has_more: bool = False
