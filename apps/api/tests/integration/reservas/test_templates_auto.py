"""Spec 043, requisito 15 — las seis plantillas de Reservas se crean solas.

Un cliente con Reservas y un número de WhatsApp de Meta recibe en su WABA las
plantillas del contrato que le faltan (es, UTILITY, variables con nombre y una
muestra por variable). Lo que ya está en la WABA con ese nombre en un idioma
``es*``, en el estado que sea, no se vuelve a pedir; lo que Meta rechazó o pausó
no se recrea ni se borra. Cada petición deja su registro de auditoría y su fila
``PENDING`` en el espejo. Una llamada que falla no se repite en la misma pasada,
y un cliente que falla no para a los demás. Meta va simulado (``FakeMeta``).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
import structlog
from nexus_channels.whatsapp_meta import MetaAPIError
from nexus_channels.whatsapp_meta.exceptions import MetaTransientError
from nexus_worker.streams.reservation_templates_cron import cron_pass

from nexus_api.db.models import AuditLog, TenantCredentials
from nexus_api.services.reservations import templates
from tests.conftest import make_client_access, make_reservas
from tests.integration.reservas._meta_templates import (
    SIX,
    FakeMeta,
    mirror,
    seed_creds,
    seed_mirror,
    token_of,
)
from tests.integration.reservas._worker import scoped

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

WABA = "WABA_A"
AUDIT = "reservations.template_requested"


@pytest.fixture
async def client_a(db_session, console_world) -> dict[str, Any]:
    """El cliente A con Reservas y su número de Meta."""
    w = console_world["a"]
    out = await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await seed_creds(db_session, w["tenant_id"], waba_id=WABA)
    return out


async def _ensure(tenant_id, meta: FakeMeta) -> templates.Outcome:
    async with scoped(tenant_id) as s:
        return await templates.ensure_templates(s, client=meta)


async def _audits(db_session) -> list[AuditLog]:
    rows = await db_session.execute(
        sa.select(AuditLog).where(AuditLog.action == AUDIT).order_by(AuditLog.created_at)
    )
    out = list(rows.scalars())
    await db_session.commit()
    return out


async def test_it_asks_meta_for_the_six_with_named_variables(client_a, db_session) -> None:
    meta = FakeMeta()
    out = await _ensure(client_a["tenant_id"], meta)

    assert sorted(out.requested) == sorted(SIX)
    assert sorted(meta.ops("create", WABA)) == sorted(SIX)
    for sent in meta.created:
        assert sent["language"] == "es"
        assert sent["category"] == "UTILITY"
        assert sent["parameter_format"] == "NAMED"
        [body] = [c for c in sent["components"] if c["type"] == "BODY"]
        spec = templates.BY_NAME[sent["name"]]
        assert body["text"] == spec.body
        assert [p["param_name"] for p in body["example"]["body_text_named_params"]] == list(
            spec.variables
        )
    # Con el token del cliente y en su WABA, nada más.
    assert {(w, t) for _o, w, t, _n in meta.calls} == {(WABA, token_of(WABA))}

    rows = await mirror(db_session, WABA)
    assert sorted(rows) == sorted(SIX)
    assert {r.status for r in rows.values()} == {"PENDING"}
    assert {r.tenant_id for r in rows.values()} == {client_a["tenant_id"]}
    assert {r.language for r in rows.values()} == {"es"}

    audits = await _audits(db_session)
    assert sorted(a.target for a in audits) == sorted(f"template:{n}" for n in SIX)
    assert {a.tenant_id for a in audits} == {client_a["tenant_id"]}
    first = next(a for a in audits if a.target == "template:reserva_hueco_libre")
    assert first.actor == templates.ACTOR
    assert first.after_json == {
        "name": "reserva_hueco_libre",
        "language": "es",
        "category": "UTILITY",
        "meta_id": f"meta-{WABA}-reserva_hueco_libre",
        "status": "PENDING",
    }


async def test_what_the_waba_already_has_in_any_status_is_not_asked_again(
    client_a, db_session
) -> None:
    meta = FakeMeta()
    meta.has(WABA, "reserva_confirmada", status="APPROVED")
    meta.has(WABA, "reserva_cancelada", language="es_ES", status="REJECTED")
    meta.has(WABA, "reserva_cambiada", language="es_MX", status="PAUSED")
    # En inglés no cuenta: el outbox solo usa las ``es*``.
    meta.has(WABA, "reserva_recordatorio", language="en_US", status="APPROVED")

    out = await _ensure(client_a["tenant_id"], meta)

    assert sorted(meta.ops("create", WABA)) == sorted(
        ["reserva_pide_confirmacion", "reserva_recordatorio", "reserva_hueco_libre"]
    )
    assert sorted(out.existing) == sorted(
        ["reserva_confirmada", "reserva_cancelada", "reserva_cambiada"]
    )
    # La rechazada y la pausada no se recrean ni se borran.
    assert meta.ops("delete") == []

    rows = await mirror(db_session, WABA)
    # Lo que ya estaba queda en el espejo con su estado: la pasada siguiente no
    # vuelve a preguntar a Meta.
    assert rows["reserva_confirmada"].status == "APPROVED"
    assert (rows["reserva_cancelada"].status, rows["reserva_cancelada"].language) == (
        "REJECTED",
        "es_ES",
    )
    assert rows["reserva_cambiada"].status == "PAUSED"
    assert rows["reserva_recordatorio"].status == "PENDING"
    audits = await _audits(db_session)
    assert sorted(a.target for a in audits) == sorted(
        f"template:{n}"
        for n in ("reserva_pide_confirmacion", "reserva_recordatorio", "reserva_hueco_libre")
    )

    again = FakeMeta()
    await _ensure(client_a["tenant_id"], again)
    assert again.calls == []


async def test_a_template_beyond_the_first_page_is_seen(client_a) -> None:
    """``list_templates`` sin paginar veía 100: la 101 se habría duplicado."""
    meta = FakeMeta(page_size=100)
    for i in range(230):
        meta.has(WABA, f"otra_{i:03d}")
    meta.has(WABA, "reserva_hueco_libre", status="PENDING")

    await _ensure(client_a["tenant_id"], meta)

    assert "reserva_hueco_libre" not in meta.ops("create", WABA)
    assert len(meta.ops("create", WABA)) == 5
    assert meta.ops("list", WABA) == [None, "100", "200"]


async def test_meta_saying_it_already_exists_counts_as_created(client_a, db_session) -> None:
    meta = FakeMeta()
    meta.fail_create[(WABA, "reserva_cambiada")] = MetaAPIError(
        "Message Template Already Exists", status_code=400, code=100, subcode=2388024
    )

    out = await _ensure(client_a["tenant_id"], meta)

    assert "reserva_cambiada" in out.existing
    assert out.failed == []
    assert len(out.requested) == 5
    assert "template:reserva_cambiada" not in {a.target for a in await _audits(db_session)}


async def test_the_whole_six_in_the_mirror_means_meta_is_not_called(client_a, db_session) -> None:
    for i, name in enumerate(SIX):
        await seed_mirror(
            db_session,
            waba_id=WABA,
            tenant_id=client_a["tenant_id"],
            name=name,
            status=("APPROVED", "REJECTED", "PENDING", "PAUSED", "APPROVED", "APPROVED")[i],
            language="es_ES" if i == 1 else "es",
        )
    meta = FakeMeta()

    out = await _ensure(client_a["tenant_id"], meta)

    assert meta.calls == []
    assert out.skipped == "complete"


async def test_a_failed_call_is_not_repeated_in_the_same_pass(client_a, db_session) -> None:
    meta = FakeMeta()
    meta.fail_create[(WABA, "reserva_recordatorio")] = MetaAPIError(
        "Invalid parameter", status_code=400, code=100
    )

    out = await _ensure(client_a["tenant_id"], meta)

    assert meta.ops("create", WABA).count("reserva_recordatorio") == 1
    assert out.failed == ["reserva_recordatorio"]
    assert len(out.requested) == 5
    assert "reserva_recordatorio" not in await mirror(db_session, WABA)

    # La pasada siguiente lo vuelve a intentar, y solo eso.
    del meta.fail_create[(WABA, "reserva_recordatorio")]
    meta.calls.clear()
    out = await _ensure(client_a["tenant_id"], meta)
    assert meta.ops("create", WABA) == ["reserva_recordatorio"]
    assert out.requested == ["reserva_recordatorio"]


async def test_meta_down_ends_the_pass_of_that_client(client_a) -> None:
    """Un 5xx no se reintenta aquí, y las demás plantillas esperan a la próxima
    pasada: insistir con Meta caído solo suma llamadas."""
    meta = FakeMeta()
    first = templates.CATALOG[0].name
    meta.fail_create[(WABA, first)] = MetaTransientError("down", status_code=503)

    out = await _ensure(client_a["tenant_id"], meta)

    assert meta.ops("create", WABA) == [first]
    assert out.failed == [first]
    assert out.requested == []


async def test_a_failed_list_asks_for_nothing(client_a, db_session) -> None:
    meta = FakeMeta()
    meta.fail_list[WABA] = MetaTransientError("down", status_code=503)

    out = await _ensure(client_a["tenant_id"], meta)

    assert meta.ops("create") == []
    assert meta.ops("list", WABA) == [None]
    assert out.skipped == "list_failed"
    assert await mirror(db_session, WABA) == {}


async def test_meta_words_never_reach_the_log(client_a) -> None:
    """15.6: del error del proveedor, el tipo y el código; nunca su texto."""
    secret = "token EAA-leaked para +56911112222"
    meta = FakeMeta()
    meta.fail_create[(WABA, "reserva_cancelada")] = MetaAPIError(
        secret, status_code=400, code=100, subcode=33, body=f'{{"error":"{secret}"}}'
    )

    with structlog.testing.capture_logs() as logs:
        await _ensure(client_a["tenant_id"], meta)

    failed = [e for e in logs if e["event"] == "reservation_templates.create_failed"]
    assert len(failed) == 1
    assert failed[0]["error_type"] == "MetaAPIError"
    assert failed[0]["code"] == 100
    assert failed[0]["template"] == "reserva_cancelada"
    assert secret not in repr(logs)


async def test_without_reservas_or_without_whatsapp_meta_is_not_called(
    db_session, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    # A: número de Meta, pero sin el módulo.
    await make_client_access(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], modules=("panel",)
    )
    await seed_creds(db_session, a["tenant_id"], waba_id=WABA)
    # B: Reservas, sin número.
    await make_reservas(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    meta = FakeMeta()

    assert (await _ensure(a["tenant_id"], meta)).skipped == "reservas_off"
    assert (await _ensure(b["tenant_id"], meta)).skipped == "no_whatsapp"
    assert meta.calls == []


async def test_a_number_to_reconnect_is_not_asked_about(client_a, db_session) -> None:
    """Con el token dado por caducado, cada llamada sería otro 190."""
    await db_session.execute(
        sa.update(TenantCredentials)
        .where(TenantCredentials.tenant_id == client_a["tenant_id"])
        .values(needs_reauth=True)
    )
    await db_session.commit()
    meta = FakeMeta()

    assert (await _ensure(client_a["tenant_id"], meta)).skipped == "needs_reauth"
    assert meta.calls == []


async def test_one_client_failing_does_not_stop_the_other(
    db_session, console_world, client_a
) -> None:
    b = console_world["b"]
    await make_reservas(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    await seed_creds(db_session, b["tenant_id"], waba_id="WABA_B")
    meta = FakeMeta()
    meta.fail_list[WABA] = MetaTransientError("down", status_code=503)

    summary = await cron_pass(client=meta)

    assert meta.ops("create", WABA) == []
    assert sorted(meta.ops("create", "WABA_B")) == sorted(SIX)
    assert summary["requested"] == 6
    assert summary["list_failed"] == 1
    # El cliente que le pasa a la pasada no se cierra: es de quien lo creó.
    assert meta.closed is False
