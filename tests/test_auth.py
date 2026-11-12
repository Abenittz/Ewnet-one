import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_user_registration_and_login_lifecycle(async_client: AsyncClient):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    password = "SuperSecretPassword123"
    display_name = "Test Reader"

    # 1. Register new user
    reg_response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert reg_response.status_code == 201
    reg_data = reg_response.json()
    assert "access_token" in reg_data
    assert reg_data["token_type"] == "bearer"
    assert reg_data["user"]["email"] == email
    assert reg_data["user"]["display_name"] == display_name
    assert reg_data["user"]["is_active"] is True
    token = reg_data["access_token"]

    # 2. Duplicate registration should be rejected
    dup_response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert dup_response.status_code == 400
    assert "already exists" in dup_response.json()["detail"]

    # 3. Login with wrong password
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    # 4. Login with correct credentials
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == email

    # 5. Get current user profile (/auth/me)
    me_response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == email
    assert me_data["display_name"] == display_name

    # 6. Unauthenticated profile access
    unauth_response = await async_client.get("/api/v1/auth/me")
    assert unauth_response.status_code == 401

    # 7. Update profile (display name and password)
    new_password = "UpdatedPassword456"
    patch_response = await async_client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "Updated Name", "password": new_password},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["display_name"] == "Updated Name"

    # 8. Verify login with new password
    new_login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login_response.status_code == 200


import io
import fitz


def create_minimal_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Chapter 1\nHello from auth test.")
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.mark.anyio
async def test_reading_progress_with_jwt_bearer_token(async_client: AsyncClient):
    # 1. Register user
    email = f"reader_{uuid.uuid4().hex[:8]}@example.com"
    reg_response = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123", "display_name": "Token Reader"},
    )
    assert reg_response.status_code == 201
    auth_data = reg_response.json()
    token = auth_data["access_token"]
    user_id = auth_data["user"]["id"]

    # 2. Ingest a minimal book using admin upload
    pdf_bytes = create_minimal_pdf()
    book_resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files={"file": ("test_auth.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "JWT Reader Book", "language_code": "en"},
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["book_id"]

    # 3. Save progress using Bearer token (no user_id query or header)
    save_progress = await async_client.put(
        f"/api/v1/reader/{book_id}/progress",
        headers={"Authorization": f"Bearer {token}"},
        json={"chapter_index": 0, "scroll_offset": 540},
    )
    assert save_progress.status_code == 200
    progress_data = save_progress.json()
    assert progress_data["user_id"] == user_id
    assert progress_data["chapter_index"] == 0
    assert progress_data["scroll_offset"] == 540

    # 4. Get progress using Bearer token
    get_progress = await async_client.get(
        f"/api/v1/reader/{book_id}/progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_progress.status_code == 200
    get_data = get_progress.json()
    assert get_data["user_id"] == user_id
    assert get_data["scroll_offset"] == 540


@pytest.mark.anyio
async def test_mobile_pwa_guest_flow_and_upgrade(async_client: AsyncClient):
    client_device_id = uuid.uuid4()

    # 1. Frictionless guest onboarding on mobile PWA app launch
    guest_resp = await async_client.post(
        "/api/v1/auth/guest",
        json={"device_name": "iPhone 15 PWA", "client_id": str(client_device_id)},
    )
    assert guest_resp.status_code == 201
    guest_data = guest_resp.json()
    assert "access_token" in guest_data
    assert "refresh_token" in guest_data
    assert guest_data["user"]["is_guest"] is True
    guest_token = guest_data["access_token"]
    guest_id = guest_data["user"]["id"]

    # 2. Ingest sample book
    pdf_bytes = create_minimal_pdf()
    book_resp = await async_client.post(
        "/api/v1/admin/books/upload",
        files={"file": ("guest_test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"title": "Guest Book", "language_code": "en"},
    )
    assert book_resp.status_code == 201
    book_id = book_resp.json()["book_id"]

    # 3. Save reading progress as guest
    prog_resp = await async_client.put(
        f"/api/v1/reader/{book_id}/progress",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"chapter_index": 0, "scroll_offset": 320},
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["scroll_offset"] == 320

    # 4. Add bookmark as guest
    bm_resp = await async_client.post(
        f"/api/v1/reader/{book_id}/bookmarks",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={"chapter_index": 0, "scroll_offset": 320, "title": "Guest Bookmark"},
    )
    assert bm_resp.status_code == 201
    bm_id = bm_resp.json()["id"]

    # 5. Upgrade guest account to registered user
    reg_email = f"upgraded_{uuid.uuid4().hex[:8]}@example.com"
    upgrade_resp = await async_client.post(
        "/api/v1/auth/upgrade-guest",
        headers={"Authorization": f"Bearer {guest_token}"},
        json={
            "email": reg_email,
            "password": "UpgradedSecurePass123",
            "display_name": "Upgraded Reader",
        },
    )
    assert upgrade_resp.status_code == 200
    upgraded_data = upgrade_resp.json()
    assert upgraded_data["user"]["is_guest"] is False
    assert upgraded_data["user"]["email"] == reg_email
    assert upgraded_data["user"]["display_name"] == "Upgraded Reader"
    upgraded_token = upgraded_data["access_token"]

    # 6. Verify reading progress and bookmark are preserved seamlessly
    check_prog = await async_client.get(
        f"/api/v1/reader/{book_id}/progress",
        headers={"Authorization": f"Bearer {upgraded_token}"},
    )
    assert check_prog.status_code == 200
    assert check_prog.json()["scroll_offset"] == 320

    check_bm = await async_client.get(
        f"/api/v1/reader/{book_id}/bookmarks",
        headers={"Authorization": f"Bearer {upgraded_token}"},
    )
    assert check_bm.status_code == 200
    bookmarks = check_bm.json()
    assert any(b["id"] == bm_id for b in bookmarks)


@pytest.mark.anyio
async def test_mobile_pwa_refresh_token_rotation_and_sessions(async_client: AsyncClient):
    email = f"session_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "MobileSessionPass123"

    # 1. Register user
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": "Mobile User",
            "device_name": "Pixel 8 PWA",
        },
    )
    assert reg_resp.status_code == 201
    auth_data = reg_resp.json()
    access_token = auth_data["access_token"]
    refresh_token = auth_data["refresh_token"]

    # 2. Check active sessions
    sessions_resp = await async_client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()
    assert len(sessions) >= 1
    assert sessions[0]["device_name"] == "Pixel 8 PWA"

    # 3. Rotate refresh token (POST /auth/refresh)
    refresh_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token, "device_name": "Pixel 8 PWA (Resumed)"},
    )
    assert refresh_resp.status_code == 200
    new_auth_data = refresh_resp.json()
    new_access_token = new_auth_data["access_token"]
    new_refresh_token = new_auth_data["refresh_token"]
    assert new_refresh_token != refresh_token

    # 4. Old refresh token cannot be reused (replay protection)
    replay_resp = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert replay_resp.status_code == 401

    # 5. Logout using active refresh token
    logout_resp = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_refresh_token},
    )
    assert logout_resp.status_code == 200

    # 6. Logged out token is rejected
    post_logout_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert post_logout_refresh.status_code == 401

    # 7. Delete all sessions endpoint
    del_sessions = await async_client.delete(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert del_sessions.status_code == 200


