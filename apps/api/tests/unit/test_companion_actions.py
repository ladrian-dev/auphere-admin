"""El cálculo de una propuesta y el ciclo de vida de una acción (CO-04).

Sin base de datos y sin red: el constructor de propuestas recibe una función
de lectura falsa, así que lo que se prueba aquí es la **aritmética** —el
diff, el hash, el impacto, los rechazos— y no el fontanero.

Lo que NO está aquí: la persistencia (``test_companion_action_graph.py``, con
dobles del puerto) y el ciclo entero por HTTP
(``tests/integration/test_companion_action_resume.py``).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexus_api.companion.tools.actions import (
    DECISION_STATUS,
    STATUS_PROPOSED,
    action_id_for,
    expires_at_of,
    is_stale,
    verify_action,
)
from nexus_api.companion.tools.proposals import (
    APPLY_ROUTES,
    IntakeRequired,
    ProposalBuilder,
    ProposalRefused,
    canonical_hash,
    line_diff,
    mask_email,
    split_list,
)

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload, default=str)

    def json(self) -> Any:
        return self._payload


def reader(routes: dict[str, Any]):
    """Una función de lectura de mentira: ruta → cuerpo (o (cuerpo, código))."""

    async def _read(path: str, params: dict[str, Any] | None = None) -> FakeResponse:
        if path not in routes:
            return FakeResponse({"detail": "Unknown client reference"}, 404)
        value = routes[path]
        if isinstance(value, tuple):
            return FakeResponse(value[0], value[1])
        return FakeResponse(value)

    return _read


ME = {
    "user_id": "u1",
    "role": "owner",
    "quota": {"max_clients": 10, "used_clients": 4, "remaining_clients": 6},
}


# ── piezas deterministas ───────────────────────────────────────────────


def test_the_action_id_is_the_same_every_time() -> None:
    """Es lo que hace idempotente la reejecución del nodo tras el
    ``interrupt()`` (C2). Un id aleatorio duplicaría la fila."""
    run = uuid.uuid4()
    assert action_id_for(run, 1) == action_id_for(run, 1)
    assert action_id_for(run, 1) != action_id_for(run, 2)
    assert action_id_for(run, 1) != action_id_for(uuid.uuid4(), 1)


def test_the_hash_ignores_key_order() -> None:
    """Dos serializaciones del mismo estado tienen que dar el mismo hash, o
    el 412 sería un sorteo."""
    assert canonical_hash({"a": 1, "b": [2, 3]}) == canonical_hash({"b": [2, 3], "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_the_diff_marks_additions_and_deletions() -> None:
    ops = line_diff("uno\ndos\ntres", "uno\nDOS\ntres")
    assert {"op": "del", "line": 2, "before": "dos"} in ops
    assert {"op": "add", "line": 2, "after": "DOS"} in ops
    assert all(op["op"] in {"add", "del", "ctx"} for op in ops)


def test_a_context_line_carries_the_same_text_on_both_sides() -> None:
    """El contrato lo fija así: ``ctx`` lleva ``before`` y ``after``
    iguales. La interfaz lo pinta sin resaltar."""
    ctx = [op for op in line_diff("a\nb\nc", "a\nb\nZ") if op["op"] == "ctx"]
    assert ctx and all(op["before"] == op["after"] for op in ctx)


def test_the_diff_is_bounded() -> None:
    """Un prompt reescrito entero no puede llenar el log durable ni la
    tarjeta."""
    before = "\n".join(f"linea {i}" for i in range(2000))
    after = "\n".join(f"otra {i}" for i in range(2000))
    assert len(line_diff(before, after)) <= 401


def test_an_email_is_masked_in_origin() -> None:
    assert mask_email("maria@facelad.com") == "m…a@facelad.com"
    assert mask_email("ab@x.com") == "a…@x.com"
    assert "@" in mask_email("a@b.co")
    # Nunca la parte local entera, que es lo que identifica a la persona.
    assert "maria" not in mask_email("maria@facelad.com")


def test_a_comma_list_is_cleaned_and_deduplicated() -> None:
    assert split_list(" a , b ,a, ") == ["a", "b"]
    assert split_list("") == []
    assert split_list(None) == []


def test_expiry_is_a_comparison_and_not_a_cron() -> None:
    class Row:
        status = STATUS_PROPOSED
        proposed_at = datetime.now(UTC) - timedelta(minutes=20)

    assert is_stale(Row(), 900)
    Row.proposed_at = datetime.now(UTC)
    assert not is_stale(Row(), 900)
    # Una acción ya decidida no caduca: su estado es terminal.
    Row.status = "confirmed"
    Row.proposed_at = datetime.now(UTC) - timedelta(days=1)
    assert not is_stale(Row(), 900)


def test_expires_at_is_the_only_source_of_the_countdown() -> None:
    at = datetime(2026, 8, 18, 14, 18, tzinfo=UTC)
    assert expires_at_of(at, 900) == datetime(2026, 8, 18, 14, 33, tzinfo=UTC)


def test_a_decision_maps_to_exactly_one_status() -> None:
    """``edit`` es ``superseded`` y no ``cancelled``: cancelar cierra el
    trabajo, editar lo continúa por otro camino."""
    assert DECISION_STATUS == {
        "confirm": "confirmed",
        "edit": "superseded",
        "cancel": "cancelled",
    }


# ── propuestas por kind ────────────────────────────────────────────────


async def test_a_prompt_proposal_diffs_against_the_editable_version() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/clients/boreal/agent": {
                    "active_version": 7,
                    "versions": [
                        {"version": 7, "status": "active", "system_prompt": "hola\nmundo"}
                    ],
                }
            }
        )
    )
    p = await build.build("prompt", {"client_ref": "boreal", "system_prompt": "hola\nplaneta"})

    assert p.kind == "prompt"
    assert p.reversible is True
    assert p.apply_path == "/console/clients/boreal/agent/versions"
    assert p.apply_body == {"system_prompt": "hola\nplaneta"}
    assert any(op["op"] == "add" and op["after"] == "planeta" for op in p.diff or [])
    # No publica, y el impacto lo dice: es lo que más se malinterpreta.
    assert {"key": "publishes", "value": "false", "severity": "info"} in p.impact
    # Los argumentos se guardan para poder revalidar el hash al confirmar.
    assert p.propose_args["system_prompt"] == "hola\nplaneta"


async def test_the_prompt_hash_changes_when_someone_else_edits_the_draft() -> None:
    """La deriva que el 412 tiene que atrapar, en su forma más común: dos
    personas del mismo partner sobre el mismo cliente."""
    before = {
        "/console/clients/boreal/agent": {
            "active_version": 7,
            "versions": [{"version": 7, "status": "active", "system_prompt": "uno"}],
        }
    }
    after = {
        "/console/clients/boreal/agent": {
            "active_version": 8,
            "versions": [{"version": 8, "status": "active", "system_prompt": "dos"}],
        }
    }
    args = {"client_ref": "boreal", "system_prompt": "nuevo"}
    first = await ProposalBuilder(read=reader(before)).build("prompt", args)
    second = await ProposalBuilder(read=reader(after)).build("prompt", args)
    assert first.state_hash != second.state_hash


async def test_an_empty_prompt_is_refused_with_something_the_model_can_fix() -> None:
    build = ProposalBuilder(read=reader({"/console/clients/b/agent": {"versions": []}}))
    with pytest.raises(ProposalRefused) as exc:
        await build.build("prompt", {"client_ref": "b", "system_prompt": "   "})
    assert exc.value.error.code == "bad_arguments"
    assert "completo" in exc.value.error.message


#: Un alta completa: los cuatro huecos del §7.1 rellenados.
FULL_CLIENT = {
    "client_ref": "boreal",
    "name": "Clínica Boreal",
    "timezone": "America/Caracas",
    "language": "es",
    "vertical": "aesthetic_clinic_v1",
    "forbidden_behaviour": "No dar precios por WhatsApp",
}


async def test_a_client_proposal_checks_the_quota_before_proposing() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/me": {**ME, "quota": {"max_clients": 4, "used_clients": 4}},
                "/console/clients": {"clients": []},
            }
        )
    )
    with pytest.raises(ProposalRefused) as exc:
        await build.build("client", {**FULL_CLIENT, "client_ref": "nuevo"})
    assert exc.value.error.code == "quota_exhausted"


async def test_a_client_proposal_is_marked_irreversible() -> None:
    build = ProposalBuilder(read=reader({"/console/me": ME, "/console/clients": {"clients": []}}))
    p = await build.build("client", FULL_CLIENT)
    assert p.reversible is False and p.risk == "high"
    assert {"key": "irreversible", "value": "true", "severity": "danger"} in p.impact
    assert p.preview["quota_used"] == 4 and p.preview["quota_max"] == 10


async def test_a_duplicate_client_ref_is_refused_before_the_router_sees_it() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/me": ME,
                "/console/clients": {"clients": [{"external_client_ref": "boreal"}]},
            }
        )
    )
    with pytest.raises(ProposalRefused) as exc:
        await build.build("client", FULL_CLIENT)
    assert exc.value.error.code == "already_exists"


# ── el expediente (§7.1) ───────────────────────────────────────────────


async def test_creating_a_client_asks_before_it_proposes() -> None:
    """No se avanza a planificar con campos vacíos. Rellenarlos con un valor
    plausible es el fallo caro: el alta es irreversible."""
    build = ProposalBuilder(read=reader({"/console/me": ME, "/console/clients": {"clients": []}}))
    with pytest.raises(IntakeRequired) as exc:
        await build.build("client", {"client_ref": "boreal", "name": "Clínica Boreal"})

    keys = [s["key"] for s in exc.value.slots]
    assert keys == ["vertical", "timezone", "language", "forbidden_behaviour"]
    for slot in exc.value.slots:
        assert slot["label"] and slot["why"]
        # Siempre lista, nunca ``null``: la interfaz la recorre sin
        # comprobar.
        assert isinstance(slot["examples"], list)
        assert slot["required"] is True


async def test_the_forbidden_behaviour_slot_is_asked_even_when_the_rest_is_there() -> None:
    """Es el campo que nadie escribe y el que causa los incidentes.
    Preguntarlo siempre cuesta diez segundos."""
    build = ProposalBuilder(read=reader({"/console/me": ME, "/console/clients": {"clients": []}}))
    args = {k: v for k, v in FULL_CLIENT.items() if k != "forbidden_behaviour"}
    with pytest.raises(IntakeRequired) as exc:
        await build.build("client", args)
    assert [s["key"] for s in exc.value.slots] == ["forbidden_behaviour"]


async def test_the_intake_answer_travels_with_the_provisioning() -> None:
    """Si se quedara fuera del alta, se perdería justo el dato por el que se
    preguntó."""
    build = ProposalBuilder(read=reader({"/console/me": ME, "/console/clients": {"clients": []}}))
    p = await build.build("client", FULL_CLIENT)
    assert p.apply_body["placeholders"]["forbidden_behaviour"] == "No dar precios por WhatsApp"
    assert p.apply_body["placeholders"]["language"] == "es"


async def test_a_plain_language_vertical_is_not_sent_as_a_template_reference() -> None:
    """El router solo acepta la referencia técnica. «Clínica estética» no lo
    es, y mandarla sería un 422 que nadie pidió."""
    build = ProposalBuilder(read=reader({"/console/me": ME, "/console/clients": {"clients": []}}))
    p = await build.build("client", {**FULL_CLIENT, "vertical": "Clínica estética"})
    assert "seed_template" not in p.apply_body
    assert p.preview["vertical"] == "Clínica estética"


async def test_a_tools_proposal_warns_about_what_it_turns_off() -> None:
    """Activar, como mucho, no se usa. Desactivar rompe algo que hoy
    funciona, y la severidad tiene que decirlo."""
    build = ProposalBuilder(
        read=reader(
            {
                "/console/clients/b/tools": {
                    "version": 3,
                    "tools": [
                        {"name": "a", "enabled": True},
                        {"name": "b", "enabled": True},
                        {"name": "c", "enabled": False},
                    ],
                }
            }
        )
    )
    p = await build.build("tools", {"client_ref": "b", "tools": "a,c"})
    assert p.apply_body == {"tools": ["a", "c"]}
    assert p.risk == "medium"
    warn = next(i for i in p.impact if i["key"] == "turning_off")
    assert warn["severity"] == "warn" and warn["value"] == "1"


async def test_an_unknown_tool_is_refused_with_the_names_to_use() -> None:
    build = ProposalBuilder(
        read=reader({"/console/clients/b/tools": {"tools": [{"name": "a", "enabled": True}]}})
    )
    with pytest.raises(ProposalRefused) as exc:
        await build.build("tools", {"client_ref": "b", "tools": "a,inventada"})
    assert exc.value.error.code == "bad_arguments"
    assert "inventada" in exc.value.error.message


async def test_proposing_the_current_state_is_refused_instead_of_staged() -> None:
    """Una tarjeta de confirmación que no cambia nada le hace perder el
    tiempo a una persona. Se corta antes."""
    build = ProposalBuilder(
        read=reader({"/console/clients/b/skills": {"skills": [{"name": "a", "enabled": True}]}})
    )
    with pytest.raises(ProposalRefused) as exc:
        await build.build("skills", {"client_ref": "b", "skills": "a"})
    assert exc.value.error.code == "no_change"


async def test_a_publish_proposal_pins_the_version_in_the_path() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/clients/b/agent": {
                    "active_version": 7,
                    "versions": [
                        {"version": 7, "status": "active", "system_prompt": "viejo"},
                        {"version": 8, "status": "staged", "system_prompt": "nuevo"},
                    ],
                }
            }
        )
    )
    p = await build.build("publish", {"client_ref": "b", "version": 8})
    assert p.apply_path == "/console/clients/b/agent/versions/8/publish"
    assert p.preview["from_version"] == 7 and p.preview["to_version"] == 8
    # Honesto: en la Ola 1 el Companion no sabe ejecutar evals.
    assert p.preview["evals_run"] is False and p.preview["evals_warning"]
    assert p.expectations == {"active_version": "8"}


async def test_publishing_the_active_version_is_refused() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/clients/b/agent": {
                    "active_version": 8,
                    "versions": [{"version": 8, "status": "active", "system_prompt": "x"}],
                }
            }
        )
    )
    with pytest.raises(ProposalRefused) as exc:
        await build.build("publish", {"client_ref": "b", "version": 8})
    assert exc.value.error.code == "no_change"


async def test_a_channel_role_hashes_every_channel_and_not_just_the_one() -> None:
    """El impacto de etiquetar un canal depende de cómo estén etiquetados
    los demás, así que un diff calculado con uno y aplicado con dos es un
    diff mentiroso."""
    one = str(uuid.uuid4())
    two = str(uuid.uuid4())
    args = {"client_ref": "b", "channel_id": one, "role": "agent"}
    solo = await ProposalBuilder(
        read=reader({"/console/clients/b/channels": [{"id": one, "role": None}]})
    ).build("channel_role", args)
    paired = await ProposalBuilder(
        read=reader(
            {
                "/console/clients/b/channels": [
                    {"id": one, "role": None},
                    {"id": two, "role": None},
                ]
            }
        )
    ).build("channel_role", args)

    assert solo.state_hash != paired.state_hash
    assert paired.apply_path.endswith(f"/channels/{one}/role")
    # Con dos canales y uno sin etiquetar, la plataforma rechaza el envío:
    # el aviso tiene que salir ANTES de dejar al cliente ahí.
    assert any(i["key"] == "channels_unlabelled_after" for i in paired.impact)


async def test_usage_alert_recipients_are_masked_in_the_preview() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/usage/alerts": {
                    "cap_messages_month": 1000,
                    "recipients": ["viejo@x.com"],
                    "enabled": True,
                }
            }
        )
    )
    p = await build.build(
        "usage_alerts", {"cap_messages_month": 5000, "recipients": "maria@facelad.com"}
    )
    assert p.preview["recipients_masked"] == ["m…a@facelad.com"]
    assert "maria@facelad.com" not in json.dumps(p.preview)
    assert p.apply_body["recipients"] == ["maria@facelad.com"]


async def test_a_policy_proposal_only_touches_the_fields_it_was_given() -> None:
    build = ProposalBuilder(
        read=reader(
            {
                "/console/clients/b/agent/settings": {
                    "version": 3,
                    "settings": {
                        "objective": "viejo",
                        "languages": {"primary": "es", "allowed": ["es"]},
                        "escalation": {"enabled": True, "triggers": ["angry"]},
                    },
                }
            }
        )
    )
    p = await build.build("policy", {"client_ref": "b", "objective": "nuevo"})
    assert p.apply_body["settings"]["objective"] == "nuevo"
    # Lo que no se pasó queda EXACTAMENTE como estaba: un PUT que sustituye
    # el objeto entero con los defaults borraría la configuración del
    # cliente sin que nadie lo pidiera.
    assert p.apply_body["settings"]["escalation"] == {"enabled": True, "triggers": ["angry"]}
    assert p.apply_body["settings"]["languages"]["allowed"] == ["es"]


async def test_the_policy_tool_cannot_reach_the_ai_disclosure() -> None:
    """§6.5: desactivar la revelación de IA está prohibido, y la forma de
    garantizarlo es que el campo no exista en el mapa."""
    from nexus_api.companion.tools.proposals import POLICY_FIELDS

    assert not any("ai_disclosure" in path for path in POLICY_FIELDS.values())


# ── verificación determinista (C5) ─────────────────────────────────────


class Row:
    def __init__(self, kind: str, payload: dict[str, Any]) -> None:
        self.id = uuid.uuid4()
        self.kind = kind
        self.payload = payload


async def test_verification_rereads_and_compares() -> None:
    action = Row(
        "publish",
        {"client_ref": "b", "expectations": {"active_version": "8"}, "apply": {}},
    )
    result = await verify_action(
        reader({"/console/clients/b/agent": {"active_version": 8}}), action
    )
    assert result["ok"] is True
    assert result["checks"] == [
        {"name": "active_version", "expected": "8", "actual": "8", "ok": True}
    ]


async def test_verification_says_no_when_the_platform_disagrees() -> None:
    """Y no se presenta como fallo del usuario: puede ser alucinación o un
    fallo real de la plataforma, y las dos cosas hay que mirarlas."""
    action = Row(
        "publish",
        {"client_ref": "b", "expectations": {"active_version": "8"}, "apply": {}},
    )
    result = await verify_action(
        reader({"/console/clients/b/agent": {"active_version": 7}}), action
    )
    assert result["ok"] is False
    assert result["checks"][0]["actual"] == "7"


async def test_an_unreadable_resource_is_a_failed_check_and_not_a_green_one() -> None:
    """Un «no lo sé» presentado como verde es peor que no verificar."""
    action = Row(
        "publish", {"client_ref": "b", "expectations": {"active_version": "8"}, "apply": {}}
    )
    result = await verify_action(reader({}), action)
    assert result["ok"] is False
    assert result["checks"][0]["actual"] == "unreadable"


async def test_verification_values_are_always_strings() -> None:
    """Para que ``8`` y ``"8"`` no se pinten distinto y ningún float
    redondee delante de alguien que decide sobre un negocio."""
    action = Row(
        "tools",
        {"client_ref": "b", "expectations": {"tools_enabled": "2"}, "apply": {}},
    )
    result = await verify_action(
        reader(
            {
                "/console/clients/b/tools": {
                    "tools": [{"name": "a", "enabled": True}, {"name": "b", "enabled": True}]
                }
            }
        ),
        action,
    )
    for check in result["checks"]:
        assert isinstance(check["expected"], str) and isinstance(check["actual"], str)


def test_every_kind_has_a_verification_read() -> None:
    """Un ``kind`` sin relectura pasaría de largo y su tabla saldría vacía
    sin que nadie lo notara."""
    from nexus_api.companion.tools.actions import VERIFY_READS
    from nexus_api.companion.tools.catalog import ACTION_KINDS

    assert set(VERIFY_READS) == set(ACTION_KINDS) == set(APPLY_ROUTES)
