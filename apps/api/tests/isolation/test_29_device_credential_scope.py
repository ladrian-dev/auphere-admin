"""Garantía 1 — la credencial de dispositivo, versión 2 (spec 002, Requisito 4.2).

La credencial ya no nombra tenant: nombra **partner, máquina y generación**. Lo
que aquí se prueba es lo que no depende de la base —firma, forma, generación y la
guarda del secreto de producción—; el alcance contra filas reales está en
``test_30``.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.services.device_credential import (
    DeviceCredentialError,
    issue_device_token,
    verify_device_token,
)

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def test_a_token_names_its_device_partner_and_generation():
    device_id, partner_id = uuid.uuid4(), uuid.uuid4()
    claims = verify_device_token(
        issue_device_token(device_id=device_id, partner_id=partner_id, generation=2)
    )
    assert claims.device_id == device_id
    assert claims.partner_id == partner_id
    assert claims.generation == 2


async def test_a_tampered_token_is_refused():
    token = issue_device_token(device_id=uuid.uuid4(), partner_id=uuid.uuid4(), generation=1)
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(DeviceCredentialError):
        verify_device_token(tampered)


async def test_garbage_is_refused():
    for bad in ["", "no-es-un-token", "a.b.c"]:
        with pytest.raises(DeviceCredentialError):
            verify_device_token(bad)


async def test_a_console_token_is_not_a_device_token():
    """El claim ``svc`` separa los dos servicios aunque compartan emisor y audiencia."""
    import jwt

    from nexus_api.config import get_settings

    s = get_settings()
    forged = jwt.encode(
        {
            "svc": "console",
            "sub": str(uuid.uuid4()),
            "pid": str(uuid.uuid4()),
            "gen": 1,
            "iss": s.console_jwt_issuer,
            "aud": s.console_jwt_audience,
        },
        s.device_token_secret,
        algorithm="HS256",
    )
    with pytest.raises(DeviceCredentialError):
        verify_device_token(forged)


async def test_the_dev_secret_does_not_work_outside_development():
    """La guarda que el resto de los `…-change-me` del repo no tiene: se conserva."""
    from nexus_api.config import get_settings

    settings = get_settings()
    original_env, original_secret = settings.environment, settings.device_token_secret
    try:
        settings.environment = "production"
        settings.device_token_secret = "dev-device-secret-change-me-min-32-chars"
        with pytest.raises(DeviceCredentialError):
            issue_device_token(device_id=uuid.uuid4(), partner_id=uuid.uuid4(), generation=1)
        with pytest.raises(DeviceCredentialError):
            verify_device_token("cualquier-cosa")
    finally:
        settings.environment, settings.device_token_secret = original_env, original_secret


async def test_a_real_secret_works_in_production():
    from nexus_api.config import get_settings

    settings = get_settings()
    original_env, original_secret = settings.environment, settings.device_token_secret
    try:
        settings.environment = "production"
        settings.device_token_secret = "un-secreto-de-verdad-largo-y-aleatorio-123456"
        device_id = uuid.uuid4()
        claims = verify_device_token(
            issue_device_token(device_id=device_id, partner_id=uuid.uuid4(), generation=1)
        )
        assert claims.device_id == device_id
    finally:
        settings.environment, settings.device_token_secret = original_env, original_secret
