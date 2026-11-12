import io
import pytest


@pytest.mark.anyio
async def test_upload_invalid_language_code(async_client):
    file_content = b"fake docx"
    files = {"file": ("book.docx", io.BytesIO(file_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    data = {
        "title": "Test Title",
        "language_code": ".docx",  # Invalid language code!
    }
    response = await async_client.post("/api/v1/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Invalid language code" in response.json()["detail"]


@pytest.mark.anyio
async def test_upload_unsupported_file_extension(async_client):
    file_content = b"fake txt"
    files = {"file": ("book.txt", io.BytesIO(file_content), "text/plain")}
    data = {
        "title": "Test Title",
        "language_code": "en",
    }
    response = await async_client.post("/api/v1/upload", files=files, data=data)
    assert response.status_code == 400
    assert "Only .docx, .pdf, and .epub files are accepted." in response.json()["detail"]
