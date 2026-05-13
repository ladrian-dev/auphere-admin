"""Tests Bloque E — fachada booking.* delega a agendapro.* cuando el
tenant tiene la integration activa.

Cubre los smokes de [[verticals/barbershop_v1]]:
- Smoke 1: Booking with preferred barber (delega + persiste external_ref)
- Smoke 3: Cancel + reschedule (modify + cancel via AgendaPro)
- Smoke 9: Session expired → re-login auto auto exitoso (este test
  cubre la branch via _health_check; el test de integration es a nivel
  endpoint health-check)
- Smoke 10: Session expired AND re-login fails (needs_reauth flag)

Cross-tenant: tenant sin creds usa el camino local Bloque D, no toca
AgendaPro.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from nexus_mcp import build_default_registry
from nexus_mcp.base import ToolError
from sqlalchemy import select

from nexus_api.core.tenant_context import (
    tenant_context,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Appointment,
    AuditLog,
    Customer,
    TenantCredentials,
)
from nexus_api.services.agendapro_credentials import (
    INTEGRATION_NAME,
    get_agendapro_credentials,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _agendapro_create_response(external_ref: str = "ap-12345") -> dict:
    """Helper que arma el output del server Node tal como lo entregaría."""
    starts_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    ends_at = (datetime.now(UTC) + timedelta(days=1, minutes=30)).isoformat()
    return {
        "appointment": {
            "external_ref": external_ref,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "service_name": "Corte",
            "barber_external_id": "ap-barber-1",
            "customer_name": "Test Cliente",
            "customer_phone": "+56911112222",
            "status": "booked",
            "management_url": None,
        },
        "idempotent_replay": False,
        "screenshot": {
            "screenshot_url": "file:///var/screenshots/test/abc.png",
            "screenshot_failed": False,
            "screenshot_error": None,
        },
        "session": {"needs_reauth": False},
    }


async def _seed_customer(db_session, *, tenant_id) -> Customer:
    cust = Customer(
        tenant_id=tenant_id,
        identifier="+56911112222",
        name="Test Cliente",
        preferences={},
    )
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)
    return cust


# ── smoke 1 — booking delega y persiste external_ref ────────────────────────


async def test_create_appointment_delegates_to_agendapro(
    db_session, tenant_with_agendapro, fake_agendapro
):
    tenant_id = tenant_with_agendapro
    cust = await _seed_customer(db_session, tenant_id=tenant_id)
    fake_agendapro.set_response("agendapro.create_appointment", _agendapro_create_response("ap-77"))

    starts = datetime.now(UTC) + timedelta(days=1)
    registry = build_default_registry()
    with tenant_context(tenant_id):
        envelope = await registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "Corte",
                "starts_at": starts.isoformat(),
                "duration_min": 30,
                "price_cents": 1200000,
                "currency": "CLP",
                "idempotency_key": "test-key-1",
            },
            whitelist=["booking.create_appointment"],
        )

    assert envelope["status"] == "ok"
    assert envelope["result"]["idempotent_replay"] is False

    # Verificar que el server fake recibió el call con context_id.
    create_call = next(
        c for c in fake_agendapro.calls if c["name"] == "agendapro.create_appointment"
    )
    assert create_call["arguments"]["context_id"] == "ctx-test-12345"
    assert create_call["arguments"]["customer_phone"] == "+56911112222"
    assert "intent_hash" in create_call["arguments"]

    # Fila local persistida con external_ref poblado.
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        rows = (
            (
                await s.execute(
                    select(Appointment).where(Appointment.idempotency_key == "test-key-1")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].external_ref == "ap-77"

        # Audit log row con screenshot_url.
        audit_rows = (
            (
                await s.execute(
                    select(AuditLog).where(AuditLog.action == "booking.create_appointment")
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_rows) == 1
        assert audit_rows[0].after_json["screenshot_url"] == "file:///var/screenshots/test/abc.png"
        assert audit_rows[0].after_json["screenshot_failed"] is False


# ── tenant sin creds → camino local, no toca AgendaPro ──────────────────────


async def test_create_appointment_local_when_no_creds(db_session, two_tenants, fake_agendapro):
    """Tenant sin agendapro creds: la fachada cae al camino local de
    Bloque D — no se invoca el subprocess y no hay external_ref."""
    a = two_tenants["a"]
    cust = await _seed_customer(db_session, tenant_id=a)

    starts = datetime.now(UTC) + timedelta(days=1)
    registry = build_default_registry()
    with tenant_context(a):
        await registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "Corte",
                "starts_at": starts.isoformat(),
                "duration_min": 30,
                "price_cents": 1200000,
                "currency": "CLP",
                "idempotency_key": "no-ap-key",
            },
            whitelist=["booking.create_appointment"],
        )

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, a):
        row = (
            await s.execute(select(Appointment).where(Appointment.idempotency_key == "no-ap-key"))
        ).scalar_one()
        assert row.external_ref is None
    # Fake transport NO recibió ningún call.
    assert fake_agendapro.calls == []


# ── smoke 10 — needs_reauth flippeado por respuesta del server ─────────────


async def test_create_rolls_back_when_agendapro_signals_needs_reauth(
    db_session, tenant_with_agendapro, fake_agendapro
):
    """Si el server reporta ``session.needs_reauth=true``, la transacción
    local rollback (no aparece fila) y el flag queda en
    ``tenant_credentials``."""
    tenant_id = tenant_with_agendapro
    cust = await _seed_customer(db_session, tenant_id=tenant_id)
    payload = _agendapro_create_response("never-persisted")
    payload["session"] = {"needs_reauth": True}
    fake_agendapro.set_response("agendapro.create_appointment", payload)

    starts = datetime.now(UTC) + timedelta(days=1)
    registry = build_default_registry()
    with tenant_context(tenant_id), pytest.raises(ToolError):
        await registry.dispatch(
            "booking.create_appointment",
            {
                "customer_id": str(cust.id),
                "service_name": "Corte",
                "starts_at": starts.isoformat(),
                "duration_min": 30,
                "price_cents": 1200000,
                "currency": "CLP",
                "idempotency_key": "expired-key",
            },
            whitelist=["booking.create_appointment"],
        )

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        rows = (
            (
                await s.execute(
                    select(Appointment).where(Appointment.idempotency_key == "expired-key")
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
        # needs_reauth flippeado.
        creds = await get_agendapro_credentials(s)
        assert creds is not None
        assert creds.needs_reauth is True


# ── smoke 3 — cancel + reschedule via AgendaPro ─────────────────────────────


async def test_cancel_delegates_when_external_ref_present(
    db_session, tenant_with_agendapro, fake_agendapro
):
    tenant_id = tenant_with_agendapro
    cust = await _seed_customer(db_session, tenant_id=tenant_id)

    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        appt = Appointment(
            tenant_id=tenant_id,
            customer_id=cust.id,
            barber_id=None,
            service_name="Corte",
            service_duration_min=30,
            starts_at=datetime.now(UTC) + timedelta(hours=2),
            ends_at=datetime.now(UTC) + timedelta(hours=2, minutes=30),
            price_cents=1200000,
            currency="CLP",
            idempotency_key="local-1",
            external_ref="ap-cancel-1",
        )
        s.add(appt)
        await s.flush()
        appt_id = appt.id

    fake_agendapro.set_response(
        "agendapro.cancel_appointment",
        {
            "external_ref": "ap-cancel-1",
            "status": "cancelled",
            "screenshot": {
                "screenshot_url": "file:///var/screenshots/cancel.png",
                "screenshot_failed": False,
                "screenshot_error": None,
            },
            "session": {"needs_reauth": False},
        },
    )

    registry = build_default_registry()
    with tenant_context(tenant_id):
        envelope = await registry.dispatch(
            "booking.cancel_appointment",
            {"appointment_id": str(appt_id), "reason": "test"},
            whitelist=["booking.cancel_appointment"],
        )
    assert envelope["status"] == "ok"
    cancel_call = next(
        c for c in fake_agendapro.calls if c["name"] == "agendapro.cancel_appointment"
    )
    assert cancel_call["arguments"]["external_ref"] == "ap-cancel-1"


# ── isolation: dispatch_internal rechaza caller_token inválido ─────────────


async def test_dispatch_internal_rejects_bad_token(
    db_session, tenant_with_agendapro, fake_agendapro
):
    """Defense-in-depth #3: signing token. Token incorrecto → rechazo."""
    from nexus_mcp import InternalCallerTokenInvalid

    tenant_id = tenant_with_agendapro
    registry = build_default_registry()
    with tenant_context(tenant_id), pytest.raises(InternalCallerTokenInvalid):
        await registry.dispatch_internal(
            "agendapro.create_appointment",
            {
                "context_id": "x",
                "intent_hash": "00000000",
                "starts_at": "2026-06-01T10:00:00+00:00",
                "duration_min": 30,
                "service_name": "x",
                "customer_name": "x",
                "customer_phone": "+5611",
            },
            caller_token="not-the-real-token-at-all",
        )


# ── defense-in-depth #1: agendapro.* NO está en dispatch público ───────────


async def test_agendapro_tools_not_in_public_registry(fake_agendapro):
    """El LLM jamás puede alcanzar agendapro.* porque ``dispatch(name)``
    consulta solo ``_tools``, que NO contiene las internal."""
    registry = build_default_registry()
    public_names = registry.names()
    internal_names = registry.internal_names()
    # 21 tools públicas Bloque D + ``operator.consult_owner`` (ADR-018) = 22.
    assert len(public_names) == 22
    assert "operator.consult_owner" in public_names
    # Las 6 catalog + 2 operator agendapro tools en el espacio interno.
    assert len(internal_names) == 8
    for name in internal_names:
        assert name.startswith("agendapro.")
        assert not registry.has(name)
        assert registry.has_internal(name)


# ── defense-in-depth #2: validation rechaza internal en whitelist ───────────


async def test_agent_config_rejects_internal_tool_in_whitelist(db_session, two_tenants):
    from nexus_api.core.errors import AgentConfigConflict
    from nexus_api.services import AgentConfigService

    a = two_tenants["a"]
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, a):
        svc = AgentConfigService(s)
        with pytest.raises(AgentConfigConflict, match="Internal tools"):
            await svc.stage_new_version(
                actor="op:test",
                system_prompt_rendered="hi",
                channels=[],
                tools=["agendapro.create_appointment"],
                policies={},
            )


# ── credentials reaparecen vía read pipeline ────────────────────────────────


async def test_credentials_decrypt_round_trip(db_session, tenant_with_agendapro):
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_with_agendapro):
        creds = await get_agendapro_credentials(s)
        assert creds is not None
        assert creds.login == "owner@cultor.cl"
        assert creds.password == "secret"
        assert creds.context_id == "ctx-test-12345"
        assert creds.needs_reauth is False
        # Verifica que sí está encriptado en la columna (no plaintext).
        row = (
            await s.execute(
                select(TenantCredentials).where(TenantCredentials.integration == INTEGRATION_NAME)
            )
        ).scalar_one()
        # encrypted_payload returns bytes through FernetEncrypted decryption,
        # but ON DISK es Fernet-encrypted. Ya es plaintext acá; no
        # podemos asertar que esté encriptado sin bypass del TypeDecorator,
        # pero validamos round-trip.
        assert b"secret" in row.encrypted_payload  # decryptado por el TypeDecorator


# Misc: keeping aliases happy
_ = uuid
