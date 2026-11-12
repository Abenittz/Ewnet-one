from datetime import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.book import Book


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    progress: Mapped[list["UserProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    bookmarks: Mapped[list["Bookmark"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    library_entries: Mapped[list["UserLibrary"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_user_progress_user_book"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped["User"] = relationship(back_populates="progress")
    book: Mapped["Book"] = relationship(back_populates="user_progress")


class Bookmark(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "bookmarks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scroll_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    user: Mapped["User"] = relationship(back_populates="bookmarks")
    book: Mapped["Book"] = relationship()


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class UserLibrary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Books saved to user's personal library for online access and local offline storage."""
    __tablename__ = "user_library"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_user_library_user_book"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_downloaded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="library_entries")
    book: Mapped["Book"] = relationship(back_populates="library_entries")



