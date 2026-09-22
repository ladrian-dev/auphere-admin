"""Garantía 8 — el barrido: ninguna herramienta deja que el modelo elija persona.

`test_35` cubre el eje de reservas con clientes de verdad: dos filas del mismo
tenant, y lo de una no se ve desde la otra. Cubre el sitio donde se vio el
defecto, y solo ese.

Esto es lo otro que hacía falta. `test_35` enumera **cuatro modelos a mano**, y
una herramienta nueva —o una vieja en un servidor en el que nadie miró— no
aparece en esa lista. El barrido no enumera: recorre lo que cada vertical
semilla pone de verdad en la whitelist, y pregunta a cada firma si acepta que le
digan a quién mirar.

La superficie que importa es ésa y no el registro entero. Una herramienta solo
es alcanzable por un cliente final si algún vertical la puso en su whitelist;
el registro tiene 58, y la mayoría no las ve nadie desde WhatsApp.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from nexus_mcp import build_default_registry

SEEDS = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src"
    / "nexus_api"
    / "services"
    / "templating"
    / "seeds"
)

# Un argumento que nombra a una persona. No es una lista de nombres prohibidos
# por estética: es que cualquiera de estos, en una herramienta que un cliente
# final alcanza, le entrega al modelo el eje que la RLS no cubre.
CUSTOMER_AXIS = frozenset(
    {
        "customer",
        "customer_id",
        "customer_email",
        "customer_phone",
        "client_id",
        "patient_id",
        "debtor_id",
    }
)

# Verticales que NO son de cara al cliente final: el turno lo abre el personal
# del negocio, así que «mira lo de esta persona» es su trabajo, no una fuga.
# Se declaran aquí, una por una y con motivo, para que añadir uno sea una
# decisión visible y no un descuido.
OPERATOR_FACING = {
    # La propia semilla lo declara: «El agente NO habla con clientes finales:
    # es el asistente de INVENTARIO del personal del negocio. Solo los
    # teléfonos en ``policies.admin_access.admin_phones`` reciben respuesta».
    "inventario_v1": "el dispatcher solo le contesta al personal del negocio",
}


def _seed_files() -> list[pathlib.Path]:
    return sorted(SEEDS.glob("*.yaml"))


def _whitelisted(seed: pathlib.Path) -> list[str]:
    data = yaml.safe_load(seed.read_text()) or {}
    tools = data.get("tools") or {}
    return [*(tools.get("required") or []), *(tools.get("optional") or [])]


def test_the_sweep_actually_sweeps_something():
    """Un barrido sobre una lista vacía pasa siempre.

    Si los seeds se mueven de sitio o cambian de forma, esto lo dice en vez de
    dar un verde que no significa nada.
    """
    seeds = _seed_files()
    assert len(seeds) >= 10, f"solo {len(seeds)} verticales; ¿se movió el directorio?"
    assert any(_whitelisted(s) for s in seeds), "ningún vertical declara herramientas"


@pytest.mark.parametrize("seed", _seed_files(), ids=lambda p: p.stem)
def test_no_customer_facing_tool_lets_the_model_name_a_person(seed):
    if seed.stem in OPERATOR_FACING:
        pytest.skip(f"{seed.stem}: {OPERATOR_FACING[seed.stem]}")

    registry = build_default_registry()
    defs = {d.name: d for d in registry.get_tool_definitions(registry.names())}

    offenders: list[tuple[str, list[str]]] = []
    for name in _whitelisted(seed):
        tool_def = defs.get(name)
        if tool_def is None:
            continue  # la herramienta no existe aún; eso lo dice otro test
        props = (tool_def.parameters or {}).get("properties") or {}
        named = sorted(CUSTOMER_AXIS.intersection(props))
        if named:
            offenders.append((name, named))

    assert not offenders, (
        f"{seed.stem} deja que el modelo elija persona: {offenders}. "
        "El cliente del turno lo resuelve el servidor (garantía 8)."
    )
