"""Spec 047, T052 — horarios, sedes y fechas especiales en la ficha (requisitos 9 y 10).

Por la API de la consola (``/console/clients/{ref}/business``, ``console-api.md``
§3), con ``If-Match`` por sección:

- guardar el horario devuelve la frase «Así lo dirá el agente», escribe la
  proyección de ``tenants.business_hours`` en la misma transacción y deja el
  historial;
- pasar de día por día a bloques con días distintos dice qué se pierde y pide
  confirmación (10.6);
- hasta 6 turnos por día, y los nocturnos;
- las sedes, con o sin horario propio, y deshacer su archivado (9.1, 9.2, 9.4);
- sin sedes, el agente no inventa una dirección (9.3);
- una fecha especial cerrada cierra también Reservas ese día (10.3, 10.4).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import BusinessChange, BusinessSection
from nexus_api.services.business_hours import parse_business_hours

from ._business_world import (
    SPLIT_WEEK,
    Biz,
    active_prompt,
    biz,
    projected_hours,
    read,
    seed_agent,
    shifts,
    write,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

__all__ = ["biz"]

SPLIT_PHRASE = (
    "Abrimos lunes a viernes de 09:00 a 14:00 y de 16:00 a 20:00. Cerramos sábados y domingos."
)


# ── el horario del negocio ─────────────────────────────────────────────────


async def test_saving_the_hours_returns_the_phrase_and_projects_it(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Historia 5, escenario 1, y la proyección para los lectores de antes."""
    before = await read(client, biz, "/hours")
    assert before["revision"] == 0 and before["label"] is None
    assert before["allowed"] == ["edit"]

    saved = await write(
        client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0
    )
    assert saved["label"] == SPLIT_PHRASE
    assert saved["revision"] == 1
    assert saved["days"]["mon"] == [
        {"open": "09:00", "close": "14:00", "overnight": False},
        {"open": "16:00", "close": "20:00", "overnight": False},
    ]
    assert saved["days"]["sat"] == [] and saved["state"] == "complete"

    projected = await projected_hours(db_session, biz.tenant_id)
    assert projected is not None and projected["label"] == SPLIT_PHRASE
    legacy = parse_business_hours(projected)
    assert legacy is not None and len(legacy["monday"]) == 2 and legacy["saturday"] == []

    async with tenant_scoped_session(db_session, biz.tenant_id):
        change = await db_session.scalar(
            sa.select(BusinessChange).where(BusinessChange.section == "hours")
        )
        assert change is not None and change.actor_kind == "partner_member"
        section = await db_session.get(BusinessSection, (biz.tenant_id, "hours"))
        assert section is not None and section.state == "complete"


async def test_a_stale_or_missing_revision_does_not_write(client: Any, biz: Biz) -> None:
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": SPLIT_WEEK}, revision=0)
    stale = await write(
        client,
        biz,
        "PUT",
        "/hours",
        {"layout": "daily", "days": {"mon": shifts(("10:00", "12:00"))}},
        revision=0,
        expect=412,
    )
    assert stale["detail"]["code"] == "revision_conflict"
    assert stale["detail"]["current"]["label"] == SPLIT_PHRASE
    assert [c["kind"] for c in stale["detail"]["changes"]] == ["edit"]
    missing = await write(
        client, biz, "PUT", "/hours", {"layout": "daily", "days": {}}, revision=None, expect=428
    )
    assert missing["detail"]["code"] == "revision_required"
    assert (await read(client, biz, "/hours"))["label"] == SPLIT_PHRASE


async def test_switching_from_daily_to_blocks_says_what_is_lost_and_asks(
    client: Any, biz: Biz
) -> None:
    """Requisito 10.6."""
    daily = {
        **SPLIT_WEEK,
        "tue": shifts(("10:00", "14:00")),
        "thu": [],
        "sat": shifts(("10:00", "13:00")),
    }
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": daily}, revision=0)

    asked = await write(
        client,
        biz,
        "PUT",
        "/hours",
        {"layout": "blocks", "days": daily},
        revision=1,
        expect=409,
    )
    assert asked["detail"]["code"] == "blocks_lose_days"
    assert asked["detail"]["lost"] == ["tue", "thu"]
    assert (await read(client, biz, "/hours"))["layout"] == "daily", "nothing changed yet"

    confirmed = await write(
        client,
        biz,
        "PUT",
        "/hours",
        {"layout": "blocks", "days": daily, "confirm_loss": True},
        revision=1,
    )
    assert confirmed["layout"] == "blocks"
    assert confirmed["days"]["tue"] == confirmed["days"]["mon"]
    assert confirmed["days"]["thu"] == confirmed["days"]["mon"]
    assert confirmed["days"]["sat"] == [{"open": "10:00", "close": "13:00", "overnight": False}]


async def test_up_to_six_shifts_a_day_and_night_shifts(client: Any, biz: Biz) -> None:
    seven = shifts(*[(f"{8 + 2 * i:02d}:00", f"{9 + 2 * i:02d}:00") for i in range(7)])
    refused = await write(
        client,
        biz,
        "PUT",
        "/hours",
        {"layout": "daily", "days": {"mon": seven}},
        revision=0,
        expect=422,
    )
    assert refused["detail"]["code"] == "too_many_shifts"
    assert refused["detail"]["day"] == "mon"

    bar = await write(
        client,
        biz,
        "PUT",
        "/hours",
        {"layout": "daily", "days": {"fri": shifts(("20:00", "02:00"))}},
        revision=0,
    )
    assert bar["days"]["fri"] == [{"open": "20:00", "close": "02:00", "overnight": True}]
    assert "del día siguiente" in bar["label"]


# ── sedes ──────────────────────────────────────────────────────────────────


async def test_locations_with_and_without_their_own_hours(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Requisitos 9.1 y 9.2; historia 5, escenario 4."""
    await write(client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0)
    _agent, cfg = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Sofía."
    )

    created = await write(
        client,
        biz,
        "POST",
        "/locations",
        {"name": "Cultor Centro", "address": "Calle Mayor 1, Madrid", "phone_e164": "+34600123456"},
        revision=0,
        expect=201,
    )
    centro = created["created_id"]
    norte_out = await write(
        client,
        biz,
        "POST",
        "/locations",
        {"name": "Cultor Norte"},
        revision=created["revision"],
        expect=201,
    )
    norte = norte_out["created_id"]
    bad_phone = await write(
        client,
        biz,
        "POST",
        "/locations",
        {"name": "Otra", "phone_e164": "600123"},
        revision=norte_out["revision"],
        expect=422,
    )
    assert bad_phone["detail"]

    own = await write(
        client,
        biz,
        "PUT",
        f"/hours?location_id={centro}",
        {"layout": "daily", "days": {"sat": shifts(("10:00", "14:00"))}},
        revision=norte_out["revision"],
    )
    assert own["location_id"] == centro and own["inherits"] is False
    assert own["label"] == "Abrimos sábados de 10:00 a 14:00. Cerramos lunes a viernes y domingos."

    listed = await read(client, biz, "/locations")
    by_id = {loc["id"]: loc for loc in listed["items"]}
    assert by_id[centro]["own_hours"] is True
    assert by_id[norte]["own_hours"] is False
    assert by_id[norte]["label"] == SPLIT_PHRASE, "without its own hours, the business's"
    inherited = await read(client, biz, f"/hours?location_id={norte}")
    assert inherited["inherits"] is True and inherited["label"] == SPLIT_PHRASE

    prompt = await active_prompt(db_session, biz.tenant_id, cfg)
    assert "Cultor Centro" in prompt and "Calle Mayor 1, Madrid" in prompt
    assert "Abrimos sábados de 10:00 a 14:00" in prompt
    assert "Cultor Norte" in prompt

    back = await write(
        client,
        biz,
        "PUT",
        f"/hours?location_id={centro}",
        {"inherit": True},
        revision=listed["revision"],
    )
    assert back["inherits"] is True and back["label"] == SPLIT_PHRASE


async def test_without_locations_the_agent_does_not_invent_an_address(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Requisito 9.3."""
    _agent, cfg = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Sofía."
    )
    await write(client, biz, "PUT", "/hours", {"layout": "blocks", "days": SPLIT_WEEK}, revision=0)
    prompt = await active_prompt(db_session, biz.tenant_id, cfg)
    assert "Sin sedes registradas" in prompt
    assert "no des ninguna dirección" in prompt


async def test_archiving_a_location_can_be_undone(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Requisito 9.4."""
    _agent, cfg = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Sofía."
    )
    created = await write(
        client, biz, "POST", "/locations", {"name": "Cultor Norte"}, revision=0, expect=201
    )
    loc = created["created_id"]
    archived = await write(
        client, biz, "POST", f"/locations/{loc}/archive", revision=created["revision"]
    )
    assert [i["id"] for i in archived["items"]] == []
    assert "Cultor Norte" not in await active_prompt(db_session, biz.tenant_id, cfg)
    with_archived = await read(client, biz, "/locations?archived=true")
    assert [(i["id"], i["archived"]) for i in with_archived["items"]] == [(loc, True)]

    restored = await write(
        client, biz, "POST", f"/locations/{loc}/restore", revision=archived["revision"]
    )
    assert [(i["id"], i["archived"]) for i in restored["items"]] == [(loc, False)]
    assert "Cultor Norte" in await active_prompt(db_session, biz.tenant_id, cfg)

    renamed = await write(
        client,
        biz,
        "PATCH",
        f"/locations/{loc}",
        {"name": "Cultor Chamberí", "address": "Calle Bravo Murillo 200"},
        revision=restored["revision"],
    )
    assert renamed["items"][0]["name"] == "Cultor Chamberí"


# ── fechas especiales ──────────────────────────────────────────────────────


async def test_a_closed_special_date_closes_the_day_everywhere(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Historia 5, escenario 3: Reservas no ofrece huecos y el agente lo sabe."""
    from nexus_api.db.models import ReservationSettings
    from nexus_api.services.reservations.core import load_ctx
    from nexus_api.services.reservations.settings import apply_defaults

    _agent, cfg = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Sofía."
    )
    every_day = {
        d: shifts(("09:00", "20:00")) for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    await write(client, biz, "PUT", "/hours", {"layout": "daily", "days": every_day}, revision=0)

    created = await write(
        client,
        biz,
        "POST",
        "/special-dates",
        {"name": "Navidad", "from": "2026-12-25", "to": "2026-12-25", "closed": True},
        revision=0,
        expect=201,
    )
    (item,) = created["items"]
    assert (item["name"], item["closed"], item["shifts"]) == ("Navidad", True, [])

    reduced = await write(
        client,
        biz,
        "POST",
        "/special-dates",
        {
            "name": "Nochebuena",
            "from": "2026-12-24",
            "to": "2026-12-24",
            "closed": False,
            "shifts": shifts(("10:00", "14:00")),
        },
        revision=created["revision"],
        expect=201,
    )
    assert len(reduced["items"]) == 2

    refused = await write(
        client,
        biz,
        "POST",
        "/special-dates",
        {"from": "2026-12-26", "to": "2026-12-20", "closed": True},
        revision=reduced["revision"],
        expect=422,
    )
    assert refused["detail"]["code"] == "date_range"

    async with tenant_scoped_session(db_session, biz.tenant_id):
        settings = ReservationSettings(tenant_id=biz.tenant_id, version=1, updated_by="tests")
        apply_defaults(settings, "services", None)
        db_session.add(settings)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        ctx = await load_ctx(db_session, biz.tenant_id)
        assert ctx is not None
        assert ctx.day_ranges(date(2026, 12, 25)) == []
        assert len(ctx.day_ranges(date(2026, 12, 24))) == 1
        assert ctx.day_ranges(date(2026, 12, 23)) != []

    prompt = await active_prompt(db_session, biz.tenant_id, cfg)
    assert "Navidad" in prompt and "25/12/2026" in prompt and "cerrado" in prompt

    nochebuena = next(i for i in reduced["items"] if i["name"] == "Nochebuena")
    archived = await write(
        client,
        biz,
        "POST",
        f"/special-dates/{nochebuena['id']}/archive",
        revision=reduced["revision"],
    )
    assert [i["name"] for i in archived["items"]] == ["Navidad"]
    patched = await write(
        client,
        biz,
        "PATCH",
        f"/special-dates/{item['id']}",
        {"to": "2026-12-26"},
        revision=archived["revision"],
    )
    assert patched["items"][0]["to"] == "2026-12-26"


async def test_another_client_never_reaches_these_sections(
    client: Any, db_session: AsyncSession, biz: Biz, console_world: dict[str, Any]
) -> None:
    other = console_world["b"]
    resp = await client.get(biz.url + "/hours", headers=other["headers"]())
    assert resp.status_code == 404
    resp = await client.put(
        biz.url + "/hours",
        json={"layout": "daily", "days": {}},
        headers={**other["headers"](), "If-Match": '"0"'},
    )
    assert resp.status_code == 404
