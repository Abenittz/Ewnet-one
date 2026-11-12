import hashlib
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db
from app.core.exceptions import AppError
from app.schemas.book import ResourceResponse
from app.services.media_storage import media_storage

router = APIRouter(prefix="/resources", tags=["resources"])

_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif"}


@router.get("/{resource_id}")
async def get_resource(
    resource_id: uuid.UUID,
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Retrieve and serve an image/media resource by ID.
    Supports HTTP caching with Cache-Control and ETag for fast offline PWA caching.
    """
    data, content_type, filename = await media_storage.get_image(resource_id, db)

    etag = f'"{hashlib.md5(data).hexdigest()}"'
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": etag,
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    return Response(content=data, media_type=content_type, headers=headers)


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def upload_resource(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ResourceResponse:
    """
    Upload an image resource directly.
    Stores the image in the centralized resources table (or S3 when enabled) and returns its ID and URL.
    """
    filename = (file.filename or "image.jpg").strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_IMAGE_EXTENSIONS:
        raise AppError(
            f"Unsupported image file extension '{suffix}'. Allowed: {', '.join(sorted(_ALLOWED_IMAGE_EXTENSIONS))}"
        )

    try:
        content = await file.read()
    finally:
        await file.close()

    if not content:
        raise AppError("Uploaded file is empty")

    if len(content) > 15 * 1024 * 1024:
        raise AppError("Image resource must be under 15MB")

    content_type = file.content_type or "image/jpeg"
    resource = await media_storage.save_image(
        file_bytes=content,
        filename=filename,
        content_type=content_type,
        db=db,
    )
    await db.commit()

    return ResourceResponse(
        id=resource.id,
        filename=resource.filename,
        content_type=resource.content_type,
        file_size=resource.file_size,
        storage_backend=resource.storage_backend,
        url=media_storage.get_image_url(resource.id) or "",
        created_at=resource.created_at,
    )


@router.delete("/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a media resource by ID."""
    deleted = await media_storage.delete_image(resource_id, db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    await db.commit()
