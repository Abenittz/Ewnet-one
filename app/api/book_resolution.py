"""Resolve reader/admin book path params (UUID or slug) into a Book UUID."""

from __future__ import annotations

import re
import uuid

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.book import Book

_CLIENT_MOCK_ID_RE = re.compile(r"^book-\d+$", re.IGNORECASE)


async def resolve_book_identifier(db: AsyncSession, book_id: str) -> uuid.UUID:
    """
    Accept a real API book id (UUID) or an optional slug.

    Client-generated ids like ``book-1794501448460`` are rejected with a clear 422.
    """
    raw = (book_id or "").strip()
    if not raw:
        raise AppError("Book id is required", status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    try:
        return uuid.UUID(raw)
    except ValueError:
        pass

    if _CLIENT_MOCK_ID_RE.match(raw):
        raise AppError(
            f"Invalid book id '{raw}'. This looks like a frontend-generated id. "
            "Use the UUID returned by POST /api/v1/upload, GET /api/v1/books, "
            "or GET /api/v1/explore (field book_id).",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    result = await db.execute(select(Book.id).where(Book.slug == raw))
    resolved = result.scalar_one_or_none()
    if resolved is None:
        raise NotFoundError(
            f"Book '{raw}' not found. "
            "Pass a book UUID from the API, or a registered slug."
        )
    return resolved
