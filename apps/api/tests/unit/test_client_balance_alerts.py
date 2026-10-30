"""Spec 030 (R15.1 a R15.3, T034/T036) — el cliente se entera de su saldo.

La campana del cliente avisa con el **mismo criterio que su Panel**
(``lite_home.balance_notice``): si su tope se agotó, ``client.balance_out``;
si al ritmo de los últimos 7 días no llega a fin de mes, ``client.balance_low``
con los días que le quedan. Lo que fija este archivo:

- solo a clientes con la consola lite encendida; sin acceso, nadie a quien
  avisar dentro del cliente (el partner sigue recibiendo lo suyo);
- ``audience = 'client'`` y correo a las personas activas del cliente — nunca
  a miembros del partner;
- una vez: el agotado, por cliente y día; el «no llega», por cliente y mes;
- sin tope asignado o con saldo de sobra, nada.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ConsoleNotification, PartnerAllocation
from nexus_api.services import wallet_alerts
from nexus_api.services.email_catalog import EmailKind
from nexus_api.services.lite_home import LiteBalance, balance_notice
from tests.conftest import add_client_member, make_client_access, spend_from_wallet

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Lo que llega a ``send_template`` (spec 051), con el destinatario como
    lista para poder buscar en él."""
    sent: list[dict[str, Any]] = []

    async def _send(kind: EmailKind, **kw: Any) -> bool:
        to = kw.pop("to")
        sent.append({"kind": kind, "to": [to] if isinstance(to, str) else list(to), **kw})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _send)
    return sent


def _client_mail(mails: list[dict[str, Any]], kind: EmailKind) -> dict[str, Any]:
    [mail] = [m for m in mails if m["kind"] == kind]
    return mail


async def _rows(db_session, partner_id: uuid.UUID, kind: str) -> list[ConsoleNotification]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == partner_id, ConsoleNotification.kind == kind
                )
            )
        ).scalars()
    )


async def _allocation(db_session, tenant_id: uuid.UUID, *, cap: int, remaining: int) -> None:
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == tenant_id)
        .values(cap=cap, remaining=remaining)
    )
    await db_session.commit()


async def _fund(db_session, partner_id: uuid.UUID, credits: int) -> None:
    await db_session.execute(
        sa.text("UPDATE partner_wallets SET purchased_remaining = :c WHERE partner_id = :p"),
        {"c": credits, "p": partner_id},
    )
    await db_session.commit()


async def test_the_bell_and_the_panel_share_one_rule() -> None:
    days_to_end = 10.0
    assert balance_notice(LiteBalance(False, None, None, None), days_to_end) is None
    assert balance_notice(LiteBalance(True, 0, 5000, 0.0), days_to_end) == "balance_out"
    assert balance_notice(LiteBalance(True, 100, 5000, 2.0), days_to_end) == "balance_low"
    assert balance_notice(LiteBalance(True, 4000, 5000, 30.0), days_to_end) is None
    assert balance_notice(LiteBalance(True, 4000, 5000, None), days_to_end) is None


async def test_out_of_quota_tells_the_client_too(db_session, console_world, mails) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    await _allocation(db_session, w["tenant_id"], cap=5000, remaining=0)

    await wallet_alerts.notify_client_out_of_quota_detached(w["tenant_id"])

    assert len(await _rows(db_session, w["partner_id"], "client.out_of_quota")) == 1
    (row,) = await _rows(db_session, w["partner_id"], "client.balance_out")
    assert row.audience == "client"
    assert row.external_client_ref == w["ref"]
    member_email = (
        await db_session.execute(
            sa.text("SELECT email FROM client_memberships WHERE id = :id"),
            {"id": member["membership_id"]},
        )
    ).scalar_one()
    to_client = [m for m in mails if member_email in m["to"]]
    assert len(to_client) == 1
    assert all(member_email not in m["to"] or len(m["to"]) == 1 for m in mails)
    # Spec 051 (catálogo §16): su plantilla, con el nombre del cliente y un
    # enlace absoluto a su consola; con el negocio (garantía 6).
    mail = _client_mail(mails, EmailKind.CLIENT_BALANCE_OUT)
    assert mail is to_client[0]
    assert mail["subject"] == "Tu saldo se ha agotado y tu agente ha dejado de responder"
    assert mail["variables"]["CLIENT_NAME"] == "Client A One"
    assert mail["variables"]["CONSOLE_URL"].startswith("http")
    assert mail["variables"]["CONSOLE_URL"].endswith("/")
    assert mail["client_ref"] == w["ref"] and mail["tenant_id"] == w["tenant_id"]

    # Una vez al día.
    await wallet_alerts.notify_client_out_of_quota_detached(w["tenant_id"])
    assert len(await _rows(db_session, w["partner_id"], "client.balance_out")) == 1


async def test_without_lite_access_only_the_partner_hears(db_session, console_world, mails) -> None:
    w = console_world["a"]
    await _allocation(db_session, w["tenant_id"], cap=5000, remaining=0)
    await wallet_alerts.notify_client_out_of_quota_detached(w["tenant_id"])
    assert len(await _rows(db_session, w["partner_id"], "client.out_of_quota")) == 1
    assert await _rows(db_session, w["partner_id"], "client.balance_out") == []
    # Spec 051 (catálogo §18): sin lista de alertas, los dueños lo leen en el
    # aviso genérico, con su texto y no con las claves del aviso.
    assert not [m for m in mails if m["kind"] == EmailKind.CLIENT_BALANCE_OUT]
    mail = _client_mail(mails, EmailKind.PARTNER_NOTICE)
    assert mail["subject"] == mail["variables"]["HEADING"] == "Client A One se ha quedado sin saldo"
    assert mail["variables"]["ACTION_LABEL"] == "Asignar saldo"
    assert mail["variables"]["ACTION_URL"].endswith("/usage")
    assert "client.out_of_quota" not in mail["subject"], "se acabó el volcado de claves"
    assert mail["partner_id"] == w["partner_id"] and mail["client_ref"] == w["ref"]


async def test_a_balance_that_will_not_last_is_said_once_a_month(
    db_session, console_world, mails, month_end_far
) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await add_client_member(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await _fund(db_session, w["partner_id"], 5_000_000)
    # 70 000 en la semana (10 000/día) y le quedan 20 000: dos días.
    await _allocation(db_session, w["tenant_id"], cap=500_000, remaining=90_000)
    await spend_from_wallet(
        partner_id=w["partner_id"], qty=70_000, lane="channel", tenant_id=w["tenant_id"]
    )
    await db_session.commit()

    created = await wallet_alerts.evaluate_client_balance_alerts(db_session, w["partner_id"])
    assert created == [w["ref"]]
    (row,) = await _rows(db_session, w["partner_id"], "client.balance_low")
    assert row.audience == "client"
    assert row.payload["days_left"] == 2
    mail = _client_mail(mails, EmailKind.CLIENT_BALANCE_LOW)
    assert mail["subject"] == "Tu saldo no llegará a fin de mes"
    assert set(mail["variables"]) == {"CLIENT_NAME", "CONSOLE_URL"}
    assert mail["variables"]["CLIENT_NAME"] == "Client A One"
    await db_session.commit()  # the evaluator, like the cron, starts without a transaction

    again = await wallet_alerts.evaluate_client_balance_alerts(db_session, w["partner_id"])
    assert again == []
    assert len(await _rows(db_session, w["partner_id"], "client.balance_low")) == 1


async def test_plenty_or_no_cap_says_nothing(db_session, console_world, mails) -> None:
    w, b = console_world["a"], console_world["b"]
    for world in (w, b):
        await make_client_access(
            db_session, partner_id=world["partner_id"], tenant_id=world["tenant_id"]
        )
    await _allocation(db_session, w["tenant_id"], cap=500_000, remaining=500_000)
    await db_session.execute(
        sa.delete(PartnerAllocation).where(PartnerAllocation.tenant_id == b["tenant_id"])
    )
    await db_session.commit()
    for world in (w, b):
        assert (
            await wallet_alerts.evaluate_client_balance_alerts(db_session, world["partner_id"])
            == []
        )
    assert await _rows(db_session, w["partner_id"], "client.balance_low") == []
    assert await _rows(db_session, b["partner_id"], "client.balance_low") == []
