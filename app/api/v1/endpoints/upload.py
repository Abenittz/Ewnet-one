import asyncio
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.book_resolution import resolve_book_identifier
from app.api.dependencies import get_db
from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.book import (
    Book,
    BookFormat,
    Chapter,
    ExploreItem,
    ReadingDirection,
    ScriptureReference,
    Work,
)
from app.schemas.book import (
    AdminChapterResult,
    AdminUploadBookResponse,
    PublishBookResponse,
    ScriptureReferenceResponse,
    UploadBookResponse,
)
from app.services.content_enricher import content_enricher
from app.services.docx_processor import docx_processor
from app.services.epub_processor import epub_processor
from app.services.media_storage import media_storage
from app.services.pdf_processor import pdf_processor
from app.services.storage import storage_service

router = APIRouter(tags=["upload"])

_ALLOWED_EXTENSIONS = {".docx", ".pdf", ".epub"}

_LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-zA-Z0-9]+)?$", re.IGNORECASE)


def _detect_file_format(file: UploadFile) -> tuple[str, BookFormat]:
    filename = (file.filename or "").strip()
    suffix = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if suffix == ".docx" or (
        not suffix
        and content_type
        in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }
    ):
        return ".docx", BookFormat.DOCX

    if suffix == ".pdf" or (not suffix and content_type == "application/pdf"):
        return ".pdf", BookFormat.PDF

    if suffix == ".epub" or (
        not suffix and content_type in {"application/epub+zip", "application/epub"}
    ):
        return ".epub", BookFormat.EPUB

    raise AppError("Unsupported file type. Only .docx, .pdf, and .epub files are accepted.")


async def _ingest_document(
    file: UploadFile,
    title: str,
    language_code: str,
    reading_direction: ReadingDirection,
    author: str | None,
    work_id: uuid.UUID | None,
    db: AsyncSession,
) -> tuple[Work, Book, list[dict[str, Any]]]:
    ext, book_format = _detect_file_format(file)

    language_code = language_code.strip().lower()
    if not _LANGUAGE_CODE_RE.match(language_code):
        raise AppError(
            f"Invalid language code '{language_code}'. Must be a valid ISO 639 code (e.g. 'en', 'am', 'fr')."
        )

    title = title.strip()
    author = author.strip() if author else None

    work = await _resolve_work(db, work_id=work_id, title=title)

    # Check for duplicate book before touching disk
    existing_book = await db.execute(
        select(Book.id).where(
            Book.work_id == work.id,
            Book.language_code == language_code,
        )
    )
    if existing_book.scalar_one_or_none() is not None:
        raise ConflictError(
            f"A book already exists for work {work.id} with language '{language_code}'"
        )

    try:
        file_bytes = await file.read()
    finally:
        await file.close()

    if not file_bytes:
        raise AppError("Uploaded file is empty")

    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise AppError(
            f"Uploaded file exceeds maximum allowed size of {max_mb}MB",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    raw_path = storage_service.raw_format_path(str(work.id), language_code, ext)
    chapters_dir = storage_service.chapters_dir(str(work.id), language_code)
    images_dir = storage_service.images_dir(str(work.id), language_code)
    cover_path = storage_service.cover_image_path(str(work.id), language_code)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(file_bytes)
    relative_raw_path = storage_service.relative_path(raw_path)
    if book_format == BookFormat.EPUB and not author:
        meta = epub_processor.extract_metadata(file_bytes)
        if meta.get("author"):
            author = meta["author"]

    book = Book(
        work_id=work.id,
        language_code=language_code,
        reading_direction=reading_direction,
        title=title,
        author=author,
        file_path=relative_raw_path,
        format=book_format,
    )
    db.add(book)

    path_prefix = storage_service.relative_path(chapters_dir)
    images_url_prefix = f"/storage/books/{work.id}/{language_code}/images"

    try:
        await db.flush()

        if book_format == BookFormat.PDF:
            chapter_payloads = await asyncio.to_thread(
                pdf_processor.process_and_split,
                file_bytes,
                chapters_dir,
                path_prefix=path_prefix,
                images_dir=images_dir,
                images_url_prefix=images_url_prefix,
                cover_image_path=cover_path,
                language_code=language_code,
            )
        elif book_format == BookFormat.EPUB:
            chapter_payloads = await asyncio.to_thread(
                epub_processor.process_and_split,
                file_bytes,
                chapters_dir,
                path_prefix=path_prefix,
                images_dir=images_dir,
                images_url_prefix=images_url_prefix,
                cover_image_path=cover_path,
                language_code=language_code,
            )
        else:
            chapter_payloads = await asyncio.to_thread(
                docx_processor.process_and_split,
                file_bytes,
                chapters_dir,
                path_prefix=path_prefix,
                images_dir=images_dir,
                images_url_prefix=images_url_prefix,
                cover_image_path=cover_path,
            )

        if not chapter_payloads:
            raise AppError("No chapters could be extracted from the uploaded document")

        chapter_titles = [str(p["title"]) for p in chapter_payloads]
        all_references: list[ScriptureReference] = []

        # Enrich each chapter with typography, content menu linking, and scripture references
        for payload in chapter_payloads:
            html_path = storage_service.resolve_stored_path(payload["content_html_path"])
            raw_html = html_path.read_text(encoding="utf-8") if html_path.is_file() else ""

            enriched_html, refs = content_enricher.enrich_chapter(
                raw_html,
                chapter_index=payload["chapter_index"],
                book_title=title,
                author=author,
                chapter_titles=chapter_titles,
            )

            if html_path.is_file():
                html_path.write_text(enriched_html, encoding="utf-8")

            # Persist detected scripture references
            for ref_item in refs:
                ref_obj = ScriptureReference(
                    book_id=book.id,
                    chapter_index=ref_item["chapter_index"],
                    reference_text=ref_item["reference_text"],
                    book_name=ref_item["book_name"],
                    chapter_num=ref_item["chapter_num"],
                    verse_start=ref_item["verse_start"],
                    verse_end=ref_item["verse_end"],
                    anchor_id=ref_item["anchor_id"],
                )
                db.add(ref_obj)
                all_references.append(ref_obj)

            db.add(
                Chapter(
                    book_id=book.id,
                    chapter_index=payload["chapter_index"],
                    title=payload["title"],
                    content_html_path=payload["content_html_path"],
                    word_count=payload["word_count"],
                )
            )

        # 1. Save cover image into centralized Resource table
        if cover_path.is_file():
            cover_bytes = cover_path.read_bytes()
            if cover_bytes:
                cover_res = await media_storage.save_image(
                    file_bytes=cover_bytes,
                    filename=cover_path.name,
                    content_type="image/jpeg",
                    db=db,
                )
                book.cover_image_id = cover_res.id

        # 2. Save inline illustrations into centralized Resource table and rewrite HTML references
        if images_dir.is_dir():
            for img_file in sorted(images_dir.glob("img_*.*")):
                if img_file.is_file():
                    img_bytes = img_file.read_bytes()
                    if img_bytes:
                        img_res = await media_storage.save_image(
                            file_bytes=img_bytes,
                            filename=img_file.name,
                            db=db,
                        )
                        old_url = f"{images_url_prefix}/{img_file.name}"
                        new_url = media_storage.get_image_url(img_res.id)
                        if new_url:
                            for payload in chapter_payloads:
                                hpath = storage_service.resolve_stored_path(payload["content_html_path"])
                                if hpath.is_file():
                                    raw_text = hpath.read_text(encoding="utf-8")
                                    if old_url in raw_text:
                                        hpath.write_text(raw_text.replace(old_url, new_url), encoding="utf-8")

        # 3. Register book in online Explore catalog
        explore_item = ExploreItem(
            book_id=book.id,
            category="general",
            is_featured=False,
            display_order=0,
        )
        db.add(explore_item)

        await db.flush()

    except Exception:
        storage_service.delete_book_files(str(work.id), language_code)
        raise

    return work, book, chapter_payloads, all_references


@router.post("/upload", response_model=UploadBookResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=512),
    language_code: str = Form(..., min_length=2, max_length=10),
    reading_direction: ReadingDirection = Form(default=ReadingDirection.LTR),
    author: str | None = Form(default=None, max_length=256),
    work_id: uuid.UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> UploadBookResponse:
    """Ingest a DOCX or PDF book: persist Work/Book, store raw file, split chapters, and save Chapter rows."""
    work, book, chapter_payloads, _refs = await _ingest_document(
        file=file,
        title=title,
        language_code=language_code,
        reading_direction=reading_direction,
        author=author,
        work_id=work_id,
        db=db,
    )
    return UploadBookResponse(
        work_id=work.id,
        book_id=book.id,
        chapters_created=len(chapter_payloads),
    )


@router.post(
    "/admin/books/upload",
    response_model=AdminUploadBookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_upload_book(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=512),
    language_code: str = Form(..., min_length=2, max_length=10),
    reading_direction: ReadingDirection = Form(default=ReadingDirection.LTR),
    author: str | None = Form(default=None, max_length=256),
    work_id: uuid.UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> AdminUploadBookResponse:
    """Admin endpoint for ingesting DOCX/PDF books and returning structured book metadata and chapter HTMLs."""
    work, book, chapter_payloads, all_references = await _ingest_document(
        file=file,
        title=title,
        language_code=language_code,
        reading_direction=reading_direction,
        author=author,
        work_id=work_id,
        db=db,
    )

    chapters = []
    for payload in chapter_payloads:
        html_path = storage_service.resolve_stored_path(payload["content_html_path"])
        html_content = html_path.read_text(encoding="utf-8") if html_path.is_file() else ""
        chapters.append(
            AdminChapterResult(
                index=payload["chapter_index"],
                title=payload["title"],
                html=html_content,
            )
        )

    return AdminUploadBookResponse(
        work_id=work.id,
        book_id=book.id,
        title=book.title,
        author=book.author,
        language=book.language_code.upper(),
        chapters=chapters,
        references=[ScriptureReferenceResponse.model_validate(r) for r in all_references],
    )


@router.post(
    "/admin/books/{book_id}/publish",
    response_model=PublishBookResponse,
    status_code=status.HTTP_200_OK,
)
async def publish_book(
    book_id: str,
    category: str = Form(default="general", max_length=64),
    is_featured: bool = Form(default=False),
    display_order: int = Form(default=0),
    slug: str | None = Form(default=None, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> PublishBookResponse:
    """
    Publish a book to the explore catalog (create/update ExploreItem).
    ``book_id`` may be a UUID or an existing slug.
    """
    resolved_id = await resolve_book_identifier(db, book_id)
    result = await db.execute(select(Book).where(Book.id == resolved_id))
    book = result.scalar_one_or_none()
    if book is None:
        raise NotFoundError(f"Book '{book_id}' not found")

    normalized_slug = (slug or book.slug or "").strip().lower() or None
    if normalized_slug:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized_slug):
            raise AppError(
                "slug must be lowercase letters, numbers, and hyphens "
                "(e.g. sample-fetha-nagast)"
            )
        clash = await db.execute(
            select(Book.id).where(Book.slug == normalized_slug, Book.id != book.id)
        )
        if clash.scalar_one_or_none() is not None:
            raise ConflictError(f"Slug '{normalized_slug}' is already in use")
        book.slug = normalized_slug

    explore = (
        await db.execute(select(ExploreItem).where(ExploreItem.book_id == book.id))
    ).scalar_one_or_none()
    if explore is None:
        explore = ExploreItem(
            book_id=book.id,
            category=category.strip() or "general",
            is_featured=is_featured,
            display_order=display_order,
        )
        db.add(explore)
    else:
        explore.category = category.strip() or explore.category
        explore.is_featured = is_featured
        explore.display_order = display_order

    await db.flush()
    return PublishBookResponse(
        book_id=book.id,
        slug=book.slug,
        explore_id=explore.id,
        category=explore.category,
        is_featured=explore.is_featured,
        display_order=explore.display_order,
        published=True,
    )


async def _resolve_work(
    db: AsyncSession,
    *,
    work_id: uuid.UUID | None,
    title: str,
) -> Work:
    if work_id is None:
        work = Work(original_title=title)
        db.add(work)
        await db.flush()
        return work

    result = await db.execute(select(Work).where(Work.id == work_id))
    work = result.scalar_one_or_none()
    if work is None:
        raise NotFoundError(f"Work '{work_id}' not found")
    return work
