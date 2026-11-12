import io
import uuid
import pytest


@pytest.mark.anyio
async def test_works_endpoints(async_client):
    # Fetch works catalog
    res = await async_client.get("/api/v1/works")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data

    if not data["items"]:
        pytest.skip("No works in test DB")

    work_id = data["items"][0]["id"]

    # Detail
    detail_res = await async_client.get(f"/api/v1/works/{work_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == work_id
    assert "books" in detail

    # Update original_title
    old_title = detail["original_title"]
    new_title = f"{old_title} (Updated)"
    patch_res = await async_client.patch(
        f"/api/v1/works/{work_id}",
        json={"original_title": new_title},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["original_title"] == new_title

    # Restore title
    await async_client.patch(
        f"/api/v1/works/{work_id}",
        json={"original_title": old_title},
    )


@pytest.mark.anyio
async def test_books_search_and_cover_upload(async_client):
    catalog_res = await async_client.get("/api/v1/books")
    assert catalog_res.status_code == 200
    items = catalog_res.json()["items"]
    if not items:
        pytest.skip("No books in test DB")

    book = items[0]
    book_id = book["id"]
    book_title = book["title"]

    # Search by title substring
    search_res = await async_client.get(f"/api/v1/books?search={book_title[:3]}")
    assert search_res.status_code == 200
    matched = search_res.json()["items"]
    assert any(b["id"] == book_id for b in matched)

    # Upload cover
    fake_img = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20  # JPEG header
    files = {"file": ("cover.jpg", io.BytesIO(fake_img), "image/jpeg")}
    cover_res = await async_client.post(f"/api/v1/books/{book_id}/cover", files=files)
    assert cover_res.status_code == 200
    cover_url = cover_res.json()["cover_image_url"]
    assert "/resources/" in cover_url or "/storage/books/" in cover_url

    # Verify cover URL is reachable
    static_res = await async_client.get(cover_url)
    assert static_res.status_code == 200

    # Book detail includes cover_image_url
    detail_res = await async_client.get(f"/api/v1/books/{book_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["cover_image_url"] == cover_url
