import uuid

import aiofiles
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.book import Book, Chapter
from app.schemas.reader import ReaderManifestChapter, ReaderManifestResponse
from app.services.storage import storage_service

router = APIRouter(prefix="/reader", tags=["reader"])


@router.get("/{book_id}/manifest", response_model=ReaderManifestResponse)
async def get_reader_manifest(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ReaderManifestResponse:
    """Return book metadata and chapter list for the reader shell (no HTML bodies)."""
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    chapters = sorted(book.chapters, key=lambda chapter: chapter.chapter_index)
    return ReaderManifestResponse(
        book_id=book.id,
        title=book.title,
        author=book.author,
        language_code=book.language_code,
        reading_direction=book.reading_direction,
        chapters=[
            ReaderManifestChapter(
                id=chapter.id,
                index=chapter.chapter_index,
                title=chapter.title,
                word_count=chapter.word_count,
            )
            for chapter in chapters
        ],
    )


@router.get(
    "/{book_id}/chapters/{chapter_index}/html",
    response_class=HTMLResponse,
)
async def get_chapter_html(
    book_id: uuid.UUID,
    chapter_index: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Deliver a chapter's stored HTML for the reader engine."""
    result = await db.execute(
        select(Chapter).where(
            Chapter.book_id == book_id,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise NotFoundError("Chapter not found")

    html_path = storage_service.resolve_stored_path(chapter.content_html_path)
    if not html_path.is_file():
        raise NotFoundError("Chapter HTML file not found")

    async with aiofiles.open(html_path, encoding="utf-8") as handle:
        html = await handle.read()

    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")
