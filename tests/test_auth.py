from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.security import AuthUser, create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("AcmeAdmin123!")
    assert hashed != "AcmeAdmin123!"
    assert verify_password("AcmeAdmin123!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_contains_tenant_claims():
    user = AuthUser(
        id="user-1",
        company_id="company-a",
        email="admin@acme.test",
        name="Admin",
        role="ADMIN",
        company_name="Acme",
        company_slug="acme",
    )
    token = create_access_token(user)
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["company_id"] == "company-a"
    assert payload["role"] == "ADMIN"


def test_expired_jwt_is_rejected(monkeypatch):
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": "user-1",
            "company_id": "company-a",
            "role": "ADMIN",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)
    assert exc.value.status_code == 401


def test_production_rejects_placeholder_jwt_secret():
    from app.core.config import Settings

    settings = Settings(
        environment="production",
        jwt_secret="change-me-to-a-long-random-string",
        cookie_secure=True,
    )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate_runtime_security()


def test_production_rejects_insecure_cookie():
    from app.core.config import Settings

    settings = Settings(
        environment="production",
        jwt_secret="a-long-enough-production-secret-value",
        cookie_secure=False,
    )
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        settings.validate_runtime_security()


def test_development_allows_placeholder_secret():
    from app.core.config import Settings

    Settings(
        environment="development",
        jwt_secret="change-me-to-a-long-random-string",
        cookie_secure=False,
    ).validate_runtime_security()
