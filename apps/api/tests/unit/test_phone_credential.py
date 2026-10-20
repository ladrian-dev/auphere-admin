"""La credencial de acceso del teléfono — spec 031, R2.1 y R2.3 (tarea T009).

Es la hermana de la del escritorio (``device_credential``) con dos diferencias
que son toda la razón de existir: **su propio secreto** y **su propio
servicio**. Ninguna de las dos credenciales vale donde vale la otra.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from nexus_api.config import get_settings
from nexus_api.core import phone_credential as pc
from nexus_api.services import device_credential


def test_issue_and_verify_roundtrip() -> None:
    phone_id = uuid.uuid4()
    token = pc.issue_access_token(phone_id=phone_id, generation=3)

    claims = pc.verify_access_token(token)

    assert claims.phone_id == phone_id
    assert claims.generation == 3


def test_claims_carry_no_tenant_and_last_one_hour() -> None:
    token = pc.issue_access_token(phone_id=uuid.uuid4(), generation=1)
    payload = jwt.decode(token, options={"verify_signature": False})

    assert payload["svc"] == "customers_phone"
    # El tenant sale de la fila del teléfono, nunca de lo que trae el llamante.
    assert "tid" not in payload and "tenant_id" not in payload and "pid" not in payload
    assert payload["exp"] - payload["iat"] == 3600
    assert payload["iss"] == get_settings().console_jwt_issuer
    assert payload["aud"] == get_settings().console_jwt_audience


def test_rejects_another_service_signed_with_the_same_secret() -> None:
    s = get_settings()
    now = int(datetime.now(UTC).timestamp())
    forged = jwt.encode(
        {
            "svc": "device",
            "sub": str(uuid.uuid4()),
            "gen": 1,
            "iat": now,
            "exp": now + 60,
            "iss": s.console_jwt_issuer,
            "aud": s.console_jwt_audience,
        },
        s.customers_app_token_secret,
        algorithm="HS256",
    )
    with pytest.raises(pc.PhoneCredentialError):
        pc.verify_access_token(forged)


def test_rejects_the_desktop_credential() -> None:
    desktop = device_credential.issue_device_token(
        device_id=uuid.uuid4(), partner_id=uuid.uuid4(), generation=1
    )
    with pytest.raises(pc.PhoneCredentialError):
        pc.verify_access_token(desktop)


def test_rejects_a_token_signed_with_another_secret() -> None:
    s = get_settings()
    now = int(datetime.now(UTC).timestamp())
    token = jwt.encode(
        {
            "svc": "customers_phone",
            "sub": str(uuid.uuid4()),
            "gen": 1,
            "iat": now,
            "exp": now + 60,
            "iss": s.console_jwt_issuer,
            "aud": s.console_jwt_audience,
        },
        "otro-secreto-que-no-es-el-de-la-api-0123456789",
        algorithm="HS256",
    )
    with pytest.raises(pc.PhoneCredentialError):
        pc.verify_access_token(token)


def test_rejects_an_expired_token() -> None:
    token = pc.issue_access_token(phone_id=uuid.uuid4(), generation=1, ttl=timedelta(seconds=-120))
    with pytest.raises(pc.PhoneCredentialError):
        pc.verify_access_token(token)


@pytest.mark.parametrize("missing", ["sub", "gen"])
def test_rejects_a_token_without_phone_or_generation(missing: str) -> None:
    s = get_settings()
    now = int(datetime.now(UTC).timestamp())
    payload = {
        "svc": "customers_phone",
        "sub": str(uuid.uuid4()),
        "gen": 1,
        "iat": now,
        "exp": now + 60,
        "iss": s.console_jwt_issuer,
        "aud": s.console_jwt_audience,
    }
    payload.pop(missing)
    token = jwt.encode(payload, s.customers_app_token_secret, algorithm="HS256")
    with pytest.raises(pc.PhoneCredentialError):
        pc.verify_access_token(token)


def test_refuses_the_factory_secret_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "environment", "production")
    with pytest.raises(pc.PhoneCredentialError):
        pc.issue_access_token(phone_id=uuid.uuid4(), generation=1)


def test_refresh_tokens_are_opaque_and_hashed() -> None:
    token = pc.new_refresh_token()

    assert len(token) >= 43
    assert pc.hash_refresh_token(token) == pc.hash_refresh_token(token)
    assert pc.hash_refresh_token(token) != pc.hash_refresh_token(pc.new_refresh_token())
    assert len(pc.hash_refresh_token(token)) == 32


def test_looks_like_phone_token_tells_the_bff_jwt_apart() -> None:
    phone = pc.issue_access_token(phone_id=uuid.uuid4(), generation=1)

    assert pc.looks_like_phone_token(phone) is True
    assert pc.looks_like_phone_token("no-es-un-jwt") is False
