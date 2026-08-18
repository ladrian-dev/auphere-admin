"""Garantía C2 — las herramientas del Companion pasan SIEMPRE por el router.

La regla que define CO-02: una herramienta llama a ``/console/*`` por HTTP
en proceso, nunca a ``services/`` ni a ``repositories/``.

No es purismo. Saltarse el router se salta, todo junto: la validación
Pydantic, ``client_scope`` (que es donde el ``external_client_ref`` se
resuelve bajo el principal y donde se abre la transacción con RLS), el
limitador de ráfaga, la cuota de aprovisionamiento (0081), el vocabulario
de auditoría (0084) y la cobertura automática de ``test_console_scope.py``.
El día que alguien "optimice" una herramienta llamando al servicio, el
Companion se convierte en un camino paralelo con sus propios agujeros —
silenciosamente, porque los tests de esa herramienta seguirían pasando.

Este test es lo que hace ruidoso ese cambio. Es el hermano del
``check:no-admin-token`` de CP-03, con AST en vez de grep: un grep se
esquiva con un import dentro de una función, y el AST no.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = [pytest.mark.isolation]

TOOLS_PACKAGE = pathlib.Path(__file__).resolve().parents[2] / "src" / "nexus_api" / "companion"

#: Prefijos prohibidos. Se comparan por segmento para que
#: ``nexus_api.services_helpers`` (si existiera) no dé un falso positivo.
FORBIDDEN_ROOTS = (
    ("nexus_api", "services"),
    ("nexus_api", "repositories"),
)


def _modules() -> list[pathlib.Path]:
    return sorted(TOOLS_PACKAGE.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> list[str]:
    """Todo lo que el módulo importa, incluidos los imports diferidos
    dentro de una función — que son exactamente los que un grep no ve."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


def _is_forbidden(module: str) -> bool:
    parts = tuple(module.split("."))
    return any(parts[: len(root)] == root for root in FORBIDDEN_ROOTS)


def test_the_tools_package_has_modules_to_check() -> None:
    """Un recorrido sobre un directorio vacío pasa siempre. Si el paquete
    se mueve, este test avisa en vez de aprobar el vacío."""
    assert TOOLS_PACKAGE.is_dir(), f"no existe {TOOLS_PACKAGE}"
    assert len(_modules()) >= 4


def test_no_tool_module_imports_services_or_repositories() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        bad = [m for m in _imported_modules(tree) if _is_forbidden(m)]
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        f"herramientas del Companion que se saltan el router: {offenders}. "
        "Una herramienta llama a /console/* por HTTP en proceso; llamar al "
        "servicio se salta client_scope, la RLS, la cuota y la auditoría."
    )


def test_the_check_would_catch_a_deferred_import() -> None:
    """Control del control: un import dentro de una función —el que un grep
    de la primera línea no vería— también cuenta."""
    tree = ast.parse("def f():\n    from nexus_api.repositories.partner import PartnerRepository\n")
    assert any(_is_forbidden(m) for m in _imported_modules(tree))
