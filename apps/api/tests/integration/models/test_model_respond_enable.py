"""Spec 065, T072 (requisitos 1.3, 1.4, 8.2 y 11.2): habilitar y deshabilitar un modelo para
responder, desde el panel, por entorno.

- ``respond-enable`` exige perfil de llamada (``409 no_respond_profile``) y una nota; escribe
  ``respond_enabled_*``, audita ``admin.model.respond_enable`` y publica el cambio del
  catálogo;
- ``respond-disable`` pasa al modelo por defecto las elecciones de los partners con ese modelo
  (un ``agent.model_reset`` por agente) sin tocar las de Auphere, y da ``409 model_in_use``
  si es el modelo por defecto o la reserva habilitada de la otra familia;
- la lista del panel enseña el estado.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core import respond_catalog
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from tests.integration.models.test_agent_model_admin import (
    _operator,
    _partner_list,
    _resets,
    _set_by_operator,
)
from tests.integration.models.test_agent_model_console import (  # noqa: F401
    _catalog,
    agent_of,
    choice_of,
    url,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
OPUS = "anthropic/claude-opus-5-5"
SONNET = "anthropic/claude-sonnet-5-5"
SONNET46 = "anthropic/claude-sonnet-4-6"
BASE = "/admin/models/deployments"


@pytest_asyncio.fixture(autouse=True)
async def _openai_enabled_again() -> AsyncIterator[None]:
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET respond_enabled_at = now(), "
                "respond_enabled_by = 'migration:0238', respond_enabled_note = NULL "
                "WHERE model_id = ANY(:m) AND respond_enabled_at IS NULL"
            ),
            {"m": [SOL, TERRA, LUNA]},
        )


async def _id(model_id: str) -> uuid.UUID:
    async with get_sessionmaker()() as session:
        found = await session.scalar(
            sa.text("SELECT id FROM model_profiles WHERE model_id = :m"), {"m": model_id}
        )
    assert found is not None, model_id
    return uuid.UUID(str(found))


async def _row(client: Any, headers: dict[str, str], model_id: str) -> dict[str, Any]:
    resp = await client.get(BASE, headers=headers)
    assert resp.status_code == 200, resp.text
    target = str(await _id(model_id))
    return next(r for r in resp.json()["items"] if r["uuid"] == target)


async def test_enabling_needs_a_profile_and_a_note_and_is_audited(
    client, admin_headers, db_session
) -> None:
    headers = await _operator(db_session, admin_headers)
    opus = await _id(OPUS)
    no_note = await client.post(f"{BASE}/{opus}/respond-enable", headers=headers, json={})
    assert no_note.status_code == 422, no_note.text
    legacy = await client.post(
        f"{BASE}/{await _id(SONNET46)}/respond-enable", headers=headers, json={"note": "x"}
    )
    assert legacy.status_code == 409, legacy.text
    assert legacy.json()["detail"]["code"] == "no_respond_profile"

    before = await _row(client, headers, OPUS)
    assert before["respond_enabled_at"] is None and before["has_respond_profile"] is True

    note = "Batería real 2026-11-20, commit abc123, 18/18"
    resp = await client.post(f"{BASE}/{opus}/respond-enable", headers=headers, json={"note": note})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["respond_enabled_at"] is not None
    assert body["respond_enabled_note"] == note
    assert body["respond_enabled_by"].startswith("operator:")
    assert OPUS in {m for m, _ in respond_catalog.RESPOND_MODELS}, "este proceso ya lo ofrece"

    async with get_sessionmaker()() as session:
        audit = (
            await session.execute(
                sa.select(AuditLog)
                .where(AuditLog.action == "admin.model.respond_enable")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
    assert audit.target == f"deployment:{OPUS}"
    assert audit.after_json["note"] == note
    assert (await _row(client, headers, SONNET46))["has_respond_profile"] is False


async def test_disabling_moves_the_partners_choices_and_keeps_auphere_s(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    await _partner_list(client, admin_headers, a, [SOL, TERRA, LUNA])
    chosen = await agent_of(a["tenant_id"], "Recepción")
    by_auphere = await agent_of(a["tenant_id"], "Soporte")
    resp = await client.put(url(a["ref"], chosen), headers=a["headers"](), json={"model_id": LUNA})
    assert resp.status_code == 200, resp.text
    await _set_by_operator(a["tenant_id"], by_auphere, LUNA)

    no_reason = await client.post(
        f"{BASE}/{await _id(LUNA)}/respond-disable", headers=headers, json={}
    )
    assert no_reason.status_code == 422, no_reason.text
    resp = await client.post(
        f"{BASE}/{await _id(LUNA)}/respond-disable",
        headers=headers,
        json={"reason": "Sube de precio"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["respond_enabled_at"] is None
    assert LUNA not in {m for m, _ in respond_catalog.RESPOND_MODELS}

    assert (await choice_of(a["tenant_id"], chosen))[:2] == (None, None)
    assert (await choice_of(a["tenant_id"], by_auphere))[:2] == (LUNA, "operator"), "8.3"
    resets = [r for r in await _resets(a["partner_id"]) if r["agent"] == "Recepción"]
    assert len(resets) == 1 and resets[0]["from_model"] == "Luna"
    view = (await client.get(url(a["ref"], chosen), headers=a["headers"]())).json()
    assert LUNA not in {o["model_id"] for o in view["options"]}


async def test_the_default_and_an_enabled_reserve_cannot_be_disabled(
    client, admin_headers, db_session
) -> None:
    headers = await _operator(db_session, admin_headers)
    sol = await client.post(
        f"{BASE}/{await _id(SOL)}/respond-disable", headers=headers, json={"reason": "x"}
    )
    assert sol.status_code == 409, sol.text
    assert sol.json()["detail"] == {"code": "model_in_use", "uses": ["agent_default"]}

    enabled = await client.post(
        f"{BASE}/{await _id(SONNET)}/respond-enable", headers=headers, json={"note": "batería"}
    )
    assert enabled.status_code == 200, enabled.text
    reserve = await client.post(
        f"{BASE}/{await _id(SONNET)}/respond-disable", headers=headers, json={"reason": "x"}
    )
    assert reserve.status_code == 409, reserve.text
    assert reserve.json()["detail"] == {
        "code": "model_in_use",
        "uses": ["respond_fallback_openai"],
    }
