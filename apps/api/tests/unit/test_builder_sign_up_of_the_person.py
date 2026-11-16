"""Spec 047, enmienda del 2026-11-16 (requisito 70) — el constructor y el alta de la
persona del turno (spec 061, requisito 3).

En staging, «Anfitriones Quédate» salió sin ``quedate.register_me`` en la tarea de
alta y con una regla que copió del prompt del constructor: «No envíes teléfono, nombre
o documento de un cliente final como argumentos…». El agente se negaba a dar de alta a
quien escribe. Lo que se comprueba sin modelo:

- **70.1**: el prompt distingue buscar a otra persona de escribir los datos que la
  persona del turno da de sí misma.
- **70.2**: el catálogo del constructor marca justo las herramientas del inventario de
  la garantía 8 (``SERVER_SIDE_ARGS``), y la marca no habla del teléfono.
- **70.3**: no enseña lo que el constructor no puede poner (``quedate.create_host``, las
  de operador). Si el modelo lo elegía, el saneado lo quitaba y la tarea de alta se
  quedaba sin herramienta.
- **70.4**: el saneado quita la regla de staging si el borrador da de alta a la persona,
  y deja la que prohíbe buscar a otra.
- **70.5**: ``register_me``, con sus argumentos de verdad, se queda en la tarea de alta.

Lo que haga el modelo de verdad con el prompt nuevo se comprueba regenerando el agente
en staging, no aquí.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from nexus_api.services.agent_spec.validator import (
    SERVER_SIDE_ARGS,
    Context,
    ToolInfo,
    validate_spec,
)
from nexus_api.services.builder.agent_draft import (
    OWN_DATA_MARK,
    PROMPT_FILE,
    DraftRequest,
    build_messages,
    forbids_own_data,
    sanitize,
)
from nexus_api.services.business.compilation import Facts

pytestmark = [pytest.mark.unit]

#: Lo que el catálogo de la plataforma tiene de Quédate (migración 0233).
QUEDATE: dict[str, Any] = json.loads(
    (Path(__file__).parents[2] / "alembic/data/0233_quedate_tools.json").read_text("utf-8")
)

#: La regla que escribió el constructor en staging, tal cual.
STAGING_RULE = (
    "No envíes teléfono, nombre o documento de un cliente final como argumentos de "
    "ninguna herramienta."
)
SEARCH_RULE = "No busques a otra persona por su teléfono con ninguna herramienta."

FACTS = Facts(name="Prueba Quédate 061")


def _ctx(*, connected: bool = True) -> Context:
    quedate = {
        name: ToolInfo(
            name,
            integration="quedate",
            connected=connected,
            activatable=True,
            args=frozenset(spec["input_schema"].get("properties") or {}),
        )
        for name, spec in QUEDATE.items()
    }
    return Context(
        tools={
            **quedate,
            "escalate.escalate_to_human": ToolInfo(
                "escalate.escalate_to_human", args=frozenset({"conversation_id", "reason"})
            ),
            "payments.request_review": ToolInfo(
                "payments.request_review",
                args=frozenset({"conversation_id", "customer_name", "amount"}),
            ),
            # De operador: busca a un cliente por su teléfono o su documento.
            "billing.find_client": ToolInfo(
                "billing.find_client", args=frozenset({"phone", "document"})
            ),
        }
    )


def _request() -> DraftRequest:
    return DraftRequest.clean(
        "Anfitriones Quédate",
        "Da de alta en Quédate a quien escribe porque quiere alquilar su casa, le manda "
        "el enlace para verificar su identidad y le ayuda a crear su anuncio.",
    )


def _catalog(ctx: Context) -> dict[str, str]:
    """Las líneas de <herramientas> que recibe el modelo, por herramienta."""
    content = build_messages(_request(), FACTS, ctx)[1]["content"]
    block = re.search(r"<herramientas>\n(.*?)\n</herramientas>", content, re.S)
    assert block is not None
    lines = {}
    for line in block.group(1).splitlines():
        name = re.match(r"- ([^ ]+) ", line)
        assert name is not None, line
        lines[name.group(1)] = line
    return lines


def _raw(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "instructions": [
            {"title": "Cómo atiendes", "body": "Ayudas a quien quiere alquilar su casa."}
        ],
        "tools": [
            "quedate.register_me",
            "quedate.my_host",
            "quedate.my_verification_link",
            "escalate.escalate_to_human",
        ],
        "procedures": [
            {
                "id": "alta",
                "title": "Dar de alta a la anfitriona",
                "when": "Cuando alguien quiere alquilar su casa en Quédate",
                "steps": (
                    "Pide su nombre y apellido, su documento, su fecha de nacimiento, su "
                    "sexo y su correo. Léele el correo y espera a que lo confirme. Dala de "
                    "alta y mándale el enlace para verificar su identidad."
                ),
                "tools": [
                    "quedate.register_me",
                    "quedate.my_host",
                    "quedate.my_verification_link",
                ],
            }
        ],
        "rules": [STAGING_RULE, SEARCH_RULE, "No ofrezcas descuentos."],
    }
    raw.update(changes)
    return raw


# ── 70.1: el prompt ──────────────────────────────────────────────────────────


def test_the_prompt_tells_searching_someone_from_writing_ones_own_data() -> None:
    prompt = PROMPT_FILE.read_text("utf-8")
    flat = " ".join(prompt.split())
    assert "Ninguna herramienta puede recibir el teléfono, el nombre o el documento" not in flat, (
        "la prohibición sin excepción es la que el modelo copió como regla"
    )
    assert OWN_DATA_MARK in flat, "el prompt explica la marca del catálogo"


# ── 70.2 y 70.3: el catálogo del constructor ─────────────────────────────────


def test_the_catalog_marks_exactly_the_tools_that_write_the_persons_own_data() -> None:
    ctx = _ctx()
    lines = _catalog(ctx)
    marked = {name for name, line in lines.items() if OWN_DATA_MARK in line}
    inventory = {tool for tool, _arg in SERVER_SIDE_ARGS if tool in ctx.tools}
    assert inventory == {"quedate.register_me", "payments.request_review"}
    assert marked == inventory
    assert "teléfono" not in OWN_DATA_MARK, "el teléfono sale del canal (061, 3.2)"


def test_the_catalog_does_not_show_what_the_builder_cannot_put() -> None:
    lines = _catalog(_ctx())
    assert "quedate.register_me" in lines and "quedate.my_host" in lines
    assert "quedate.create_host" not in lines, "es de equipo y el constructor la quita"
    assert "billing.find_client" not in lines, "busca a un cliente por su teléfono"


# ── 70.4 y 70.5: el saneado ──────────────────────────────────────────────────


@pytest.mark.parametrize("connected", [True, False], ids=["conectada", "sin conectar"])
def test_the_sign_up_stays_in_its_task_and_the_rule_against_it_leaves(connected: bool) -> None:
    ctx = _ctx(connected=connected)
    draft = sanitize(_raw(), _request(), ctx, FACTS, model_policy=None)
    spec = draft.spec
    assert "quedate.register_me" in (spec.tools or [])
    alta = {p.id: p for p in spec.procedures or []}["alta"]
    assert alta.tools is not None and "quedate.register_me" in alta.tools
    assert spec.rules == [SEARCH_RULE, "No ofrezcas descuentos."]
    assert draft.dropped_tools == []
    if not connected:
        assert [c["integration"] for c in draft.connect] == ["quedate"]
    # Validará igual al guardarse.
    _spec, problems = validate_spec(spec, ctx, author="builder")
    assert problems == []


def test_without_a_tool_that_writes_it_the_rule_is_not_touched() -> None:
    raw = _raw(tools=["quedate.my_host", "escalate.escalate_to_human"], procedures=[])
    draft = sanitize(raw, _request(), _ctx(), FACTS, model_policy=None)
    assert STAGING_RULE in (draft.spec.rules or [])


@pytest.mark.parametrize(
    "text",
    [
        STAGING_RULE,
        "Nunca pases el nombre ni el documento de la persona a una herramienta.",
        "No uses su correo ni su cédula como argumento.",
        "No envíes datos personales del cliente a las herramientas.",
        "No le pases el documento a ninguna herramienta.",
        "No debes enviar el correo de la persona como argumento.",
    ],
)
def test_a_rule_against_passing_the_persons_data_to_tools_is_found(text: str) -> None:
    assert forbids_own_data(text)


@pytest.mark.parametrize(
    "text",
    [
        SEARCH_RULE,
        "Nunca uses una herramienta para buscar a otro cliente por su nombre.",
        "No pidas el documento por WhatsApp si ya lo mandó.",
        "No ofrezcas descuentos.",
        "Pide siempre el nombre y el correo antes de usar la herramienta de alta.",
        "",
        # Las que ordenan el alta en vez de prohibirla se quedan (spec 061, 3.3).
        "No llames a la herramienta de alta sin el correo confirmado.",
        "No uses la herramienta de alta hasta tener nombre, documento y correo.",
        "Si no tienes el documento, pídelo antes de usar la herramienta.",
        "No inventes el nombre ni el correo que pasas a la herramienta.",
        "No envíes el documento a la herramienta sin que ella lo confirme.",
        "Nunca pases a la herramienta un correo que no te haya confirmado.",
    ],
)
def test_other_rules_are_not_taken_for_it(text: str) -> None:
    """Solo se quita la que prohíbe pasar el dato. La que pone una condición al alta
    (el correo confirmado, tener los datos antes) la protege y se queda."""
    assert not forbids_own_data(text)
