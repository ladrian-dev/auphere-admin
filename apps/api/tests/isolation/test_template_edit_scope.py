"""Spec 075 — garantía 1: una edición de plantilla no sale de la cuenta de
WhatsApp del cliente de la sesión.

Dos clientes, A y B, cada uno con su cuenta de WhatsApp (``WABA_A`` y
``WABA_B``). La plantilla ``solo_de_b`` existe únicamente en la cuenta de B.
Con la sesión de A —en la consola y en el panel— nombrarla tiene que dar
404, sin llamar a Meta para editar y sin tocar el espejo de la cuenta de B.

**Barre, no enumera** (constitución §I): recorre ``app.routes`` y prueba
toda ruta ``PUT`` que acabe en ``/templates/{name}/{language}``. Una ruta de
edición nueva que se añada mañana entra sola en esta prueba.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
import sqlalchemy as sa
from fastapi.routing import APIRoute
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.db.models import TenantCredentials
from nexus_api.db.models.conversation import WhatsAppTemplateStatus
from nexus_api.main import app
from nexus_api.services import operator_identity
from nexus_api.services import whatsapp_template_edit as rules
from nexus_api.services.whatsapp_templates import TemplateOut, invalidate_template_cache

pytestmark = pytest.mark.asyncio

_ADMIN = {"Authorization": "Bearer test-admin-token"}
_SUFFIX = "/templates/{name}/{language}"


def _edit_routes() -> list[str]:
    return sorted(
        r.path
        for r in app.routes
        if isinstance(r, APIRoute) and "PUT" in r.methods and r.path.endswith(_SUFFIX)
    )


def _raw(tpl_id: str) -> dict[str, Any]:
    return {
        "id": tpl_id,
        "name": "solo_de_b",
        "language": "es",
        "status": "REJECTED",
        "category": "UTILITY",
        "components": [{"type": "BODY", "text": "Hola, te esperamos."}],
    }


def _version(raw: dict[str, Any]) -> str:
    return rules.template_version(TemplateOut(**{k: raw[k] for k in raw}))


async def _seed_creds(db_session, tenant_id: uuid.UUID, waba_id: str) -> None:
    creds = MetaCredentials(
        bisuat=f"EAA-{waba_id}",
        waba_id=waba_id,
        phone_number_id=f"PN_{waba_id}",
        business_id="BIZ",
        display_phone_number="+34600000001",
        verify_token="v" * 32,
    )
    async with db_session.begin():
        await db_session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            TenantCredentials(
                tenant_id=tenant_id,
                integration="meta_whatsapp",
                encrypted_payload=creds.to_payload(),
                needs_reauth=False,
            )
        )


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_template_cache()
    yield
    invalidate_template_cache()


@pytest_asyncio.fixture
async def worlds(console_world, db_session) -> dict[str, Any]:
    a, b = console_world["a"], console_world["b"]
    await _seed_creds(db_session, a["tenant_id"], "WABA_A")
    await _seed_creds(db_session, b["tenant_id"], "WABA_B")
    db_session.add(
        WhatsAppTemplateStatus(
            waba_id="WABA_B",
            template_name="solo_de_b",
            language="es",
            status="REJECTED",
            reason="INVALID_FORMAT",
            tenant_id=b["tenant_id"],
            last_event_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    await db_session.commit()
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session,
            email=f"ops-iso-075-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {"a": a, "b": b, "operator_id": str(account.id)}


def _request_for(path: str, worlds: dict[str, Any]) -> tuple[str, dict[str, str]]:
    a = worlds["a"]
    url = (
        path.replace("{ref}", a["ref"])
        .replace("{tenant_id}", str(a["tenant_id"]))
        .replace("{name}", "solo_de_b")
        .replace("{language}", "es")
    )
    if path.startswith("/console/"):
        return url, a["headers"]()
    return url, {**_ADMIN, "X-Operator-Id": worlds["operator_id"]}


async def test_the_sweep_finds_the_console_and_panel_routes() -> None:
    """Si la prueba no encuentra las dos rutas, no prueba nada."""
    routes = _edit_routes()
    assert any(p.startswith("/console/") for p in routes), routes
    assert any(p.startswith("/admin/") for p in routes), routes


@pytest.mark.parametrize("path", _edit_routes())
async def test_a_session_of_a_cannot_edit_a_template_of_b(
    client, worlds, db_session, path: str
) -> None:
    url, headers = _request_for(path, worlds)
    raw_b = _raw("B-1")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get("/WABA_A/message_templates").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        mock.get("/WABA_B/message_templates").mock(
            return_value=httpx.Response(200, json={"data": [raw_b]})
        )
        edits = mock.post(url__regex=r"^/[^/]+$")
        edits.respond(200, json={"success": True})
        r = await client.put(
            url,
            headers=headers,
            json={"version": _version(raw_b), "body_text": "Hola, ya no te esperamos."},
        )
        assert r.status_code == 404, (path, r.text)
        assert r.json()["detail"]["code"] == "template_not_found"
        assert edits.call_count == 0
        assert not any("/WABA_B/" in str(call.request.url) for call in mock.calls), (
            "la sesión de A habló con la cuenta de B"
        )

    db_session.expire_all()
    row = (
        await db_session.execute(
            sa.select(WhatsAppTemplateStatus).where(
                WhatsAppTemplateStatus.waba_id == "WABA_B",
                WhatsAppTemplateStatus.template_name == "solo_de_b",
            )
        )
    ).scalar_one()
    assert row.status == "REJECTED" and row.reason == "INVALID_FORMAT"


@pytest.mark.parametrize("path", _edit_routes())
async def test_the_body_cannot_name_a_meta_account_or_template(client, worlds, path: str) -> None:
    url, headers = _request_for(path, worlds)
    r = await client.put(
        url,
        headers=headers,
        json={
            "version": "0" * 16,
            "body_text": "Hola",
            "template_id": "B-1",
            "waba_id": "WABA_B",
        },
    )
    assert r.status_code == 422, (path, r.text)
