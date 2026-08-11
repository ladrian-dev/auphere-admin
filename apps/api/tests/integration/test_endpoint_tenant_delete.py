"""``DELETE /admin/tenants/{id}`` con un tenant que tiene historia (WP-29).

``test_tenant_delete_cascade.py`` prueba la cadena tenants → conversations
→ messages con SQL directo. Esto prueba el endpoint contra las tablas que
NO estaban en esa cadena, que son las que rompían:

- ``whatsapp_opt_outs``, ``partner_tenants`` y ``broadcasts`` (vía
  ``channels`` RESTRICT) devolvían un 502 sin decir cuál bloqueaba;
- ``agent_sales``, ``usage_records`` y ``embed_audit_log`` se quedaban
  huérfanas sin dar ninguna señal.

Un tenant de verdad tiene filas en todas ellas, así que el borrado
"probado" hasta ahora era el de un tenant que nadie había usado.

Los dos casos que NO son borrado también se fijan aquí, porque son
decisiones y no efectos secundarios: una factura bloquea con 409 y la
traza de auditoría sobrevive sin datos personales.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerTenant,
    Tenant,
    TenantPlan,
    TenantStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# Todo lo que tiene que quedar a cero. Se comprueba por SQL contra la
# tabla real y no por el ORM: lo que importa es lo que queda en la base.
_MUST_BE_EMPTY = (
    "channels",
    "conversations",
    "messages",
    "whatsapp_opt_outs",
    "partner_tenants",
    "broadcasts",
    "broadcast_recipients",
    "agent_sales",
    "usage_records",
    "embed_audit_log",
    "whatsapp_template_status",
    "tenant_connectors",
    "agent_configs",
)


async def _tenant_with_history(db_session, *, partner_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Un tenant con una fila en cada tabla que antes bloqueaba o dejaba
    huérfanos. Sin esto el test sería el de un tenant recién creado, que
    es justo el caso que sí funcionaba."""
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Con historia",
            slug=f"hist-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ARCHIVED,
        )
    )
    await db_session.commit()

    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+5699{tenant_id.hex[:7]}",
        status=ChannelStatus.ACTIVE,
        config={},
    )
    db_session.add(channel)
    db_session.add(
        PartnerTenant(
            partner_id=partner_id,
            external_client_ref=f"ref-{tenant_id.hex[:8]}",
            tenant_id=tenant_id,
            client_name="Con historia",
        )
    )
    await db_session.commit()
    await db_session.refresh(channel)

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "INSERT INTO whatsapp_opt_outs (tenant_id, channel_id, recipient_phone, reason) "
                "VALUES (:t, :c, '+56911112222', 'keyword_stop')"
            ),
            {"t": str(tenant_id), "c": str(channel.id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO whatsapp_template_status "
                "(tenant_id, waba_id, template_name, language, status) "
                "VALUES (:t, 'WABA1', 'plantilla', 'es', 'approved')"
            ),
            {"t": str(tenant_id)},
        )
        # Mes en curso: su partición la crea la 0068, así que no hace
        # falta pedirla (y el rol de test no podría).
        await session.execute(
            sa.text(
                "INSERT INTO usage_records "
                "(tenant_id, occurred_at, meter, quantity, billable_qty, idempotency_key) "
                "VALUES (:t, now(), 'llm.input_tokens', 100, 100, :k)"
            ),
            {"t": str(tenant_id), "k": uuid.uuid4().hex},
        )
        await session.execute(
            sa.text(
                "INSERT INTO embed_audit_log (partner_id, tenant_id, event, payload) "
                "VALUES (:p, :t, 'broadcast.created', '{}'::jsonb)"
            ),
            {"p": str(partner_id), "t": str(tenant_id)},
        )
        # Difusión + su destinatario: el par que bloqueaba por la FK
        # RESTRICT de ``broadcasts`` hacia ``channels``.
        broadcast_id = await session.scalar(
            sa.text(
                "INSERT INTO broadcasts "
                "(tenant_id, channel_id, template_name, template_language, total) "
                "VALUES (:t, :c, 'plantilla', 'es', 1) RETURNING id"
            ),
            {"t": str(tenant_id), "c": str(channel.id)},
        )
        await session.execute(
            sa.text(
                "INSERT INTO broadcast_recipients "
                "(tenant_id, broadcast_id, phone_e164, status) "
                "VALUES (:t, :b, '+56911112222', 'queued')"
            ),
            {"t": str(tenant_id), "b": str(broadcast_id)},
        )
        # Venta atribuida: llevaba ``tenant_id`` sin ninguna FK, así que
        # sobrevivía al borrado con todas sus referencias a NULL.
        await session.execute(
            sa.text(
                "INSERT INTO agent_sales "
                "(tenant_id, wc_order_id, currency, gross_amount, commission_rate, "
                " commission_amount, wc_status) "
                "VALUES (:t, 1001, 'USD', 120.00, 0.1000, 12.00, 'completed')"
            ),
            {"t": str(tenant_id)},
        )
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor="admin:test",
                action="tenant.update",
                target=f"tenant:{tenant_id}",
                before_json={"owner_phone": "+56911112222"},
                after_json={"owner_phone": "+56933334444"},
            )
        )
    return tenant_id, channel.id


@pytest.fixture
async def partner(db_session):
    partner_id = uuid.uuid4()
    db_session.add(Partner(id=partner_id, name="Partner GDPR", slug=f"gdpr-{partner_id.hex[:6]}"))
    await db_session.commit()
    return partner_id


async def _residual(table: str, tenant_id: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as session:
        return (
            await session.scalar(
                sa.text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),
                {"t": str(tenant_id)},
            )
        ) or 0


async def test_a_tenant_with_history_deletes_without_residual_rows(
    client, admin_headers, db_session, partner
) -> None:
    tenant_id, _ = await _tenant_with_history(db_session, partner_id=partner)

    r = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert r.status_code == 204, r.text

    leftovers = {t: await _residual(t, tenant_id) for t in _MUST_BE_EMPTY}
    assert not {t: n for t, n in leftovers.items() if n}, (
        f"filas que sobrevivieron al borrado: {leftovers}"
    )


async def test_the_audit_trail_survives_without_personal_data(
    client, admin_headers, db_session, partner
) -> None:
    """Anonimizar, no borrar. Con el CASCADE anterior la traza entera se
    iba con el tenant — incluida la fila que registra este borrado, que
    es exactamente la que hay que poder enseñar después."""
    tenant_id, _ = await _tenant_with_history(db_session, partner_id=partner)

    assert (
        await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    ).status_code == 204

    sm = get_sessionmaker()
    async with sm() as session:
        rows = (
            await session.execute(
                sa.text(
                    "SELECT action, before_json, after_json FROM audit_log "
                    " WHERE target = :target ORDER BY created_at"
                ),
                {"target": f"tenant:{tenant_id}"},
            )
        ).all()

    actions = [r[0] for r in rows]
    assert "tenant.delete" in actions, "no queda constancia del borrado"
    # El teléfono del dueño estaba en el before_json de la actualización
    # previa. Ninguna fila puede llevárselo consigo.
    assert all(r[1] in (None, {}) or "owner_phone" not in r[1] for r in rows)
    assert all(r[2] in (None, {}) for r in rows)


async def test_a_tenant_with_invoices_is_refused_with_a_readable_reason(
    client, admin_headers, db_session, partner
) -> None:
    """No se destruye facturación para satisfacer un borrado. Antes esto
    salía como 502 nombrando una constraint; ahora dice qué hacer."""
    tenant_id, _ = await _tenant_with_history(db_session, partner_id=partner)
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text(
                "INSERT INTO invoices (tenant_id, period_year, period_month, status, total_cents) "
                "VALUES (:t, 2026, 8, 'issued', 1500)"
            ),
            {"t": str(tenant_id)},
        )
        await session.commit()

    r = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert r.status_code == 409
    assert "factura" in r.text

    # Y no se ha borrado nada por el camino.
    assert await _residual("channels", tenant_id) == 1


async def test_an_active_tenant_still_has_to_be_archived_first(
    client, admin_headers, db_session, partner
) -> None:
    """Control negativo del guardarraíl que ya existía: el borrado sigue
    siendo un flujo de dos pasos y esta tanda no lo ha aflojado."""
    tenant_id, _ = await _tenant_with_history(db_session, partner_id=partner)
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text("UPDATE tenants SET status = 'active' WHERE id = :t"),
            {"t": str(tenant_id)},
        )
        await session.commit()

    r = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert r.status_code == 409
    assert "archived" in r.text
