from datetime import datetime, timezone
import uuid

import aiofiles
from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bs4 import BeautifulSoup

from app.api.book_resolution import resolve_book_identifier
from app.api.dependencies import get_db, get_optional_current_user
from app.core.exceptions import AppError, NotFoundError
from app.models.book import Book, Chapter, ScriptureReference
from app.models.user import Bookmark, User, UserProgress
from app.schemas.book import (
    BookCatalogItem,
    OfflineBookPackageResponse,
    OfflineChapterBundle,
    ScriptureReferenceResponse,
)
from app.schemas.reader import (
    BookmarkCreate,
    BookmarkResponse,
    ChapterDetailResponse,
    ReaderEdition,
    ReaderManifestChapter,
    ReaderManifestResponse,
    UserProgressResponse,
    UserProgressUpdate,
)
from app.services.media_storage import media_storage
from app.services.storage import storage_service

router = APIRouter(prefix="/reader", tags=["reader"])


@router.get("/{book_id}/manifest", response_model=ReaderManifestResponse)
async def get_reader_manifest(
    book_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReaderManifestResponse:
    """Return book metadata, sibling language editions, and chapter TOC for the reader shell."""
    book_id = await resolve_book_identifier(db, book_id)
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError("Book not found")

    # Fetch sibling editions of the same work
    editions_result = await db.execute(
        select(Book).where(Book.work_id == book.work_id).order_by(Book.language_code)
    )
    sibling_books = list(editions_result.scalars().all())

    chapters = sorted(book.chapters, key=lambda chapter: chapter.chapter_index)
    total_words = sum(chapter.word_count for chapter in chapters)

    ref_count_res = await db.execute(
        select(func.count()).select_from(ScriptureReference).where(ScriptureReference.book_id == book_id)
    )
    total_references = int(ref_count_res.scalar_one() or 0)

    return ReaderManifestResponse(
        book_id=book.id,
        work_id=book.work_id,
        title=book.title,
        author=book.author,
        language_code=book.language_code,
        reading_direction=book.reading_direction,
        total_chapters=len(chapters),
        total_words=total_words,
        total_references=total_references,
        chapters=[
            ReaderManifestChapter(
                id=chapter.id,
                index=chapter.chapter_index,
                title=chapter.title,
                word_count=chapter.word_count,
            )
            for chapter in chapters
        ],
        available_editions=[
            ReaderEdition(
                book_id=sibling.id,
                language_code=sibling.language_code,
                title=sibling.title,
            )
            for sibling in sibling_books
        ],
    )


@router.get(
    "/{book_id}/chapters/{chapter_index}",
    response_model=ChapterDetailResponse,
)
async def get_chapter_detail(
    book_id: str,
    chapter_index: int,
    db: AsyncSession = Depends(get_db),
) -> ChapterDetailResponse:
    """Return chapter navigation metadata, word counts, and links to content."""
    book_id = await resolve_book_identifier(db, book_id)
    # Count total chapters
    total_chapters = int(
        (
            await db.execute(
                select(func.count()).select_from(Chapter).where(Chapter.book_id == book_id)
            )
        ).scalar_one()
    )
    if total_chapters == 0:
        raise NotFoundError("Book has no chapters")

    result = await db.execute(
        select(Chapter).where(
            Chapter.book_id == book_id,
            Chapter.chapter_index == chapter_index,
        )
    )
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise NotFoundError("Chapter not found")

    has_previous = chapter_index > 0
    has_next = chapter_index < total_chapters - 1

    return ChapterDetailResponse(
        book_id=book_id,
        chapter_index=chapter.chapter_index,
        title=chapter.title,
        word_count=chapter.word_count,
        total_chapters=total_chapters,
        has_previous=has_previous,
        has_next=has_next,
        previous_chapter_index=chapter_index - 1 if has_previous else None,
        next_chapter_index=chapter_index + 1 if has_next else None,
        content_html_url=f"/api/v1/reader/{book_id}/chapters/{chapter_index}/html",
    )


@router.get(
    "/{book_id}/chapters/{chapter_index}/html",
    response_class=HTMLResponse,
)
async def get_chapter_html(
    book_id: str,
    chapter_index: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Deliver a chapter's stored HTML for the reader engine."""
    book_id = await resolve_book_identifier(db, book_id)
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


@router.get(
    "/{book_id}/progress",
    response_model=UserProgressResponse,
)
async def get_reading_progress(
    book_id: str,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProgressResponse:
    """Fetch reading position (chapter index & scroll offset) for a user."""
    book_id = await resolve_book_identifier(db, book_id)
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id
    if resolved_uid is None:
        raise AppError(
            "User identifier required via authentication token, 'user_id' query parameter, or 'X-User-Id' header",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    result = await db.execute(
        select(UserProgress).where(
            UserProgress.user_id == resolved_uid,
            UserProgress.book_id == book_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress is None:
        return UserProgressResponse(
            id=uuid.uuid4(),
            user_id=resolved_uid,
            book_id=book_id,
            chapter_index=0,
            scroll_offset=0,
            updated_at=datetime.now(timezone.utc),
        )

    return UserProgressResponse.model_validate(progress)


@router.put(
    "/{book_id}/progress",
    response_model=UserProgressResponse,
)
async def save_reading_progress(
    book_id: str,
    payload: UserProgressUpdate,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProgressResponse:
    """Upsert reading position for a user on a given book."""
    book_id = await resolve_book_identifier(db, book_id)
    resolved_uid = (
        (current_user.id if current_user else None)
        or payload.user_id
        or user_id
        or x_user_id
        or uuid.uuid4()
    )

    # Verify book exists
    book_result = await db.execute(select(Book.id).where(Book.id == book_id))
    if book_result.scalar_one_or_none() is None:
        raise NotFoundError("Book not found")

    # Ensure user exists (auto-create guest user if necessary)
    user = (
        await db.execute(select(User).where(User.id == resolved_uid))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=resolved_uid,
            email=f"reader_{str(resolved_uid)[:8]}@ewnet.local",
            display_name="Reader",
        )
        db.add(user)
        await db.flush()

    progress = (
        await db.execute(
            select(UserProgress).where(
                UserProgress.user_id == resolved_uid,
                UserProgress.book_id == book_id,
            )
        )
    ).scalar_one_or_none()

    if progress is None:
        progress = UserProgress(
            user_id=resolved_uid,
            book_id=book_id,
            chapter_index=payload.chapter_index,
            scroll_offset=payload.scroll_offset,
        )
        db.add(progress)
    else:
        progress.chapter_index = payload.chapter_index
        progress.scroll_offset = payload.scroll_offset

    await db.flush()
    return UserProgressResponse.model_validate(progress)


@router.get(
    "/{book_id}/bookmarks",
    response_model=list[BookmarkResponse],
)
async def list_bookmarks(
    book_id: str,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BookmarkResponse]:
    """Retrieve all bookmarks created by a user for a given book."""
    book_id = await resolve_book_identifier(db, book_id)
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id
    if resolved_uid is None:
        raise AppError(
            "User identifier required via authentication token, 'user_id' query parameter, or 'X-User-Id' header",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    stmt = (
        select(Bookmark)
        .where(
            Bookmark.book_id == book_id,
            Bookmark.user_id == resolved_uid,
        )
        .order_by(Bookmark.chapter_index, Bookmark.scroll_offset)
    )
    result = await db.execute(stmt)
    bookmarks = list(result.scalars().all())
    return [BookmarkResponse.model_validate(b) for b in bookmarks]


@router.post(
    "/{book_id}/bookmarks",
    response_model=BookmarkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bookmark(
    book_id: str,
    payload: BookmarkCreate,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookmarkResponse:
    """Create a new bookmark in a book."""
    book_id = await resolve_book_identifier(db, book_id)
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id or uuid.uuid4()

    # Verify book exists
    book_result = await db.execute(select(Book.id).where(Book.id == book_id))
    if book_result.scalar_one_or_none() is None:
        raise NotFoundError("Book not found")

    # Ensure user exists (auto-create guest user if necessary)
    user = (
        await db.execute(select(User).where(User.id == resolved_uid))
    ).scalar_one_or_none()
    if user is None:
        user = User(
            id=resolved_uid,
            email=f"reader_{str(resolved_uid)[:8]}@ewnet.local",
            display_name="Reader",
        )
        db.add(user)
        await db.flush()

    bookmark = Bookmark(
        user_id=resolved_uid,
        book_id=book_id,
        chapter_index=payload.chapter_index,
        scroll_offset=payload.scroll_offset,
        title=payload.title,
        note=payload.note,
    )
    db.add(bookmark)
    await db.commit()
    await db.refresh(bookmark)
    return BookmarkResponse.model_validate(bookmark)


@router.delete(
    "/{book_id}/bookmarks/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_bookmark(
    book_id: str,
    bookmark_id: uuid.UUID,
    user_id: uuid.UUID | None = Query(default=None),
    x_user_id: uuid.UUID | None = Header(default=None, alias="X-User-Id"),
    current_user: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a user bookmark."""
    book_id = await resolve_book_identifier(db, book_id)
    resolved_uid = (current_user.id if current_user else None) or user_id or x_user_id

    stmt = select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.book_id == book_id)
    if resolved_uid is not None:
        stmt = stmt.where(Bookmark.user_id == resolved_uid)

    result = await db.execute(stmt)
    bookmark = result.scalar_one_or_none()
    if bookmark is None:
        raise NotFoundError("Bookmark not found")

    await db.delete(bookmark)
    await db.commit()


@router.get(
    "/{book_id}/references",
    response_model=list[ScriptureReferenceResponse],
)
async def list_scripture_references(
    book_id: str,
    chapter_index: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[ScriptureReferenceResponse]:
    """Retrieve all scripture references detected in a book, optionally filtered by chapter index."""
    book_id = await resolve_book_identifier(db, book_id)
    stmt = select(ScriptureReference).where(ScriptureReference.book_id == book_id)
    if chapter_index is not None:
        stmt = stmt.where(ScriptureReference.chapter_index == chapter_index)
    stmt = stmt.order_by(ScriptureReference.chapter_index, ScriptureReference.created_at)

    result = await db.execute(stmt)
    refs = list(result.scalars().all())
    return [ScriptureReferenceResponse.model_validate(r) for r in refs]


@router.get(
    "/{book_id}/offline-package",
    response_model=OfflineBookPackageResponse,
)
async def get_offline_book_package(
    book_id: str,
    db: AsyncSession = Depends(get_db),
) -> OfflineBookPackageResponse:
    """
    Download complete offline reader package for PWA / mobile client storage.
    Includes book metadata, all chapters with full HTML content, scripture references,
    and asset URLs for caching in local storage / IndexedDB / Cache Storage.
    """
    book_id = await resolve_book_identifier(db, book_id)
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id)
        .options(selectinload(Book.chapters), selectinload(Book.references))
    )
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError(f"Book '{book_id}' not found")

    cover_url = media_storage.get_image_url(book.cover_image_id) or storage_service.cover_image_url(
        str(book.work_id), book.language_code
    )

    book_item = BookCatalogItem(
        id=book.id,
        work_id=book.work_id,
        title=book.title,
        author=book.author,
        cover_image_id=book.cover_image_id,
        cover_image_url=cover_url,
        language_code=book.language_code,
    )

    chapters_sorted = sorted(book.chapters, key=lambda c: c.chapter_index)
    total_words = sum(c.word_count for c in chapters_sorted)

    offline_chapters = []
    asset_urls_set: set[str] = set()
    if cover_url:
        asset_urls_set.add(cover_url)

    for ch in chapters_sorted:
        html_path = storage_service.resolve_stored_path(ch.content_html_path)
        html_content = html_path.read_text(encoding="utf-8") if html_path.is_file() else ""

        # Extract asset URLs from HTML (e.g. img src, image xlink:href)
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all(["img", "image"]):
            src = tag.get("src") or tag.get("xlink:href") or tag.get("href")
            if src and not src.startswith("data:"):
                asset_urls_set.add(src)

        offline_chapters.append(
            OfflineChapterBundle(
                index=ch.chapter_index,
                title=ch.title,
                word_count=ch.word_count,
                html=html_content,
            )
        )

    refs_sorted = sorted(book.references, key=lambda r: (r.chapter_index, r.created_at))
    refs_response = [ScriptureReferenceResponse.model_validate(r) for r in refs_sorted]

    return OfflineBookPackageResponse(
        book=book_item,
        total_chapters=len(offline_chapters),
        total_words=total_words,
        total_references=len(refs_response),
        chapters=offline_chapters,
        references=refs_response,
        asset_urls=sorted(asset_urls_set),
    )



