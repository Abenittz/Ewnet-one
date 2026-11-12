import uuid
import pytest


@pytest.mark.anyio
async def test_reading_progress_lifecycle(async_client):
    # First, fetch existing books to test with a real book
    catalog_res = await async_client.get("/api/v1/books")
    assert catalog_res.status_code == 200
    catalog = catalog_res.json()

    if not catalog["items"]:
        pytest.skip("No books in test database to run progress test")

    book_id = catalog["items"][0]["id"]
    user_id = str(uuid.uuid4())

    # 1. Fetch progress for a new user -> returns default 0,0
    prog_res = await async_client.get(
        f"/api/v1/reader/{book_id}/progress",
        headers={"X-User-Id": user_id},
    )
    assert prog_res.status_code == 200
    data = prog_res.json()
    assert data["chapter_index"] == 0
    assert data["scroll_offset"] == 0
    assert data["user_id"] == user_id

    # 2. Update progress
    update_res = await async_client.put(
        f"/api/v1/reader/{book_id}/progress",
        json={"chapter_index": 2, "scroll_offset": 450},
        headers={"X-User-Id": user_id},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["chapter_index"] == 2
    assert updated_data["scroll_offset"] == 450

    # 3. Retrieve updated progress
    get_res = await async_client.get(
        f"/api/v1/reader/{book_id}/progress",
        headers={"X-User-Id": user_id},
    )
    assert get_res.status_code == 200
    assert get_res.json()["chapter_index"] == 2
    assert get_res.json()["scroll_offset"] == 450


@pytest.mark.anyio
async def test_reader_manifest_and_chapter_nav(async_client):
    catalog_res = await async_client.get("/api/v1/books")
    assert catalog_res.status_code == 200
    catalog = catalog_res.json()

    if not catalog["items"]:
        pytest.skip("No books in test database to run manifest test")

    book_id = catalog["items"][0]["id"]

    # Manifest test
    manifest_res = await async_client.get(f"/api/v1/reader/{book_id}/manifest")
    assert manifest_res.status_code == 200
    manifest = manifest_res.json()
    assert "work_id" in manifest
    assert "total_chapters" in manifest
    assert "total_words" in manifest
    assert "available_editions" in manifest
    assert isinstance(manifest["available_editions"], list)

    # Chapter nav test
    if manifest["total_chapters"] > 0:
        ch_res = await async_client.get(f"/api/v1/reader/{book_id}/chapters/0")
        assert ch_res.status_code == 200
        ch_nav = ch_res.json()
        assert ch_nav["chapter_index"] == 0
        assert ch_nav["has_previous"] is False
        assert "content_html_url" in ch_nav
