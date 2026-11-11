"""D7 y D8: el saldo avisa antes de callar, y «activado» no miente.

El corte del 31-ago fue silencioso: los agentes dejaron de responder y no
hubo error, ni alarma, ni aviso. Estas dos piezas son lo que convierte ese
silencio en algo que alguien ve.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    ConsoleNotification,
    NotificationSeverity,
    Partner,
    PartnerAllocation,
    PartnerMembership,
    PartnerTenant,
    PartnerWallet,
    Tenant,
    TenantStatus,
)
from nexus_api.services.console_reporting import month_bounds
from nexus_api.services.email_catalog import CATALOG, EmailKind, format_month
from nexus_api.services.wallet_alerts import (
    clients_without_quota,
    evaluate_partner_wallet_alerts,
    notify_client_out_of_quota_detached,
)

pytestmark = pytest.mark.asyncio

CAP = 500_000


async def _partner(db_session, *, available: int, spent: int = 0) -> Partner:
    """Partner con el wallet en el saldo pedido, vigente este mes, y ``spent``
    gastado este mes en el libro (spec 033: el % sale del gasto, no de un tope)."""
    partner = Partner(
        id=uuid.uuid4(),
        name="Avisos Test",
        slug=f"avisos-{uuid.uuid4().hex[:6]}",
        companion_monthly_token_cap=CAP,
        console_enabled=True,
        usage_alerts_enabled=True,
        usage_alert_recipients=[],
    )
    db_session.add(partner)
    await db_session.flush()
    wallet = await db_session.get(PartnerWallet, partner.id)
    expires = datetime.now(UTC) + timedelta(days=20)
    if wallet is None:
        wallet = PartnerWallet(
            partner_id=partner.id,
            # Spec 033: a client's turn is paid from the recharged pocket.
            included_remaining=0,
            purchased_remaining=available,
            included_expires_at=expires,
        )
        db_session.add(wallet)
    else:
        wallet.included_remaining = 0
        wallet.purchased_remaining = available
        wallet.included_expires_at = expires
    await db_session.commit()
    if spent:
        from nexus_api.core.partner_context import apply_partner_to_session
        from nexus_api.db.base import get_sessionmaker
        from nexus_api.db.models.partner_wallet import UsageLedger

        async with get_sessionmaker()() as s, s.begin():
            await apply_partner_to_session(s, partner.id)
            s.add(
                UsageLedger(
                    partner_id=partner.id,
                    qty=spent,
                    bucket="purchased",
                    kind="debit",
                    idempotency_key=f"channel:alerts-{uuid.uuid4().hex}",
                )
            )
    return partner


async def _kinds(db_session, partner_id: uuid.UUID) -> dict[str, str]:
    rows = await db_session.execute(
        sa.select(ConsoleNotification.kind, ConsoleNotification.severity).where(
            ConsoleNotification.partner_id == partner_id
        )
    )
    return {r[0]: r[1] for r in rows.all()}


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Spec 051: what reaches ``send_localized`` — kind, recipients, owner and
    ``compose``, that the tests call in each language."""
    sent: list[dict[str, Any]] = []

    async def _send(kind: EmailKind, **kw: Any) -> bool:
        sent.append({"kind": kind, **kw})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_localized", _send)
    return sent


@pytest.fixture
def paused_emails_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los correos de saldo están en pausa (spec 047, criterio 44.9). Las
    pruebas de lo que dicen los encienden: es lo que saldrá el día que vuelvan."""
    monkeypatch.setattr("nexus_api.services.console_notifications.EMAIL_PAUSED_KINDS", frozenset())


def _of(sent: list[dict[str, Any]], kind: EmailKind) -> list[dict[str, Any]]:
    return [m for m in sent if m["kind"] is kind]


def _period(locale: str) -> str:
    since = month_bounds(None)[0]
    return format_month(since.year, since.month, locale)


async def test_full_wallet_says_nothing(db_session) -> None:
    partner = await _partner(db_session, available=CAP)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 0.0
    assert ev.created == []
    assert await _kinds(db_session, partner.id) == {}


async def test_eighty_percent_warns_before_the_silence(db_session) -> None:
    partner = await _partner(
        db_session, available=int(CAP * 0.2), spent=int(CAP * 0.8)
    )  # 80 % gastado
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 80.0
    assert ev.created == [80]
    kinds = await _kinds(db_session, partner.id)
    assert kinds["wallet.low"] == NotificationSeverity.WARNING.value
    assert "wallet.empty" not in kinds


async def test_empty_wallet_is_critical_not_a_warning(db_session) -> None:
    """A cero no es «te acercas al tope»: es que ya no se contesta."""
    partner = await _partner(db_session, available=0)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.percent_used == 100.0
    assert ev.created == [80, 100]
    kinds = await _kinds(db_session, partner.id)
    assert kinds["wallet.empty"] == NotificationSeverity.CRITICAL.value


async def test_alerts_do_not_repeat_within_the_month(db_session) -> None:
    partner = await _partner(db_session, available=0)
    first = await evaluate_partner_wallet_alerts(db_session, partner)
    second = await evaluate_partner_wallet_alerts(db_session, partner)
    assert first.created == [80, 100]
    assert second.created == [], "un tick repetido no puede volver a avisar"
    total = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(ConsoleNotification.partner_id == partner.id)
    )
    assert int(total) == 2


async def test_a_client_out_of_quota_is_reported_even_with_partner_balance(db_session) -> None:
    """El caso más difícil de ver desde fuera: el partner tiene saldo y un
    cliente concreto ya no contesta porque agotó su asignación.

    Spec 016 (R2.1): «sin cupo» significa lo mismo que en la puerta del canal,
    así que un tope de 0 también cuenta — la puerta no distingue «apagado a
    propósito» de «agotado», y la pantalla no puede decir otra cosa. Devuelve
    refs, que es lo que guardan los avisos.
    """
    partner = await _partner(db_session, available=CAP)

    async def _client(name: str, *, cap: int, remaining: int) -> str:
        tenant_id = uuid.uuid4()
        ref = f"{name}-{tenant_id.hex[:8]}"
        db_session.add(
            Tenant(
                id=tenant_id,
                name=name,
                slug=ref,
                status=TenantStatus.ACTIVE,
                partner_id=partner.id,
            )
        )
        await db_session.flush()
        db_session.add(
            PartnerTenant(partner_id=partner.id, external_client_ref=ref, tenant_id=tenant_id)
        )
        db_session.add(
            PartnerAllocation(
                partner_id=partner.id, tenant_id=tenant_id, cap=cap, remaining=remaining
            )
        )
        return ref

    agotado = await _client("sin-cuota", cap=50_000, remaining=0)
    apagado = await _client("apagado", cap=0, remaining=0)
    con_cupo = await _client("con-cupo", cap=50_000, remaining=10)
    await db_session.commit()

    out = await clients_without_quota(db_session, partner.id)
    assert out == sorted([agotado, apagado])
    assert con_cupo not in out


async def test_with_bags_the_safety_net_of_today_says_nothing(db_session) -> None:
    """Spec 047 (T161), recorrido UI: con la consola nueva y las bolsas, un
    cliente sin fila en ``partner_allocations`` no está «sin cupo»: su saldo es
    su bolsa, y el aviso cuando se vacía es ``client.wallet.empty``. El cron
    avisaba «se ha quedado sin saldo» de clientes con la bolsa llena."""
    partner = await _partner(db_session, available=CAP)
    partner.console_v2_enabled_at = datetime.now(UTC)
    tenant_id = uuid.uuid4()
    ref = f"con-bolsa-{tenant_id.hex[:8]}"
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Con bolsa",
            slug=ref,
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(partner_id=partner.id, external_client_ref=ref, tenant_id=tenant_id)
    )
    await db_session.commit()
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.clients_out == []
    assert "client.out_of_quota" not in await _kinds(db_session, partner.id)


async def test_activation_says_when_the_client_cannot_serve(db_session) -> None:
    """D8 — «activado» con la cuota a cero avisa, no felicita."""
    from nexus_api.services.console_notifications import record_client_activation

    partner = await _partner(db_session, available=CAP)
    tenant_id = uuid.uuid4()
    ref = f"cliente-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Recién Activado",
            slug=f"activado-{tenant_id.hex[:8]}",
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(partner_id=partner.id, external_client_ref=ref, tenant_id=tenant_id)
    )
    await db_session.commit()

    # Sin fila en partner_allocations: la puerta del canal está cerrada.
    async with db_session.begin():
        await record_client_activation(db_session, partner_id=partner.id, external_client_ref=ref)

    row = await db_session.scalar(
        sa.select(ConsoleNotification).where(
            ConsoleNotification.partner_id == partner.id,
            ConsoleNotification.kind == "client.activated",
        )
    )
    assert row is not None
    assert row.payload["can_serve"] is False
    assert row.severity == NotificationSeverity.WARNING.value


async def test_the_alert_is_actually_persisted(db_session) -> None:
    """Lo que de verdad importa: que el aviso sobreviva a la llamada.

    Probando en staging el 2026-09-08 se ensayó una variante «tolerante» que
    reutilizaba la transacción del llamador cuando ya había una. Parecía más
    robusta y era peor: no comiteaba, y las notificaciones se perdían en el
    rollback **sin un solo error**. El cron se lo habría tragado con su
    ``except`` y los avisos no habrían salido nunca.
    """
    partner = await _partner(db_session, available=0)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.created == [80, 100]

    # Leído desde una sesión nueva: si solo viviera en la transacción de la
    # llamada, aquí no habría nada.
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as fresh:
        rows = await fresh.execute(
            sa.select(ConsoleNotification.kind).where(
                ConsoleNotification.partner_id == partner.id,
                ConsoleNotification.kind.like("wallet.%"),
            )
        )
        kinds = {r[0] for r in rows.all()}
    assert kinds == {"wallet.low", "wallet.empty"}


async def test_a_caller_with_an_open_transaction_fails_loudly(db_session) -> None:
    """El contrato es «sesión limpia», igual que ``usage_alerts``.

    Se deja que reviente a propósito. La alternativa —seguir adelante sin
    comitear— es la que perdía los avisos en silencio.
    """
    partner = await _partner(db_session, available=0)
    await db_session.execute(sa.select(sa.literal(1)))
    assert db_session.in_transaction()

    with pytest.raises(Exception, match="already begun"):
        await evaluate_partner_wallet_alerts(db_session, partner)


# ── spec 051 · los correos del saldo ─────────────────────────────────────────


async def test_account_balance_emails_are_paused(db_session, mails) -> None:
    """Enmienda del 2026-11-11 (criterio 44.9): el saldo de la cuenta del
    partner avisa en la campana, al 80 % y al agotarse, y no por correo."""
    low = await _partner(db_session, available=int(CAP * 0.2), spent=int(CAP * 0.8))
    low.usage_alert_recipients = ["ops@example.com"]
    empty = await _partner(db_session, available=0)
    empty.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()

    ev = await evaluate_partner_wallet_alerts(db_session, low)
    assert ev.created == [80] and ev.emailed is False
    assert await _kinds(db_session, low.id) == {"wallet.low": "warning"}
    await db_session.commit()

    ev = await evaluate_partner_wallet_alerts(db_session, empty)
    assert ev.created == [80, 100] and ev.emailed is False
    assert (await _kinds(db_session, empty.id))["wallet.empty"] == "critical"
    assert mails == [], "ningún correo por el saldo de la cuenta"


async def test_eighty_percent_emails_wallet_low_in_each_language(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=int(CAP * 0.2), spent=int(CAP * 0.8))
    partner.usage_alert_recipients = ["ops@example.com", "dueno@example.com"]
    await db_session.commit()

    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.created == [80] and ev.emailed is True
    assert len(mails) == 1
    mail = mails[0]
    assert mail["kind"] is EmailKind.WALLET_LOW
    assert mail["to"] == ["ops@example.com", "dueno@example.com"]
    assert mail["partner_id"] == partner.id

    subject, variables = mail["compose"]("es")
    assert subject == "Has usado el 80 % del saldo de este mes"
    assert set(variables) == CATALOG[EmailKind.WALLET_LOW].variables
    assert variables["PARTNER_NAME"] == "Avisos Test"
    assert variables["PERCENT_USED"] == "80"
    assert variables["PERIOD"] == _period("es")
    assert variables["CLIENTS_OUT_NOTE"] == ""
    assert variables["BILLING_URL"].endswith("/billing")

    subject_en, variables_en = mail["compose"]("en")
    assert subject_en == "You've used 80% of this month's balance"
    assert variables_en["PERIOD"] == _period("en")
    assert variables_en["CLIENTS_OUT_NOTE"] == ""


async def test_wallet_low_says_how_many_clients_have_stopped(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=int(CAP * 0.2), spent=int(CAP * 0.8))
    partner.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()
    await _mapped_client(db_session, partner, "uno", cap=50_000, remaining=0)
    await _mapped_client(db_session, partner, "dos", cap=50_000, remaining=0)

    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert len(ev.clients_out) == 2
    [low] = _of(mails, EmailKind.WALLET_LOW)
    assert low["compose"]("es")[1]["CLIENTS_OUT_NOTE"] == (
        "Además, 2 de tus clientes ya han llegado a su propio límite y no están respondiendo, "
        "aunque todavía te quede saldo."
    )
    assert low["compose"]("en")[1]["CLIENTS_OUT_NOTE"] == (
        "Also, 2 of your clients have already reached their own limit and aren't replying, "
        "even though you still have balance left."
    )
    # Y cada cliente parado tiene su propio correo.
    assert len(_of(mails, EmailKind.CLIENT_OUT_OF_QUOTA)) == 2


async def test_wallet_low_with_one_client_stopped_says_one(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=int(CAP * 0.2), spent=int(CAP * 0.8))
    partner.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()
    await _mapped_client(db_session, partner, "solo", cap=50_000, remaining=0)

    await evaluate_partner_wallet_alerts(db_session, partner)
    [low] = _of(mails, EmailKind.WALLET_LOW)
    assert low["compose"]("es")[1]["CLIENTS_OUT_NOTE"] == (
        "Además, uno de tus clientes ya ha llegado a su propio límite y no está respondiendo, "
        "aunque todavía te quede saldo."
    )
    assert low["compose"]("en")[1]["CLIENTS_OUT_NOTE"] == (
        "Also, one of your clients has already reached its own limit and isn't replying, "
        "even though you still have balance left."
    )


async def test_an_empty_wallet_emails_only_wallet_empty(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=0)
    partner.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()

    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.created == [80, 100] and ev.emailed is True
    assert [m["kind"] for m in mails] == [EmailKind.WALLET_EMPTY]
    mail = mails[0]
    assert mail["partner_id"] == partner.id
    subject, variables = mail["compose"]("es")
    assert subject == "Tu saldo se ha agotado y tus agentes no responden"
    assert variables == {
        "PARTNER_NAME": "Avisos Test",
        "PERIOD": _period("es"),
        "BILLING_URL": variables["BILLING_URL"],
    }
    assert variables["BILLING_URL"].endswith("/billing")
    subject_en, variables_en = mail["compose"]("en")
    assert subject_en == "Your balance has run out and your agents have stopped replying"
    assert variables_en["PERIOD"] == _period("en")


async def test_no_recipients_no_wallet_email(db_session, mails) -> None:
    partner = await _partner(db_session, available=0)
    ev = await evaluate_partner_wallet_alerts(db_session, partner)
    assert ev.created == [80, 100] and ev.emailed is False
    assert mails == []


# ── spec 016 · aviso por cliente «sin cupo» (R2.2, R2.3, R2.5) ───────────────


async def _mapped_client(db_session, partner: Partner, name: str, *, cap: int, remaining: int):
    tenant_id = uuid.uuid4()
    ref = f"{name}-{tenant_id.hex[:8]}"
    db_session.add(
        Tenant(
            id=tenant_id,
            name=name,
            slug=ref,
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(partner_id=partner.id, external_client_ref=ref, tenant_id=tenant_id)
    )
    db_session.add(
        PartnerAllocation(partner_id=partner.id, tenant_id=tenant_id, cap=cap, remaining=remaining)
    )
    await db_session.commit()
    return tenant_id, ref


async def test_out_of_quota_is_said_once_until_the_client_recovers(db_session, mails) -> None:
    """Enmienda del 2026-11-03: el cron no repite cada día a un cliente sin saldo
    y, cuando lo recupera, un segundo agotamiento vuelve a avisar."""
    partner = await _partner(db_session, available=CAP)
    tenant_id, ref = await _mapped_client(db_session, partner, "vuelve", cap=50_000, remaining=0)

    async def _sent_notices() -> int:
        found = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(ConsoleNotification)
            .where(
                ConsoleNotification.partner_id == partner.id,
                ConsoleNotification.kind == "client.out_of_quota",
            )
        )
        # El evaluador, como el cron, empieza sin transacción abierta.
        await db_session.commit()
        return int(found or 0)

    async def _set_remaining(remaining: int) -> None:
        await db_session.execute(
            sa.update(PartnerAllocation)
            .where(PartnerAllocation.tenant_id == tenant_id)
            .values(remaining=remaining)
        )
        await db_session.commit()

    tomorrow = datetime.now(UTC) + timedelta(days=1)
    assert await notify_client_out_of_quota_detached(tenant_id) is not None
    assert await _sent_notices() == 1

    await evaluate_partner_wallet_alerts(db_session, partner, now=tomorrow)
    assert await _sent_notices() == 1, "al día siguiente sigue sin saldo: no se repite"

    await _set_remaining(10)
    await evaluate_partner_wallet_alerts(db_session, partner, now=tomorrow)
    assert await _sent_notices() == 1, "con saldo, nada que avisar"

    await _set_remaining(0)
    await evaluate_partner_wallet_alerts(db_session, partner, now=tomorrow)
    assert await _sent_notices() == 2, "recuperó saldo y lo volvió a agotar"
    assert ref


async def test_the_rollout_does_not_repeat_a_notice_already_sent(db_session) -> None:
    """La migración 0216 traslada el último aviso con fecha a la clave sin fecha:
    quien sigue sin saldo no recibe otro correo al desplegar."""
    path = Path(__file__).parents[2] / "alembic" / "versions" / "0216_out_of_balance_notice_once.py"
    spec = importlib.util.spec_from_file_location("migration_0216", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    partner = await _partner(db_session, available=CAP)
    key = f"partner:{partner.id}:client.out_of_quota:viejo"
    for day in ("2026-11-02", "2026-11-03"):
        db_session.add(
            ConsoleNotification(
                id=uuid.uuid4(),
                partner_id=partner.id,
                kind="client.out_of_quota",
                severity=NotificationSeverity.WARNING.value,
                external_client_ref="viejo",
                payload={},
                dedupe_key=f"{key}:{day}",
                created_at=datetime.fromisoformat(f"{day}T00:06:00+00:00"),
            )
        )
    other = f"partner:{partner.id}:wallet:80:2026-11-03"
    db_session.add(
        ConsoleNotification(
            id=uuid.uuid4(),
            partner_id=partner.id,
            kind="partner.wallet.low",
            severity=NotificationSeverity.WARNING.value,
            payload={},
            dedupe_key=other,
        )
    )
    await db_session.commit()

    await db_session.execute(sa.text(migration.CARRY_LATEST_NOTICE))
    await db_session.commit()

    keys = set(
        (
            await db_session.scalars(
                sa.select(ConsoleNotification.dedupe_key).where(
                    ConsoleNotification.partner_id == partner.id
                )
            )
        ).all()
    )
    assert keys == {key, f"{key}:2026-11-02", other}


async def test_out_of_quota_notice_is_once_per_client_and_emails(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=CAP)
    partner.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()
    tenant_id, ref = await _mapped_client(db_session, partner, "agotado", cap=50_000, remaining=0)
    sent = mails

    row = await notify_client_out_of_quota_detached(tenant_id)
    assert row is not None
    assert row.kind == "client.out_of_quota"
    assert row.severity == NotificationSeverity.WARNING.value
    assert row.external_client_ref == ref
    assert row.payload == {"external_client_ref": ref, "remaining": 0}
    assert row.dedupe_key == f"partner:{partner.id}:client.out_of_quota:{ref}"
    assert len(sent) == 1
    mail = sent[0]
    assert mail["kind"] is EmailKind.CLIENT_OUT_OF_QUOTA
    assert mail["to"] == ["ops@example.com"]
    assert mail["partner_id"] == partner.id
    assert mail["client_ref"] == ref
    # Sin nombre propio en el mapeo, el nombre del cliente es el de su tenant.
    subject, variables = mail["compose"]("es")
    assert subject == "agotado se ha quedado sin saldo"
    assert set(variables) == CATALOG[EmailKind.CLIENT_OUT_OF_QUOTA].variables
    assert variables["CLIENT_NAME"] == "agotado"
    assert variables["USAGE_URL"].endswith("/usage")
    assert mail["compose"]("en")[0] == "agotado has run out of balance"

    # Otro turno saltado, sin haber recuperado saldo, no crea otro aviso ni otro correo.
    assert await notify_client_out_of_quota_detached(tenant_id) is None
    count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(
            ConsoleNotification.partner_id == partner.id,
            ConsoleNotification.kind == "client.out_of_quota",
        )
    )
    assert count == 1
    assert len(sent) == 1


async def test_out_of_quota_email_is_paused_for_everyone(db_session, mails) -> None:
    """Enmienda del 2026-11-11 (criterio 44.9): el aviso se queda en la campana
    y no sale ningún correo, ni a la lista de alertas ni a owners y admins, ni
    por el turno saltado ni por el cron."""
    with_list = await _partner(db_session, available=CAP)
    with_list.usage_alert_recipients = ["ops@example.com"]
    without_list = await _partner(db_session, available=CAP)
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=without_list.id,
            user_id=f"user_{uuid.uuid4().hex[:8]}",
            email="duena@example.com",
            role="owner",
            status="active",
        )
    )
    await db_session.commit()
    listed, _ = await _mapped_client(db_session, with_list, "con-lista", cap=50_000, remaining=0)
    unlisted, _ = await _mapped_client(
        db_session, without_list, "sin-lista", cap=50_000, remaining=0
    )
    await _mapped_client(db_session, without_list, "por-el-cron", cap=50_000, remaining=0)

    for tenant_id in (listed, unlisted):
        row = await notify_client_out_of_quota_detached(tenant_id)
        assert row is not None and row.kind == "client.out_of_quota"
    ev = await evaluate_partner_wallet_alerts(db_session, without_list)
    assert len(ev.clients_out) == 2

    notices = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(
            ConsoleNotification.partner_id.in_([with_list.id, without_list.id]),
            ConsoleNotification.kind == "client.out_of_quota",
        )
    )
    assert notices == 3, "la campana sigue avisando"
    assert mails == [], "ningún correo por client.out_of_quota"


async def test_out_of_quota_notice_rechecks_the_gate_before_speaking(db_session) -> None:
    """R2.5: si al recomprobar el cliente ya tiene cupo, no hay aviso."""
    partner = await _partner(db_session, available=CAP)
    tenant_id, _ref = await _mapped_client(
        db_session, partner, "con-cupo", cap=50_000, remaining=10
    )
    assert await notify_client_out_of_quota_detached(tenant_id) is None
    count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(ConsoleNotification.partner_id == partner.id)
    )
    assert count == 0
    # Un tenant sin partner no tiene a quién avisar.
    assert await notify_client_out_of_quota_detached(uuid.uuid4()) is None


async def test_out_of_quota_email_uses_the_name_the_partner_gave_the_client(
    db_session, mails, paused_emails_on
) -> None:
    partner = await _partner(db_session, available=CAP)
    partner.usage_alert_recipients = ["ops@example.com"]
    await db_session.commit()
    tenant_id, ref = await _mapped_client(db_session, partner, "interno", cap=50_000, remaining=0)
    await db_session.execute(
        sa.update(PartnerTenant)
        .where(PartnerTenant.partner_id == partner.id, PartnerTenant.external_client_ref == ref)
        .values(client_name="Peluquería <Sol>")
    )
    await db_session.commit()

    assert await notify_client_out_of_quota_detached(tenant_id) is not None
    [mail] = _of(mails, EmailKind.CLIENT_OUT_OF_QUOTA)
    subject, variables = mail["compose"]("es")
    # Sin escapar: lo escapa ``send_template``, una sola vez.
    assert variables["CLIENT_NAME"] == "Peluquería <Sol>"
    assert subject == "Peluquería <Sol> se ha quedado sin saldo"
