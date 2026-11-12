import io
import uuid
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.media_storage import DatabaseMediaStorage, S3MediaStorage, media_storage


def create_test_image(color_byte: int = 120) -> bytes:
    """Generate minimal valid PNG bytes."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def create_minimal_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Chapter 1: The Beginning\nContent of chapter 1 with john 4:21 citation.")
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.mark.anyio
async def test_resource_upload_and_serve_with_caching(async_client: AsyncClient):
    img_bytes = create_test_image()

    # 1. Direct resource upload
    files = {"file": ("custom_art.png", io.BytesIO(img_bytes), "image/png")}
    upload_res = await async_client.post("/api/v1/resources", files=files)
    assert upload_res.status_code == 201
    res_data = upload_res.json()
    resource_id = res_data["id"]
    assert res_data["filename"] == "custom_art.png"
    assert res_data["content_type"] == "image/png"
    assert res_data["file_size"] == len(img_bytes)
    assert f"/resources/{resource_id}" in res_data["url"]

    # 2. Retrieve resource (GET /resources/{id})
    get_res = await async_client.get(f"/api/v1/resources/{resource_id}")
    assert get_res.status_code == 200
    assert get_res.content == img_bytes
    assert get_res.headers["content-type"] == "image/png"
    assert "public, max-age=" in get_res.headers["cache-control"]
    etag = get_res.headers.get("etag")
    assert etag is not None

    # 3. HTTP 304 Not Modified validation with ETag
    cached_res = await async_client.get(
        f"/api/v1/resources/{resource_id}",
        headers={"If-None-Match": etag},
    )
    assert cached_res.status_code == 304


@pytest.mark.anyio
async def test_cover_upload_from_file_stores_resource_id(async_client: AsyncClient):
    # 1. Ingest book
    pdf_bytes = create_minimal_pdf()
    files = {"file": ("book_cover_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    book_resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files=files,
        data={"title": "Cover Image Book", "language_code": "en"},
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["book_id"]

    # 2. Upload cover from file (not URL)
    cover_bytes = create_test_image()
    cover_file = {"file": ("new_cover.png", io.BytesIO(cover_bytes), "image/png")}
    upload_cover_resp = await async_client.post(
        f"/api/v1/books/{book_id}/cover",
        files=cover_file,
    )
    assert upload_cover_resp.status_code == 200
    cover_data = upload_cover_resp.json()
    assert cover_data["book_id"] == book_id
    assert "cover_image_id" in cover_data
    cover_res_id = cover_data["cover_image_id"]
    assert f"/resources/{cover_res_id}" in cover_data["cover_image_url"]

    # 3. Verify book detail reflects the cover_image_id
    detail_resp = await async_client.get(f"/api/v1/books/{book_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["cover_image_id"] == cover_res_id
    assert f"/resources/{cover_res_id}" in detail["cover_image_url"]

    # 4. Fetch the cover image using /resources/{id}
    rendered_cover = await async_client.get(f"/api/v1/resources/{cover_res_id}")
    assert rendered_cover.status_code == 200
    assert rendered_cover.content == cover_bytes


@pytest.mark.anyio
async def test_explore_and_user_library_lifecycle(async_client: AsyncClient):
    # 1. Create a guest user
    guest_resp = await async_client.post("/api/v1/auth/guest", json={"device_name": "Test PWA"})
    assert guest_resp.status_code == 201
    token = guest_resp.json()["access_token"]
    user_id = guest_resp.json()["user"]["id"]

    # 2. Ingest two sample books
    pdf_bytes = create_minimal_pdf()
    b1_resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files={"file": ("b1.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Explore Book One", "language_code": "en"},
    )
    assert b1_resp.status_code == 201
    book1_id = b1_resp.json()["book_id"]

    b2_resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files={"file": ("b2.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Explore Book Two", "language_code": "en"},
    )
    assert b2_resp.status_code == 201
    book2_id = b2_resp.json()["book_id"]

    # 3. Check Explore page: both books should be listed and is_in_library should be False
    explore_resp = await async_client.get(
        "/api/v1/explore",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert explore_resp.status_code == 200
    explore_items = explore_resp.json()
    assert len(explore_items) >= 2
    b1_item = next(it for it in explore_items if it["book_id"] == book1_id)
    assert b1_item["is_in_library"] is False
    assert b1_item["is_downloaded"] is False

    # 4. Save Book 1 to User's Library
    add_lib_resp = await async_client.post(
        f"/api/v1/library/{book1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert add_lib_resp.status_code == 201
    lib_item = add_lib_resp.json()
    assert lib_item["book_id"] == book1_id
    assert lib_item["title"] == "Explore Book One"
    assert lib_item["is_downloaded"] is False

    # 5. Verify Library listing (GET /library)
    list_lib_resp = await async_client.get(
        "/api/v1/library",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_lib_resp.status_code == 200
    user_lib = list_lib_resp.json()
    assert len(user_lib) == 1
    assert user_lib[0]["book_id"] == book1_id

    # 6. Re-check Explore page: Book 1 is now marked as is_in_library=True
    explore_again = await async_client.get(
        "/api/v1/explore",
        headers={"Authorization": f"Bearer {token}"},
    )
    b1_again = next(it for it in explore_again.json() if it["book_id"] == book1_id)
    assert b1_again["is_in_library"] is True

    # 7. Update download state (simulating PWA downloading to IndexedDB / local storage)
    dl_resp = await async_client.patch(
        f"/api/v1/library/{book1_id}/download-state",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_downloaded": True},
    )
    assert dl_resp.status_code == 200
    assert dl_resp.json()["is_downloaded"] is True
    assert dl_resp.json()["downloaded_at"] is not None

    # 8. Remove from library
    del_lib = await async_client.delete(
        f"/api/v1/library/{book1_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_lib.status_code == 204

    # 9. Verify library is now empty
    empty_lib = await async_client.get(
        "/api/v1/library",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(empty_lib.json()) == 0


@pytest.mark.anyio
async def test_offline_book_package_bundle_download(async_client: AsyncClient):
    # 1. Ingest a book with scripture citations
    pdf_bytes = create_minimal_pdf()
    resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files={"file": ("offline_bundle.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Offline Package Book", "language_code": "en"},
    )
    assert resp.status_code == 201
    book_id = resp.json()["book_id"]

    # 2. Fetch offline package (GET /reader/{id}/offline-package)
    package_resp = await async_client.get(f"/api/v1/reader/{book_id}/offline-package")
    assert package_resp.status_code == 200
    package = package_resp.json()

    assert package["book"]["id"] == book_id
    assert package["book"]["title"] == "Offline Package Book"
    assert package["total_chapters"] >= 1
    assert len(package["chapters"]) == package["total_chapters"]

    # Verify chapters include the full HTML content
    ch0 = package["chapters"][0]
    assert ch0["index"] == 0
    assert "<p" in ch0["html"] or "<h" in ch0["html"]
    assert ch0["word_count"] > 0

    # Verify scriptures are included in the bundle
    assert "references" in package
    assert isinstance(package["references"], list)

    # Verify asset_urls list for client caching
    assert "asset_urls" in package
    assert isinstance(package["asset_urls"], list)


def test_s3_storage_backend_readiness():
    """Verify S3 media storage abstraction and URL generation readiness."""
    s3_storage = S3MediaStorage()
    assert s3_storage.bucket == settings.S3_BUCKET_NAME
    assert s3_storage.region == settings.S3_REGION

    sample_id = uuid.uuid4()
    url = s3_storage.get_image_url(sample_id)
    assert f"/resources/{sample_id}" in url

    db_storage = DatabaseMediaStorage()
    db_url = db_storage.get_image_url(sample_id)
    assert f"/resources/{sample_id}" in db_url
