"""Spec 047, T068 — la ficha sabe de dónde viene cada dato y se puede deshacer (historia 17).

``/console/clients/{ref}/business`` (``contracts/console-api.md`` §3) y los
servicios que hay detrás (``services/business/{writes,provenance,history,suggestions}``):

- **Procedencia** (13.1): los cinco tipos («Escrito por ti», «Leído de la web ·
  revísalo», «Migrado · revísalo», «Propuesto por el constructor», «Editado por
  Marta desde la app»), cada uno con su autor y su fecha.
- **Confirmar un dato leído** (13.2) lo marca escrito por esa persona y la
  sección deja de salir como pendiente.
- **Historial** (13.3): antes y después, y deshacer el último cambio; si alguien
  escribió después, ``412`` con lo que cambió.
- **Concurrencia** (13.4): ``412`` por sección, sin pisar a nadie.
- **Quién edita** (13.5): ``clients:write``; todas las personas del cliente; el
  constructor, solo por propuesta. La auditoría dice quién y desde dónde.
- **Avisos** (13.6): cuando edita una persona del cliente, el partner recibe
  ``client.business_changed`` en la campana, agrupado por cliente y hora.
- **Pruebas** (13.7): las de los agentes del cliente vuelven a pasar en segundo
  plano; hasta la fase 9, un trabajo ``tests`` que solo las marca ``stale``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog, ConsoleNotification, Job
from nexus_api.db.models.business import BusinessChange, BusinessSuggestion
from nexus_api.services.business import writes
from nexus_api.services.business.profile_edits import update_policies
from nexus_api.services.business.reader import Extraction, apply_extraction
from nexus_api.services.business.sections import Actor
from tests.conftest import add_client_member, add_console_member

from ..clients._client_world import add_agent, new_client, roomy, tenant_of

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


async def _cultor(client: Any, db_session: AsyncSession, world: dict[str, Any]) -> dict[str, Any]:
    a = world["a"]
    created = await new_client(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería de barrio con 2 sedes"
    )
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    return {
        "ref": created["ref"],
        "tenant_id": tenant_id,
        "base": f"/console/clients/{created['ref']}/business",
    }


async def _ficha(client: Any, headers: dict[str, str], base: str) -> dict[str, Any]:
    resp = await client.get(base, headers=headers)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _section(ficha: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in ficha["sections"] if s["section"] == name)


async def _put_links(
    client: Any, headers: dict[str, str], base: str, links: list[dict[str, Any]], rev: int
) -> Any:
    return await client.put(
        f"{base}/links", json={"links": links}, headers={**headers, "If-Match": f'"{rev}"'}
    )


# ── procedencia ─────────────────────────────────────────────────────────────


async def test_every_datum_says_where_it_came_from_who_and_when(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    marta = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"], email="marta@cultor.test"
    )
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        # Leído de la web: se aplica con la revisión pendiente.
        await apply_extraction(
            db_session,
            Extraction(policies={"cancellation": "Avisa con 24 h."}),
            source="web",
            source_url="https://cultorbarber.com/condiciones",
            translated_from=None,
        )
        # Migrado (ola 10) y editado por Marta desde la app.
        await writes.set_provenance(
            db_session,
            ["/policies/deposit"],
            source="migrated",
            actor=Actor(kind="system", id="migration", origin="system"),
            review="pending",
        )
        await update_policies(
            db_session,
            {"payments": "Tarjeta y efectivo."},
            actor=Actor(kind="client_user", id=marta["user_id"], origin="app"),
        )
    await writes.drain_after_commit()

    ficha = await _ficha(client, a["headers"](), c["base"])
    prov = ficha["provenance"]
    assert prov["/business/niche"]["source"] == "person"
    assert prov["/business/niche"]["by"]["kind"] == "partner_member"
    assert prov["/business/niche"]["by"]["name"] == "Owner A"
    assert prov["/business/niche"]["origin"] == "console"
    assert prov["/business/niche"]["at"]
    web = prov["/policies/cancellation"]
    assert (web["source"], web["review"]) == ("web", "pending")
    assert web["source_url"] == "https://cultorbarber.com/condiciones"
    assert (prov["/policies/deposit"]["source"], prov["/policies/deposit"]["review"]) == (
        "migrated",
        "pending",
    )
    app = prov["/policies/payments"]
    assert (app["source"], app["origin"], app["by"]["kind"]) == ("person", "app", "client_user")
    assert app["by"]["name"] == "Valeria Ríos"
    # La sección lo resume: leída de la web y pendiente de revisar.
    assert _section(ficha, "policies")["state"] == "read_pending"
    assert _section(ficha, "policies")["updated_by"]["name"] == "Valeria Ríos"
    assert ficha["spec"]["policies"]["payments"] == "Tarjeta y efectivo."
    assert "tenant_id" not in str(ficha)


async def test_the_builder_only_writes_through_a_proposal_a_person_accepts(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    builder = Actor(kind="builder", id="client_builder", origin="system")
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        with pytest.raises(PermissionError):
            await update_policies(db_session, {"no_show": "Se cobra la mitad."}, actor=builder)
        db_session.add(
            BusinessSuggestion(
                tenant_id=c["tenant_id"],
                pointer="/policies/no_show",
                proposed_value="Se cobra la mitad.",
                current_value=None,
                source="builder",
            )
        )
    ficha = await _ficha(client, a["headers"](), c["base"])
    (suggestion,) = [s for s in ficha["suggestions"] if s["pointer"] == "/policies/no_show"]
    assert suggestion["section"] == "policies" and suggestion["source"] == "builder"

    resp = await client.post(
        f"{c['base']}/suggestions/{suggestion['id']}/decide",
        json={"decision": "accept"},
        headers=a["headers"](),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["decision"] == "accepted"

    ficha = await _ficha(client, a["headers"](), c["base"])
    assert ficha["spec"]["policies"]["no_show"] == "Se cobra la mitad."
    prov = ficha["provenance"]["/policies/no_show"]
    # «Propuesto por el constructor», aplicado por quien lo aceptó.
    assert (prov["source"], prov["by"]["name"], prov["review"]) == (
        "builder",
        "Owner A",
        "confirmed",
    )
    assert not [s for s in ficha["suggestions"] if s["id"] == suggestion["id"]]
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        kinds = (
            await db_session.scalars(
                sa.select(BusinessChange.kind).where(BusinessChange.section == "policies")
            )
        ).all()
    assert "builder_applied" in kinds

    # Descartar no aplica nada y la sugerencia deja de salir.
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        other = BusinessSuggestion(
            tenant_id=c["tenant_id"],
            pointer="/policies/deposit",
            proposed_value="20 €",
            current_value=None,
            source="web",
        )
        db_session.add(other)
        await db_session.flush()
        other_id = other.id
    resp = await client.post(
        f"{c['base']}/suggestions/{other_id}/decide",
        json={"decision": "discard"},
        headers=a["headers"](),
    )
    assert resp.status_code == 200, resp.text
    ficha = await _ficha(client, a["headers"](), c["base"])
    assert "deposit" not in ficha["spec"]["policies"]
    # Editar antes de aceptar: vale lo editado, validado sin modelo.
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        third = BusinessSuggestion(
            tenant_id=c["tenant_id"],
            pointer="/business/timezone",
            proposed_value="Europe/Madird",
            current_value="UTC",
            source="web",
        )
        db_session.add(third)
        await db_session.flush()
        third_id = third.id
    bad = await client.post(
        f"{c['base']}/suggestions/{third_id}/decide",
        json={"decision": "accept"},
        headers=a["headers"](),
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_value"
    edited = await client.post(
        f"{c['base']}/suggestions/{third_id}/decide",
        json={"decision": "edit", "value": "Europe/Madrid"},
        headers=a["headers"](),
    )
    assert edited.status_code == 200, edited.text
    ficha = await _ficha(client, a["headers"](), c["base"])
    assert ficha["spec"]["business"]["timezone"] == "Europe/Madrid"


async def test_confirming_a_read_section_makes_it_written_by_that_person(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 1: «Es correcto» → «Escrito por ti», y deja de salir como pendiente."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        await apply_extraction(
            db_session,
            Extraction(policies={"cancellation": "Avisa con 24 h.", "payments": "Tarjeta."}),
            source="web",
            source_url="https://cultorbarber.com",
            translated_from=None,
        )
    before = await _ficha(client, a["headers"](), c["base"])
    assert _section(before, "policies")["state"] == "read_pending"

    resp = await client.post(f"{c['base']}/sections/policies/confirm", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert resp.json()["confirmed"] == 2
    after = await _ficha(client, a["headers"](), c["base"])
    assert _section(after, "policies")["state"] == "complete"
    for pointer in ("/policies/cancellation", "/policies/payments"):
        prov = after["provenance"][pointer]
        assert (prov["source"], prov["review"], prov["by"]["name"]) == (
            "person",
            "confirmed",
            "Owner A",
        )
    # Confirmar no cambia los datos ni sube la revisión de la sección.
    assert after["spec"]["policies"] == before["spec"]["policies"]
    assert _section(after, "policies")["revision"] == _section(before, "policies")["revision"]


# ── historial, deshacer y concurrencia ──────────────────────────────────────


async def test_history_keeps_before_and_after_and_undoes_the_last_change(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    ficha = await _ficha(client, a["headers"](), c["base"])
    rev = _section(ficha, "links")["revision"]
    first = await _put_links(
        client, a["headers"](), c["base"], [{"network": "instagram", "handle": "cultorbarber"}], rev
    )
    assert first.status_code == 200, first.text
    assert first.headers["ETag"] == f'"{rev + 1}"'
    second = await _put_links(
        client,
        a["headers"](),
        c["base"],
        [
            {"network": "instagram", "handle": "cultorbarber"},
            {"network": "web", "url": "https://cultorbarber.com"},
        ],
        rev + 1,
    )
    assert second.status_code == 200, second.text

    history = await client.get(f"{c['base']}/history?section=links", headers=a["headers"]())
    assert history.status_code == 200, history.text
    items = history.json()["items"]
    assert [i["kind"] for i in items[:2]] == ["edit", "edit"]
    last = items[0]
    assert last["by"]["name"] == "Owner A" and last["origin"] == "console"
    assert [x["network"] for x in last["after"]["links"]] == ["instagram", "web"]
    assert [x["network"] for x in last["before"]["links"]] == ["instagram"]
    assert last["undoable"] is True and items[1]["undoable"] is False

    # Deshacer el penúltimo, con uno escrito después: 412 con lo que cambió.
    stale = await client.post(f"{c['base']}/history/{items[1]['id']}/undo", headers=a["headers"]())
    assert stale.status_code == 412, stale.text
    assert stale.json()["detail"]["code"] == "revision_conflict"
    assert [ch["change_id"] for ch in stale.json()["detail"]["changes"]] == [last["id"]]

    undone = await client.post(f"{c['base']}/history/{last['id']}/undo", headers=a["headers"]())
    assert undone.status_code == 200, undone.text
    ficha = await _ficha(client, a["headers"](), c["base"])
    assert [x["network"] for x in ficha["spec"]["links"]] == ["instagram"]
    items = (await client.get(f"{c['base']}/history?section=links", headers=a["headers"]())).json()[
        "items"
    ]
    assert items[0]["kind"] == "undo" and items[0]["undo_of"] == last["id"]
    assert next(i for i in items if i["id"] == last["id"])["undone_at"] is not None
    # Lo deshecho no se deshace dos veces.
    again = await client.post(f"{c['base']}/history/{last['id']}/undo", headers=a["headers"]())
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_undone"

    async with tenant_scoped_session(db_session, c["tenant_id"]):
        actions = (
            await db_session.scalars(
                sa.select(AuditLog.action).where(AuditLog.target == "business:links")
            )
        ).all()
    assert actions.count("business.section_updated") == 2
    assert "business.section_undone" in actions


async def test_two_people_on_the_same_section_never_overwrite_each_other(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 4: la segunda ve qué cambió la primera y decide."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    rev = _section(await _ficha(client, a["headers"](), c["base"]), "links")["revision"]
    ana = await _put_links(
        client, a["headers"](), c["base"], [{"network": "tiktok", "handle": "cultor"}], rev
    )
    assert ana.status_code == 200, ana.text
    late = await _put_links(
        client, other["headers"](), c["base"], [{"network": "x", "handle": "cultor"}], rev
    )
    assert late.status_code == 412, late.text
    body = late.json()["detail"]
    assert body["code"] == "revision_conflict" and body["current"] == rev + 1
    assert [x["network"] for x in body["changes"][0]["after"]["links"]] == ["tiktok"]
    ficha = await _ficha(client, a["headers"](), c["base"])
    assert [x["network"] for x in ficha["spec"]["links"]] == ["tiktok"]

    # Sin If-Match, la consola nueva no escribe.
    blind = await client.put(f"{c['base']}/links", json={"links": []}, headers=other["headers"]())
    assert blind.status_code == 428


# ── quién edita, avisos y pruebas ───────────────────────────────────────────


async def test_an_analyst_reads_but_does_not_edit(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    ficha = await _ficha(client, analyst["headers"](), c["base"])
    assert ficha["allowed"] == []
    resp = await _put_links(
        client, analyst["headers"](), c["base"], [], _section(ficha, "links")["revision"]
    )
    assert resp.status_code == 403


async def test_a_change_by_the_clients_person_tells_the_partner_once_an_hour(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 2 y requisito 13.6: el aviso a la campana, agrupado por cliente y hora."""
    a = world["a"]
    c = await _cultor(client, db_session, world)
    marta = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"]
    )
    marta_actor = Actor(kind="client_user", id=marta["user_id"], origin="app")
    for payments in ("Tarjeta.", "Tarjeta y efectivo."):
        async with tenant_scoped_session(db_session, c["tenant_id"]):
            await update_policies(db_session, {"payments": payments}, actor=marta_actor)
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        await update_policies(
            db_session,
            {"cancellation": "24 h"},
            actor=Actor(kind="partner_member", id=a["user_id"], origin="console"),
        )
    await writes.drain_after_commit()

    async with db_session.begin():
        rows = (
            await db_session.scalars(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == a["partner_id"],
                    ConsoleNotification.kind == "client.business_changed",
                )
            )
        ).all()
    assert len(rows) == 1, [r.payload for r in rows]
    (notice,) = rows
    assert notice.external_client_ref == c["ref"]
    assert notice.payload["sections"] == ["policies"]
    assert notice.payload["by"] == "Valeria Ríos" and notice.payload["origin"] == "app"
    # Nunca el dato en sí: solo qué sección cambió.
    assert "efectivo" not in str(notice.payload)

    async with tenant_scoped_session(db_session, c["tenant_id"]):
        audit = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "business.section_updated")
            )
        ).all()
    who = {(row.actor, row.after_json["origin"]) for row in audit if row.after_json}
    assert (f"client:{marta['user_id']}", "app") in who


async def test_a_change_marks_the_agents_tests_stale_in_the_background(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Requisito 13.7 (y 21.7): las pruebas afectadas quedan desactualizadas, y
    las del agente publicado vuelven a pasar en segundo plano."""
    from nexus_api.db.models.agent_spec import AgentTest, AgentTestRun
    from nexus_api.services.testing.suites import add_test, ensure_suite

    a = world["a"]
    c = await _cultor(client, db_session, world)
    citas = await add_agent(db_session, c["tenant_id"], "Citas")
    borrador = await add_agent(
        db_session, c["tenant_id"], "Borrador", published=False, channel=None
    )
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        for agent in (citas, borrador):
            suite = await ensure_suite(db_session, agent["agent_id"])
            await add_test(
                db_session, suite, {"name": "Redes", "first_message": "¿Tenéis Instagram?"}
            )
    rev = _section(await _ficha(client, a["headers"](), c["base"]), "links")["revision"]
    for n, handle in enumerate(("cultor", "cultorbarber")):
        resp = await _put_links(
            client, a["headers"](), c["base"], [{"network": "instagram", "handle": handle}], rev + n
        )
        assert resp.status_code == 200, resp.text

    async with tenant_scoped_session(db_session, c["tenant_id"]):
        jobs = (await db_session.scalars(sa.select(Job).where(Job.kind == "tests"))).all()
        runs = (await db_session.scalars(sa.select(AgentTestRun))).all()
        tests = (
            await db_session.scalars(sa.select(AgentTest).execution_options(populate_existing=True))
        ).all()
    # Uno por agente publicado, no uno por cambio; el borrador no habla con nadie.
    assert [j.agent_id for j in jobs] == [citas["agent_id"]]
    (job,) = jobs
    assert job.status == "queued"
    (run,) = runs
    assert (run.agent_id, run.reason, run.scope) == (
        citas["agent_id"],
        "business_change",
        "affected",
    )
    assert run.summary["sections"] == ["links"]
    # Las pruebas de los dos agentes quedan desactualizadas.
    assert all(t.stale for t in tests) and len(tests) == 2


async def test_another_client_never_sees_the_ficha(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    c = await _cultor(client, db_session, world)
    b = world["b"]
    resp = await client.get(c["base"], headers=b["headers"]())
    assert resp.status_code == 404
    missing = await client.post(
        f"{c['base']}/history/{uuid.uuid4()}/undo", headers=world["a"]["headers"]()
    )
    assert missing.status_code == 404
