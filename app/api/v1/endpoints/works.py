import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db
from app.core.exceptions import NotFoundError
from app.models.book import Book, Work
from app.schemas.book import (
    BookCatalogItem,
    PaginatedWorkList,
    WorkCatalogItem,
    WorkDetailResponse,
    WorkResponse,
    WorkUpdate,
)
from app.services.storage import storage_service

router = APIRouter(prefix="/works", tags=["works"])


@router.get("", response_model=PaginatedWorkList)
async def list_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> PaginatedWorkList:
    """Paginated list of intellectual Works with available language editions."""
    count_stmt = select(func.count()).select_from(Work)
    total = int((await db.execute(count_stmt)).scalar_one())

    list_stmt = (
        select(Work)
        .options(selectinload(Work.books))
        .order_by(Work.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    works = list((await db.execute(list_stmt)).scalars().all())

    items = [
        WorkCatalogItem(
            id=w.id,
            original_title=w.original_title,
            languages=[b.language_code for b in w.books],
            book_count=len(w.books),
            created_at=w.created_at,
        )
        for w in works
    ]

    return PaginatedWorkList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{work_id}", response_model=WorkDetailResponse)
async def get_work(
    work_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WorkDetailResponse:
    """Get work details including all available translations/editions."""
    result = await db.execute(
        select(Work)
        .where(Work.id == work_id)
        .options(selectinload(Work.books))
    )
    work = result.scalar_one_or_none()
    if work is None:
        raise NotFoundError("Work not found")

    books = [
        BookCatalogItem(
            id=b.id,
            work_id=work.id,
            title=b.title,
            author=b.author,
            cover_image_url=storage_service.cover_image_url(str(work.id), b.language_code),
            language_code=b.language_code,
        )
        for b in work.books
    ]

    return WorkDetailResponse(
        id=work.id,
        original_title=work.original_title,
        created_at=work.created_at,
        updated_at=work.updated_at,
        books=books,
    )


@router.patch("/{work_id}", response_model=WorkResponse)
async def update_work(
    work_id: uuid.UUID,
    payload: WorkUpdate,
    db: AsyncSession = Depends(get_db),
) -> WorkResponse:
    """Update a work's original title."""
    result = await db.execute(select(Work).where(Work.id == work_id))
    work = result.scalar_one_or_none()
    if work is None:
        raise NotFoundError("Work not found")

    work.original_title = payload.original_title.strip()
    await db.flush()
    await db.refresh(work)

    return WorkResponse.model_validate(work)


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(
    work_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a work and all its language editions from DB and wipe storage files."""
    result = await db.execute(select(Work).where(Work.id == work_id))
    work = result.scalar_one_or_none()
    if work is None:
        raise NotFoundError("Work not found")

    work_id_str = str(work.id)
    await db.delete(work)
    await db.flush()

    storage_service.delete_work_files(work_id_str)
