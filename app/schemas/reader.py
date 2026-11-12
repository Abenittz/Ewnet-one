from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.book import ReadingDirection


class ReaderManifestChapter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    index: int
    title: str
    word_count: int


class ReaderEdition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: uuid.UUID
    language_code: str
    title: str


class ReaderManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: uuid.UUID
    work_id: uuid.UUID
    title: str
    author: str | None
    language_code: str
    reading_direction: ReadingDirection
    total_chapters: int
    total_words: int
    total_references: int = 0
    chapters: list[ReaderManifestChapter] = Field(default_factory=list)
    available_editions: list[ReaderEdition] = Field(default_factory=list)



class ChapterDetailResponse(BaseModel):
    book_id: uuid.UUID
    chapter_index: int
    title: str
    word_count: int
    total_chapters: int
    has_previous: bool
    has_next: bool
    previous_chapter_index: int | None
    next_chapter_index: int | None
    content_html_url: str


class UserProgressUpdate(BaseModel):
    chapter_index: int = Field(default=0, ge=0)
    scroll_offset: int = Field(default=0, ge=0)
    user_id: uuid.UUID | None = None


class UserProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    book_id: uuid.UUID
    chapter_index: int
    scroll_offset: int
    updated_at: datetime


class BookmarkCreate(BaseModel):
    chapter_index: int = Field(default=0, ge=0)
    scroll_offset: int = Field(default=0, ge=0)
    title: str | None = None
    note: str | None = None


class BookmarkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    book_id: uuid.UUID
    chapter_index: int
    scroll_offset: int
    title: str | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime

