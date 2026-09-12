"""Spec 004 · puerta de aislamiento, garantía 6 (log + trace tagging).

Cada renovación y cada débito dejan rastro con el partner identificado, y
**ningún** registro lleva contenido de conversación.

La segunda mitad es la que importa más y la que se olvida: el camino del dinero
pasa cerca del camino del contenido —el mismo turno que se cobra es el que lleva
lo que escribió un cliente final— y basta con añadir un campo «para
diagnosticar» a un log para sacar texto de cliente de su tenant.
"""

from __future__ import annotations

import pytest
import structlog
import structlog.testing

from tests.conftest import make_partner_with_wallet, spend_from_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

#: Lo que un log del camino del dinero nunca puede llevar.
FORBIDDEN_KEYS = ("text", "body", "content", "message", "prompt", "answer", "transcript")


@pytest.fixture
def captured():
    """``structlog.testing.capture_logs`` y no una reconfiguración a mano.

    Los módulos crean su logger con ``structlog.get_logger(__name__)`` en la
    importación, y un *bound logger* ya creado se queda con la configuración
    que había. Cambiar los procesadores por debajo funciona cuando el fichero
    corre solo y deja de funcionar dentro de la suite — que es exactamente el
    tipo de test inestable que enseña a ignorar los rojos.
    """
    with structlog.testing.capture_logs() as events:
        yield events


async def test_a_renewal_names_the_partner(db_session, captured) -> None:
    from datetime import UTC, datetime, timedelta

    from nexus_api.metering.wallet import renew_included_if_expired

    past = datetime.now(UTC) - timedelta(days=1)
    world = await make_partner_with_wallet(db_session, included=0, expires_at=past)

    await renew_included_if_expired(db_session, partner_id=world["partner_id"])

    renewals = [e for e in captured if e.get("event") == "wallet.included_renewed"]
    assert renewals, "una renovación sin rastro no se puede auditar"
    assert renewals[0]["partner_id"] == str(world["partner_id"])


async def test_no_money_log_carries_conversation_content(db_session, captured) -> None:
    world = await make_partner_with_wallet(db_session, included=10_000)
    await spend_from_wallet(partner_id=world["partner_id"], qty=1_000, lane="companion")

    for event in captured:
        name = str(event.get("event") or "")
        if not name.startswith(("wallet.", "metering.")):
            continue
        for key in FORBIDDEN_KEYS:
            assert key not in event, (
                f"el registro «{name}» lleva la clave «{key}». El camino del dinero "
                "pasa junto al del contenido, y un campo añadido para diagnosticar "
                "es como el texto de un cliente final sale de su tenant (§III)"
            )


async def test_a_debit_leaves_a_ledger_entry_with_its_partner(db_session) -> None:
    """El rastro durable no es el log, es el asiento."""
    import sqlalchemy as sa

    world = await make_partner_with_wallet(db_session, included=10_000)
    pid = world["partner_id"]
    await spend_from_wallet(partner_id=pid, qty=2_500, lane="companion")

    rows = (
        await db_session.execute(
            sa.text("SELECT partner_id, qty, bucket FROM usage_ledger WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    ).all()
    assert rows, "un débito sin asiento es dinero que se movió sin rastro"
    assert sum(int(r[1]) for r in rows) == 2_500
