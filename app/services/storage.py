from pathlib import Path

from app.core.config import settings


class StorageService:
    def __init__(self, base_path: str | None = None) -> None:
        self.base_path = Path(base_path or settings.STORAGE_PATH).resolve()
        self.raw_dir = self.base_path / "raw"
        self.extracted_dir = self.base_path / "extracted"

    def ensure_directories(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)

    def raw_book_path(self, book_id: str, extension: str) -> Path:
        return self.raw_dir / f"{book_id}.{extension.lstrip('.')}"

    def extracted_book_dir(self, book_id: str) -> Path:
        return self.extracted_dir / book_id

    def chapter_html_path(self, book_id: str, chapter_index: int) -> Path:
        return self.extracted_book_dir(book_id) / f"chapter_{chapter_index:04d}.html"


storage_service = StorageService()
