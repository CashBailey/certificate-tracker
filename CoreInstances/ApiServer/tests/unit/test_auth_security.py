"""Negative tests for authentication configuration and JWT parsing."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.auth.config import (
    _bounded_env_int,
    _validate_origin,
    _validate_secret,
    auth_settings,
)
from src.auth.security import decode_token


def _claims(**overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "1",
        "email": "coordinator@ci.laredo.tx.us",
        "role": "Coordinator",
        "type": "access",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "token_version": 1,
    }
    claims.update(overrides)
    return claims


def _encode(claims: dict) -> str:
    return jwt.encode(
        claims,
        auth_settings.JWT_SECRET_KEY,
        algorithm=auth_settings.JWT_ALGORITHM,
    )


def test_valid_access_token_decodes():
    payload = decode_token(_encode(_claims()))

    assert payload is not None
    assert payload.sub == "1"
    assert payload.type == "access"


@pytest.mark.parametrize("missing", ["sub", "email", "role", "type", "exp", "iat"])
def test_required_claims_cannot_be_omitted(missing):
    claims = _claims()
    claims.pop(missing)

    assert decode_token(_encode(claims)) is None


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", "0"),
        ("sub", "not-an-id"),
        ("email", None),
        ("role", None),
        ("type", "doc_view"),
        ("exp", True),
        ("exp", "tomorrow"),
        ("exp", 10**30),
        ("iat", "now"),
        ("token_version", True),
        ("token_version", -1),
    ],
)
def test_malformed_claims_return_none_instead_of_raising(claim, value):
    assert decode_token(_encode(_claims(**{claim: value}))) is None


def test_refresh_token_requires_valid_original_session_time():
    missing = _claims(type="refresh")
    malformed = _claims(type="refresh", session_created_at="not-a-date")

    assert decode_token(_encode(missing)) is None
    assert decode_token(_encode(malformed)) is None


def test_valid_refresh_session_time_decodes():
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    payload = decode_token(
        _encode(_claims(type="refresh", session_created_at=started.isoformat()))
    )

    assert payload is not None
    assert payload.session_created_at == started


@pytest.mark.parametrize(
    "secret",
    [
        "short",
        "dev-secret-key-change-in-production",
        "change_me_in_production",
        "REPLACE_ME_generate_with_openssl_rand_hex_32",
    ],
)
def test_insecure_secrets_are_rejected(secret):
    with pytest.raises(RuntimeError):
        _validate_secret(secret)


def test_secure_secret_is_accepted():
    secret = "6f" * 32
    assert _validate_secret(secret) == secret


@pytest.mark.parametrize(
    "origin",
    [
        "http://certificates.example.gov",
        "https://user:password@example.gov",
        "https://example.gov?redirect=evil",
        "javascript:alert(1)",
    ],
)
def test_unsafe_frontend_origins_are_rejected(origin):
    with pytest.raises(RuntimeError):
        _validate_origin(origin)


def test_https_and_local_http_origins_are_accepted():
    assert _validate_origin("https://certs.example.gov/") == "https://certs.example.gov"
    assert _validate_origin("http://localhost:3000") == "http://localhost:3000"


def test_bounded_integer_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("TEST_AUTH_WINDOW", "0")
    with pytest.raises(RuntimeError, match="between 1 and 10"):
        _bounded_env_int("TEST_AUTH_WINDOW", 5, 1, 10)

    monkeypatch.setenv("TEST_AUTH_WINDOW", "not-an-integer")
    with pytest.raises(RuntimeError, match="must be an integer"):
        _bounded_env_int("TEST_AUTH_WINDOW", 5, 1, 10)
