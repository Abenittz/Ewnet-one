import tempfile
from pathlib import Path

from app.services.storage import StorageService


def test_storage_service_directories():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageService(base_path=tmpdir)
        storage.ensure_directories()

        assert storage.books_dir.is_dir()
        assert storage.raw_dir.is_dir()
        assert storage.extracted_dir.is_dir()


def test_storage_paths_and_cover():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageService(base_path=tmpdir)
        work_id = "test-work-123"
        lang = "am"

        book_dir = storage.book_language_dir(work_id, lang)
        raw_path = storage.raw_docx_path(work_id, lang)
        chapters_dir = storage.chapters_dir(work_id, lang)
        images_dir = storage.images_dir(work_id, lang)
        cover_path = storage.cover_image_path(work_id, lang)

        assert raw_path == book_dir / "raw_file.docx"
        assert chapters_dir == book_dir / "chapters"
        assert images_dir == book_dir / "images"
        assert cover_path == book_dir / "cover.jpg"

        # Initially no cover
        assert storage.cover_image_url(work_id, lang) is None

        # Create cover file
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cover_path.write_bytes(b"fake image data")

        assert storage.cover_image_url(work_id, lang) == f"/storage/books/{work_id}/{lang}/cover.jpg"

        # Test deletion
        storage.delete_book_files(work_id, lang)
        assert not book_dir.exists()
        assert storage.cover_image_url(work_id, lang) is None
