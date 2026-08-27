"""Las garantías E4, E7 y E8 de la Ola 2 (CO-08).

Tres afirmaciones que, si dejan de ser ciertas, no se ven mirando la
pantalla:

- **E4** · ``console.apply`` sigue siendo la **única** ``mutates`` del
  catálogo **con las dos herramientas de soporte dentro**. Es la garantía
  que el escalado a soporte podía romper sin que nadie lo notara: mandar un
  ticket es escribir, y la tentación de hacerlo "directo, que es solo un
  correo" es exactamente el atajo que abriría una segunda puerta.
- **E7** · ``GET /console/audit?client=<ajeno>`` y ``<inexistente>`` dan el
  **mismo** 404, en la lista y en la exportación. Antes daban 200 con la
  lista vacía, que para el Companion es una afirmación falsa **con
  respaldo** — la que R1 no marca, porque sí hubo lectura.
- **E8** · con ``companion_enabled = false``: 403 ``companion_disabled`` al
  escribir, **200 al leer un hilo que ya existe**. Apagar la bandera no
  puede hacer desaparecer la historia de lo que ya pasó.

Y, de paso, el guardián del documento de capacidades: una entrada inventada
es una promesa rota con el cliente de un partner, así que el fichero se
valida como código.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.companion.tools.catalog import ALL_TOOLS, PROPOSE_TOOLS, TOOLS_BY_NAME
from nexus_api.companion.tools.proposals import APPLY_ROUTES
from nexus_api.companion.tools.support import (
    CAPABILITY_FAMILIES,
    CAPABILITY_STATUSES,
    SLAS,
    SUPPORT_KINDS,
    TOPIC_FAMILIES,
    load_capabilities,
    normalise_topic,
    sla_for,
)

pytestmark = [pytest.mark.isolation]


# ── E4 · la puerta de escritura sigue siendo una ───────────────────────


def test_support_tools_propose_and_do_not_write() -> None:
    """E4. Las dos de soporte son ``propose``; la única ``mutates`` en todo
    el catálogo sigue siendo ``console.apply``."""
    mutating = [t.name for t in ALL_TOOLS if t.tool_class == "mutates"]
    assert mutating == ["console.apply"], mutating

    for name in ("support.request_help", "support.request_capability"):
        spec = TOOLS_BY_NAME[name]
        assert spec.tool_class == "propose", name
        assert spec.permission_policy == "always_ask", name
        assert spec.method == "GET", f"{name} no escribe: lee para componer el expediente"
        assert spec.kind in SUPPORT_KINDS, name


def test_the_support_kinds_apply_through_the_closed_map() -> None:
    """El destino sale del ``kind``, no de un argumento del modelo: no hay
    forma de redirigir un ticket a otro endpoint."""
    for kind in SUPPORT_KINDS:
        method, path = APPLY_ROUTES[kind]
        assert (method, path) == ("POST", "/console/support/tickets"), kind
    assert {t.kind for t in PROPOSE_TOOLS} >= set(SUPPORT_KINDS)


def test_the_support_endpoint_exists_and_is_a_post() -> None:
    from nexus_api.main import app

    routes = {
        (getattr(r, "path", None), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or set())
    }
    assert ("/console/support/tickets", "POST") in routes
    assert ("/console/capabilities", "GET") in routes
    support = {
        (path, method) for path, method in routes if path and path.startswith("/console/support")
    }
    assert support == {("/console/support/tickets", "POST")}
    assert ("/console/support/tickets", "GET") not in routes
    assert ("/admin/tickets", "GET") in routes
    assert ("/admin/tickets/{ticket_id}", "GET") in routes
    assert ("/admin/tickets/{ticket_id}", "PATCH") in routes
    assert ("/admin/tickets", "POST") not in routes


def test_the_support_tools_accept_no_tenant_or_partner_id() -> None:
    for name in ("support.request_help", "support.request_capability"):
        params = {p.name for p in TOOLS_BY_NAME[name].params}
        assert not (params & {"tenant_id", "partner_id", "tenant", "partner"}), name
        # Y tampoco ``sla``: la expectativa la decide el motor. Si fuera un
        # argumento, el modelo prometería plazos que Auphere no ha dado.
        assert "sla" not in params, name


def test_the_apply_echo_is_a_closed_whitelist_and_lets_nothing_else_through() -> None:
    """C8 sobre el camino nuevo. ``APPLY_ECHO`` es lo único de la respuesta
    de aplicar que se guarda, y se guarda **por clave y por kind**: si
    guardara el cuerpo entero, el día que un endpoint devolviera un campo de
    texto de un cliente final acabaría en ``companion.actions.result`` y de
    ahí en un evento, sin que nadie lo decidiera."""
    from nexus_api.companion.tools.actions import APPLY_ECHO, apply_echo

    assert set(APPLY_ECHO) == set(SUPPORT_KINDS)
    for keys in APPLY_ECHO.values():
        assert set(keys) == {"ticket_ref", "sla", "category", "topic"}

    smuggled = (
        '{"ticket_ref": "AU-7", "sla": "best_effort", "category": "help", '
        '"topic": "connector.shopify", "message": "hola, queria reservar cita", '
        '"content": "...", "notes": ["..."]}'
    )
    kept = apply_echo("support_help", smuggled)
    assert kept == {
        "ticket_ref": "AU-7",
        "sla": "best_effort",
        "category": "help",
        "topic": "connector.shopify",
    }
    # Y un ``kind`` sin entrada no guarda nada, ni siquiera lo inocuo.
    assert apply_echo("prompt", smuggled) == {}


def test_the_pilot_counters_have_the_names_the_contract_fixed() -> None:
    """§11: los nombres los fija el contrato para que no se renombren a
    mitad del piloto y la serie se parta en dos."""
    from nexus_api.core.otel_metrics import COMPANION_COUNTERS, record_companion

    assert set(COMPANION_COUNTERS) == {
        "companion.thread.opened",
        "companion.task.completed",
        "companion.hitl.proposed",
        "companion.hitl.cancelled",
        "companion.turn.total",
        "companion.turn.unsupported",
        "companion.verify.total",
        "companion.verify.failed",
    }
    # Y registrar nunca lanza, ni con un nombre inventado: la
    # instrumentacion no puede tumbar un turno.
    record_companion("companion.turn.total")
    record_companion("no.existe")


def test_operational_counters_live_outside_the_frozen_contract() -> None:
    """Las metricas de SALUD no entran en el vocabulario del piloto.

    Si entraran, el test de arriba habria que editarlo cada vez que se
    instrumenta algo — y un guardian que se edita por rutina deja de guardar.
    La separacion es lo que permite anadir observabilidad sin tocar el
    contrato congelado del §11.
    """
    from nexus_api.core.otel_metrics import (
        COMPANION_COUNTERS,
        COMPANION_OPS_COUNTERS,
        record_companion,
    )

    assert "companion.cas.revalidate_failed" in COMPANION_OPS_COUNTERS
    assert not set(COMPANION_COUNTERS) & set(COMPANION_OPS_COUNTERS)
    # Y el registrador acepta las dos familias.
    record_companion("companion.cas.revalidate_failed")


# ── el documento de capacidades como código ────────────────────────────


def test_the_capability_document_parses_and_every_entry_is_valid() -> None:
    document = load_capabilities(force=True)
    assert document.version
    assert document.entries
    for entry in document.entries:
        assert entry.family in CAPABILITY_FAMILIES, entry.key
        assert entry.status in CAPABILITY_STATUSES, entry.key
        assert entry.key.startswith(f"{entry.family}."), entry.key
        if entry.status == "planned":
            # §5.2: ``planned`` autoriza a decir que llega **con** ``eta``.
            # Sin ella, "está planificado" es una fecha implícita que nadie
            # dio.
            assert entry.eta, f"{entry.key}: planned sin eta"
        if entry.status == "retired":
            assert entry.replaced_by, f"{entry.key}: retired sin replaced_by"


def test_the_document_seeds_what_the_model_would_hallucinate() -> None:
    """§5.2, las tres que el contrato nombra por su nombre."""
    document = load_capabilities(force=True)
    widget = document.get("capability.embed_widget")
    assert widget is not None and widget.status == "retired"
    assert set(widget.replaced_by) == {"api", "mcp"}

    for key in ("connector.tiktok_bm", "channel.tiktok"):
        entry = document.get(key)
        assert entry is not None and entry.status == "out_of_scope", key
        assert entry.note, key  # "y por qué" no es opcional en out_of_scope

    for key in ("capability.evals_console", "connector.stripe"):
        entry = document.get(key)
        assert entry is not None and entry.status == "planned", key


def test_capability_keys_share_the_namespace_of_topic() -> None:
    """§5.2: ``key`` y ``topic`` son el mismo espacio. Es lo que permite
    cruzar "qué pidieron" con "qué dijimos que había"; si divergieran, la
    agregación del §25.2 no serviría para nada."""
    document = load_capabilities(force=True)
    for entry in document.entries:
        assert normalise_topic(entry.key) == entry.key, entry.key
        assert entry.family in TOPIC_FAMILIES, entry.key


def test_the_sla_is_one_of_three_stable_identifiers() -> None:
    assert sla_for("capability", "connector.shopify") == "best_effort"
    assert sla_for("help", "platform.outage") == "business_hours"
    assert sla_for("help", "quota.clients") == "business_hours"
    assert sla_for("help", "connector.shopify") == "next_business_day"
    for category in ("help", "capability"):
        for family in (*TOPIC_FAMILIES, "other"):
            assert sla_for(category, f"{family}.x") in SLAS


def test_an_unknown_topic_family_lands_in_other_instead_of_being_refused() -> None:
    """Rechazar un ticket por una discusión de taxonomía sería el "no" que
    §25 existe para evitar. Una fila en ``other.*`` es un dato."""
    assert normalise_topic("Necesito Shopify ya!!") == "other.necesito_shopify_ya"
    assert normalise_topic("connector.shopify") == "connector.shopify"
    assert normalise_topic("") == "other.unspecified"
    assert normalise_topic("weird.family.thing").startswith("other.")


# ── E7 · el filtro por cliente de la auditoría ─────────────────────────


async def test_audit_by_foreign_client_ref_is_the_same_404_as_a_missing_one(
    client, console_world
) -> None:
    """E7. Y el cuerpo tiene que ser **idéntico**: si difiriera, el llamante
    podría distinguir "es de otro" de "no existe" y la auditoría sería un
    oráculo sobre la cartera de la competencia."""
    a, b = console_world["a"], console_world["b"]
    foreign = await client.get(f"/console/audit?client={b['ref']}", headers=a["headers"]())
    missing = await client.get("/console/audit?client=no-existe", headers=a["headers"]())
    assert foreign.status_code == 404, foreign.text
    assert (foreign.status_code, foreign.json()) == (missing.status_code, missing.json())

    # Y en la exportación, que es la otra mitad del cabo: un CSV vacío con
    # 200 diría lo mismo que el 200 vacío que se acaba de cerrar.
    foreign_csv = await client.get(
        f"/console/audit/export.csv?client={b['ref']}", headers=a["headers"]()
    )
    missing_csv = await client.get(
        "/console/audit/export.csv?client=no-existe", headers=a["headers"]()
    )
    assert foreign_csv.status_code == 404, foreign_csv.text
    assert (foreign_csv.status_code, foreign_csv.json()) == (
        missing_csv.status_code,
        missing_csv.json(),
    )


async def test_audit_by_own_client_ref_still_answers(client, console_world) -> None:
    """El control del control: el 404 es del ámbito, no de haber roto el
    filtro."""
    a = console_world["a"]
    resp = await client.get(f"/console/audit?client={a['ref']}", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert "items" in resp.json()


# ── cabo 3 · la auditoría dice qué persona hay detrás del Companion ────


def test_the_companion_actor_never_renders_a_raw_identifier() -> None:
    from nexus_api.api.console.audit import _human_actor

    assert _human_actor("companion:user_a_1234") == "Companion"
    assert (
        _human_actor("companion:user_a_1234", {"user_a_1234": "maria@facelad.com"})
        == "Companion · maria@facelad.com"
    )
    # Un miembro de otro partner no está en el mapa (que se construye con el
    # partner del llamante), así que cae al genérico — nunca al uuid.
    assert _human_actor("companion:user_b_9999", {"user_a_1234": "maria@facelad.com"}) == (
        "Companion"
    )


async def test_the_email_map_is_scoped_to_the_callers_partner(client, console_world, db_session):
    from nexus_api.api.console.audit import partner_member_emails

    a, b = console_world["a"], console_world["b"]
    mapping = await partner_member_emails(db_session, a["partner_id"])
    assert mapping.get(a["user_id"]) == "owner-a@example.com"
    assert b["user_id"] not in mapping


# ── E8 · la bandera por partner ────────────────────────────────────────


async def _set_flag(db_session, partner_id: uuid.UUID, value: bool) -> None:
    from nexus_api.db.models import Partner

    async with db_session.begin():
        await db_session.execute(
            sa.update(Partner).where(Partner.id == partner_id).values(companion_enabled=value)
        )


async def test_without_the_flag_writes_are_403_and_reads_of_an_existing_thread_are_200(
    client, console_world, db_session
) -> None:
    """E8, entera. El orden importa: primero se crea el hilo **con** la
    bandera puesta, y solo después se apaga. Es el caso real —un piloto que
    se apaga— y es el único que puede probar que la historia sobrevive."""
    a = console_world["a"]
    created = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "antes de apagar", "mode": "consult"},
    )
    assert created.status_code == 201, created.text
    thread_id = created.json()["id"]

    await _set_flag(db_session, a["partner_id"], False)

    # Escrituras: 403 con el código estable que la interfaz mira.
    for method, path, body in (
        ("POST", "/console/companion/threads", {"title": "x", "mode": "build"}),
        ("PATCH", f"/console/companion/threads/{thread_id}", {"title": "y"}),
        ("POST", f"/console/companion/threads/{thread_id}/runs", {"prompt": "hola"}),
        (
            "POST",
            f"/console/companion/runs/{uuid.uuid4()}/resume",
            {"action_id": str(uuid.uuid4()), "decision": "confirm"},
        ),
    ):
        resp = await client.request(method, path, headers=a["headers"](), json=body)
        assert resp.status_code == 403, f"{method} {path} → {resp.status_code} {resp.text}"
        assert resp.json()["detail"]["code"] == "companion_disabled", resp.text

    # Lecturas del hilo que ya existe: 200. Apagar la bandera no borra lo
    # que pasó.
    listing = await client.get("/console/companion/threads", headers=a["headers"]())
    assert listing.status_code == 200, listing.text
    assert any(t["id"] == thread_id for t in listing.json())

    runs = await client.get(f"/console/companion/threads/{thread_id}/runs", headers=a["headers"]())
    assert runs.status_code == 200, runs.text

    budget = await client.get("/console/companion/budget", headers=a["headers"]())
    assert budget.status_code == 200, budget.text

    await _set_flag(db_session, a["partner_id"], True)


async def test_me_publishes_the_flag(client, console_world, db_session) -> None:
    """La interfaz monta la burbuja desde aquí. Sin este campo tendría que
    adivinar, y una burbuja que aparece y da 403 es peor que ninguna."""
    a = console_world["a"]
    me = await client.get("/console/me", headers=a["headers"]())
    assert me.status_code == 200
    assert me.json()["companion_enabled"] is True

    await _set_flag(db_session, a["partner_id"], False)
    me = await client.get("/console/me", headers=a["headers"]())
    assert me.json()["companion_enabled"] is False
    await _set_flag(db_session, a["partner_id"], True)


def test_no_support_read_or_write_scopes() -> None:
    from nexus_api.core.console_auth import PERMISSIONS

    assert "support:read" not in PERMISSIONS
    assert "support:write" not in PERMISSIONS
