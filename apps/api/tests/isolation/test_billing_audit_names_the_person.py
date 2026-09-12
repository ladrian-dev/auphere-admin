"""Spec 005 · garantía 4 — el rastro nombra a la persona, no al proceso.

Contratar un plan, cambiarlo, comprar crédito y cancelar son **acciones
consecuentes de una persona** (§IV). El rastro tiene que decir quién, y «quién»
no es el partner ni es «el sistema»: es la persona con permiso de facturación
que lo decidió.

La distinción importa más aquí que en otros sitios porque el cobro tiene un
segundo actor —el aviso del proveedor— y es fácil que acabe figurando él. Un
webhook **no decide** contratar: confirma algo que una persona ya decidió. Una
auditoría que dijera «stripe contrató Business» habría perdido el dato que
sirve para responder «¿quién autorizó este gasto?».
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_SRC = Path(__file__).resolve().parents[2] / "src" / "nexus_api"
_BILLING_ROUTER = _SRC / "api" / "console" / "billing.py"
_WORKER = Path(__file__).resolve().parents[3] / "worker" / "src" / "nexus_worker" / "billing"

#: Lo que nunca puede ser el actor de una acción de facturación.
_FORBIDDEN_ACTORS = ("system", "webhook", "stripe", "provider", "cron", "-")


def _audit_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(), filename=str(path))
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if "audit" in name.lower():
                out.append(node)
    return out


async def test_console_billing_actions_write_an_audit_entry() -> None:
    """Si la ruta existe, deja rastro. Ninguna acción de dinero es silenciosa."""
    if not _BILLING_ROUTER.exists():
        pytest.fail("apps/api/src/nexus_api/api/console/billing.py no existe")
    calls = _audit_calls(_BILLING_ROUTER)
    assert calls, (
        "ninguna acción de /console/billing deja rastro de auditoría. Contratar, "
        "cambiar de plan, comprar crédito y cancelar son acciones consecuentes "
        "de una persona y la auditoría tiene que nombrarla (§IV)"
    )


async def test_no_billing_audit_entry_has_a_machine_as_its_actor() -> None:
    """Ni en la ruta ni en el trabajo de fondo.

    Se mira el literal que se pasa como actor. Un webhook que escribiera
    auditoría con actor «stripe» convertiría el rastro de una decisión humana
    en el rastro de un mensaje recibido.
    """
    paths = [p for p in (_BILLING_ROUTER, *(_WORKER.rglob("*.py") if _WORKER.exists() else ()))]
    offenders: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        for call in _audit_calls(path):
            for kw in call.keywords:
                if kw.arg != "actor":
                    continue
                if (
                    isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                    and kw.value.value.strip().lower() in _FORBIDDEN_ACTORS
                ):
                    offenders.append(f"{path.name}: actor={kw.value.value!r}")
    assert not offenders, (
        f"auditoría de facturación con una máquina como actor: {offenders}. "
        "El aviso del proveedor CONFIRMA lo que una persona decidió; no lo decide"
    )
