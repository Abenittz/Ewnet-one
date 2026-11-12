import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import Bookmark, RefreshToken, User, UserProgress
from app.schemas.user import (
    GuestAuthRequest,
    LogoutRequest,
    RefreshTokenRequest,
    SessionResponse,
    Token,
    UpgradeGuestRequest,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def _issue_tokens_for_user(
    user: User,
    device_name: str | None,
    db: AsyncSession,
) -> Token:
    """Generate access token and persistent refresh token for mobile PWA session."""
    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    raw_refresh_token = generate_refresh_token()
    token_h = hash_token(raw_refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session_record = RefreshToken(
        user_id=user.id,
        token_hash=token_h,
        device_name=device_name or "Mobile PWA",
        expires_at=expires_at,
        revoked=False,
    )
    db.add(session_record)
    await db.commit()
    await db.refresh(user)

    return Token(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Register a new user account.
    If guest_user_id is provided, migrates all reading progress and bookmarks to the new account.
    """
    email_clean = data.email.strip().lower()
    stmt = select(User).where(User.email == email_clean)
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )
        # Upgrading a guest user registered previously via guest mode
        existing_user.hashed_password = hash_password(data.password)
        existing_user.is_guest = False
        if data.display_name:
            existing_user.display_name = data.display_name
        user = existing_user
    else:
        # Check if caller wants to upgrade an existing guest UUID
        if data.guest_user_id:
            guest_stmt = select(User).where(User.id == data.guest_user_id)
            guest_res = await db.execute(guest_stmt)
            guest_user = guest_res.scalar_one_or_none()
            if guest_user and guest_user.is_guest:
                guest_user.email = email_clean
                guest_user.hashed_password = hash_password(data.password)
                guest_user.is_guest = False
                if data.display_name:
                    guest_user.display_name = data.display_name
                user = guest_user
            else:
                user = User(
                    email=email_clean,
                    display_name=data.display_name,
                    hashed_password=hash_password(data.password),
                    is_active=True,
                    is_superuser=False,
                    is_guest=False,
                )
                db.add(user)
        else:
            user = User(
                email=email_clean,
                display_name=data.display_name,
                hashed_password=hash_password(data.password),
                is_active=True,
                is_superuser=False,
                is_guest=False,
            )
            db.add(user)

    await db.flush()
    return await _issue_tokens_for_user(user, data.device_name, db)


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Log in an existing user and create a persistent mobile PWA session."""
    email_clean = data.email.strip().lower()
    stmt = select(User).where(User.email == email_clean)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if (
        not user
        or not user.hashed_password
        or not verify_password(data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive",
        )

    return await _issue_tokens_for_user(user, data.device_name, db)


@router.post("/guest", response_model=Token, status_code=status.HTTP_201_CREATED)
async def create_or_resume_guest(
    data: GuestAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Frictionless mobile PWA guest onboarding.
    Enables instant reading, bookmarking, and progress tracking upon app install without a forced login.
    """
    if data.client_id:
        stmt = select(User).where(User.id == data.client_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return await _issue_tokens_for_user(user, data.device_name, db)

    guest_id = data.client_id or uuid.uuid4()
    guest_email = f"guest_{guest_id.hex[:12]}@guest.ewnet.app"
    user = User(
        id=guest_id,
        email=guest_email,
        display_name="Guest Reader",
        hashed_password=None,
        is_active=True,
        is_superuser=False,
        is_guest=True,
    )
    db.add(user)
    await db.flush()
    return await _issue_tokens_for_user(user, data.device_name, db)


@router.post("/upgrade-guest", response_model=Token)
async def upgrade_guest_account(
    data: UpgradeGuestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Convert the active guest mobile session into a permanent registered account.
    Preserves all existing bookmarks, notes, and reading progress seamlessly.
    """
    email_clean = data.email.strip().lower()

    # Check if this email is already registered by another account
    stmt = select(User).where(User.email == email_clean)
    res = await db.execute(stmt)
    existing_user = res.scalar_one_or_none()

    if existing_user and existing_user.id != current_user.id:
        if existing_user.hashed_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A registered account with this email already exists",
            )
        # Existing account is another unactivated guest: migrate progress to current_user
        # and delete other guest
        await db.execute(
            update(UserProgress)
            .where(UserProgress.user_id == existing_user.id)
            .values(user_id=current_user.id)
        )
        await db.execute(
            update(Bookmark)
            .where(Bookmark.user_id == existing_user.id)
            .values(user_id=current_user.id)
        )
        await db.delete(existing_user)

    current_user.email = email_clean
    current_user.hashed_password = hash_password(data.password)
    current_user.is_guest = False
    if data.display_name:
        current_user.display_name = data.display_name

    await db.flush()
    return await _issue_tokens_for_user(current_user, "Mobile PWA", db)


@router.post("/refresh", response_model=Token)
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Rotate refresh token and issue a fresh access token for mobile PWA persistent login.
    Enforces refresh token rotation to prevent replay attacks.
    """
    token_str = data.refresh_token.strip()
    token_h = hash_token(token_str)

    stmt = (
        select(RefreshToken)
        .options(selectinload(RefreshToken.user))
        .where(RefreshToken.token_hash == token_h)
    )
    result = await db.execute(stmt)
    session_record = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if (
        not session_record
        or session_record.revoked
        or session_record.expires_at < now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session_record.user
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rotate token: revoke old one
    session_record.revoked = True

    # Generate new pair
    return await _issue_tokens_for_user(
        user=user,
        device_name=data.device_name or session_record.device_name,
        db=db,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    data: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke a refresh token on mobile logout."""
    if data.refresh_token:
        token_h = hash_token(data.refresh_token.strip())
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_h)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        if record:
            record.revoked = True
            await db.commit()

    return {"message": "Logged out successfully"}


@router.get("/sessions", response_model=list[SessionResponse])
async def list_active_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all active mobile/PWA devices registered for this user."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > now,
        )
        .order_by(RefreshToken.created_at.desc())
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [SessionResponse.model_validate(r) for r in records]


@router.delete("/sessions", status_code=status.HTTP_200_OK)
async def revoke_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Log out from all devices by revoking all active refresh tokens."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id)
        .values(revoked=True)
    )
    await db.commit()
    return {"message": "All sessions revoked successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Get profile of currently authenticated reader."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update profile attributes or password."""
    if data.display_name is not None:
        current_user.display_name = data.display_name
    if data.password is not None:
        current_user.hashed_password = hash_password(data.password)

    await db.commit()
    await db.refresh(current_user)
    return UserResponse.model_validate(current_user)
