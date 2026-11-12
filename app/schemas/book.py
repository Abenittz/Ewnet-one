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


class WorkUpdate(BaseModel):
    original_title: str = Field(..., min_length=1, max_length=512)


class BookCreate(BaseModel):
    work_id: uuid.UUID | None = None
    original_title: str | None = Field(default=None, min_length=1, max_length=512)
    language_code: str = Field(
        ...,
        min_length=2,
        max_length=10,
        pattern=r"^[a-z]{2,3}(?:-[a-zA-Z0-9]+)?$",
    )
    reading_direction: ReadingDirection = ReadingDirection.LTR
    title: str = Field(..., min_length=1, max_length=512)
    author: str | None = Field(default=None, max_length=256)
    format: BookFormat


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    author: str | None = Field(default=None, max_length=256)
    reading_direction: ReadingDirection | None = None


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
    cover_image_id: uuid.UUID | None = None
    cover_image_url: str | None = None
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


class UploadBookResponse(BaseModel):
    work_id: uuid.UUID
    book_id: uuid.UUID
    chapters_created: int


class ScriptureReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    chapter_index: int
    reference_text: str
    book_name: str
    chapter_num: int | None = None
    verse_start: int | None = None
    verse_end: int | None = None
    anchor_id: str | None = None


class AdminChapterResult(BaseModel):
    index: int
    title: str
    html: str


class AdminUploadBookResponse(BaseModel):
    work_id: uuid.UUID
    book_id: uuid.UUID
    title: str
    author: str | None
    language: str
    chapters: list[AdminChapterResult]
    references: list[ScriptureReferenceResponse] = Field(default_factory=list)


class BookCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
    title: str
    author: str | None
    cover_image_id: uuid.UUID | None = None
    cover_image_url: str | None = None
    language_code: str


class PaginatedBookList(BaseModel):
    items: list[BookCatalogItem]
    total: int
    page: int
    page_size: int


class CoverUploadResponse(BaseModel):
    book_id: uuid.UUID
    cover_image_id: uuid.UUID
    cover_image_url: str


class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    storage_backend: str
    url: str
    created_at: datetime


class ExploreItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    category: str
    is_featured: bool
    display_order: int
    title: str
    author: str | None
    language_code: str
    cover_image_id: uuid.UUID | None = None
    cover_image_url: str | None = None
    is_in_library: bool = False
    is_downloaded: bool = False


class PublishBookResponse(BaseModel):
    book_id: uuid.UUID
    slug: str | None = None
    explore_id: uuid.UUID
    category: str
    is_featured: bool
    display_order: int
    published: bool = True


class UserLibraryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    book_id: uuid.UUID
    title: str
    author: str | None
    language_code: str
    format: BookFormat
    cover_image_id: uuid.UUID | None = None
    cover_image_url: str | None = None
    is_downloaded: bool
    downloaded_at: datetime | None = None
    last_read_chapter: int = 0
    scroll_offset: int = 0
    saved_at: datetime


class DownloadStateUpdate(BaseModel):
    is_downloaded: bool = True


class OfflineChapterBundle(BaseModel):
    index: int
    title: str
    word_count: int
    html: str


class OfflineBookPackageResponse(BaseModel):
    book: BookCatalogItem
    total_chapters: int
    total_words: int
    total_references: int
    chapters: list[OfflineChapterBundle]
    references: list[ScriptureReferenceResponse]
    asset_urls: list[str] = Field(
        default_factory=list,
        description="List of image resource URLs to download and store in local storage / Cache Storage",
    )


class WorkDetailResponse(WorkResponse):
    books: list[BookCatalogItem] = Field(default_factory=list)


class WorkCatalogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_title: str
    languages: list[str] = Field(default_factory=list)
    book_count: int = 0
    created_at: datetime


class PaginatedWorkList(BaseModel):
    items: list[WorkCatalogItem]
    total: int
    page: int
    page_size: int
