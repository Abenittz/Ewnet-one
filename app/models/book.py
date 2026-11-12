import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.resource import Resource

if TYPE_CHECKING:
    from app.models.user import UserLibrary, UserProgress


class ReadingDirection(str, enum.Enum):
    LTR = "ltr"
    RTL = "rtl"


class BookFormat(str, enum.Enum):
    DOCX = "docx"
    EPUB = "epub"
    PDF = "pdf"


class Work(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "works"

    original_title: Mapped[str] = mapped_column(String(512), nullable=False)

    books: Mapped[list["Book"]] = relationship(
        back_populates="work",
        cascade="all, delete-orphan",
    )


class Book(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        UniqueConstraint("work_id", "language_code", name="uq_books_work_language"),
    )

    work_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    reading_direction: Mapped[ReadingDirection] = mapped_column(
        Enum(ReadingDirection, name="reading_direction"),
        nullable=False,
        default=ReadingDirection.LTR,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Optional human-readable id for admin/sample URLs (e.g. sample-fetha-nagast)
    slug: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[BookFormat] = mapped_column(
        Enum(BookFormat, name="book_format"),
        nullable=False,
    )
    cover_image_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    work: Mapped["Work"] = relationship(back_populates="books")
    cover_image: Mapped[Resource | None] = relationship(foreign_keys=[cover_image_id])
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.chapter_index",
    )
    user_progress: Mapped[list["UserProgress"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )
    references: Mapped[list["ScriptureReference"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="ScriptureReference.chapter_index",
    )
    explore_entry: Mapped["ExploreItem | None"] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        uselist=False,
    )
    library_entries: Mapped[list["UserLibrary"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
    )


class Chapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("book_id", "chapter_index", name="uq_chapters_book_index"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content_html_path: Mapped[Text] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    book: Mapped["Book"] = relationship(back_populates="chapters")


class ScriptureReference(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scripture_references"

    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    reference_text: Mapped[str] = mapped_column(String(128), nullable=False)
    book_name: Mapped[str] = mapped_column(String(64), nullable=False)
    chapter_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verse_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verse_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    book: Mapped["Book"] = relationship(back_populates="references")


class ExploreItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalog entry for online book discovery and explore feed."""
    __tablename__ = "explore"
    __table_args__ = (
        UniqueConstraint("book_id", name="uq_explore_book"),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general", server_default="general")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    book: Mapped["Book"] = relationship(back_populates="explore_entry")


