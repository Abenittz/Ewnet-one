import io
import tempfile
import uuid
from pathlib import Path

import pymupdf as fitz
import pytest
from app.models.book import Book, BookFormat
from app.services.pdf_processor import pdf_processor


def create_sample_pdf_with_toc() -> bytes:
    doc = fitz.open()
    # Page 1 - Chapter 1
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Chapter 1: The Beginning\n\nThis is the content of chapter one.")
    # Page 2 - Chapter 2
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Chapter 2: The Journey\n\nThis is the content of chapter two.")
    # Add TOC / Bookmarks
    doc.set_toc([
        [1, "Chapter 1: The Beginning", 1],
        [1, "Chapter 2: The Journey", 2],
    ])
    buf = doc.tobytes()
    doc.close()
    return buf


def create_amharic_pdf() -> bytes:
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Intro content for Amharic chapter 1.")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Main content for Amharic chapter 2.")
    doc.set_toc([
        [1, "ምዕራፍ 1: መግቢያ", 1],
        [1, "ምዕራፍ 2: ዋናው ክፍል", 2],
    ])
    buf = doc.tobytes()
    doc.close()
    return buf


def create_scanned_mock_pdf() -> bytes:
    doc = fitz.open()
    # Create page with an image and no text (simulating scanned document)
    p = doc.new_page()
    # Draw simple graphics to make a valid image
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
    pix.clear_with(255)  # white background
    img_bytes = pix.tobytes("png")
    p.insert_image(fitz.Rect(50, 50, 250, 250), stream=img_bytes)
    buf = doc.tobytes()
    doc.close()
    return buf


def test_pdf_processor_with_toc():
    pdf_bytes = create_sample_pdf_with_toc()
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        results = pdf_processor.process_and_split(pdf_bytes, out_dir)

        assert len(results) == 2
        assert "Chapter 1" in results[0]["title"]
        assert results[0]["chapter_index"] == 0
        assert results[0]["word_count"] > 0
        assert "Chapter 2" in results[1]["title"]
        assert results[1]["chapter_index"] == 1

        ch0_html = (out_dir / "chapter_0000.html").read_text(encoding="utf-8")
        assert "<p>" in ch0_html
        assert "content of chapter one" in ch0_html


def test_pdf_processor_amharic_headings():
    pdf_bytes = create_amharic_pdf()
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        results = pdf_processor.process_and_split(pdf_bytes, out_dir, language_code="am")

        assert len(results) == 2
        assert "ምዕራፍ 1" in results[0]["title"]
        assert "ምዕራፍ 2" in results[1]["title"]


def test_pdf_processor_heading_detection_no_toc():
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((50, 72), "Chapter 1: The Beginning\n\nSome body text here.")
    p2 = doc.new_page()
    p2.insert_text((50, 72), "Chapter 2: The Next Step\n\nMore body text here.")
    buf = doc.tobytes()
    doc.close()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        results = pdf_processor.process_and_split(buf, out_dir)
        assert len(results) == 2
        assert results[0]["title"] == "Chapter 1: The Beginning"
        assert results[1]["title"] == "Chapter 2: The Next Step"


def test_pdf_scanned_page_detection_and_fallback():
    pdf_bytes = create_scanned_mock_pdf()
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        img_dir = out_dir / "images"
        results = pdf_processor.process_and_split(
            pdf_bytes,
            out_dir,
            images_dir=img_dir,
            images_url_prefix="/storage/books/test/images",
        )

        assert len(results) >= 1
        ch0_html = (out_dir / "chapter_0000.html").read_text(encoding="utf-8")
        assert 'class="scanned-page"' in ch0_html or "<img" in ch0_html


@pytest.mark.anyio
async def test_pdf_upload_endpoint(async_client):
    pdf_bytes = create_sample_pdf_with_toc()
    files = {"file": ("test_book.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "title": "A Great PDF Novel",
        "language_code": "en",
        "author": "Sample Author",
    }
    response = await async_client.post("/api/v1/upload", files=files, data=data)
    assert response.status_code == 201
    res_data = response.json()
    assert "work_id" in res_data
    assert "book_id" in res_data
    assert res_data["chapters_created"] == 2

    book_id = res_data["book_id"]
    # Check book detail
    detail = await async_client.get(f"/api/v1/books/{book_id}")
    assert detail.status_code == 200
    assert detail.json()["format"] == "pdf"


@pytest.mark.anyio
async def test_admin_books_upload_endpoint(async_client):
    pdf_bytes = create_amharic_pdf()
    files = {"file": ("amharic_sample.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {
        "title": "የኢትዮጵያ ታሪክ",
        "language_code": "am",
        "author": "ደራሲ አበበ",
    }
    response = await async_client.post("/api/v1/admin/books/upload", files=files, data=data)
    assert response.status_code == 201
    admin_data = response.json()

    assert admin_data["title"] == "የኢትዮጵያ ታሪክ"
    assert admin_data["author"] == "ደራሲ አበበ"
    assert admin_data["language"] == "AM"
    assert len(admin_data["chapters"]) == 2
    assert admin_data["chapters"][0]["index"] == 0
    assert "ምዕራፍ 1" in admin_data["chapters"][0]["title"]
    assert "<p" in admin_data["chapters"][0]["html"]
    assert admin_data["chapters"][1]["index"] == 1
