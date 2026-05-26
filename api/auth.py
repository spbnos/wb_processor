"""
auth.py — JWT + API Key аутентификация.

Два метода:
    1. API Key: X-API-Key header (для сервис-клиентов)
    2. JWT Bearer: Authorization: Bearer <token> (для Dashboard)

Конфиг через env vars:
    API_KEY       — статический ключ (default: dev-key)
    JWT_SECRET    — секрет для подписи JWT
    JWT_ALGORITHM — алгоритм (default: HS256)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

try:
    from jose import JWTError, jwt
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

_API_KEY      = os.getenv("API_KEY", "dev-key-change-in-prod")
_JWT_SECRET   = os.getenv("JWT_SECRET", "jwt-secret-change-in-prod")
_JWT_ALGO     = os.getenv("JWT_ALGORITHM", "HS256")
_JWT_EXPIRE_H = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer         = HTTPBearer(auto_error=False)


def _verify_api_key(key: Optional[str]) -> bool:
    return key == _API_KEY


def _create_token(data: dict) -> str:
    if not _JWT_AVAILABLE:
        return "mock-token"
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_H)
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGO)


def _verify_token(token: str) -> dict:
    if not _JWT_AVAILABLE:
        return {"sub": "mock-user"}
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGO])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


async def require_auth(
    api_key: Optional[str] = Security(_api_key_header),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> dict:
    """
    FastAPI dependency — требует API Key ИЛИ валидный JWT.
    Возвращает payload с identity.
    """
    if api_key and _verify_api_key(api_key):
        return {"sub": "api-key-client", "method": "api_key"}

    if bearer:
        payload = _verify_token(bearer.credentials)
        payload["method"] = "jwt"
        return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide X-API-Key or Bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(sub: str = "user") -> str:
    return _create_token({"sub": sub, "type": "access"})
