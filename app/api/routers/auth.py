"""Authentication endpoints for signup, login, and logout."""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer

from app.schemas.auth import SignupRequest, LoginRequest, AuthResponse, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
security = HTTPBearer()


def _extract_token_from_header(credentials) -> str:
    """Extract Bearer token from Authorization header."""
    return credentials.credentials


async def get_current_user(credentials = Depends(security)) -> dict:
    """Verify JWT token and return user info."""
    token = _extract_token_from_header(credentials)
    try:
        user_data = await auth_service.verify_token(access_token=token)
        return user_data
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest) -> AuthResponse:
    """Register a new user."""
    try:
        result = await auth_service.signup(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    user = result.get("user", {})
    session = result.get("session")
    
    token_response = None
    if session:
        token_response = TokenResponse(
            access_token=session.get("access_token", ""),
            refresh_token=session.get("refresh_token", ""),
            expires_in=session.get("expires_in", 3600),
            token_type=session.get("token_type", "bearer"),
            user_id=user.get("id", ""),
            email=user.get("email", ""),
        )
    
    return AuthResponse(
        success=True,
        message="Signup successful",
        token=token_response,
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    """Log in a user and return JWT token."""
    try:
        result = await auth_service.login(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    
    token_response = TokenResponse(
        access_token=result.get("access_token", ""),
        refresh_token=result.get("refresh_token", ""),
        expires_in=result.get("expires_in", 3600),
        token_type=result.get("token_type", "bearer"),
        user_id=result.get("user", {}).get("id", ""),
        email=result.get("user", {}).get("email", ""),
    )
    
    return AuthResponse(
        success=True,
        message="Login successful",
        token=token_response,
    )


@router.post("/logout", response_model=AuthResponse)
async def logout(credentials = Depends(security)) -> AuthResponse:
    """Log out a user (invalidate their session)."""
    token = _extract_token_from_header(credentials)
    try:
        await auth_service.signout(access_token=token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    return AuthResponse(
        success=True,
        message="Logout successful",
        token=None,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(credentials = Depends(security)) -> TokenResponse:
    """Refresh an access token using a refresh token."""
    refresh_token_value = _extract_token_from_header(credentials)
    try:
        result = await auth_service.refresh_token(refresh_token=refresh_token_value)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    
    return TokenResponse(
        access_token=result.get("access_token", ""),
        refresh_token=result.get("refresh_token", refresh_token_value),
        expires_in=result.get("expires_in", 3600),
        token_type=result.get("token_type", "bearer"),
        user_id=result.get("user", {}).get("id", ""),
        email=result.get("user", {}).get("email", ""),
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)) -> UserResponse:
    """Get current logged-in user info."""
    profile = await auth_service.get_user_profile(user.get("id", ""))
    if profile:
        return UserResponse(
            id=profile.get("id", ""),
            email=profile.get("email", ""),
            created_at=profile.get("created_at", ""),
        )

    return UserResponse(
        id=user.get("id", ""),
        email=user.get("email", ""),
        created_at=user.get("created_at", ""),
    )
