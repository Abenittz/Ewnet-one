import io
import zipfile
import pytest
from httpx import AsyncClient

from app.services.epub_processor import epub_processor


def create_sample_epub(
    title: str = "Test EPUB Book",
    author: str = "Test Author",
    language: str = "en",
) -> bytes:
    """Generate a minimal, valid EPUB archive in memory."""
    buf = io.BytesIO()

    # 1x1 PNG image bytes
    dummy_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype must be first and uncompressed per EPUB spec
        z.writestr("mimetype", "application/epub+zip")

        # META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>"""
        z.writestr("META-INF/container.xml", container_xml)

        # OEBPS/content.opf
        content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookID" version="2.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
        <dc:title>{title}</dc:title>
        <dc:creator>{author}</dc:creator>
        <dc:language>{language}</dc:language>
        <meta name="cover" content="cover-image"/>
    </metadata>
    <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="cover-image" href="images/cover.png" media-type="image/png"/>
        <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
        <item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
    </manifest>
    <spine toc="ncx">
        <itemref idref="ch1"/>
        <itemref idref="ch2"/>
    </spine>
</package>"""
        z.writestr("OEBPS/content.opf", content_opf)

        # OEBPS/toc.ncx
        toc_ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <navMap>
        <navPoint id="navPoint-1" playOrder="1">
            <navLabel><text>Chapter 1: The First Step</text></navLabel>
            <content src="text/ch1.xhtml"/>
        </navPoint>
        <navPoint id="navPoint-2" playOrder="2">
            <navLabel><text>Chapter 2: The Journey Continues</text></navLabel>
            <content src="text/ch2.xhtml"/>
        </navPoint>
    </navMap>
</ncx>"""
        z.writestr("OEBPS/toc.ncx", toc_ncx)

        # OEBPS/text/ch1.xhtml
        ch1_html = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1: The First Step</title></head>
<body>
    <h1>Chapter 1: The First Step</h1>
    <p>This is the initial paragraph of chapter one in the EPUB test file.</p>
</body>
</html>"""
        z.writestr("OEBPS/text/ch1.xhtml", ch1_html)

        # OEBPS/text/ch2.xhtml
        ch2_html = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 2: The Journey Continues</title></head>
<body>
    <h2>Chapter 2: The Journey Continues</h2>
    <p>Here is another chapter that contains an inline image.</p>
    <img src="../images/cover.png" alt="inline cover"/>
</body>
</html>"""
        z.writestr("OEBPS/text/ch2.xhtml", ch2_html)

        # OEBPS/images/cover.png
        z.writestr("OEBPS/images/cover.png", dummy_png)

    return buf.getvalue()


def test_epub_metadata_and_splitting(tmp_path):
    epub_bytes = create_sample_epub(title="My Story", author="Abebe B.", language="am")

    # 1. Test metadata extraction
    meta = epub_processor.extract_metadata(epub_bytes)
    assert meta["title"] == "My Story"
    assert meta["author"] == "Abebe B."
    assert meta["language"] == "am"

    # 2. Test splitting
    out_dir = tmp_path / "chapters"
    images_dir = tmp_path / "images"
    cover_file = tmp_path / "cover.jpg"

    chapters = epub_processor.process_and_split(
        epub_bytes,
        out_dir,
        images_dir=images_dir,
        images_url_prefix="/storage/books/test/am/images",
        cover_image_path=cover_file,
    )

    assert len(chapters) == 2
    assert chapters[0]["chapter_index"] == 0
    assert "Chapter 1" in chapters[0]["title"]
    assert chapters[0]["word_count"] > 5

    assert chapters[1]["chapter_index"] == 1
    assert "Chapter 2" in chapters[1]["title"]

    # Verify cover file was written
    assert cover_file.exists()
    assert cover_file.stat().st_size > 0

    # Verify inline image was extracted
    extracted_images = list(images_dir.glob("img_*.*"))
    assert len(extracted_images) >= 1

    # Verify chapter html content
    ch2_html = (out_dir / "chapter_001.html").read_text(encoding="utf-8")
    assert "/storage/books/test/am/images/img_" in ch2_html


@pytest.mark.anyio
async def test_epub_upload_endpoint(async_client: AsyncClient):
    epub_bytes = create_sample_epub(title="Uploaded EPUB Book", author="Author Name", language="en")
    files = {"file": ("uploaded_book.epub", io.BytesIO(epub_bytes), "application/epub+zip")}
    data = {
        "title": "Uploaded EPUB Book",
        "language_code": "en",
        "author": "Author Name",
    }
    response = await async_client.post("/api/v1/upload", files=files, data=data)
    assert response.status_code == 201
    res = response.json()
    assert res["chapters_created"] == 2
    book_id = res["book_id"]

    # Verify book detail shows EPUB format
    book_resp = await async_client.get(f"/api/v1/books/{book_id}")
    assert book_resp.status_code == 200
    assert book_resp.json()["format"] == "epub"

    # Verify reader manifest
    manifest_resp = await async_client.get(f"/api/v1/reader/{book_id}/manifest")
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert manifest["total_chapters"] == 2
    assert "Chapter 1" in manifest["chapters"][0]["title"]

    # Verify reader chapter HTML
    html_resp = await async_client.get(f"/api/v1/reader/{book_id}/chapters/0/html")
    assert html_resp.status_code == 200
    assert "<p" in html_resp.text


@pytest.mark.anyio
async def test_admin_books_upload_with_epub(async_client: AsyncClient):
    epub_bytes = create_sample_epub(title="Admin EPUB Book", author="EPUB Creator", language="fr")
    files = {"file": ("admin_book.epub", io.BytesIO(epub_bytes), "application/epub+zip")}
    data = {
        "title": "Admin EPUB Book",
        "language_code": "fr",
        "author": "EPUB Creator",
    }
    response = await async_client.post("/api/v1/admin/books/upload", files=files, data=data)
    assert response.status_code == 201
    admin_data = response.json()

    assert admin_data["title"] == "Admin EPUB Book"
    assert admin_data["author"] == "EPUB Creator"
    assert admin_data["language"] == "FR"
    assert len(admin_data["chapters"]) == 2
    assert admin_data["chapters"][0]["index"] == 0
    assert "<p" in admin_data["chapters"][0]["html"]


def create_advanced_epub() -> bytes:
    """Generate an EPUB with multiple authors, guide cover page with SVG, and Amharic headings."""
    buf = io.BytesIO()
    dummy_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")

        z.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>""",
        )

        package_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="PubId" version="2.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>የተወደደ ታሪክ</dc:title>
        <dc:creator>አበበ ተስፋዬ</dc:creator>
        <dc:creator>ዮናስ ታደሰ</dc:creator>
        <dc:description>ልዩ የሆነ የአማርኛ መጽሐፍ</dc:description>
        <dc:language>am</dc:language>
    </metadata>
    <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="coverpage" href="text/cover.xhtml" media-type="application/xhtml+xml"/>
        <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
        <item id="art" href="images/art.png" media-type="image/png"/>
    </manifest>
    <spine toc="ncx">
        <itemref idref="coverpage"/>
        <itemref idref="ch1"/>
    </spine>
    <guide>
        <reference type="cover" title="Cover Page" href="text/cover.xhtml"/>
    </guide>
</package>"""
        z.writestr("OEBPS/package.opf", package_opf)

        toc_ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <navMap>
        <navPoint id="p1" playOrder="1">
            <navLabel><text>መቅድም</text></navLabel>
            <content src="text/cover.xhtml"/>
        </navPoint>
        <navPoint id="p2" playOrder="2">
            <navLabel><text>ምዕራፍ ፩: መግቢያ</text></navLabel>
            <content src="text/ch1.xhtml"/>
        </navPoint>
    </navMap>
</ncx>"""
        z.writestr("OEBPS/toc.ncx", toc_ncx)

        cover_xhtml = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>መቅድም</title></head>
<body>
    <h1>መቅድም</h1>
    <svg xmlns="http://www.w3.org/2000/svg" height="100%" width="100%">
        <image xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="../images/art.png" height="500" width="500"/>
    </svg>
    <p>የመጽሐፉ መቅድም ክፍል ነው።</p>
</body>
</html>"""
        z.writestr("OEBPS/text/cover.xhtml", cover_xhtml)

        ch1_xhtml = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>ምዕራፍ ፩: መግቢያ</title></head>
<body>
    <h2>ምዕራፍ ፩: መግቢያ</h2>
    <p>በዚህ ምዕራፍ ውስጥ ስለ ፍቅር ይነገራል 2john3:6 ተመልከት።</p>
    <svg xmlns="http://www.w3.org/2000/svg">
        <image xlink:href="../images/art.png" />
    </svg>
</body>
</html>"""
        z.writestr("OEBPS/text/ch1.xhtml", ch1_xhtml)
        z.writestr("OEBPS/images/art.png", dummy_png)

    return buf.getvalue()


def test_epub_advanced_guide_cover_and_svg_images(tmp_path):
    epub_bytes = create_advanced_epub()

    # 1. Test metadata with multiple authors and description
    meta = epub_processor.extract_metadata(epub_bytes)
    assert meta["title"] == "የተወደደ ታሪክ"
    assert "አበበ ተስፋዬ" in meta["author"]
    assert "ዮናስ ታደሰ" in meta["author"]
    assert meta["description"] == "ልዩ የሆነ የአማርኛ መጽሐፍ"

    # 2. Test split with SVG cover page resolution
    out_dir = tmp_path / "chapters"
    images_dir = tmp_path / "images"
    cover_file = tmp_path / "cover.jpg"

    chapters = epub_processor.process_and_split(
        epub_bytes,
        out_dir,
        images_dir=images_dir,
        images_url_prefix="/storage/books/test/am/images",
        cover_image_path=cover_file,
    )

    assert len(chapters) == 2
    # Verify cover extracted from XHTML guide page
    assert cover_file.exists()
    assert cover_file.stat().st_size > 0

    # Verify SVG <image xlink:href="..."> was rewritten
    ch1_html = (out_dir / "chapter_001.html").read_text(encoding="utf-8")
    assert "/storage/books/test/am/images/img_" in ch1_html


@pytest.mark.anyio
async def test_epub_upload_auto_extracts_author(async_client: AsyncClient):
    epub_bytes = create_advanced_epub()
    files = {"file": ("advanced.epub", io.BytesIO(epub_bytes), "application/epub+zip")}
    data = {
        "title": "የተወደደ ታሪክ",
        "language_code": "am",
        # Notice: author is omitted! Should be auto-extracted from EPUB metadata!
    }
    response = await async_client.post("/api/v1/upload", files=files, data=data)
    assert response.status_code == 201
    book_id = response.json()["book_id"]

    # Verify that the author was auto-extracted and stored in DB
    book_res = await async_client.get(f"/api/v1/books/{book_id}")
    assert book_res.status_code == 200
    book_data = book_res.json()
    assert "አበበ ተስፋዬ" in book_data["author"]
    assert "ዮናስ ታደሰ" in book_data["author"]

    # Verify scripture references were detected and linked
    refs_res = await async_client.get(f"/api/v1/reader/{book_id}/references")
    assert refs_res.status_code == 200
    refs = refs_res.json()
    assert any("2john" in r["reference_text"] or "2john" in r["book_name"] for r in refs)


