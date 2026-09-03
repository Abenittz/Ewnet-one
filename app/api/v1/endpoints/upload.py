import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.models.book import BookFormat, ReadingDirection
from app.schemas.book import BookResponse

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
async def upload_book(
    title: str = Form(...),
    language_code: str = Form(...),
    format: BookFormat = Form(...),
    file: UploadFile = File(...),
    author: str | None = Form(default=None),
) -> BookResponse:
    """
    Dummy upload endpoint for testing file ingestion wiring.
    Accepts a file and returns placeholder metadata without persisting to the database.
    """
    _ = file  # Processing pipeline will consume the uploaded file later.

    now = datetime.now(UTC)
    book_id = uuid.uuid4()

    return BookResponse(
        id=book_id,
        work_id=book_id,
        language_code=language_code,
        reading_direction=ReadingDirection.LTR,
        title=title,
        author=author,
        file_path=f"storage/raw/{book_id}.{format.value}",
        format=format,
        created_at=now,
        updated_at=now,
    )
