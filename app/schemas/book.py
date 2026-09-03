import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.book import BookFormat, ReadingDirection


class WorkCreate(BaseModel):
    original_title: str = Field(..., min_length=1, max_length=512)


class WorkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_title: str
    created_at: datetime
    updated_at: datetime


class BookCreate(BaseModel):
    work_id: uuid.UUID | None = None
    original_title: str | None = Field(default=None, min_length=1, max_length=512)
    language_code: str = Field(..., min_length=2, max_length=10)
    reading_direction: ReadingDirection = ReadingDirection.LTR
    title: str = Field(..., min_length=1, max_length=512)
    author: str | None = Field(default=None, max_length=256)
    format: BookFormat


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
    language_code: str
    reading_direction: ReadingDirection
    title: str
    author: str | None
    file_path: str
    format: BookFormat
    created_at: datetime
    updated_at: datetime


class ChapterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    chapter_index: int
    title: str
    content_html_path: str
    word_count: int
    created_at: datetime
    updated_at: datetime


class BookDetailResponse(BookResponse):
    chapters: list[ChapterResponse] = Field(default_factory=list)
