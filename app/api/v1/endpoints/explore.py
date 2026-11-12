import uuid

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db, get_optional_current_user
from app.models.book import Book, ExploreItem
from app.models.user import User, UserLibrary
from app.schemas.book import ExploreItemResponse
from app.services.media_storage import media_storage
from app.services.storage import storage_service

router = APIRouter(prefix="/explore", tags=["explore"])


@router.get("", response_model=list[ExploreItemResponse])
async def list_explore_books(
    category: str | None = Query(default=None, description="Filter by book category"),
    featured_only: bool = Query(default=False, description="Filter to featured books only"),
    search: str | None = Query(default=None, description="Search by title or author"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ExploreItemResponse]:
    """
    Public explore catalog listing all available online books.
    Provides categories, featured status, and indicates whether each book is already in the user's library.
    """
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id

    # Query books joined with explore entries
    stmt = (
        select(Book, ExploreItem)
        .outerjoin(ExploreItem, Book.id == ExploreItem.book_id)
        .order_by(
            ExploreItem.is_featured.desc().nullslast(),
            ExploreItem.display_order.asc().nullslast(),
            Book.created_at.desc(),
        )
    )

    if category:
        stmt = stmt.where(func.lower(ExploreItem.category) == category.strip().lower())
    if featured_only:
        stmt = stmt.where(ExploreItem.is_featured.is_(True))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Book.title).like(term),
                func.lower(Book.author).like(term),
            )
        )

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    rows = result.all()

    # User library lookup
    user_lib_map: dict[uuid.UUID, UserLibrary] = {}
    if resolved_uid:
        lib_stmt = select(UserLibrary).where(UserLibrary.user_id == resolved_uid)
        lib_res = await db.execute(lib_stmt)
        user_lib_map = {entry.book_id: entry for entry in lib_res.scalars().all()}

    items: list[ExploreItemResponse] = []
    for book, explore_entry in rows:
        lib_entry = user_lib_map.get(book.id)
        is_in_lib = lib_entry is not None
        is_down = lib_entry.is_downloaded if lib_entry else False

        cat = explore_entry.category if explore_entry else "general"
        featured = explore_entry.is_featured if explore_entry else False
        order = explore_entry.display_order if explore_entry else 0
        explore_id = explore_entry.id if explore_entry else book.id

        cover_url = media_storage.get_image_url(book.cover_image_id)
        if not cover_url:
            cover_url = storage_service.cover_image_url(str(book.work_id), book.language_code)

        items.append(
            ExploreItemResponse(
                id=explore_id,
                book_id=book.id,
                category=cat,
                is_featured=featured,
                display_order=order,
                title=book.title,
                author=book.author,
                language_code=book.language_code,
                cover_image_id=book.cover_image_id,
                cover_image_url=cover_url,
                is_in_library=is_in_lib,
                is_downloaded=is_down,
            )
        )

    return items
