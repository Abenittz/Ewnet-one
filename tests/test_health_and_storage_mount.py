from pathlib import Path
import pytest
from app.core.config import settings


@pytest.mark.anyio
async def test_health_check(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


@pytest.mark.anyio
async def test_storage_mount_serving(async_client):
    # Create a dummy test file in STORAGE_PATH
    storage_root = Path(settings.STORAGE_PATH)
    storage_root.mkdir(parents=True, exist_ok=True)
    test_file = storage_root / "test_file.txt"
    test_file.write_text("hello ewnet reader", encoding="utf-8")

    try:
        response = await async_client.get("/storage/test_file.txt")
        assert response.status_code == 200
        assert response.text == "hello ewnet reader"
    finally:
        test_file.unlink(missing_ok=True)
