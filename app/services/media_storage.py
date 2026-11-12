import abc
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.models.resource import Resource


class BaseMediaStorage(abc.ABC):
    """Abstract base class for image and media asset storage."""

    @abc.abstractmethod
    async def save_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        db: AsyncSession,
    ) -> Resource:
        """Store an image asset and return the persisted Resource model."""
        pass

    @abc.abstractmethod
    async def get_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[bytes, str, str]:
        """Retrieve binary data, content-type, and filename for a resource."""
        pass

    @abc.abstractmethod
    async def delete_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        """Delete resource asset."""
        pass

    @abc.abstractmethod
    def get_image_url(self, resource_id: uuid.UUID | str | None) -> str | None:
        """Generate relative or CDN URL for the given resource ID."""
        pass


class DatabaseMediaStorage(BaseMediaStorage):
    """
    Stores binary images directly in the PostgreSQL database within the 'resources' table.
    Self-contained, reliable, and cost-effective for initial deployment.
    """

    async def save_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        db: AsyncSession,
    ) -> Resource:
        resource = Resource(
            filename=filename,
            content_type=content_type,
            file_size=len(file_bytes),
            data=file_bytes,
            storage_backend="database",
            s3_key=None,
        )
        db.add(resource)
        await db.flush()
        await db.refresh(resource)
        return resource

    async def get_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[bytes, str, str]:
        stmt = select(Resource).where(Resource.id == resource_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record or not record.data:
            raise NotFoundError(f"Resource '{resource_id}' not found")
        return record.data, record.content_type, record.filename

    async def delete_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        stmt = select(Resource).where(Resource.id == resource_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return False
        await db.delete(record)
        await db.flush()
        return True

    def get_image_url(self, resource_id: uuid.UUID | str | None) -> str | None:
        if not resource_id:
            return None
        return f"{settings.API_V1_STR}/resources/{resource_id}"


class S3MediaStorage(BaseMediaStorage):
    """
    Cloud object storage implementation ready for Amazon S3, MinIO, or Cloudflare R2.
    Stores metadata in 'resources' table and uploads binary payload to S3 bucket.
    """

    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME
        self.region = settings.S3_REGION
        self.endpoint_url = settings.S3_ENDPOINT_URL
        self.public_prefix = settings.S3_PUBLIC_URL_PREFIX

    async def save_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        db: AsyncSession,
    ) -> Resource:
        resource_id = uuid.uuid4()
        clean_ext = Path(filename).suffix.lower() or ".jpg"
        s3_key = f"resources/{resource_id.hex}{clean_ext}"

        # If boto3/s3 credentials are provided, upload to bucket
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            try:
                import boto3  # type: ignore[import-untyped]
                s3_client = boto3.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
                s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                )
            except Exception:
                pass

        resource = Resource(
            id=resource_id,
            filename=filename,
            content_type=content_type,
            file_size=len(file_bytes),
            data=None,  # Not stored in DB when using S3
            storage_backend="s3",
            s3_key=s3_key,
        )
        db.add(resource)
        await db.flush()
        await db.refresh(resource)
        return resource

    async def get_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[bytes, str, str]:
        stmt = select(Resource).where(Resource.id == resource_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise NotFoundError(f"Resource '{resource_id}' not found")

        # If S3 key exists, retrieve object from bucket
        if record.s3_key and settings.AWS_ACCESS_KEY_ID:
            import boto3
            s3_client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            )
            response = s3_client.get_object(Bucket=self.bucket, Key=record.s3_key)
            data = response["Body"].read()
            return data, record.content_type, record.filename

        # Fallback to local data if stored
        if record.data:
            return record.data, record.content_type, record.filename

        raise NotFoundError(f"Asset data for resource '{resource_id}' not found")

    async def delete_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        stmt = select(Resource).where(Resource.id == resource_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return False

        if record.s3_key and settings.AWS_ACCESS_KEY_ID:
            try:
                import boto3
                s3_client = boto3.client(
                    "s3",
                    region_name=self.region,
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
                s3_client.delete_object(Bucket=self.bucket, Key=record.s3_key)
            except Exception:
                pass

        await db.delete(record)
        await db.flush()
        return True

    def get_image_url(self, resource_id: uuid.UUID | str | None) -> str | None:
        if not resource_id:
            return None
        if self.public_prefix:
            return f"{self.public_prefix.rstrip('/')}/resources/{resource_id}"
        return f"{settings.API_V1_STR}/resources/{resource_id}"


class MediaStorageManager:
    """Unified manager dispatching to the configured backend (database or s3)."""

    def __init__(self) -> None:
        self._db_backend = DatabaseMediaStorage()
        self._s3_backend = S3MediaStorage()

    @property
    def backend(self) -> BaseMediaStorage:
        if settings.MEDIA_STORAGE_BACKEND.lower() == "s3":
            return self._s3_backend
        return self._db_backend

    async def save_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        db: AsyncSession | None = None,
    ) -> Resource:
        if not content_type:
            content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
        if db is None:
            raise ValueError("Database session required for saving resources")
        return await self.backend.save_image(file_bytes, filename, content_type, db)

    async def get_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[bytes, str, str]:
        # Always check record's own storage_backend first
        stmt = select(Resource).where(Resource.id == resource_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise NotFoundError(f"Resource '{resource_id}' not found")

        if record.storage_backend == "s3":
            return await self._s3_backend.get_image(resource_id, db)
        return await self._db_backend.get_image(resource_id, db)

    async def delete_image(
        self,
        resource_id: uuid.UUID,
        db: AsyncSession,
    ) -> bool:
        return await self.backend.delete_image(resource_id, db)

    def get_image_url(self, resource_id: uuid.UUID | str | None) -> str | None:
        return self.backend.get_image_url(resource_id)


media_storage = MediaStorageManager()
