"""El catálogo de herramientas del Companion, como contrato (CO-02).

Un catálogo declarativo se puede recorrer, y eso es la mitad de su valor:
las reglas del paquete —ninguna acepta ``tenant_id``, todas son de lectura,
toda descripción dice cuándo llamar— dejan de ser convenciones y pasan a
ser cuatro bucles sobre una tabla.

Lo que NO se prueba aquí es la ejecución: eso es
``test_companion_tools_runner.py`` (con dobles) y
``tests/isolation/test_companion_tool_scope.py`` (contra la app real).
"""

from __future__ import annotations

import pytest

from nexus_api.companion.tools.catalog import READ_TOOLS, TOOLS_BY_NAME, tool_specs

pytestmark = pytest.mark.unit

#: Los nombres del §6.1. Está escrito a mano a propósito: si alguien quita
#: una herramienta, este test se pone rojo en vez de encogerse en silencio.
EXPECTED = {
    "console.whoami",
    "console.list_clients",
    "console.get_client",
    "console.get_agent",
    "console.get_policy",
    "console.list_tools",
    "console.list_skills",
    "console.list_knowledge",
    "console.list_channels",
    "console.channel_diagnostics",
    "console.list_templates",
    "console.get_usage",
    "console.usage_series",
    "console.conversation_stats",
    "console.get_audit",
    "console.get_onboarding",
    "console.get_quota",
    "console.get_wallet",
    "console.list_allocations",
    "console.get_prompt_library",
    # CO-08 §5: el documento de capacidades se LEE, no se hornea en el
    # prompt. Que sea una herramienta más es lo que hace que dejar cita y
    # dejar ``tool.call.started`` salga gratis.
    "console.get_capabilities",
}


def test_the_catalogue_is_exactly_the_read_surface_of_6_1() -> None:
    """CO-04 amplió ``TOOLS_BY_NAME`` con propuesta y ejecución, así que la
    comprobación se hace sobre ``READ_TOOLS``, que es de quien habla el §6.1.
    El resto del catálogo tiene su propia lista escrita a mano en
    ``tests/isolation/test_companion_action_guarantees.py``."""
    assert {t.name for t in READ_TOOLS} == EXPECTED


def test_every_tool_is_read_only() -> None:
    """CO-02 no trae ni una escritura, "ni siquiera preparada". Las de
    propuesta y ejecución llegan en CO-04 por la única puerta
    ``console.apply``."""
    for tool in READ_TOOLS:
        assert tool.method == "GET", tool.name
        assert "propose" not in tool.name and "apply" not in tool.name


def test_no_tool_takes_an_internal_identifier() -> None:
    """Regla CP-04, heredada: el cliente se nombra por la referencia del
    partner y el router la resuelve bajo el principal."""
    for tool in READ_TOOLS:
        for param in tool.params:
            assert param.name not in {"tenant_id", "partner_id"}, tool.name


def test_the_client_parameter_is_always_called_client_ref() -> None:
    """Un solo nombre en todo el catálogo. Dos nombres para lo mismo es
    exactamente el tipo de detalle que hace que un modelo se equivoque."""
    for tool in READ_TOOLS:
        for param in tool.params:
            assert param.name != "ref", tool.name
        if tool.needs_client:
            assert any(p.name == "client_ref" and p.required for p in tool.params), tool.name


def test_names_are_namespaced_and_unique() -> None:
    assert len({t.name for t in READ_TOOLS}) == len(READ_TOOLS)
    for tool in READ_TOOLS:
        assert tool.name.startswith("console."), tool.name


# ── descripciones prescriptivas ────────────────────────────────────────


@pytest.mark.parametrize("tool", READ_TOOLS, ids=lambda t: t.name)
def test_the_description_says_when_to_call_it(tool) -> None:
    """La guía de migración a Opus 5 mide mejora real con descripciones
    prescriptivas: modelos recientes tiran poco de herramientas por defecto,
    y una descripción que solo dice QUÉ hace no dispara nada."""
    lowered = tool.description.lower()
    assert "llama a esto" in lowered or "úsalo" in lowered, f"{tool.name} no dice cuándo llamarla"


@pytest.mark.parametrize("tool", READ_TOOLS, ids=lambda t: t.name)
def test_the_description_says_when_not_to(tool) -> None:
    """El cuándo-no es lo que evita que el modelo use la herramienta
    equivocada para una pregunta parecida."""
    lowered = tool.description.lower()
    assert any(
        marker in lowered
        for marker in (
            "no lo uses",
            "no la uses",
            "no lo confundas",
            "no confundas",
            "no inventes",
            "no cites",
            "no existe",
        )
    ), f"{tool.name} no dice cuándo NO usarla"


@pytest.mark.parametrize("tool", READ_TOOLS, ids=lambda t: t.name)
def test_the_description_is_long_enough_to_be_useful(tool) -> None:
    """Tres o cuatro frases mínimo. Una línea no cabe ni la condición de
    disparo ni el cuándo-no."""
    assert len(tool.description) >= 240, tool.name
    assert tool.description.count(".") >= 3, tool.name


# ── el esquema que ve el proveedor ─────────────────────────────────────


def test_the_provider_schema_is_well_formed() -> None:
    # En modo *Consultar* se publican SOLO las lecturas: es el catálogo de
    # CO-02 intacto, y comprobarlo aquí fija de paso que el modo del hilo
    # recorta de verdad lo que el modelo puede pedir.
    specs = tool_specs(mode="consult")
    assert len(specs) == len(READ_TOOLS)
    for spec in specs:
        fn = spec["function"]
        params = fn["parameters"]
        assert spec["type"] == "function"
        assert params["additionalProperties"] is False
        assert set(params["required"]) <= set(params["properties"])
        for prop in params["properties"].values():
            assert prop["type"] in {"string", "integer", "boolean"}
            assert prop["description"]


def test_a_required_client_ref_is_required_in_the_schema() -> None:
    schema = TOOLS_BY_NAME["console.get_agent"].json_schema()
    assert schema["required"] == ["client_ref"]


def test_partner_wide_tools_take_no_client():
    """``whoami``, ``onboarding`` y la cuota son del PARTNER. Pedirles un
    cliente sería inventarse un ámbito que no tienen."""
    for name in ("console.whoami", "console.get_onboarding", "console.get_quota", "console.get_wallet", "console.list_allocations"):
        assert TOOLS_BY_NAME[name].params == (), name
