import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_db, get_optional_current_user
from app.core.exceptions import NotFoundError
from app.models.book import Book
from app.models.user import User, UserLibrary, UserProgress
from app.schemas.book import DownloadStateUpdate, UserLibraryItemResponse
from app.services.media_storage import media_storage
from app.services.storage import storage_service

router = APIRouter(prefix="/library", tags=["library"])


async def _resolve_user(
    current_user: User | None,
    user_id: uuid.UUID | None,
    x_user_id: uuid.UUID | None,
    db: AsyncSession,
) -> User:
    """Resolve authenticated or guest user, creating guest record if needed."""
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id
    if not resolved_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access personal library",
        )

    user = (await db.execute(select(User).where(User.id == resolved_uid))).scalar_one_or_none()
    if user is None:
        user = User(
            id=resolved_uid,
            email=f"guest_{str(resolved_uid)[:8]}@guest.ewnet.app",
            display_name="Guest Reader",
            is_guest=True,
        )
        db.add(user)
        await db.flush()

    return user


@router.get("", response_model=list[UserLibraryItemResponse])
async def list_user_library(
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UserLibraryItemResponse]:
    """
    List all books saved to the user's personal library.
    Includes download status, reading position, and book metadata for offline synchronization.
    """
    user = await _resolve_user(current_user, user_id, x_user_id, db)

    stmt = (
        select(UserLibrary, Book)
        .join(Book, UserLibrary.book_id == Book.id)
        .where(UserLibrary.user_id == user.id)
        .order_by(UserLibrary.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Get reading progress for these books
    prog_stmt = select(UserProgress).where(UserProgress.user_id == user.id)
    prog_res = await db.execute(prog_stmt)
    prog_map = {p.book_id: p for p in prog_res.scalars().all()}

    items: list[UserLibraryItemResponse] = []
    for lib_entry, book in rows:
        prog = prog_map.get(book.id)
        ch_idx = prog.chapter_index if prog else 0
        scroll = prog.scroll_offset if prog else 0

        cover_url = media_storage.get_image_url(book.cover_image_id)
        if not cover_url:
            cover_url = storage_service.cover_image_url(str(book.work_id), book.language_code)

        items.append(
            UserLibraryItemResponse(
                id=lib_entry.id,
                book_id=book.id,
                title=book.title,
                author=book.author,
                language_code=book.language_code,
                format=book.format,
                cover_image_id=book.cover_image_id,
                cover_image_url=cover_url,
                is_downloaded=lib_entry.is_downloaded,
                downloaded_at=lib_entry.downloaded_at,
                last_read_chapter=ch_idx,
                scroll_offset=scroll,
                saved_at=lib_entry.created_at,
            )
        )

    return items


@router.post("/{book_id}", response_model=UserLibraryItemResponse, status_code=status.HTTP_201_CREATED)
async def add_book_to_library(
    book_id: uuid.UUID,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserLibraryItemResponse:
    """Save a book from the Explore page into the user's personal library."""
    user = await _resolve_user(current_user, user_id, x_user_id, db)

    book = (await db.execute(select(Book).where(Book.id == book_id))).scalar_one_or_none()
    if book is None:
        raise NotFoundError(f"Book '{book_id}' not found")

    stmt = select(UserLibrary).where(
        UserLibrary.user_id == user.id,
        UserLibrary.book_id == book_id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        entry = existing
    else:
        entry = UserLibrary(
            user_id=user.id,
            book_id=book.id,
            is_downloaded=False,
            downloaded_at=None,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)

    # Reading progress
    prog = (
        await db.execute(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.book_id == book.id,
            )
        )
    ).scalar_one_or_none()

    cover_url = media_storage.get_image_url(book.cover_image_id) or storage_service.cover_image_url(
        str(book.work_id), book.language_code
    )

    return UserLibraryItemResponse(
        id=entry.id,
        book_id=book.id,
        title=book.title,
        author=book.author,
        language_code=book.language_code,
        format=book.format,
        cover_image_id=book.cover_image_id,
        cover_image_url=cover_url,
        is_downloaded=entry.is_downloaded,
        downloaded_at=entry.downloaded_at,
        last_read_chapter=prog.chapter_index if prog else 0,
        scroll_offset=prog.scroll_offset if prog else 0,
        saved_at=entry.created_at,
    )


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_book_from_library(
    book_id: uuid.UUID,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a book from the user's personal library."""
    user = await _resolve_user(current_user, user_id, x_user_id, db)

    stmt = select(UserLibrary).where(
        UserLibrary.user_id == user.id,
        UserLibrary.book_id == book_id,
    )
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if entry is not None:
        await db.delete(entry)
        await db.commit()


@router.patch("/{book_id}/download-state", response_model=UserLibraryItemResponse)
async def update_download_state(
    book_id: uuid.UUID,
    payload: DownloadStateUpdate,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserLibraryItemResponse:
    """Update offline download status after client saves the book package into local storage."""
    user = await _resolve_user(current_user, user_id, x_user_id, db)

    stmt = select(UserLibrary).where(
        UserLibrary.user_id == user.id,
        UserLibrary.book_id == book_id,
    )
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if entry is None:
        # Auto-create if not in library yet
        entry = UserLibrary(
            user_id=user.id,
            book_id=book_id,
            is_downloaded=payload.is_downloaded,
            downloaded_at=datetime.now(timezone.utc) if payload.is_downloaded else None,
        )
        db.add(entry)
    else:
        entry.is_downloaded = payload.is_downloaded
        entry.downloaded_at = datetime.now(timezone.utc) if payload.is_downloaded else None

    await db.commit()
    await db.refresh(entry)

    book = (await db.execute(select(Book).where(Book.id == book_id))).scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    cover_url = media_storage.get_image_url(book.cover_image_id) or storage_service.cover_image_url(
        str(book.work_id), book.language_code
    )

    prog = (
        await db.execute(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.book_id == book.id,
            )
        )
    ).scalar_one_or_none()

    return UserLibraryItemResponse(
        id=entry.id,
        book_id=book.id,
        title=book.title,
        author=book.author,
        language_code=book.language_code,
        format=book.format,
        cover_image_id=book.cover_image_id,
        cover_image_url=cover_url,
        is_downloaded=entry.is_downloaded,
        downloaded_at=entry.downloaded_at,
        last_read_chapter=prog.chapter_index if prog else 0,
        scroll_offset=prog.scroll_offset if prog else 0,
        saved_at=entry.created_at,
    )
