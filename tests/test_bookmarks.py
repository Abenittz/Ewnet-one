import io
import uuid
import fitz
import pytest
from httpx import AsyncClient


def create_test_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Chapter 1\nBookmark test book.")
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.mark.anyio
async def test_bookmarks_lifecycle(async_client: AsyncClient):
    # 1. Ingest a test book
    pdf_bytes = create_test_pdf()
    book_resp = await async_client.post(
        "/api/v1/upload",
        files={"file": ("bookmarks_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Bookmark Book", "language_code": "en"},
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["book_id"]

    # 2. Register user
    user_email = f"bookmark_{uuid.uuid4().hex[:8]}@example.com"
    auth_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": user_email, "password": "Password123", "display_name": "BM User"},
    )
    assert auth_resp.status_code == 201
    token = auth_resp.json()["access_token"]
    user_id = auth_resp.json()["user"]["id"]

    # 3. Create bookmark
    create_bm = await async_client.post(
        f"/api/v1/reader/{book_id}/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "chapter_index": 0,
            "scroll_offset": 1250,
            "title": "Interesting quote",
            "note": "Remember to revisit this section",
        },
    )
    assert create_bm.status_code == 201
    bm_data = create_bm.json()
    assert bm_data["user_id"] == user_id
    assert bm_data["book_id"] == book_id
    assert bm_data["chapter_index"] == 0
    assert bm_data["scroll_offset"] == 1250
    assert bm_data["title"] == "Interesting quote"
    assert bm_data["note"] == "Remember to revisit this section"
    bookmark_id = bm_data["id"]

    # 4. List bookmarks for this user
    list_resp = await async_client.get(
        f"/api/v1/reader/{book_id}/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    bm_list = list_resp.json()
    assert len(bm_list) == 1
    assert bm_list[0]["id"] == bookmark_id

    # 5. List bookmarks with different user ID (should be isolated)
    other_user_id = str(uuid.uuid4())
    other_list = await async_client.get(
        f"/api/v1/reader/{book_id}/bookmarks?user_id={other_user_id}",
    )
    assert other_list.status_code == 200
    assert len(other_list.json()) == 0

    # 6. Delete bookmark
    del_resp = await async_client.delete(
        f"/api/v1/reader/{book_id}/bookmarks/{bookmark_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code == 204

    # 7. List again to confirm deletion
    list_after_del = await async_client.get(
        f"/api/v1/reader/{book_id}/bookmarks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_after_del.status_code == 200
    assert len(list_after_del.json()) == 0

    # 8. Deleting already deleted bookmark should return 404
    del_404 = await async_client.delete(
        f"/api/v1/reader/{book_id}/bookmarks/{bookmark_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_404.status_code == 404
