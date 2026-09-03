import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.book import Book
from app.schemas.book import BookDetailResponse, BookResponse

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=list[BookResponse])
async def list_books(db: AsyncSession = Depends(get_db)) -> list[Book]:
    result = await db.execute(select(Book).order_by(Book.created_at.desc()))
    return list(result.scalars().all())


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
