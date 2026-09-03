import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import UserProgress


class ReadingDirection(str, enum.Enum):
    LTR = "ltr"
    RTL = "rtl"


class BookFormat(str, enum.Enum):
    DOCX = "docx"
    EPUB = "epub"


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
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[BookFormat] = mapped_column(
        Enum(BookFormat, name="book_format"),
        nullable=False,
    )

    work: Mapped["Work"] = relationship(back_populates="books")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="Chapter.chapter_index",
    )
    user_progress: Mapped[list["UserProgress"]] = relationship(
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
    content_html_path: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    book: Mapped["Book"] = relationship(back_populates="chapters")
