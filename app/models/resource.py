import uuid
from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Resource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Centralized media resource table for covers and illustrations.
    Stores binary image data in database now, and tracks S3 keys when switched to S3.
    """
    __tablename__ = "resources"

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    storage_backend: Mapped[str] = mapped_column(
        String(32),
        default="database",
        server_default="database",
        nullable=False,
    )
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
