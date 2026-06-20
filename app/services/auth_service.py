"""Postgres-backed authentication service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any
from uuid import uuid4

import asyncpg

from app.core.settings import settings

ACCESS_TOKEN_SECONDS = 3600
REFRESH_TOKEN_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 210_000


def _pg_url() -> str:
    """Return a DSN asyncpg can use."""
    return settings.AUTH_PG_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_pg_url())


async def _ensure_users_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_sign_in_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_sign_in_at TIMESTAMPTZ")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()")


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def _verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_b64encode(digest), expected)
    except (TypeError, ValueError):
        return False


def _sign(data: str) -> str:
    digest = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        data.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _create_token(*, user: dict[str, Any], token_type: str, expires_in: int) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    payload = _b64encode(
        json.dumps(
            {
                "sub": str(user["id"]),
                "email": user["email"],
                "type": token_type,
                "iat": int(time.time()),
                "exp": int(time.time()) + expires_in,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{signature}"


def _decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        header, payload, signature = token.split(".", 2)
    except ValueError as exc:
        raise ValueError("Invalid token") from exc

    expected_signature = _sign(f"{header}.{payload}")
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid token")

    try:
        claims = json.loads(_b64decode(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid token") from exc

    if claims.get("type") != expected_type:
        raise ValueError("Invalid token type")
    if int(claims.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired")
    return claims


def _token_session(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_token": _create_token(user=user, token_type="access", expires_in=ACCESS_TOKEN_SECONDS),
        "refresh_token": _create_token(user=user, token_type="refresh", expires_in=REFRESH_TOKEN_SECONDS),
        "expires_in": ACCESS_TOKEN_SECONDS,
        "token_type": "bearer",
    }


def _public_user(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    created_at = row["created_at"] if row["created_at"] else None
    last_sign_in_at = row["last_sign_in_at"] if row["last_sign_in_at"] else None
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "created_at": created_at.isoformat() if created_at else "",
        "last_sign_in_at": last_sign_in_at.isoformat() if last_sign_in_at else None,
    }


async def get_user_profile(user_id: str) -> dict[str, Any] | None:
    """Fetch a user profile from local Postgres."""
    if not user_id:
        return None

    conn = await _connect()
    try:
        await _ensure_users_table(conn)
        row = await conn.fetchrow(
            """
            SELECT id, email, created_at, last_sign_in_at
            FROM users
            WHERE id = $1::uuid
            """,
            user_id,
        )
    finally:
        await conn.close()

    return _public_user(row) if row else None


async def signup(*, email: str, password: str) -> dict[str, Any]:
    """Create a local Postgres user and return auth tokens."""
    normalized_email = email.strip().lower()
    conn = await _connect()
    try:
        await _ensure_users_table(conn)
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, email, password_hash, created_at, updated_at)
            VALUES ($1::uuid, $2, $3, NOW(), NOW())
            RETURNING id, email, created_at, last_sign_in_at
            """,
            str(uuid4()),
            normalized_email,
            _hash_password(password),
        )
    except asyncpg.UniqueViolationError as exc:
        raise ValueError("Signup failed: email already exists") from exc
    finally:
        await conn.close()

    user = _public_user(row)
    return {"user": user, "session": _token_session(user)}


async def login(*, email: str, password: str) -> dict[str, Any]:
    """Authenticate a local Postgres user and return auth tokens."""
    normalized_email = email.strip().lower()
    conn = await _connect()
    try:
        await _ensure_users_table(conn)
        row = await conn.fetchrow(
            """
            SELECT id, email, password_hash, created_at, last_sign_in_at
            FROM users
            WHERE email = $1
            """,
            normalized_email,
        )
        if not row or not _verify_password(password, row["password_hash"]):
            raise ValueError("Login failed: invalid credentials")

        row = await conn.fetchrow(
            """
            UPDATE users
            SET last_sign_in_at = NOW(), updated_at = NOW()
            WHERE id = $1
            RETURNING id, email, created_at, last_sign_in_at
            """,
            row["id"],
        )
    finally:
        await conn.close()

    user = _public_user(row)
    return {**_token_session(user), "user": user}


async def refresh_token(*, refresh_token: str) -> dict[str, Any]:
    """Refresh an access token using a locally signed refresh token."""
    claims = _decode_token(refresh_token, expected_type="refresh")
    user = await get_user_profile(claims.get("sub", ""))
    if not user:
        raise ValueError("Token refresh failed")
    return {**_token_session(user), "user": user}


async def verify_token(*, access_token: str) -> dict[str, Any]:
    """Verify a locally signed access token and return the user."""
    claims = _decode_token(access_token, expected_type="access")
    user = await get_user_profile(claims.get("sub", ""))
    if not user:
        raise ValueError("Invalid or expired token")
    return user


async def signout(*, access_token: str) -> None:
    """Stateless logout placeholder; clients discard the token."""
    _decode_token(access_token, expected_type="access")
