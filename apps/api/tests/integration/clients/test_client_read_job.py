"""Spec 047, T044 — la lectura de la web en segundo plano (historia 4, requisito 5).

El alta lanza el trabajo ``client_read``; el worker lo corre y la ficha se
empieza a llenar sola. Con ``respx`` y páginas de prueba, y un DNS y un modelo
de mentira (``_reader_world``): nada sale a internet ni a un modelo real.

- **Límites**: hasta 25 páginas del mismo dominio, con ``robots.txt``, solo
  direcciones públicas y tamaño máximo.
- **Sin web**: los perfiles públicos de redes, si su ``robots.txt`` lo permite.
- **Resultado**: propone «Leído de la web · revísalo» sedes, horario, servicios,
  políticas y preguntas frecuentes.
- **Contradicciones**: lo que contradice un dato escrito por una persona queda
  como sugerencia, al lado del valor actual.
- **Idioma**: lo traducido va marcado «Traducido de {idioma}».
- **Fallos**: dice por qué (inalcanzable, bloqueada, sin texto o demasiado
  grande), se puede reintentar y el cliente sigue usable.
- **Medidor**: se mide en la partida «Construcción y pruebas».
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job, ReservationService
from nexus_api.db.models.business import (
    BusinessChange,
    BusinessFaq,
    BusinessFieldProvenance,
    BusinessLink,
    BusinessLocation,
    BusinessProfile,
    BusinessSection,
    BusinessSuggestion,
)
from nexus_api.services.business import hours as business_hours
from nexus_api.services.knowledge_indexer import MAX_URL_BYTES

from ._reader_world import (
    CULTOR_READ,
    FakeExtractor,
    create_client,
    fake_dns,  # noqa: F401 - fixture
    page,
    roomy,
    run_reader,
    scoped,
    tenant_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.usefixtures("fake_dns")]

SITE = "https://cultorbarber.com"


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


async def _cultor(client: Any, db_session: AsyncSession, world: dict[str, Any], **extra: Any):
    a = world["a"]
    body = {"name": "Barbería Cultor", "niche": "Barbería de barrio con 2 sedes"}
    body.update(extra)
    created = await create_client(client, a["headers"](), **body)
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    return created, tenant_id


async def _job(db_session: AsyncSession, tenant_id: uuid.UUID, job_id: str) -> Job:
    async with tenant_scoped_session(db_session, tenant_id):
        job = await db_session.scalar(
            sa.select(Job)
            .where(Job.id == uuid.UUID(job_id))
            .execution_options(populate_existing=True)
        )
    assert job is not None
    return job


def _home(
    links: list[str], text: str = "Bienvenido a Barbería Cultor, tu barbería de barrio."
) -> str:
    anchors = "".join(f'<a href="{href}">{href}</a> ' for href in links)
    return page(f"<header><nav>{anchors}</nav></header><main><p>{text}</p></main>")


def _site(router: respx.MockRouter, *, robots: str = "User-agent: *\nDisallow: /privado\n") -> None:
    router.get(f"{SITE}/robots.txt").mock(return_value=httpx.Response(200, text=robots))


# ── límites ────────────────────────────────────────────────────────────────


async def test_the_reading_stays_in_the_domain_respects_robots_and_stops_at_25(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    assert created["read_job_id"]

    many = [f"/pagina-{n}" for n in range(1, 41)]
    links = [
        "/servicios",
        "/horario",
        "/privado/precios-internos",  # robots.txt lo prohíbe
        "https://otrodominio.com/ofertas",  # otro dominio
        "http://intranet.cultorbarber.com/",  # otro nombre, y además privado
        "/redir-interna",  # redirige a una dirección privada
        "mailto:hola@cultorbarber.com",
        "tel:+34600123456",
        "#reservar",
        "/logo.png",
        *many,
    ]
    extract = FakeExtractor(reply=CULTOR_READ)
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        home = router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home(links)))
        services = router.get(f"{SITE}/servicios").mock(
            return_value=httpx.Response(200, html=page("<p>Corte de pelo 15 €. Barba 9,50 €.</p>"))
        )
        hours = router.get(f"{SITE}/horario").mock(
            return_value=httpx.Response(200, html=page("<p>Lunes 10 a 14 y 16 a 20.</p>"))
        )
        private = router.get(f"{SITE}/privado/precios-internos").mock(
            return_value=httpx.Response(200, html=page("<p>secreto</p>"))
        )
        foreign = router.get("https://otrodominio.com/ofertas").mock(
            return_value=httpx.Response(200, html=page("<p>otro</p>"))
        )
        intranet = router.get("http://intranet.cultorbarber.com/").mock(
            return_value=httpx.Response(200, html=page("<p>intranet</p>"))
        )
        router.get(f"{SITE}/redir-interna").mock(
            return_value=httpx.Response(302, headers={"location": "http://10.0.0.7/admin"})
        )
        internal = router.get("http://10.0.0.7/admin").mock(
            return_value=httpx.Response(200, html=page("<p>admin</p>"))
        )
        logo = router.get(f"{SITE}/logo.png").mock(return_value=httpx.Response(200, content=b"x"))
        pages = router.get(url__regex=rf"{SITE}/pagina-\d+").mock(
            return_value=httpx.Response(200, html=page("<p>Una página más de la barbería.</p>"))
        )
        assert await run_reader(fake_redis, extract) == 1

    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert job.status == "done", job.error_code
    assert home.called and services.called and hours.called
    assert not private.called, "robots.txt lo prohibía"
    assert not foreign.called, "otro dominio"
    assert not intranet.called, "otro nombre de host"
    assert not internal.called, "una dirección privada"
    assert not logo.called, "no es una página"
    fetched = home.call_count + services.call_count + hours.call_count + pages.call_count
    assert fetched == 25
    (web,) = job.result["sources"]
    assert (web["network"], web["status"], web["failure"], web["pages"]) == (
        "web",
        "read",
        None,
        25,
    )
    # Lo que el modelo lee va vallado: una página es un dato, nunca una orden.
    assert "<web_page" in extract.prompt
    assert "Corte de pelo 15 €" in extract.prompt


async def test_what_was_read_is_proposed_for_review(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    extract = FakeExtractor(reply=CULTOR_READ)
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(
            return_value=httpx.Response(
                200,
                html=_home(
                    ["/servicios", "https://www.instagram.com/cultorbarber"],
                    text="Corte 15 €. Abrimos de lunes a sábado.",
                ),
            )
        )
        router.get(f"{SITE}/servicios").mock(
            return_value=httpx.Response(200, html=page("<p>Corte de pelo 15 €.</p>"))
        )
        await run_reader(fake_redis, extract)

    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert job.status == "done", job.error_code
    assert job.result["found"] == {
        "locations": 2,
        "hours": 1,
        "services": 3,
        "policies": 2,
        "faqs": 1,
        "links": 1,
    }
    assert job.result["translated_from"] is None

    # Las políticas no chocan con nada: se aplican, marcadas «Leído de la web · revísalo».
    (profile,) = await scoped(db_session, tenant_id, sa.select(BusinessProfile))
    assert profile.policies == {
        "cancellation": "Avisa con 24 h de antelación.",
        "payments": "Tarjeta y efectivo.",
    }
    assert profile.content_rev > 1, "the agents compile again with what was read"
    provenance = {
        p.pointer: p
        for p in await scoped(db_session, tenant_id, sa.select(BusinessFieldProvenance))
    }
    cancel = provenance["/policies/cancellation"]
    assert (cancel.source, cancel.review, cancel.origin, cancel.actor_kind) == (
        "web",
        "pending",
        "system",
        "system",
    )
    assert cancel.source_url.startswith(SITE)

    # Sedes, horario, servicios y preguntas: nada chocaba, así que entran en la
    # ficha por el servicio de su sección (T056 a T058), marcados «revísalo».
    open_ = await scoped(
        db_session,
        tenant_id,
        sa.select(BusinessSuggestion).where(BusinessSuggestion.decision.is_(None)),
    )
    assert open_ == [], "nothing clashed: nothing waits as a suggestion"
    places = {
        loc.name: loc for loc in await scoped(db_session, tenant_id, sa.select(BusinessLocation))
    }
    assert set(places) == {"Cultor Centro", "Cultor Norte"}
    assert places["Cultor Centro"].phone_e164 == "+34600123456"
    async with tenant_scoped_session(db_session, tenant_id):
        week = await business_hours.load_week(db_session)
    assert week is not None
    assert week.days[0] == (
        business_hours.parse_shift("10:00", "14:00"),
        business_hours.parse_shift("16:00", "20:00"),
    )
    services = {
        s.name: s for s in await scoped(db_session, tenant_id, sa.select(ReservationService))
    }
    assert (services["Corte de pelo"].price_kind, services["Corte de pelo"].price_minor) == (
        "amount",
        1500,
    )
    assert services["Arreglo de barba"].price_minor == 950
    assert services["Corte de pelo"].bookable is True
    assert services["Corte de pelo"].duration_minutes == 30
    assert services["Cera para el pelo"].bookable is False
    assert services["Cera para el pelo"].duration_minutes is None
    (faq,) = await scoped(db_session, tenant_id, sa.select(BusinessFaq))
    assert faq.q == "¿Hay que pedir cita?"
    provenance = {
        p.pointer: p
        for p in await scoped(db_session, tenant_id, sa.select(BusinessFieldProvenance))
    }
    for pointer in (
        "/hours",
        f"/locations/{places['Cultor Centro'].id}",
        f"/services/{services['Corte de pelo'].id}",
        f"/faqs/{faq.id}",
    ):
        assert (provenance[pointer].source, provenance[pointer].review) == ("web", "pending")

    # La red que enlaza la web entra en la ficha, también para revisar.
    links = await scoped(db_session, tenant_id, sa.select(BusinessLink))
    assert ("instagram", "@cultorbarber") in {(link.network, link.handle) for link in links}

    states = {
        s.section: s.state for s in await scoped(db_session, tenant_id, sa.select(BusinessSection))
    }
    for section in ("locations", "hours", "services", "policies", "faqs"):
        assert states[section] == "read_pending", section
    changes = await scoped(
        db_session,
        tenant_id,
        sa.select(BusinessChange).where(BusinessChange.kind == "read_applied"),
    )
    assert {c.section for c in changes} >= {"policies", "locations", "hours", "services", "faqs"}


async def test_reading_again_does_not_repeat_the_proposals(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    extract = FakeExtractor(reply=CULTOR_READ)
    a = world["a"]
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home([])))
        await run_reader(fake_redis, extract)
        again = await client.post(
            f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
        )
        assert again.status_code == 202, again.text
        await run_reader(fake_redis, extract)
    # Lo mismo, leído otra vez: ni filas repetidas ni sugerencias.
    assert await scoped(db_session, tenant_id, sa.select(BusinessSuggestion)) == []
    assert len(await scoped(db_session, tenant_id, sa.select(BusinessLocation))) == 2
    assert len(await scoped(db_session, tenant_id, sa.select(ReservationService))) == 3
    assert len(await scoped(db_session, tenant_id, sa.select(BusinessFaq))) == 1


async def test_what_contradicts_hours_a_person_wrote_stays_a_suggestion(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    """T056: el horario que escribió una persona no se pisa con el de la web."""
    from nexus_api.services.business.sections import Actor

    _created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    luis = Actor(kind="partner_member", id=world["a"]["user_id"], origin="console")
    async with tenant_scoped_session(db_session, tenant_id):
        week = business_hours.week_from_days(
            "daily", {"mon": [{"open": "09:00", "close": "13:00"}]}
        )
        await business_hours.save_week(db_session, week, actor=luis)
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home([])))
        await run_reader(fake_redis, FakeExtractor(reply=CULTOR_READ))

    async with tenant_scoped_session(db_session, tenant_id):
        kept = await business_hours.load_week(db_session)
    assert kept == week, "the web overwrote the person's hours"
    (conflict,) = await scoped(
        db_session,
        tenant_id,
        sa.select(BusinessSuggestion).where(BusinessSuggestion.pointer == "/hours"),
    )
    assert conflict.proposed_value["days"]["mon"][0] == {"open": "10:00", "close": "14:00"}
    assert conflict.current_value["days"]["mon"] == [{"open": "09:00", "close": "13:00"}]


# ── contradicciones e idioma ───────────────────────────────────────────────


async def test_what_contradicts_a_person_stays_a_suggestion(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    _created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    # Luis escribió la política de cancelación antes de que la lectura terminara.
    async with tenant_scoped_session(db_session, tenant_id):
        profile = await db_session.get(BusinessProfile, tenant_id)
        assert profile is not None
        profile.policies = {"cancellation": "Avisa con 48 h."}
        db_session.add(
            BusinessFieldProvenance(
                tenant_id=tenant_id,
                pointer="/policies/cancellation",
                source="person",
                actor_kind="partner_member",
                actor_id=world["a"]["user_id"],
                origin="console",
                review="confirmed",
            )
        )
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home([])))
        await run_reader(fake_redis, FakeExtractor(reply=CULTOR_READ))

    (profile,) = await scoped(db_session, tenant_id, sa.select(BusinessProfile))
    assert profile.policies["cancellation"] == "Avisa con 48 h.", "se sobrescribió a una persona"
    assert profile.policies["payments"] == "Tarjeta y efectivo."
    (conflict,) = await scoped(
        db_session,
        tenant_id,
        sa.select(BusinessSuggestion).where(BusinessSuggestion.pointer == "/policies/cancellation"),
    )
    assert conflict.proposed_value == "Avisa con 24 h de antelación."
    assert conflict.current_value == "Avisa con 48 h."
    assert conflict.source == "web"
    provenance = {
        p.pointer: p
        for p in await scoped(db_session, tenant_id, sa.select(BusinessFieldProvenance))
    }
    assert provenance["/policies/cancellation"].source == "person"


async def test_what_was_translated_is_marked(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    english = {**CULTOR_READ, "source_language": "en"}
    extract = FakeExtractor(reply=english)
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(
            return_value=httpx.Response(200, html=_home([], text="Haircut 15 EUR. Open Mon-Sat."))
        )
        await run_reader(fake_redis, extract)

    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert job.result["translated_from"] == "en"
    provenance = {
        p.pointer: p
        for p in await scoped(db_session, tenant_id, sa.select(BusinessFieldProvenance))
    }
    assert provenance["/policies/payments"].translated_from == "en"
    read = [p for p in provenance.values() if p.source == "web"]
    assert {p.pointer.split("/")[1] for p in read} >= {"locations", "hours", "services", "faqs"}
    assert {p.translated_from for p in read} == {"en"}
    # Se le pidió al modelo que lo propusiera en el idioma del negocio.
    assert "español" in extract.prompt


# ── sin web: los perfiles públicos ───────────────────────────────────────────


async def test_without_a_web_the_public_profiles_are_read_when_allowed(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(
        client,
        db_session,
        world,
        info="@cultor.barber · https://www.tiktok.com/@cultorbarber",
    )
    assert created["read_job_id"]
    extract = FakeExtractor(
        reply={
            "source_language": "es",
            "faqs": [{"q": "¿Dónde estáis?", "a": "En la calle Mayor 1."}],
        }
    )
    with respx.mock(assert_all_called=False) as router:
        router.get("https://www.instagram.com/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        )
        insta = router.get("https://www.instagram.com/cultor.barber").mock(
            return_value=httpx.Response(200, html=page("<p>bio</p>"))
        )
        router.get("https://www.tiktok.com/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nAllow: /\n")
        )
        tiktok = router.get("https://www.tiktok.com/@cultorbarber").mock(
            return_value=httpx.Response(
                200,
                html=page(
                    "<div id='app'></div>",
                    head='<meta name="description" content="Barbería de barrio en Madrid. '
                    'Cita por WhatsApp.">',
                ),
            )
        )
        await run_reader(fake_redis, extract)

    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert job.status == "done", job.error_code
    assert not insta.called, "Instagram no lo permite: no se lee"
    assert tiktok.called
    sources = {s["network"]: s for s in job.result["sources"]}
    assert sources["instagram"]["status"] == "failed"
    assert sources["instagram"]["failure"] == "blocked"
    assert sources["tiktok"]["status"] == "read"
    assert "Barbería de barrio en Madrid" in extract.prompt
    (faq,) = await scoped(db_session, tenant_id, sa.select(BusinessFaq))
    assert faq.q == "¿Dónde estáis?"
    (read,) = await scoped(
        db_session,
        tenant_id,
        sa.select(BusinessFieldProvenance).where(
            BusinessFieldProvenance.pointer == f"/faqs/{faq.id}"
        ),
    )
    assert (read.source, read.review) == ("social", "pending")
    assert read.source_url == "https://www.tiktok.com/@cultorbarber"


# ── fallos ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("unreachable", "unreachable"),
        ("robots_all", "blocked"),
        ("forbidden", "blocked"),
        ("no_text", "no_text"),
        ("too_large", "too_large"),
    ],
)
async def test_a_failed_reading_says_why_and_the_client_stays_usable(
    client: Any,
    db_session: AsyncSession,
    world: dict[str, Any],
    fake_redis: Any,
    setup: str,
    code: str,
) -> None:
    a = world["a"]
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    extract = FakeExtractor(reply=CULTOR_READ)
    with respx.mock(assert_all_called=False) as router:
        if setup == "unreachable":
            router.get(f"{SITE}/robots.txt").mock(side_effect=httpx.ConnectError("down"))
            router.get(f"{SITE}/").mock(side_effect=httpx.ConnectError("down"))
        elif setup == "robots_all":
            _site(router, robots="User-agent: *\nDisallow: /\n")
            router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home([])))
        elif setup == "forbidden":
            _site(router)
            router.get(f"{SITE}/").mock(return_value=httpx.Response(403, text="Forbidden"))
        elif setup == "no_text":
            _site(router)
            router.get(f"{SITE}/").mock(
                return_value=httpx.Response(
                    200, html="<html><body><script>app()</script></body></html>"
                )
            )
        elif setup == "too_large":
            _site(router)
            router.get(f"{SITE}/").mock(
                return_value=httpx.Response(
                    200,
                    content=b"<p>" + b"a" * (MAX_URL_BYTES + 1) + b"</p>",
                    headers={"content-type": "text/html"},
                )
            )
        await run_reader(fake_redis, extract)

    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert (job.status, job.error_code) == ("failed", code)
    assert extract.calls == [], "con la lectura fallida no hay nada que extraer"

    # El cliente sigue usable, y la consola sabe qué pasó y puede reintentar.
    detail = await client.get(f"/console/clients/{created['ref']}", headers=a["headers"]())
    assert detail.status_code == 200
    card = await client.get(
        f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
    )
    assert card.status_code == 200, card.text
    assert card.json()["job"]["status"] == "failed"
    assert card.json()["job"]["error_code"] == code
    assert card.json()["website"] == "cultorbarber.com"
    retry = await client.post(
        f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
    )
    assert retry.status_code == 202, retry.text
    assert retry.json()["job_id"] != created["read_job_id"]


async def test_a_site_on_a_private_address_is_unreachable(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="interna.example")
    with respx.mock(assert_all_called=False) as router:
        hit = router.get(url__regex=r"https?://interna\.example.*").mock(
            return_value=httpx.Response(200, html=page("<p>dentro</p>"))
        )
        await run_reader(fake_redis, FakeExtractor(reply=CULTOR_READ))
    job = await _job(db_session, tenant_id, created["read_job_id"])
    assert (job.status, job.error_code) == ("failed", "unreachable")
    assert not hit.called


async def test_nothing_to_read_is_a_409(client: Any, world: dict[str, Any]) -> None:
    a = world["a"]
    created = await create_client(client, a["headers"](), name="Sin web", niche="Barbería")
    resp = await client.post(
        f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
    )
    assert resp.status_code == 409, resp.text
    card = await client.get(
        f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
    )
    assert card.json() == {"job": None, "website": None, "networks": []}


async def test_a_live_reading_is_not_started_twice(client: Any, world: dict[str, Any]) -> None:
    a = world["a"]
    created = await create_client(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería", info="cultorbarber.com"
    )
    again = await client.post(
        f"/console/clients/{created['ref']}/business/read", headers=a["headers"]()
    )
    assert again.status_code == 202
    assert again.json()["job_id"] == created["read_job_id"]


# ── el medidor ───────────────────────────────────────────────────────────


async def test_the_reading_is_metered_in_build_and_tests(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    created, tenant_id = await _cultor(client, db_session, world, info="cultorbarber.com")
    with respx.mock(assert_all_called=False) as router:
        _site(router)
        router.get(f"{SITE}/").mock(return_value=httpx.Response(200, html=_home([])))
        await run_reader(fake_redis, FakeExtractor(reply=CULTOR_READ))

    entries = await fake_redis.xrange("nexus:usage")
    assert entries, "la lectura no publicó su consumo"
    (fields,) = [e[1] for e in entries]
    assert fields["source"] == "reader"
    assert fields["tenant_id"] == str(tenant_id)
    assert "agent_id" not in fields and "conversation_id" not in fields
    events = json.loads(fields["events"])
    assert {e["task"] for e in events} == {"read_source"}
    assert {e["meter"] for e in events} == {"llm.input_tokens", "llm.output_tokens"}
    assert fields["turn_id"] == f"job:{created['read_job_id']}"

    from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE

    assert USAGE_LINE_BY_SOURCE[fields["source"]] == "build"


async def test_the_default_registry_knows_the_reading() -> None:
    from nexus_worker.jobs import default_registry

    spec = default_registry.get("client_read")
    assert spec is not None
    assert spec.timeout_s >= 300
