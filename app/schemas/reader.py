import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.book import ChapterResponse


class ReaderManifestChapter(BaseModel):
    chapter_index: int
    title: str
    content_url: str
    word_count: int


class ReaderManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: uuid.UUID
    title: str
    author: str | None
    language_code: str
    reading_direction: str
    chapters: list[ReaderManifestChapter] = Field(default_factory=list)
