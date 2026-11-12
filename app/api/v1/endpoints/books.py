import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import AppError, NotFoundError
from app.models.book import Book, Work
from app.schemas.book import (
    BookCatalogItem,
    BookDetailResponse,
    BookUpdate,
    CoverUploadResponse,
    PaginatedBookList,
)
from app.services.media_storage import media_storage
from app.services.storage import storage_service

router = APIRouter(prefix="/books", tags=["books"])

_ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("", response_model=PaginatedBookList)
async def list_books(
    language_code: str | None = Query(default=None, min_length=2, max_length=10),
    search: str | None = Query(default=None, description="Search across title and author"),
    work_id: uuid.UUID | None = Query(default=None, description="Filter by work ID"),
    sort_by: str = Query(default="created_at", pattern="^(created_at|title)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedBookList:
    """Paginated catalog of ingested books with search, language filter, and sorting."""
    filters = []
    if language_code is not None:
        filters.append(Book.language_code == language_code.strip().lower())

    if work_id is not None:
        filters.append(Book.work_id == work_id)

    if search is not None and search.strip():
        term = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Book.title).like(term),
                func.lower(Book.author).like(term),
            )
        )

    order_col = Book.title if sort_by == "title" else Book.created_at
    order_clause = order_col.desc() if sort_order == "desc" else order_col.asc()

    count_stmt = select(func.count()).select_from(Book)
    list_stmt = select(Book).order_by(order_clause)
    if filters:
        count_stmt = count_stmt.where(*filters)
        list_stmt = list_stmt.where(*filters)

    total = int((await db.execute(count_stmt)).scalar_one())
    result = await db.execute(list_stmt.offset((page - 1) * page_size).limit(page_size))
    books = list(result.scalars().all())

    items = [
        BookCatalogItem(
            id=book.id,
            work_id=book.work_id,
            title=book.title,
            author=book.author,
            cover_image_id=book.cover_image_id,
            cover_image_url=media_storage.get_image_url(book.cover_image_id)
            or storage_service.cover_image_url(
                str(book.work_id),
                book.language_code,
            ),
            language_code=book.language_code,
        )
        for book in books
    ]
    return PaginatedBookList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{book_id}", response_model=BookDetailResponse)
async def get_book(book_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> BookDetailResponse:
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    response = BookDetailResponse.model_validate(book)
    response.cover_image_url = media_storage.get_image_url(book.cover_image_id) or storage_service.cover_image_url(
        str(book.work_id),
        book.language_code,
    )
    return response


@router.patch("/{book_id}", response_model=BookDetailResponse)
async def update_book(
    book_id: uuid.UUID,
    payload: BookUpdate,
    db: AsyncSession = Depends(get_db),
) -> BookDetailResponse:
    """Update book title, author, or reading direction."""
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    if payload.title is not None:
        book.title = payload.title.strip()
    if payload.author is not None:
        book.author = payload.author.strip() if payload.author else None
    if payload.reading_direction is not None:
        book.reading_direction = payload.reading_direction

    await db.flush()

    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one()

    response = BookDetailResponse.model_validate(book)
    response.cover_image_url = media_storage.get_image_url(book.cover_image_id) or storage_service.cover_image_url(
        str(book.work_id),
        book.language_code,
    )
    return response


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a book and its chapters from DB and wipe files from disk."""
    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    work_id_str = str(book.work_id)
    language_code = book.language_code
    work_id = book.work_id

    # Delete book from DB (cascades to chapters and user_progress)
    await db.delete(book)
    await db.flush()

    # Clean up disk files
    storage_service.delete_book_files(work_id_str, language_code)

    # Check if this work has any other books left
    remaining_books = await db.execute(
        select(func.count()).select_from(Book).where(Book.work_id == work_id)
    )
    if int(remaining_books.scalar_one()) == 0:
        work = (await db.execute(select(Work).where(Work.id == work_id))).scalar_one_or_none()
        if work is not None:
            await db.delete(work)
            await db.flush()
        storage_service.delete_work_files(work_id_str)


@router.post("/{book_id}/cover", response_model=CoverUploadResponse)
async def upload_book_cover(
    book_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CoverUploadResponse:
    """
    Upload a custom cover image file for a book.
    Stores the binary in the centralized resources table (or S3 cloud) and links its ID to the book.
    """
    filename = (file.filename or "cover.jpg").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_COVER_EXTENSIONS:
        raise AppError("Cover image must be a .jpg, .jpeg, .png, or .webp file")

    result = await db.execute(select(Book).where(Book.id == book_id))
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    try:
        content = await file.read()
    finally:
        await file.close()

    if not content:
        raise AppError("Uploaded image is empty")

    if len(content) > 10 * 1024 * 1024:
        raise AppError("Cover image must be under 10MB")

    # 1. Save image to centralized Resource table (or S3)
    content_type = file.content_type or "image/jpeg"
    resource = await media_storage.save_image(
        file_bytes=content,
        filename=filename,
        content_type=content_type,
        db=db,
    )

    # 2. Link book to resource ID
    book.cover_image_id = resource.id

    # 3. Write local disk copy for legacy static serving / fallback
    cover_path = storage_service.cover_image_path(str(book.work_id), book.language_code)
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(content)

    await db.commit()

    url = media_storage.get_image_url(resource.id) or storage_service.cover_image_url(
        str(book.work_id), book.language_code
    )
    return CoverUploadResponse(
        book_id=book.id,
        cover_image_id=resource.id,
        cover_image_url=url or "",
    )
