from __future__ import annotations

import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Farm, FarmMembership, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = hashed.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)},
        settings.jwt_secret,
        algorithm="HS256",
    )


async def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


async def ensure_farm_access(session: AsyncSession, farm_id: uuid.UUID, user: User | None) -> Farm:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    if farm.is_demo:
        return farm
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    membership = await session.scalar(
        select(FarmMembership).where(
            FarmMembership.farm_id == farm_id, FarmMembership.user_id == user.id
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="No access to this farm")
    return farm
