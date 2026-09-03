import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.book import Book
from app.schemas.reader import ReaderManifestChapter, ReaderManifestResponse

router = APIRouter(prefix="/reader", tags=["reader"])


@router.get("/{book_id}/manifest", response_model=ReaderManifestResponse)
async def get_reader_manifest(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReaderManifestResponse:
    """
    Dummy manifest endpoint returning chapter metadata for the PWA reader shell.
    """
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    chapters = [
        ReaderManifestChapter(
            chapter_index=chapter.chapter_index,
            title=chapter.title,
            content_url=f"/api/v1/reader/{book_id}/chapters/{chapter.chapter_index}",
            word_count=chapter.word_count,
        )
        for chapter in book.chapters
    ]

    return ReaderManifestResponse(
        book_id=book.id,
        title=book.title,
        author=book.author,
        language_code=book.language_code,
        reading_direction=book.reading_direction.value,
        chapters=chapters,
    )
