"""Spec 075, requisito 10.5 (D7, 2026-11-25) — el panel crea con la forma de la consola.

El alta del panel recibe lo mismo que la de la consola (``TemplateCreateIn``)
y arma lo que va a Meta con la misma función (``to_components`` y
``parameter_format``): una regla escrita una sola vez (9.3). Antes recibía los
``components`` de Meta tal cual, u ``otp`` para autenticación, y no mandaba
``parameter_format``. Meta se simula con ``respx`` sobre Graph.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import pytest_asyncio
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.db.models import AuditLog, TenantCredentials
from nexus_api.schemas.whatsapp_authentication import authentication_components
from nexus_api.services.whatsapp_templates import invalidate_template_cache

pytestmark = pytest.mark.asyncio

_ADMIN = {"Authorization": "Bearer test-admin-token"}
WABA = "WABA_CREATE"


async def _seed_creds(db_session, tenant_id: uuid.UUID) -> None:
    creds = MetaCredentials(
        bisuat=f"EAA-{WABA}",
        waba_id=WABA,
        phone_number_id=f"PN_{WABA}",
        business_id="BIZ",
        display_phone_number="+34600000002",
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
async def tenant(console_world, db_session) -> uuid.UUID:
    tenant_id: uuid.UUID = console_world["a"]["tenant_id"]
    await _seed_creds(db_session, tenant_id)
    return tenant_id


def _url(tenant_id: uuid.UUID) -> str:
    return f"/admin/tenants/{tenant_id}/whatsapp/templates"


async def _create(client, tenant_id: uuid.UUID, body: dict[str, Any]) -> tuple[Any, Any]:
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        route = mock.post(f"/{WABA}/message_templates").respond(
            200, json={"id": "T9", "status": "PENDING", "category": body.get("category")}
        )
        r = await client.post(_url(tenant_id), headers=_ADMIN, json=body)
    return r, route


async def test_panel_builds_what_goes_to_meta_as_the_console_does(client, tenant) -> None:
    r, route = await _create(
        client,
        tenant,
        {
            "name": "pedido_listo",
            "language": "es_CL",
            "category": "UTILITY",
            "header_text": "Tu pedido",
            "body_text": "Hola {{nombre}}, tu pedido sale hoy.",
            "footer_text": "Tienda Centro",
            "buttons": [{"type": "URL", "label": "Ver pedido", "url": "https://tienda.test/p"}],
            "examples": {"nombre": "Camila"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "T9"
    sent = json.loads(route.calls.last.request.content)
    assert (sent["name"], sent["language"], sent["category"]) == (
        "pedido_listo",
        "es_CL",
        "UTILITY",
    )
    # The panel did not send it before: Meta reads {{nombre}} as positional without it.
    assert sent["parameter_format"] == "NAMED"
    assert sent["components"] == [
        {"type": "HEADER", "format": "TEXT", "text": "Tu pedido"},
        {
            "type": "BODY",
            "text": "Hola {{nombre}}, tu pedido sale hoy.",
            "example": {"body_text_named_params": [{"param_name": "nombre", "example": "Camila"}]},
        },
        {"type": "FOOTER", "text": "Tienda Centro"},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "URL", "text": "Ver pedido", "url": "https://tienda.test/p"}],
        },
    ]


async def test_panel_builds_authentication_from_the_otp_fields(client, tenant) -> None:
    r, route = await _create(
        client,
        tenant,
        {
            "name": "tecfin_codigo",
            "category": "AUTHENTICATION",
            "otp_button_text": "Copiar código",
            "otp_expiration_minutes": 5,
            "otp_security_recommendation": False,
        },
    )
    assert r.status_code == 201, r.text
    sent = json.loads(route.calls.last.request.content)
    assert sent["language"] == "es"
    assert sent["components"] == authentication_components(
        button_text="Copiar código", code_expiration_minutes=5, add_security_recommendation=False
    )
    assert "parameter_format" not in sent


@pytest.mark.parametrize(
    "body",
    [
        {"name": "aviso", "category": "UTILITY", "components": [{"type": "BODY", "text": "Hola"}]},
        {"name": "codigo", "category": "AUTHENTICATION", "otp": {"button_text": "Copiar"}},
        {"name": "aviso", "category": "UTILITY"},
    ],
    ids=["components", "otp", "sin-cuerpo"],
)
async def test_panel_refuses_its_old_shape_before_meta(client, tenant, body) -> None:
    r, route = await _create(client, tenant, body)
    assert r.status_code == 422, r.text
    assert not route.called


async def test_panel_audit_names_the_template_as_before(client, tenant, db_session) -> None:
    r, _ = await _create(
        client,
        tenant,
        {"name": "aviso_simple", "category": "MARKETING", "body_text": "Hoy hay ofertas."},
    )
    assert r.status_code == 201, r.text
    db_session.expire_all()
    rows = await db_session.execute(
        sa.select(AuditLog).where(AuditLog.action == "channel.whatsapp.template_created")
    )
    audit = next(a for a in rows.scalars() if a.target == "template:aviso_simple")
    assert audit.tenant_id == tenant
    assert audit.after_json == {
        "name": "aviso_simple",
        "language": "es",
        "category": "MARKETING",
        "meta_id": "T9",
        "status": "PENDING",
    }
    assert r.json()["audit_log_id"] == str(audit.id)
