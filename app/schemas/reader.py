import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.book import ReadingDirection


class ReaderManifestChapter(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    index: int
    title: str
    word_count: int


class ReaderManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: uuid.UUID
    title: str
    author: str | None
    language_code: str
    reading_direction: ReadingDirection
    chapters: list[ReaderManifestChapter] = Field(default_factory=list)
