"""Spec 077 · R4 — códigos de un solo uso por ``POST /v1/messages/template``.

Una plantilla de autenticación de Meta tiene el texto fijo (``{{1}}`` o sin
texto) y un botón de copiar código, y el código va dos veces: en el cuerpo y en
el botón. Esta suite fija el contrato del campo ``code`` y que los envíos con
variables con nombre (New Air) siguen exactamente igual.

La resolución de plantillas se simula (Meta no se alcanza en pruebas); lo demás
es real: la clave, la RLS, la fila ``pending`` y la idempotencia.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
import structlog

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    Partner,
    PartnerApiKey,
    Tenant,
    TenantPlan,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = pytest.mark.asyncio

_CODE = "482913"

#: La forma que documenta Meta al leer una plantilla de autenticación: cuerpo
#: fijo con ``{{1}}``, pie con la caducidad y el botón convertido en ``URL``.
_OTP_WITH_TEXT = TemplateOut(
    id="otp1",
    name="tecfin_codigo",
    language="es",
    category="AUTHENTICATION",
    status="APPROVED",
    components=[
        {
            "type": "BODY",
            "text": "*{{1}}* es tu código de verificación. Por tu seguridad, no lo compartas.",
            "add_security_recommendation": True,
        },
        {
            "type": "FOOTER",
            "text": "Este código caduca en 10 minutos.",
            "code_expiration_minutes": 10,
        },
        {
            "type": "BUTTONS",
            "buttons": [
                {
                    "type": "URL",
                    "text": "Copiar código",
                    "url": "https://www.whatsapp.com/otp/code/?otp_type=COPY_CODE&code=otp{{1}}",
                }
            ],
        },
    ],
)
#: La otra forma posible: cuerpo sin texto y el botón todavía como ``OTP``.
_OTP_NO_TEXT = TemplateOut(
    id="otp2",
    name="tecfin_codigo_corto",
    language="es",
    category="AUTHENTICATION",
    status="APPROVED",
    components=[
        {"type": "BODY", "add_security_recommendation": True},
        {
            "type": "BUTTONS",
            "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copiar código"}],
        },
    ],
)
#: Sin botón: solo el cuerpo lleva el código.
_OTP_NO_BUTTON = TemplateOut(
    id="otp3",
    name="tecfin_codigo_sin_boton",
    language="es",
    category="AUTHENTICATION",
    status="APPROVED",
    components=[{"type": "BODY", "text": "*{{1}}* es tu código de verificación."}],
)
_NAMED = TemplateOut(
    id="t1",
    name="newair_instalacion_recordatorio",
    language="es",
    category="MARKETING",
    status="APPROVED",
    components=[
        {"type": "BODY", "text": "Hola {{nombre}}, el día {{fecha}} instalamos tu equipo."}
    ],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_OTP_WITH_TEXT, _OTP_NO_TEXT, _OTP_NO_BUTTON, _NAMED], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


async def _set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))


@pytest_asyncio.fixture
async def world(db_session):
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(id=tenant_id, name="Tecfin", slug=f"tf-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.flush()
    db_session.add(
        Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+5622{tenant_id.int % 10_000_000:07d}",
            status=ChannelStatus.ACTIVE,
        )
    )
    db_session.add(Partner(id=partner_id, name="Direct", slug=f"dd-{partner_id.hex[:6]}"))
    db_session.add(
        PartnerApiKey(
            partner_id=partner_id,
            tenant_id=tenant_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    return {
        "tenant_id": tenant_id,
        "headers": {"Authorization": f"Bearer {generated.plaintext}"},
    }


def _otp(**overrides):
    payload = {
        "to": "+56912345678",
        "template_name": "tecfin_codigo",
        "language": "es",
        "code": _CODE,
    }
    payload.update(overrides)
    return payload


async def _message(db_session, tenant_id: uuid.UUID, message_id: str) -> Message:
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, tenant_id)
        row: Message = (
            await db_session.execute(sa.select(Message).where(Message.id == uuid.UUID(message_id)))
        ).scalar_one()
        return row


@pytest.mark.parametrize(
    ("template", "has_button"),
    [("tecfin_codigo", True), ("tecfin_codigo_corto", True), ("tecfin_codigo_sin_boton", False)],
)
async def test_code_is_queued_in_body_and_button(
    client, world, db_session, template, has_button
) -> None:
    """R4.1: 202 y el código en el cuerpo y, si hay botón, en el botón."""
    resp = await client.post(
        "/v1/messages/template", json=_otp(template_name=template), headers=world["headers"]
    )
    assert resp.status_code == 202, resp.text
    message = await _message(db_session, world["tenant_id"], resp.json()["message_id"])
    payload = message.template_payload
    assert payload["category"] == "AUTHENTICATION"
    assert payload["otp"] is True
    assert payload["params"]["body"] == [_CODE]
    if has_button:
        assert payload["params"]["buttons"] == [
            {"sub_type": "url", "parameters": [{"type": "text", "text": _CODE}]}
        ]
    else:
        assert "buttons" not in payload["params"]


async def test_authentication_without_code_is_422(client, world) -> None:
    """R4.2."""
    body = _otp()
    del body["code"]
    resp = await client.post("/v1/messages/template", json=body, headers=world["headers"])
    assert resp.status_code == 422
    assert "code_required" in resp.text


async def test_authentication_with_variables_is_422(client, world) -> None:
    """R4.2: el código no va en variables."""
    resp = await client.post(
        "/v1/messages/template",
        json=_otp(variables={"1": _CODE}),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "variables_not_allowed" in resp.text


async def test_code_on_a_named_template_is_422(client, world) -> None:
    """R4.3."""
    resp = await client.post(
        "/v1/messages/template",
        json={
            "to": "+56912345678",
            "template_name": "newair_instalacion_recordatorio",
            "variables": {"nombre": "Juan", "fecha": "15/01/2026"},
            "code": _CODE,
        },
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "code_not_allowed" in resp.text


@pytest.mark.parametrize("code", ["", "1234567890123456", "12 34", "https://x.co", "www.a.b"])
async def test_invalid_code_is_422(client, world, code) -> None:
    """R4.4: vacío, más de 15, con espacios o con un enlace."""
    resp = await client.post(
        "/v1/messages/template", json=_otp(code=code), headers=world["headers"]
    )
    assert resp.status_code == 422, resp.text
    assert "invalid_code" in resp.text or "code" in resp.text


async def test_named_template_send_is_unchanged(client, world, db_session) -> None:
    """R4.5 y R11.1: New Air sigue exactamente igual."""
    resp = await client.post(
        "/v1/messages/template",
        json={
            "to": "+56912345678",
            "template_name": "newair_instalacion_recordatorio",
            "language": "es",
            "variables": {"nombre": "Juan Pérez", "fecha": "15/01/2026"},
        },
        headers=world["headers"],
    )
    assert resp.status_code == 202, resp.text
    message = await _message(db_session, world["tenant_id"], resp.json()["message_id"])
    assert message.template_payload == {
        "name": "newair_instalacion_recordatorio",
        "language": "es",
        "params": {"body": {"nombre": "Juan Pérez", "fecha": "15/01/2026"}},
        "category": "MARKETING",
    }


async def test_replay_with_same_key_is_duplicate(client, world) -> None:
    """R4.7: la misma clave no manda dos códigos."""
    first = await client.post(
        "/v1/messages/template", json=_otp(idempotency_key="login-1"), headers=world["headers"]
    )
    second = await client.post(
        "/v1/messages/template", json=_otp(idempotency_key="login-1"), headers=world["headers"]
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["duplicate"] is True
    assert second.json()["message_id"] == first.json()["message_id"]


async def test_code_never_reaches_the_log(client, world) -> None:
    """R4.6: ningún log lleva el código (y la captura ve los eventos de verdad)."""
    with structlog.testing.capture_logs() as logs:
        resp = await client.post(
            "/v1/messages/template", json=_otp(code="Q7X9Z2"), headers=world["headers"]
        )
    assert resp.status_code == 202, resp.text
    events = [entry["event"] for entry in logs]
    assert "direct_message.queued" in events
    assert "Q7X9Z2" not in repr(logs)


async def test_authentication_template_in_a_broadcast_is_refused(db_session) -> None:
    """Caso límite: una difusión no manda plantillas de autenticación."""
    from fastapi import HTTPException

    from nexus_api.services.broadcasts import resolve_template

    with pytest.raises(HTTPException) as exc:
        await resolve_template(db_session, name="tecfin_codigo", language="es")
    assert exc.value.status_code == 422
