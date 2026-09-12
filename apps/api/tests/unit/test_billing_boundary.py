"""Spec 005 · la frontera del proveedor, comprobada en vez de prometida.

Tres invariantes estructurales. Los tres son reglas que se escribieron en
`research.md` y que, sin un test, dejan de existir en dos meses:

* **D2** — ningún ``import stripe`` fuera de ``nexus_api/billing/``.
* **D3** — el paquete de cobro no resta saldo.
* **CE-004** — el camino del turno no depende del proveedor de pago.

Sobre el orden test-primero (§VII): estos tres **pasan desde el primer día**,
porque describen una ausencia. Un test así no se puede ver en rojo escribiéndolo
antes que el código — se ve en rojo introduciendo la violación que persigue, y
eso se hizo a mano al escribirlos. Lo que cubren no es una funcionalidad que
aún no existe: es una que nunca debe aparecer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.asyncio]

_SRC = Path(__file__).resolve().parents[2] / "src" / "nexus_api"
_BILLING = _SRC / "billing"

#: Lo que decide si un turno pasa. Una llamada al proveedor de pago aquí
#: significa que una incidencia suya apaga a todos los agentes a la vez.
_TURN_PATH = (
    _SRC / "metering",
    _SRC / "api" / "console" / "companion.py",
    _SRC / "services" / "agent_runtime.py",
)


def _modules(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imported_names(path: Path) -> set[str]:
    """Top-level module names imported by ``path`` — including lazy imports
    inside a function, which are exactly how a boundary gets crossed quietly."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


async def test_stripe_is_imported_only_inside_the_billing_package() -> None:
    offenders = [
        str(path.relative_to(_SRC))
        for path in _modules(_SRC)
        if _BILLING not in path.parents
        and any(name == "stripe" or name.startswith("stripe.") for name in _imported_names(path))
    ]
    assert not offenders, (
        f"``import stripe`` fuera de nexus_api/billing/: {offenders}. La cuenta "
        "de Stripe se va a migrar (research D5); con el proveedor importado por "
        "todo el repositorio esa migración deja de ser un trabajo acotado"
    )


def _uses_debit(path: Path) -> bool:
    """Busca el SÍMBOLO, no el texto.

    La primera versión de esta comprobación buscaba la cadena ``debit_wallet``
    en el fichero y se disparó con el docstring de ``billing/__init__.py``, que
    precisamente explica por qué no se debita. Una regla que no distingue entre
    documentar una prohibición y violarla enseña a ignorar el rojo.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "debit_wallet" for alias in node.names):
                return True
        elif (isinstance(node, ast.Name) and node.id == "debit_wallet") or (
            isinstance(node, ast.Attribute) and node.attr == "debit_wallet"
        ):
            return True
    return False


async def test_the_billing_package_never_debits() -> None:
    """ADR-037 D3: la conciliación va en una sola dirección.

    Sumar de más es un error que se ve y se corrige. Restar de más es dinero
    que un partner pagó y ya no tiene, y lo descubre cuando su agente se calla.
    """
    offenders = [str(path.relative_to(_SRC)) for path in _modules(_BILLING) if _uses_debit(path)]
    assert not offenders, (
        f"el paquete de cobro menciona ``debit_wallet``: {offenders}. Ningún "
        "camino que arranque en un aviso externo puede restar saldo (ADR-037 D3)"
    )


async def test_the_turn_path_does_not_depend_on_the_payment_provider() -> None:
    """CE-004: con el proveedor caído, el trabajo continúa.

    Es la misma forma de avería que el ``_require_wallet`` colado en
    ``resume_run`` que la Spec A tuvo que quitar: una dependencia en el camino
    caliente que no se nota hasta que el externo falla — y entonces falla para
    todos a la vez.
    """
    offenders: list[str] = []
    for root in _TURN_PATH:
        if not root.exists():
            continue
        for path in _modules(root) if root.is_dir() else [root]:
            names = _imported_names(path)
            if any(
                name == "stripe"
                or name.startswith("stripe.")
                or name == "nexus_api.billing"
                or name.startswith("nexus_api.billing.")
                for name in names
            ):
                offenders.append(str(path.relative_to(_SRC)))
    assert not offenders, (
        f"el camino del turno importa el cobro: {offenders}. Una incidencia del "
        "proveedor de pago no puede impedir que un agente conteste con el saldo "
        "que ya tiene (CE-004)"
    )
