"""Spec 047, enmienda del 2026-10-29, T201 — los sectores sin guía en el panel de
operador y «Convertir en guía de Auphere» (requisito 58.5;
``contracts/admin-sector-guides.md``; D47, D65 y D66).

- La lista dice qué etiquetas sin guía se repiten más, cliente a cliente con su
  contexto puesto, y con sus guías generadas candidatas.
- Revisar exige una persona de Auphere y que no quede ningún dato del cliente.
- Convertir exige la guía revisada, deja una guía de plataforma sin nada del cliente
  y sus 12 pruebas en el catálogo, y la etiqueta deja de faltar.
- La guía de un cliente no se lee con el id de otro.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog, Tenant, TenantPlan, TenantStatus
from nexus_api.db.models.agent_spec import GeneratedGuide, SectorTestCatalog
from nexus_api.db.models.business import BusinessLocation, BusinessProfile
from nexus_api.services import operator_identity

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

BASE = "/admin/builder"


def guide_doc() -> dict[str, Any]:
    return {
        "ask": ["¿Hay cuota de inscripción?", "¿Se puede probar una clase gratis?"],
        "procedures": [
            {
                "title": "Clase de prueba",
                "when": "Alguien quiere probar antes de apuntarse",
                "steps": "Ofrece la clase de prueba y pide el día que prefiere.",
            }
        ],
        "risks": ["Una lesión durante una clase"],
        "tools": ["escalate.escalate_to_human"],
    }


def twelve_tests() -> list[dict[str, Any]]:
    return [
        {
            "key": f"prueba_{n}",
            "name": f"Pregunta {n}",
            "persona": "Cliente nuevo",
            "first_message": f"Hola, una duda {n}",
            "plan": "Pregunta y se despide.",
            "expected_state": {},
            "criteria": [{"key": "ok", "text": "Responde con los datos de la ficha."}],
            "critical": n == 1,
        }
        for n in range(1, 13)
    ]


@pytest_asyncio.fixture
async def ops(db_session: AsyncSession, admin_headers: dict[str, str]) -> dict[str, str]:
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-guides-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def _client(
    db_session: AsyncSession,
    name: str,
    *,
    key: str = "otro",
    label: str | None = None,
    phone: str | None = None,
) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(
                id=tenant_id,
                name=name,
                slug=f"g-{tenant_id.hex[:12]}",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                timezone="Europe/Madrid",
            )
        )
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            BusinessProfile(
                tenant_id=tenant_id,
                niche=label or "Barbería",
                timezone="Europe/Madrid",
                website=f"https://{name.lower().replace(' ', '')}.es",
                sector=None
                if label is None and key == "otro"
                else {
                    "key": key,
                    "label": label or "Barbería y peluquería",
                    "confidence": 0.9,
                    "source": "niche",
                    "decided_by": "system",
                },
            )
        )
        db_session.add(
            BusinessLocation(
                tenant_id=tenant_id,
                name="Sede Centro",
                address="Calle Mayor 12, Madrid",
                phone_e164=phone,
            )
        )
    return tenant_id


async def _guide(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    label: str,
    *,
    status: str = "generated",
    guide: dict[str, Any] | None = None,
) -> uuid.UUID:
    from nexus_api.services.builder.guides import label_key

    guide_id = uuid.uuid4()
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            GeneratedGuide(
                id=guide_id,
                tenant_id=tenant_id,
                sector_label=label,
                label_key=label_key(label),
                guide=guide or guide_doc(),
                tests=twelve_tests(),
                status=status,
                reviewed_by="operator:x@auphere.test" if status == "reviewed" else None,
                reviewed_at=sa.func.now() if status == "reviewed" else None,
            )
        )
    return guide_id


async def test_the_list_needs_the_panel_token(client: Any) -> None:
    resp = await client.get(f"{BASE}/sector-guides/missing")
    assert resp.status_code == 401


async def test_the_labels_without_guide_most_repeated_with_their_candidates(
    client: Any, db_session: AsyncSession, ops: dict[str, str]
) -> None:
    gyms = [
        await _client(db_session, "Gimnasio Norte", label="Gimnasio"),
        await _client(db_session, "Fit Sur", label="gimnasio"),
        await _client(db_session, "Box Este", label="Gimnásio"),
    ]
    await _client(db_session, "Óptica Luz", label="Óptica")
    await _client(db_session, "Barbería Cultor", key="barberia_peluqueria")
    await _client(db_session, "Sin sector")  # aún sin identificar: no cuenta
    older = await _guide(db_session, gyms[0], "Gimnasio")
    reviewed = await _guide(db_session, gyms[1], "gimnasio", status="reviewed")

    resp = await client.get(f"{BASE}/sector-guides/missing", headers=ops)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    keys = [item["label_key"] for item in body["items"]]
    assert keys == ["gimnasio", "optica"]
    gym = body["items"][0]
    assert gym["clients"] == 3
    assert gym["label"] == "Gimnasio"
    assert gym["guides"] == {"generated": 1, "reviewed": 1}
    assert [c["guide_id"] for c in gym["candidates"]] == [str(reviewed), str(older)]
    first = gym["candidates"][0]
    assert first["client_name"] == "Fit Sur" and first["tests"] == 12
    assert first["status"] == "reviewed" and first["reviewed_by"]
    assert body["items"][1]["candidates"] == []
    assert body["clients_scanned"] >= 6

    limited = await client.get(f"{BASE}/sector-guides/missing?limit=1", headers=ops)
    assert [i["label_key"] for i in limited.json()["items"]] == ["gimnasio"]


async def test_reviewing_needs_an_operator_and_no_client_data(
    client: Any, db_session: AsyncSession, ops: dict[str, str], admin_headers: dict[str, str]
) -> None:
    tenant_id = await _client(db_session, "Gimnasio Norte", label="Gimnasio", phone="+34612345678")
    dirty = guide_doc()
    dirty["procedures"][0]["steps"] = (
        "Si duda, que llame al 612 345 678 o venga a Calle Mayor 12, Madrid."
    )
    dirty["ask"].append("¿Cómo se llama el gerente de Gimnasio Norte?")
    guide_id = await _guide(db_session, tenant_id, "Gimnasio", guide=dirty)
    url = f"{BASE}/generated-guides/{tenant_id}/{guide_id}"

    read = await client.get(url, headers=admin_headers)
    assert read.status_code == 200, read.text
    out = read.json()
    assert out["status"] == "generated" and out["promotable"] is False
    kinds = {(f["pointer"], f["kind"]) for f in out["client_data"]}
    assert ("/guide/procedures/0/steps", "phone") in kinds
    assert ("/guide/procedures/0/steps", "address") in kinds
    assert ("/guide/ask/2", "client_name") in kinds

    no_operator = await client.post(f"{url}/review", json={}, headers=admin_headers)
    assert no_operator.status_code == 400

    refused = await client.post(f"{url}/review", json={}, headers=ops)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "client_data_found"
    assert refused.json()["detail"]["findings"]
    async with tenant_scoped_session(db_session, tenant_id):
        row = await db_session.get(GeneratedGuide, guide_id, populate_existing=True)
        assert row is not None and row.status == "generated"

    bad_tests = await client.post(
        f"{url}/review", json={"guide": guide_doc(), "tests": twelve_tests()[:11]}, headers=ops
    )
    assert bad_tests.status_code == 422
    assert bad_tests.json()["detail"]["code"] == "twelve_tests_required"

    ok = await client.post(
        f"{url}/review",
        json={"guide": guide_doc(), "tests": twelve_tests(), "note": "Quitado el teléfono"},
        headers=ops,
    )
    assert ok.status_code == 200, ok.text
    done = ok.json()
    assert done["status"] == "reviewed" and done["promotable"] is True
    assert done["client_data"] == [] and done["reviewed_by"].startswith("operator:ops-guides-")
    async with tenant_scoped_session(db_session, tenant_id):
        audit = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "generated_guide.reviewed")
            )
        ).all()
    assert len(audit) == 1 and audit[0].tenant_id == tenant_id
    assert audit[0].after_json == {
        "status": "reviewed",
        "edited": True,
        "note": "Quitado el teléfono",
    }
    assert "test-admin-token" not in audit[0].actor


async def test_the_label_is_not_exempt_when_it_is_the_clients_own_name(
    client: Any, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30): la etiqueta del sector
    no cuenta como dato del cliente («Gimnasio» no ensucia todas las guías de
    gimnasios), salvo que sea el nombre del cliente o el de una de sus sedes: ahí es
    su nombre, y una guía de Auphere no lo lleva."""
    named = await _client(db_session, "Pilates Reformer", label="Pilates Reformer")
    dirty = guide_doc()
    dirty["ask"].append("¿Hay clases de Pilates Reformer los sábados?")
    guide_id = await _guide(db_session, named, "Pilates Reformer", guide=dirty)
    read = await client.get(f"{BASE}/generated-guides/{named}/{guide_id}", headers=admin_headers)
    assert read.status_code == 200, read.text
    assert ("/guide/ask/2", "client_name") in {
        (f["pointer"], f["kind"]) for f in read.json()["client_data"]
    }

    sede = await _client(db_session, "Grupo Norte", label="Yoga Aéreo")
    async with tenant_scoped_session(db_session, sede):
        db_session.add(BusinessLocation(tenant_id=sede, name="Yoga Aereo", address="Calle Sol 3"))
    dirty = guide_doc()
    dirty["ask"].append("¿Cuánto cuesta la clase de yoga aéreo?")
    guide_id = await _guide(db_session, sede, "Yoga Aéreo", guide=dirty)
    read = await client.get(f"{BASE}/generated-guides/{sede}/{guide_id}", headers=admin_headers)
    assert ("/guide/ask/2", "location") in {
        (f["pointer"], f["kind"]) for f in read.json()["client_data"]
    }

    # La etiqueta que no es el nombre de nadie sigue sin contar.
    plain = await _client(db_session, "Gimnasio Norte", label="Gimnasio")
    dirty = guide_doc()
    dirty["ask"].append("¿El gimnasio abre los domingos?")
    guide_id = await _guide(db_session, plain, "Gimnasio", guide=dirty)
    read = await client.get(f"{BASE}/generated-guides/{plain}/{guide_id}", headers=admin_headers)
    assert read.json()["client_data"] == []


async def test_converting_needs_it_reviewed_and_leaves_nothing_of_the_client(
    client: Any, db_session: AsyncSession, ops: dict[str, str]
) -> None:
    tenant_id = await _client(db_session, "Gimnasio Norte", label="Gimnasio")
    other = await _client(db_session, "Fit Sur", label="gimnasio")
    guide_id = await _guide(db_session, tenant_id, "Gimnasio")
    other_guide = await _guide(db_session, other, "gimnasio", status="reviewed")
    url = f"{BASE}/generated-guides/{tenant_id}/{guide_id}"
    body = {"key": "gimnasio", "label": "Gimnasio", "reason": "Siete clientes, revisada"}

    early = await client.post(f"{url}/promote", json=body, headers=ops)
    assert early.status_code == 409 and early.json()["detail"]["code"] == "guide_not_reviewed"
    assert (await client.post(f"{url}/review", json={}, headers=ops)).status_code == 200

    taken = await client.post(
        f"{url}/promote", json={**body, "key": "barberia_peluqueria"}, headers=ops
    )
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "guide_key_taken"
    other_key = await client.post(f"{url}/promote", json={**body, "key": "otro"}, headers=ops)
    assert other_key.json()["detail"]["code"] == "guide_key_taken"
    malformed = await client.post(f"{url}/promote", json={**body, "key": "Gym 1"}, headers=ops)
    assert malformed.status_code == 422

    done = await client.post(f"{url}/promote", json=body, headers=ops)
    assert done.status_code == 201, done.text
    out = done.json()
    assert out["key"] == "gimnasio" and out["source"] == "promoted" and out["version"] == 1
    assert out["tests"] == 12 and out["guide"]["ask"] == guide_doc()["ask"]

    async with db_session.begin():
        stored = (
            (
                await db_session.execute(
                    sa.text("SELECT * FROM sector_guides WHERE key = 'gimnasio'")
                )
            )
            .mappings()
            .one()
        )
        catalog = (
            await db_session.scalars(
                sa.select(SectorTestCatalog).where(SectorTestCatalog.sector_key == "gimnasio")
            )
        ).all()
        platform = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "sector_guide.promoted")
            )
        ).all()
    assert str(tenant_id) not in str(dict(stored)) and "Gimnasio Norte" not in str(dict(stored))
    assert [c.version for c in catalog] == [1] and len(catalog[0].tests) == 12
    assert len(platform) == 1 and platform[0].tenant_id is None
    assert str(tenant_id) not in str(platform[0].after_json)
    assert platform[0].after_json["reason"] == body["reason"]

    async with tenant_scoped_session(db_session, tenant_id):
        row = await db_session.get(GeneratedGuide, guide_id, populate_existing=True)
        assert row is not None and row.status == "promoted" and row.promoted_to == "gimnasio"
        client_audit = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "generated_guide.promoted")
            )
        ).all()
    assert len(client_audit) == 1

    again = await client.post(f"{url}/promote", json=body, headers=ops)
    assert again.json()["detail"]["code"] == "guide_already_promoted"
    same_label = await client.post(
        f"{BASE}/generated-guides/{other}/{other_guide}/promote",
        json={**body, "key": "gimnasios"},
        headers=ops,
    )
    assert same_label.status_code == 409
    assert same_label.json()["detail"]["code"] == "guide_label_taken"

    listed = (await client.get(f"{BASE}/sector-guides", headers=ops)).json()["items"]
    sources = {g["key"]: g["source"] for g in listed}
    assert sources["gimnasio"] == "promoted" and sources["barberia_peluqueria"] == "template"
    template = next(g for g in listed if g["key"] == "barberia_peluqueria")
    assert "barbershop_v1" in template["templates"] and template["tests"] == 12
    assert not [t for t in template["guide"]["tools"] if t.startswith("booking.")]
    missing = (await client.get(f"{BASE}/sector-guides/missing", headers=ops)).json()
    assert "gimnasio" not in {i["label_key"] for i in missing["items"]}


async def test_the_promoted_copy_is_checked_again_for_client_data(
    client: Any, db_session: AsyncSession, ops: dict[str, str]
) -> None:
    """Revisada ayer, con un dato del cliente puesto después: convertir lo vuelve a
    comprobar y no escribe nada."""
    tenant_id = await _client(db_session, "Gimnasio Norte", label="Gimnasio")
    dirty = copy.deepcopy(guide_doc())
    dirty["risks"].append("Escribe a info@gimnasionorte.es si hay una lesión")
    guide_id = await _guide(db_session, tenant_id, "Gimnasio", status="reviewed", guide=dirty)
    resp = await client.post(
        f"{BASE}/generated-guides/{tenant_id}/{guide_id}/promote",
        json={"key": "gimnasio", "label": "Gimnasio", "reason": "Revisada"},
        headers=ops,
    )
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "client_data_found"
    async with db_session.begin():
        assert not (await db_session.execute(sa.text("SELECT 1 FROM sector_guides"))).first()


async def test_a_guide_is_read_only_under_its_own_client(
    client: Any, db_session: AsyncSession, ops: dict[str, str]
) -> None:
    a = await _client(db_session, "Gimnasio Norte", label="Gimnasio")
    b = await _client(db_session, "Fit Sur", label="Gimnasio")
    b_guide = await _guide(db_session, b, "Gimnasio")
    crossed = await client.get(f"{BASE}/generated-guides/{a}/{b_guide}", headers=ops)
    assert crossed.status_code == 404 and crossed.json()["detail"]["code"] == "unknown_guide"
    nobody = await client.get(f"{BASE}/generated-guides/{uuid.uuid4()}/{b_guide}", headers=ops)
    assert nobody.status_code == 404
    review = await client.post(
        f"{BASE}/generated-guides/{a}/{b_guide}/review", json={}, headers=ops
    )
    assert review.status_code == 404
