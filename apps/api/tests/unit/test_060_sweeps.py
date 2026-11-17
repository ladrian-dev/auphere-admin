"""Barridos de la spec 060 (T014): la regla de disponibilidad por partner no se
puede saltar por un camino nuevo (constitución §I: barrer, no enumerar).

1. **Las altas.** Toda construcción de ``TenantConnector(`` en ``apps/api/src`` está
   en una función que pasa por la regla (``_load_available_connector`` o
   ``ensure_connector_available``), o en la lista cerrada de abajo con su razón.
2. **Las lecturas de una conexión** fuera del API. Todo ``select(TenantConnector``
   en ``apps/mcp/src`` y ``apps/worker/src`` está en una función que llama a
   ``connection_is_available``, o en la lista cerrada con su razón.
3. **Los canales**: la lista fija de ``availability.CHANNEL_CONNECTORS`` coincide
   con los seeds que llevan ``channel_only``.

Una función nueva que cree o lea una conexión sin pasar por la regla pone esto en
rojo hasta que pase por ella o explique por qué no.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from nexus_api.services.connectors.availability import CHANNEL_CONNECTORS

ROOT = Path(__file__).resolve().parents[4]
API_SRC = ROOT / "apps/api/src"
OUTSIDE_API = (ROOT / "apps/mcp/src", ROOT / "apps/worker/src")

#: Altas que no pasan por la regla, con su razón.
CREATES_WITHOUT_RULE: dict[str, str] = {
    "bootstrap_webhook_manual": "Canales (WhatsApp, TikTok): la regla no los gestiona (1.5).",
}
CREATE_GUARDS = frozenset({"_load_available_connector", "ensure_connector_available"})

#: Lecturas de una conexión fuera del API que no pasan por la regla, con su razón.
READS_WITHOUT_RULE: dict[str, str] = {
    "load_blueprints_for_tenant": (
        "Construye los proxies de Composio a partir de filas de tool_catalog; antes de "
        "llegar al modelo pasan por activations.tool_policy, que aplica la regla "
        "(tests/isolation/test_060_connector_partner_access.py)."
    ),
    "_reconcile_tenant": (
        "Solo reconcilia el estado con Composio; no usa la conexión para nada del "
        "negocio, y mantenerlo al día es lo que deja todo intacto al rehabilitar (5.6)."
    ),
}
READ_GUARDS = frozenset({"connection_is_available"})

Fn = ast.FunctionDef | ast.AsyncFunctionDef


def _functions(path: Path) -> list[Fn]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]


def _calls(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            f = sub.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _innermost(path: Path, predicate: object) -> list[tuple[Fn, int]]:
    """Las funciones más internas cuyo cuerpo contiene un nodo que cumple ``predicate``.

    Devuelve el nodo y no el nombre: un ``Protocol`` declara el mismo método sin
    cuerpo, y buscarlo por nombre daba con la declaración (quedate/accounts.py).
    """
    found: list[tuple[Fn, int]] = []
    for fn in _functions(path):
        inner = [
            n
            for n in ast.walk(fn)
            if n is not fn and isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
        ]
        hits = [n for n in ast.walk(fn) if predicate(n)]  # type: ignore[operator]
        nested_hits = {id(h) for i in inner for h in ast.walk(i) if predicate(h)}  # type: ignore[operator]
        for h in hits:
            if id(h) not in nested_hits:
                found.append((fn, getattr(h, "lineno", 0)))
    return found


def _constructs_tenant_connector(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TenantConnector"
    )


def _selects_tenant_connector(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return (
        name == "select"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "TenantConnector"
    )


def test_every_connection_created_goes_through_the_rule() -> None:
    offenders: list[str] = []
    seen = 0
    for path in API_SRC.rglob("*.py"):
        for fn, line in _innermost(path, _constructs_tenant_connector):
            seen += 1
            if fn.name in CREATES_WITHOUT_RULE:
                continue
            if not (_calls(fn) & CREATE_GUARDS):
                offenders.append(f"{path.relative_to(ROOT)}:{line} ({fn.name})")
    assert seen >= 4, "barrido roto: no encuentra las altas"
    assert not offenders, "altas que no pasan por la regla de la spec 060:\n" + "\n".join(offenders)


def test_every_connection_read_outside_the_api_goes_through_the_rule() -> None:
    offenders: list[str] = []
    seen = 0
    for root in OUTSIDE_API:
        for path in root.rglob("*.py"):
            for fn, line in _innermost(path, _selects_tenant_connector):
                seen += 1
                if fn.name in READS_WITHOUT_RULE:
                    continue
                if not (_calls(fn) & READ_GUARDS):
                    offenders.append(f"{path.relative_to(ROOT)}:{line} ({fn.name})")
    assert seen >= 5, "barrido roto: no encuentra las lecturas"
    assert not offenders, "lecturas de una conexión sin la regla de la spec 060:\n" + "\n".join(
        offenders
    )


@pytest.mark.parametrize("guarded", [True, False], ids=["con la regla", "sin la regla"])
def test_a_protocol_with_the_same_name_does_not_hide_the_function(
    tmp_path: Path, guarded: bool
) -> None:
    """El barrido mira la función que lee, no la primera con ese nombre: en
    quedate/accounts.py el ``Protocol`` declara ``require_connection`` antes que la
    implementación, y la tubería del PR 24 la dio por una lectura sin la regla."""
    guard = "        await connection_is_available(s, t, 'x')\n" if guarded else ""
    src = tmp_path / "store.py"
    src.write_text(
        "class Store(Protocol):\n"
        "    async def read(self): ...\n"
        "class _Db:\n"
        "    async def read(self):\n"
        "        select(TenantConnector)\n" + guard,
        encoding="utf-8",
    )
    [(fn, line)] = _innermost(src, _selects_tenant_connector)
    assert line == 5
    assert bool(_calls(fn) & READ_GUARDS) is guarded


def test_the_listed_exceptions_still_exist() -> None:
    """Una excepción que ya no existe en el código se quita de la lista."""
    names = {
        f.name
        for root in (API_SRC, *OUTSIDE_API)
        for path in root.rglob("*.py")
        for f in _functions(path)
    }
    stale = (set(CREATES_WITHOUT_RULE) | set(READS_WITHOUT_RULE)) - names
    assert not stale, sorted(stale)


def test_the_channel_list_matches_the_seeds() -> None:
    seeds = API_SRC / "nexus_api/services/connectors/seeds"
    channels = set()
    for path in seeds.glob("*.yaml"):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if (doc.get("provider_meta") or {}).get("channel_only") is True:
            channels.add(doc["slug"])
    assert channels == set(CHANNEL_CONNECTORS)
