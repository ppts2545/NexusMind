import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl


class DocumentIngest(BaseModel):
    title: str
    content: str | None = None
    source_url: HttpUrl | None = None
    mime_type: str = "text/plain"
    meta: dict | None = None


class CrawlRequest(BaseModel):
    url: HttpUrl
    max_depth: int = 2
    max_pages: int = 50
    follow_external: bool = False
    meta: dict | None = None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str
    source_url: str | None
    source_type: str
    status: str
    chunk_count: int
    language: str | None
    meta: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
