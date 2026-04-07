"""Верификация Keycloak JWT с кешированием JWKS в Redis."""
from __future__ import annotations

import json

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from redis.asyncio import Redis

from app.core.config import settings

_JWKS_CACHE_KEY = "keycloak:jwks"
_JWKS_CACHE_TTL = 3600  # seconds


async def _fetch_jwks() -> dict:
    url = (
        f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
        "/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def _get_jwks(redis: Redis) -> dict:
    cached = await redis.get(_JWKS_CACHE_KEY)
    if cached:
        return json.loads(cached)
    jwks = await _fetch_jwks()
    await redis.set(_JWKS_CACHE_KEY, json.dumps(jwks), ex=_JWKS_CACHE_TTL)
    return jwks


async def verify_keycloak_token(token: str, redis: Redis) -> dict:
    """Верифицирует JWT от Keycloak и возвращает его payload.

    JWKS кешируются в Redis на час, чтобы не долбить Keycloak каждый раз.
    Если kid не нашёлся в кеше — принудительно обновляем.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT header",
        ) from exc

    kid = header.get("kid")
    alg = header.get("alg", "RS256")

    try:
        jwks = await _get_jwks(redis)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach Keycloak JWKS endpoint: {exc}",
        ) from exc

    keys = jwks.get("keys", [])
    key = next((k for k in keys if k.get("kid") == kid), None)
    if key is None:
        # kid не найден — кеш устарел, принудительно обновляем
        await redis.delete(_JWKS_CACHE_KEY)
        try:
            jwks = await _fetch_jwks()
            await redis.set(_JWKS_CACHE_KEY, json.dumps(jwks), ex=_JWKS_CACHE_TTL)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot reach Keycloak JWKS endpoint: {exc}",
            ) from exc
        keys = jwks.get("keys", [])
        key = next((k for k in keys if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No matching key found in Keycloak JWKS",
            )

    decode_options: dict = {"verify_at_hash": False}
    decode_kwargs: dict = {"algorithms": [alg], "options": decode_options}
    if settings.KEYCLOAK_VERIFY_AUDIENCE:
        decode_kwargs["audience"] = settings.KEYCLOAK_CLIENT_ID
    else:
        decode_options["verify_aud"] = False

    try:
        payload = jwt.decode(token, key, **decode_kwargs)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload
