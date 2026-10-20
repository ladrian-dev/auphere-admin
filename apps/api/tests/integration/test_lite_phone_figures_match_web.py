"""Spec 031 · R4.3, CE-005 — las cifras del teléfono son las de la web
(tarea T062).

Inicio y Consumo en la app leen las mismas rutas que la consola lite. Con la
credencial del teléfono y con el JWT de la BFF, para la misma persona y en el
mismo momento, la respuesta es **idéntica**: al céntimo y en la misma moneda.
"""

from __future__ import annotations

import pytest

from tests.conftest import add_client_phone, make_inbox

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ROUTES = (
    "/console/lite/home",
    "/console/lite/usage/summary",
    "/console/lite/usage/spend?days=7",
    "/console/lite/usage/spend?days=30",
    "/console/lite/usage/spend?days=90",
    "/console/lite/inbox/counts",
)


@pytest.mark.parametrize("path", ROUTES)
async def test_the_phone_reads_the_same_figures_as_the_web(
    client, db_session, console_world, path
) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    phone = await add_client_phone(db_session, membership_id=inbox["member"]["membership_id"])

    web = await client.get(path, headers=inbox["headers"]())
    app = await client.get(path, headers=phone["headers"]())

    assert web.status_code == 200, web.text
    assert app.status_code == 200, app.text
    assert app.json() == web.json()
