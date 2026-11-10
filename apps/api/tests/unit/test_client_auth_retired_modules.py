"""Spec 056, T022 (requisito 2.5) — un módulo retirado responde siempre el 403.

``require_client_principal("agents")`` sigue importando (las rutas de
``lite/agents.py`` y ``lite/business.py`` no se borran: research R2), y su
dependencia responde **siempre** el 403 de un módulo que no se tiene, aunque la
persona, por lo que sea, lo trajera entre sus módulos. La regla está escrita en la
dependencia, no se deja en manos de lo guardado.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from nexus_api.core import client_auth
from nexus_api.db.models import CLIENT_MODULES, RETIRED_CLIENT_MODULES

pytestmark = pytest.mark.asyncio


def _principal(modules: tuple[str, ...]) -> Any:
    return SimpleNamespace(
        modules=modules,
        has=lambda m: m in modules,
        partner=SimpleNamespace(slug="p"),
        membership=SimpleNamespace(email="valeria@negocio.test"),
    )


@pytest.fixture
def everything(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Una persona que lo tiene todo, también lo retirado, por las dos credenciales."""
    principal = _principal(CLIENT_MODULES + RETIRED_CLIENT_MODULES)

    async def verify(authorization: str | None, redis: Any) -> dict[str, Any]:
        return {"sub": "u-1", "jti": "j-1", "partner_id": str(uuid.uuid4())}

    async def resolve(session: Any, **kw: Any) -> Any:
        return principal

    async def phone(token: str, **kw: Any) -> Any:
        return principal

    monkeypatch.setattr(client_auth, "_verify_bearer", verify)
    monkeypatch.setattr(client_auth, "resolve_client_principal", resolve)
    monkeypatch.setattr(client_auth, "_resolve_phone", phone)
    return principal


async def _call(dep: Any, *, phone: bool, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(client_auth.phone_credential, "looks_like_phone_token", lambda t: phone)
    return await dep(
        authorization="Bearer token", session=None, redis=None, app_platform=None, app_version=None
    )


def test_a_retired_name_still_imports_and_an_invented_one_does_not() -> None:
    for module in RETIRED_CLIENT_MODULES:
        client_auth.require_client_principal(module)
    with pytest.raises(ValueError):
        client_auth.require_client_principal("invented")


@pytest.mark.parametrize("phone", [False, True], ids=["web", "phone"])
@pytest.mark.parametrize("module", RETIRED_CLIENT_MODULES)
async def test_a_retired_module_is_always_the_absent_module_403(
    module: str, phone: bool, everything: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dep = client_auth.require_client_principal(module)
    with pytest.raises(HTTPException) as refused:
        await _call(dep, phone=phone, monkeypatch=monkeypatch)
    absent = client_auth._forbidden()
    assert (refused.value.status_code, refused.value.detail) == (absent.status_code, absent.detail)


@pytest.mark.parametrize("phone", [False, True], ids=["web", "phone"])
async def test_a_current_module_still_lets_her_in(
    phone: bool, everything: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    dep = client_auth.require_client_principal("panel")
    assert await _call(dep, phone=phone, monkeypatch=monkeypatch) is everything
