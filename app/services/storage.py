from pathlib import Path

from app.core.config import settings


class StorageService:
    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = Path(base_path or settings.STORAGE_PATH).resolve()
        self.books_dir = self.base_path / "books"
        # Legacy directories kept for backward compatibility.
        self.raw_dir = self.base_path / "raw"
        self.extracted_dir = self.base_path / "extracted"

    def ensure_directories(self) -> None:
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)

    def book_language_dir(self, work_id: str, language_code: str) -> Path:
        return self.books_dir / work_id / language_code

    def raw_docx_path(self, work_id: str, language_code: str) -> Path:
        return self.book_language_dir(work_id, language_code) / "raw_file.docx"

    def chapters_dir(self, work_id: str, language_code: str) -> Path:
        return self.book_language_dir(work_id, language_code) / "chapters"

    def relative_path(self, path: Path) -> str:
        """Return a stable path relative to STORAGE_PATH for DB storage."""
        try:
            return path.resolve().relative_to(self.base_path).as_posix()
        except ValueError:
            return path.as_posix()

    def resolve_stored_path(self, stored_path: str) -> Path:
        """Resolve a DB-stored relative (or absolute) path against STORAGE_PATH."""
        path = Path(stored_path)
        if path.is_absolute():
            return path
        return (self.base_path / path).resolve()

    def cover_image_url(self, work_id: str, language_code: str) -> str | None:
        cover = self.book_language_dir(work_id, language_code) / "cover.jpg"
        if cover.is_file():
            return f"/storage/books/{work_id}/{language_code}/cover.jpg"
        return None

    # Legacy helpers (kept for older call sites / reader paths).
    def raw_book_path(self, book_id: str, extension: str) -> Path:
        return self.raw_dir / f"{book_id}.{extension.lstrip('.')}"

    def extracted_book_dir(self, book_id: str) -> Path:
        return self.extracted_dir / book_id

    def chapter_html_path(self, book_id: str, chapter_index: int) -> Path:
        return self.extracted_book_dir(book_id) / f"chapter_{chapter_index:04d}.html"


storage_service = StorageService()
