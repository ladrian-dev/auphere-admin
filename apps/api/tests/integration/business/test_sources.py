"""Spec 047, T070 — documentos, webs y redes del negocio (historia 17, requisito 12).

``/console/clients/{ref}/business/sources`` y ``PUT …/links``
(``contracts/console-api.md`` §3), con el indexado en segundo plano: subir o
añadir una fuente responde ``202`` y la lee el trabajo ``client_read`` del worker
(el de verdad, con un modelo y una visión de mentira).

- **Subir**: archivos de hasta 10 MB, con su estado (leyendo, leído, no se pudo
  leer con el motivo), su tamaño y su fecha.
- **Quitar**: deja de usarse desde el siguiente mensaje, con deshacer de 10 min.
- **Releer**: cada semana y con «Volver a leer»; los cambios llegan como propuestas.
- **Redes**: con su enlace y su usuario.
- **Precios en un documento**: se proponen como servicios, sin tocar los que hay.
- **Fotos de cartas**: se leen con visión y se miden en «Construcción y pruebas».
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job, KnowledgeDocument
from nexus_api.db.models.business import BusinessChange, BusinessSuggestion
from nexus_api.services.business.profile_edits import update_policies
from nexus_api.services.business.sections import Actor
from nexus_api.services.knowledge_indexer import MAX_UPLOAD_BYTES
from nexus_api.services.media_storage import InMemoryMediaStorage
from nexus_api.services.media_storage.storage import set_media_storage

from ..clients._client_world import new_client, roomy, tenant_of
from ..clients._reader_world import FakeExtractor, fake_dns  # noqa: F401 - fixture

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.usefixtures("fake_dns")]

PRICES = {
    "services": [
        {"name": "Corte de pelo", "duration_min": 30, "price_amount": 15, "currency": "EUR"},
        {"name": "Arreglo de barba", "duration_min": 20, "price_amount": 9.5, "currency": "EUR"},
    ]
}


@dataclass
class FakeVision:
    """El modelo con visión, de mentira: devuelve el texto de la carta y anota
    su consumo como el proveedor con el rol ``vision`` (tarea ``vision``)."""

    text: str = "CARTA · Corte de pelo 15 € · Arreglo de barba 9,50 €"
    calls: list[tuple[int, str]] = field(default_factory=list)

    async def __call__(self, data: bytes, mime: str) -> str:
        from nexus_worker.metering.collector import record_llm_usage

        self.calls.append((len(data), mime))
        record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage={"prompt_tokens": 900, "completion_tokens": 120},
            task="vision",
        )
        return self.text


@pytest.fixture(autouse=True)
def storage() -> Any:
    store = InMemoryMediaStorage()
    set_media_storage(store)
    yield store
    set_media_storage(None)


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


async def _cultor(client: Any, db_session: AsyncSession, world: dict[str, Any]) -> dict[str, Any]:
    a = world["a"]
    created = await new_client(
        client,
        a["headers"](),
        name="Barbería Cultor",
        niche="Barbería de barrio",
        country="ES",
        price_currency="EUR",
    )
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    return {
        "ref": created["ref"],
        "tenant_id": tenant_id,
        "base": f"/console/clients/{created['ref']}/business",
    }


async def _run(fake_redis: Any, extract: FakeExtractor, vision: FakeVision | None = None) -> int:
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_read import make_client_read_handler

    registry = JobRegistry()
    registry.register(
        "client_read",
        make_client_read_handler(
            extractor_factory=lambda _t: extract,
            vision_factory=(lambda _t: vision) if vision is not None else None,
        ),
        timeout_s=60,
    )
    return await drain_once(fake_redis, registry=registry, store=DbJobStore())


async def _proposed_services(
    db_session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, tuple[int | None, str]]:
    """Los servicios propuestos y pendientes de una persona: ``nombre → (precio, fuente)``.
    Como sugerencia al lado (``/services/-``) o ya en Servicios, marcados «revísalo»."""
    from nexus_api.db.models import ReservationService
    from nexus_api.db.models.business import BusinessFieldProvenance

    out: dict[str, tuple[int | None, str]] = {}
    async with tenant_scoped_session(db_session, tenant_id):
        for s in (
            await db_session.scalars(
                sa.select(BusinessSuggestion).where(
                    BusinessSuggestion.pointer == "/services/-",
                    BusinessSuggestion.decision.is_(None),
                )
            )
        ).all():
            price = (s.proposed_value.get("price") or {}).get("amount_minor")
            out[s.proposed_value["name"]] = (price, s.source)
        pending = {
            p.pointer: p.source
            for p in (
                await db_session.scalars(
                    sa.select(BusinessFieldProvenance).where(
                        BusinessFieldProvenance.review == "pending",
                        BusinessFieldProvenance.pointer.like("/services/%"),
                    )
                )
            ).all()
        }
        for svc in (await db_session.scalars(sa.select(ReservationService))).all():
            source = pending.get(f"/services/{svc.id}")
            if source is not None:
                out[svc.name] = (svc.price_minor, source)
    return out


async def _sources(client: Any, headers: dict[str, str], base: str) -> dict[str, Any]:
    resp = await client.get(f"{base}/sources", headers=headers)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _upload(
    client: Any, headers: dict[str, str], base: str, name: str, data: bytes, mime: str
) -> Any:
    return await client.post(f"{base}/sources", files={"file": (name, data, mime)}, headers=headers)


# ── subir, con su estado, su tamaño y su fecha ──────────────────────────────


async def test_a_document_is_read_in_the_background_and_its_prices_become_proposals(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    data = b"Lista de precios\n\nCorte de pelo: 15 EUR\nArreglo de barba: 9,50 EUR\n"
    resp = await _upload(client, a["headers"](), c["base"], "precios.txt", data, "text/plain")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["source"]["status"] == "reading"
    assert body["source"]["size_bytes"] == len(data)
    assert body["source"]["title"] == "precios.txt" and body["source"]["kind"] == "file"
    assert body["job_id"]
    # Responde sin haberlo leído: indexar es un trabajo, no la petición.
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        doc = await db_session.get(KnowledgeDocument, uuid.UUID(body["source"]["id"]))
        assert doc is not None and doc.status == "pending" and doc.content_text is None

    extract = FakeExtractor(reply=PRICES)
    # La fuente y la identificación del sector que el alta dejó en cola (57.2).
    assert await _run(fake_redis, extract) == 2
    listed = await _sources(client, a["headers"](), c["base"])
    (item,) = listed["items"]
    assert item["status"] == "read" and item["failure"] is None
    assert item["read_at"] is not None and item["size_bytes"] == len(data)
    assert "content_text" not in json.dumps(listed) and "Arreglo" not in json.dumps(listed)
    # El texto le llegó al modelo vallado como dato, y los precios son propuestas
    # pendientes de revisar: una sugerencia o un servicio «Leído · revísalo».
    assert "Corte de pelo: 15 EUR" in extract.prompt
    proposed = await _proposed_services(db_session, c["tenant_id"])
    assert proposed == {"Corte de pelo": (1500, "document"), "Arreglo de barba": (950, "document")}
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        doc = await db_session.get(KnowledgeDocument, uuid.UUID(item["id"]), populate_existing=True)
    assert (
        doc is not None and doc.status == "indexed" and "Corte de pelo" in (doc.content_text or "")
    )
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        job = await db_session.get(Job, uuid.UUID(body["job_id"]))
    assert job is not None and job.status == "done" and job.kind == "client_read"
    assert job.result is not None and job.result["source_id"] == item["id"]
    assert job.result["suggested"] + job.result["applied"] == 2


async def test_too_large_or_unreadable_files_say_why(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    big = await _upload(
        client,
        a["headers"](),
        c["base"],
        "enorme.pdf",
        b"x" * (MAX_UPLOAD_BYTES + 1),
        "application/pdf",
    )
    assert big.status_code == 413 and big.json()["detail"]["code"] == "too_large"
    exe = await _upload(
        client, a["headers"](), c["base"], "virus.exe", b"MZ", "application/x-msdownload"
    )
    assert exe.status_code == 415 and exe.json()["detail"]["code"] == "unsupported_type"

    empty = await _upload(client, a["headers"](), c["base"], "vacio.txt", b"   \n", "text/plain")
    assert empty.status_code == 202
    await _run(fake_redis, FakeExtractor(reply={}))
    (item,) = (await _sources(client, a["headers"](), c["base"]))["items"]
    assert (item["status"], item["failure"]) == ("failed", "no_text")


async def test_a_word_document_is_read_too(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Corte de pelo 15 EUR</w:t></w:r></w:p></w:body></w:document>",
        )
    a = world["a"]
    c = await _cultor(client, db_session, world)
    resp = await _upload(
        client,
        a["headers"](),
        c["base"],
        "tarifas.docx",
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert resp.status_code == 202, resp.text
    extract = FakeExtractor(reply=PRICES)
    await _run(fake_redis, extract)
    (item,) = (await _sources(client, a["headers"](), c["base"]))["items"]
    assert item["status"] == "read"
    assert "Corte de pelo 15 EUR" in extract.prompt


async def test_a_photo_of_a_menu_is_read_with_vision_and_metered_in_build(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    photo = b"\xff\xd8\xff\xe0" + b"jpeg" * 100
    resp = await _upload(client, a["headers"](), c["base"], "carta.jpg", photo, "image/jpeg")
    assert resp.status_code == 202, resp.text
    vision = FakeVision()
    extract = FakeExtractor(reply=PRICES)
    await _run(fake_redis, extract, vision)
    assert vision.calls == [(len(photo), "image/jpeg")]
    (item,) = (await _sources(client, a["headers"](), c["base"]))["items"]
    assert item["status"] == "read"
    assert "Arreglo de barba 9,50" in extract.prompt

    entries = await fake_redis.xrange("nexus:usage")
    (fields,) = [e[1] for e in entries]
    from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE

    assert USAGE_LINE_BY_SOURCE[fields["source"]] == "build"
    assert {e["task"] for e in json.loads(fields["events"])} == {"read_source", "vision"}
    # La visión y la extracción, las dos en la misma partida.
    assert sum(1 for e in json.loads(fields["events"]) if e["meter"] == "llm.input_tokens") == 2


# ── webs ────────────────────────────────────────────────────────────────────


async def test_a_web_page_is_read_and_a_dead_one_says_unreachable(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    ok = await client.post(
        f"{c['base']}/sources",
        json={"url": "https://cultorbarber.com/precios"},
        headers=a["headers"](),
    )
    assert ok.status_code == 202, ok.text
    assert ok.json()["source"]["kind"] == "web" and ok.json()["source"]["status"] == "reading"
    dead = await client.post(
        f"{c['base']}/sources",
        json={"url": "https://cultorbarber.com/vieja"},
        headers=a["headers"](),
    )
    assert dead.status_code == 202
    bad = await client.post(f"{c['base']}/sources", json={"url": "ftp://x"}, headers=a["headers"]())
    assert bad.status_code == 422

    with respx.mock(assert_all_called=False) as router:
        router.get("https://cultorbarber.com/precios").mock(
            return_value=httpx.Response(
                200, html="<html><body><p>Corte de pelo 15 EUR</p></body></html>"
            )
        )
        router.get("https://cultorbarber.com/vieja").mock(return_value=httpx.Response(404))
        await _run(fake_redis, FakeExtractor(reply=PRICES))
    items = {i["url"]: i for i in (await _sources(client, a["headers"](), c["base"]))["items"]}
    assert items["https://cultorbarber.com/precios"]["status"] == "read"
    assert (
        items["https://cultorbarber.com/vieja"]["status"],
        items["https://cultorbarber.com/vieja"]["failure"],
    ) == (
        "failed",
        "unreachable",
    )


async def test_rereading_brings_changes_as_proposals_never_overwrites(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        await update_policies(
            db_session,
            {"cancellation": "Avisa con 24 h."},
            actor=Actor(kind="partner_member", id=a["user_id"], origin="console"),
        )
    added = await client.post(
        f"{c['base']}/sources",
        json={"url": "https://cultorbarber.com/condiciones"},
        headers=a["headers"](),
    )
    source_id = added.json()["source"]["id"]
    page = "<html><body><p>Cancelaciones con 48 h.</p></body></html>"
    with respx.mock(assert_all_called=False) as router:
        router.get("https://cultorbarber.com/condiciones").mock(
            return_value=httpx.Response(200, html=page)
        )
        await _run(fake_redis, FakeExtractor(reply={"policies": {"cancellation": "Con 48 h."}}))
        again = await client.post(f"{c['base']}/sources/{source_id}/reread", headers=a["headers"]())
        assert again.status_code == 202, again.text
        assert (await _sources(client, a["headers"](), c["base"]))["items"][0][
            "status"
        ] == "reading"
        await _run(fake_redis, FakeExtractor(reply={"policies": {"cancellation": "Con 48 h."}}))

    ficha = (await client.get(c["base"], headers=a["headers"]())).json()
    assert ficha["spec"]["policies"]["cancellation"] == "Avisa con 24 h."
    (proposal,) = [s for s in ficha["suggestions"] if s["pointer"] == "/policies/cancellation"]
    assert proposal["proposed_value"] == "Con 48 h." and proposal["source"] == "web"


# ── quitar, con deshacer de 10 minutos ──────────────────────────────────────


async def test_removing_a_source_stops_using_it_and_can_be_undone_for_ten_minutes(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    up = await _upload(
        client, a["headers"](), c["base"], "carta.txt", b"Menu del dia 12 EUR", "text/plain"
    )
    source_id = up.json()["source"]["id"]
    await _run(fake_redis, FakeExtractor(reply={}))

    gone = await client.post(f"{c['base']}/sources/{source_id}/remove", headers=a["headers"]())
    assert gone.status_code == 200, gone.text
    assert gone.json()["restore_until"]
    listed = await _sources(client, a["headers"](), c["base"])
    assert listed["items"] == []
    (removed,) = listed["removed"]
    assert removed["id"] == source_id and removed["title"] == "carta.txt"
    # Desde el siguiente mensaje: el turno lee los documentos indexados, y ya no está.
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        assert await db_session.get(KnowledgeDocument, uuid.UUID(source_id)) is None

    back = await client.post(f"{c['base']}/sources/{source_id}/restore", headers=a["headers"]())
    assert back.status_code == 200, back.text
    (item,) = (await _sources(client, a["headers"](), c["base"]))["items"]
    assert item["id"] == source_id and item["status"] == "read"
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        doc = await db_session.get(KnowledgeDocument, uuid.UUID(source_id), populate_existing=True)
    assert doc is not None and doc.content_text == "Menu del dia 12 EUR"

    # Pasados los 10 minutos ya no se recupera.
    again = await client.post(f"{c['base']}/sources/{source_id}/remove", headers=a["headers"]())
    assert again.status_code == 200
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        await db_session.execute(
            sa.update(BusinessChange)
            .where(BusinessChange.section == "sources", BusinessChange.undone_at.is_(None))
            .values(at=datetime.now(UTC) - timedelta(minutes=11))
        )
    late = await client.post(f"{c['base']}/sources/{source_id}/restore", headers=a["headers"]())
    assert late.status_code == 409 and late.json()["detail"]["code"] == "undo_window_closed"
    assert (await _sources(client, a["headers"](), c["base"]))["removed"] == []


# ── redes ──────────────────────────────────────────────────────────────────


async def test_social_profiles_keep_their_link_and_their_user(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    ficha = (await client.get(c["base"], headers=a["headers"]())).json()
    rev = next(s["revision"] for s in ficha["sections"] if s["section"] == "links")
    resp = await client.put(
        f"{c['base']}/links",
        json={
            "links": [
                {"network": "instagram", "handle": "@cultorbarber"},
                {"network": "tiktok", "url": "https://www.tiktok.com/@cultor.bcn"},
                {"network": "web", "url": "https://cultorbarber.com"},
            ]
        },
        headers={**a["headers"](), "If-Match": f'"{rev}"'},
    )
    assert resp.status_code == 200, resp.text
    links = {x["network"]: x for x in resp.json()["links"]}
    assert links["instagram"]["handle"] == "@cultorbarber"
    assert links["instagram"]["url"] == "https://www.instagram.com/cultorbarber"
    assert links["tiktok"]["handle"] == "@cultor.bcn"
    ficha = (await client.get(c["base"], headers=a["headers"]())).json()
    assert ficha["spec"]["business"]["website"] == "https://cultorbarber.com"
    bad = await client.put(
        f"{c['base']}/links",
        json={"links": [{"network": "instagram", "handle": "no vale"}]},
        headers={**a["headers"](), "If-Match": f'"{rev + 1}"'},
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_link"


async def test_another_partner_never_reaches_the_sources(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    c = await _cultor(client, db_session, world)
    resp = await client.get(f"{c['base']}/sources", headers=world["b"]["headers"]())
    assert resp.status_code == 404
    foreign = await client.post(
        f"{c['base']}/sources/{uuid.uuid4()}/remove", headers=world["a"]["headers"]()
    )
    assert foreign.status_code == 404
