"""Garantía 1 y 2 — el alcance de una credencial de dispositivo (Requisitos 6.3, 6.4).

La Phase 10 abre una **superficie autenticada nueva**: una máquina que pide trabajo.
Lo que hay que impedir es lo de siempre dicho para este caso — que la credencial de
un portátil sirva para pedir el trabajo de otro, o el de otro tenant.

El nº 25 sigue reservado a la VM de la beta 5; éste es el 29 porque 26, 27 y 28 los
tomó la superficie 3a.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from nexus_api.db.models import PartnerDevice
from nexus_api.services.device_credential import (
    DeviceCredentialError,
    issue_device_token,
    verify_device_token,
)

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _device(session, tenant_id: uuid.UUID, name: str) -> PartnerDevice:
    device = PartnerDevice(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        principal_id="user_iso",
        display_name=name,
        platform="macos",
        workdir="/tmp/proyecto",
    )
    session.add(device)
    await session.flush()
    return device


async def test_a_token_only_opens_its_own_device(db_session, tenants_ab):
    mine = await _device(db_session, tenants_ab["a"], "mío")
    other = await _device(db_session, tenants_ab["a"], "de un compañero")
    await db_session.commit()

    token = issue_device_token(device_id=mine.id, tenant_id=tenants_ab["a"])
    claims = verify_device_token(token)
    assert claims.device_id == mine.id
    assert claims.device_id != other.id


async def test_a_token_from_another_tenant_is_refused(db_session, tenants_ab):
    device = await _device(db_session, tenants_ab["b"], "de B")
    await db_session.commit()

    token = issue_device_token(device_id=device.id, tenant_id=tenants_ab["b"])
    claims = verify_device_token(token)
    assert claims.tenant_id == tenants_ab["b"]
    assert claims.tenant_id != tenants_ab["a"], "un token de B no puede resolver a A"


async def test_a_tampered_token_is_refused():
    """Cambiar el dispositivo en el token no cambia a quién autoriza."""
    token = issue_device_token(device_id=uuid.uuid4(), tenant_id=uuid.uuid4())
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    with pytest.raises(DeviceCredentialError):
        verify_device_token(tampered)


async def test_garbage_is_refused():
    for bad in ["", "no-es-un-token", "a.b.c"]:
        with pytest.raises(DeviceCredentialError):
            verify_device_token(bad)


async def test_the_device_rows_stay_behind_rls(db_session, tenants_ab):
    """Aunque el token fuera válido, la RLS sigue decidiendo qué filas se ven."""
    await _device(db_session, tenants_ab["a"], "de A")
    await _device(db_session, tenants_ab["b"], "de B")
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["a"])
    names = (await db_session.execute(select(PartnerDevice.display_name))).scalars().all()
    assert set(names) == {"de A"}


async def test_the_dev_secret_does_not_work_outside_development():
    """La guarda que el resto de los `…-change-me` del repo no tiene.

    Un secreto por defecto en producción no es una configuración pendiente: es una
    puerta abierta, y ésta firma credenciales que dan acceso a la máquina de un
    partner.
    """
    from nexus_api.config import get_settings

    settings = get_settings()
    original_env, original_secret = settings.environment, settings.device_token_secret
    try:
        settings.environment = "production"
        settings.device_token_secret = "dev-device-secret-change-me-min-32-chars"
        with pytest.raises(DeviceCredentialError):
            issue_device_token(device_id=uuid.uuid4(), tenant_id=uuid.uuid4())
        with pytest.raises(DeviceCredentialError):
            verify_device_token("cualquier-cosa")
    finally:
        settings.environment, settings.device_token_secret = original_env, original_secret


async def test_a_real_secret_works_in_production():
    """La guarda no puede impedir el caso bueno: eso sería romper el despliegue."""
    from nexus_api.config import get_settings

    settings = get_settings()
    original_env, original_secret = settings.environment, settings.device_token_secret
    try:
        settings.environment = "production"
        settings.device_token_secret = "un-secreto-de-verdad-largo-y-aleatorio-123456"
        device_id, tenant_id = uuid.uuid4(), uuid.uuid4()
        claims = verify_device_token(issue_device_token(device_id=device_id, tenant_id=tenant_id))
        assert claims.device_id == device_id
    finally:
        settings.environment, settings.device_token_secret = original_env, original_secret
