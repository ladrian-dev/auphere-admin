"""Bug ``acceso-500-en-produccion`` — «Acceso» del admin con la guarda de
aislamiento en modo de corte, como en producción.

En producción (``is_prod``) ``core/isolation_enforcer.py`` **corta** toda
consulta a una tabla de cliente (``channels``, ``conversations``…) que no
declare ``app.tenant_id``; en el resto de entornos solo avisa. Las rutas de
``/admin/tenants/{id}/client-access`` usan la sesión de plataforma y contaban
los canales del cliente sin declararlo: en producción, 500 al abrir la pestaña
(2026-10-12, Flor y Encanto). Ni las pruebas ni staging lo veían, porque allí
la guarda no corta.

Aquí la guarda corta (``NEXUS_ISOLATION_ENFORCER_RAISE_IN_DEV=true``) y se
recorre todo lo que la pestaña hace: leer, encender con Bandeja, quitar la
Bandeja (libera las conversaciones escaladas), invitar, reenviar y revocar.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from nexus_api.config import get_settings
from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio


@pytest.fixture
def strict_isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("NEXUS_ISOLATION_ENFORCER_RAISE_IN_DEV", "true")
    get_settings.cache_clear()
    assert get_settings().isolation_enforcer_raise_in_dev is True
    yield
    get_settings.cache_clear()


async def test_the_access_tab_works_when_the_guard_blocks(
    client, db_session, console_world, admin_headers, strict_isolation
) -> None:
    w = console_world["a"]
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
        db_session.add(
            Channel(
                id=uuid.uuid4(),
                tenant_id=w["tenant_id"],
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
                config={"phone_number_id": "PN"},
                status=ChannelStatus.ACTIVE,
            )
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    base = f"/admin/tenants/{w['tenant_id']}"

    read = await client.get(f"{base}/client-access", headers=headers)
    assert read.status_code == 200, read.text
    assert read.json()["whatsapp_connected"] is True

    on = await client.put(
        f"{base}/client-access",
        headers=headers,
        json={"enabled": True, "modules": ["panel", "inbox", "usage"]},
    )
    assert on.status_code == 200, on.text

    invited = await client.post(
        f"{base}/client-members",
        headers=headers,
        json={"email": f"persona-{uuid.uuid4().hex[:6]}@cliente.test", "name": "Persona"},
    )
    assert invited.status_code in (200, 201), invited.text
    member = invited.json()["id"]

    resent = await client.post(f"{base}/client-members/{member}/resend", headers=headers, json={})
    assert resent.status_code in (200, 201), resent.text

    # Taking the Inbox away releases the client's escalated conversations.
    off_inbox = await client.put(
        f"{base}/client-access",
        headers=headers,
        json={"enabled": True, "modules": ["panel", "usage"]},
    )
    assert off_inbox.status_code == 200, off_inbox.text

    revoked = await client.post(f"{base}/client-members/{member}/revoke", headers=headers, json={})
    assert revoked.status_code in (200, 204), revoked.text
