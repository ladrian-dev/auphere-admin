"""Spec 005 · R3.5 — la puerta que acreditaba saldo sin pago desaparece.

Su propia docstring decía que K2 la sustituye: *«cuando exista Stripe, el
crédito entrará por el webhook del pago confirmado y no por esta llamada, que
entonces sobra»*. Ya existe.

**Se borra, no se apaga por entorno.** Estaba viva en dev y era un 404 opaco en
producción, que es una forma de decir «esto existe pero aquí no». Una puerta
que añade saldo sin cobro no debe existir ni apagada: el día que alguien
cambie una condición de entorno por error, la puerta vuelve.

La recarga de Auphere —``POST /admin/partners/{id}/wallet/purchased``, con
token de admin y auditoría— **no se toca**: ésa es una decisión de un operador
con rastro, que es otra cosa.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_WALLET = (
    Path(__file__).resolve().parents[2] / "src" / "nexus_api" / "api" / "console" / "wallet.py"
)


async def test_the_route_is_not_registered_anywhere() -> None:
    from nexus_api.main import app

    offenders = [
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "").endswith("/wallet/purchased")
        and "POST" in (getattr(route, "methods", None) or set())
        and not getattr(route, "path", "").startswith("/admin")
    ]
    assert not offenders, f"la ruta sigue registrada: {offenders}"


async def test_the_console_module_no_longer_defines_it() -> None:
    """Y no está sólo comentada ni apagada por una condición de entorno."""
    tree = ast.parse(_WALLET.read_text(), filename=str(_WALLET))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            method = func.attr if isinstance(func, ast.Attribute) else ""
            if method != "post":
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and "wallet/purchased" in str(arg.value):
                    pytest.fail(f"«{node.name}» sigue declarando la ruta")


async def test_the_operator_recharge_survives() -> None:
    """La de admin sigue: un operador que acredita deja auditoría."""
    from nexus_api.main import app

    admin = [
        getattr(route, "path", "")
        for route in app.routes
        if "wallet/purchased" in getattr(route, "path", "")
    ]
    assert any(path.startswith("/admin") for path in admin), (
        f"se llevó por delante la recarga de operador: {admin}"
    )


async def test_a_console_caller_gets_a_plain_404() -> None:
    from httpx import ASGITransport, AsyncClient

    from nexus_api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/console/wallet/purchased", json={"qty": 1000})
    assert resp.status_code == 404, resp.text
