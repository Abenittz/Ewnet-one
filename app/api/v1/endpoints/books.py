import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.book import Book
from app.schemas.book import BookCatalogItem, BookDetailResponse, PaginatedBookList
from app.services.storage import storage_service

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=PaginatedBookList)
async def list_books(
    language_code: str | None = Query(default=None, min_length=2, max_length=10),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedBookList:
    """Paginated catalog of ingested books, optionally filtered by language."""
    filters = []
    if language_code is not None:
        filters.append(Book.language_code == language_code.strip().lower())

    count_stmt = select(func.count()).select_from(Book)
    list_stmt = select(Book).order_by(Book.created_at.desc())
    if filters:
        count_stmt = count_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int((await db.execute(count_stmt)).scalar_one())
    result = await db.execute(list_stmt.offset((page - 1) * page_size).limit(page_size))
    books = list(result.scalars().all())

    items = [
        BookCatalogItem(
            id=book.id,
            title=book.title,
            author=book.author,
            cover_image_url=storage_service.cover_image_url(
                str(book.work_id),
                book.language_code,
            ),
            language_code=book.language_code,
        )
        for book in books
    ]
    return PaginatedBookList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Book:
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")
    return book
