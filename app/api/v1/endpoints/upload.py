import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.book import Book, BookFormat, Chapter, ReadingDirection, Work
from app.schemas.book import UploadBookResponse
from app.services.docx_processor import docx_processor
from app.services.storage import storage_service

router = APIRouter(prefix="/upload", tags=["upload"])

_ALLOWED_DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/octet-stream",
}


@router.post("", response_model=UploadBookResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=512),
    language_code: str = Form(..., min_length=2, max_length=10),
    reading_direction: ReadingDirection = Form(default=ReadingDirection.LTR),
    author: str | None = Form(default=None, max_length=256),
    work_id: uuid.UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> UploadBookResponse:
    """
    Ingest a DOCX book: persist Work/Book, store the raw file, split chapters,
    and save Chapter rows.
    """
    _validate_docx_upload(file)

    language_code = language_code.strip().lower()
    title = title.strip()
    author = author.strip() if author else None

    work = await _resolve_work(db, work_id=work_id, title=title)

    raw_path = storage_service.raw_docx_path(str(work.id), language_code)
    chapters_dir = storage_service.chapters_dir(str(work.id), language_code)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        docx_bytes = await file.read()
    finally:
        await file.close()

    if not docx_bytes:
        raise AppError("Uploaded file is empty")

    raw_path.write_bytes(docx_bytes)
    relative_raw_path = storage_service.relative_path(raw_path)

    book = Book(
        work_id=work.id,
        language_code=language_code,
        reading_direction=reading_direction,
        title=title,
        author=author,
        file_path=relative_raw_path,
        format=BookFormat.DOCX,
    )
    db.add(book)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"A book already exists for work {work.id} with language '{language_code}'"
        ) from exc

    path_prefix = storage_service.relative_path(chapters_dir)
    try:
        chapter_payloads = await asyncio.to_thread(
            docx_processor.process_and_split,
            docx_bytes,
            chapters_dir,
            path_prefix=path_prefix,
        )
    except ValueError as exc:
        raise AppError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface conversion failures cleanly
        raise AppError(f"Failed to process DOCX file: {exc}") from exc

    if not chapter_payloads:
        raise AppError("No chapters could be extracted from the uploaded document")

    for payload in chapter_payloads:
        db.add(
            Chapter(
                book_id=book.id,
                chapter_index=payload["chapter_index"],
                title=payload["title"],
                content_html_path=payload["content_html_path"],
                word_count=payload["word_count"],
            )
        )

    await db.flush()

    return UploadBookResponse(
        work_id=work.id,
        book_id=book.id,
        chapters_created=len(chapter_payloads),
    )


def _validate_docx_upload(file: UploadFile) -> None:
    filename = (file.filename or "").strip()
    suffix = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if suffix and suffix != ".docx":
        raise AppError("Unsupported file type. Only .docx files are accepted.")

    if not suffix and content_type and content_type not in _ALLOWED_DOCX_CONTENT_TYPES:
        raise AppError("Unsupported file type. Only .docx files are accepted.")


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
