import pytest
from httpx import ASGITransport, AsyncClient
from main import app


@pytest.mark.anyio
async def test_cors_localhost_allowed(async_client):
    response = await async_client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.anyio
async def test_cors_pc_ip_allowed(async_client):
    # Test typical PC LAN IPs (10.x, 192.168.x, 172.x)
    for origin in [
        "http://10.119.184.74:3000",
        "http://10.119.184.74:5173",
        "http://192.168.1.150:3000",
        "http://172.17.209.102:8080",
    ]:
        response = await async_client.get(
            "/health",
            headers={"Origin": origin}
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.anyio
async def test_cors_preflight_options(async_client):
    response = await async_client.options(
        "/api/v1/books",
        headers={
            "Origin": "http://10.119.184.74:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://10.119.184.74:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.anyio
async def test_cors_unauthorized_external_origin_denied(async_client):
    response = await async_client.get(
        "/health",
        headers={"Origin": "http://malicious-website.com"}
    )
    assert response.status_code == 200
    # Disallowed origins must not receive Access-Control-Allow-Origin matching their domain
    assert response.headers.get("access-control-allow-origin") is None
