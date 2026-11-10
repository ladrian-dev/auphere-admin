"""Spec 047, T117 — la beta «WhatsApp login» por país en el panel de operador
(requisitos 31.5 y 54.7): se activa y se quita por país, nunca en la UE ni en el
EEE, y cada cambio queda en la auditoría con quién y por qué."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.api.admin.whatsapp_login_beta import EU_EEA
from nexus_api.db.models import AuditLog

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

URL = "/admin/whatsapp/login-beta/countries"


async def _operator(db_session: Any) -> tuple[str, str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id), account.email


async def test_the_beta_is_enabled_per_country_and_never_in_the_eu(
    client: Any, admin_headers: dict[str, str], db_session: Any
) -> None:
    op, email = await _operator(db_session)
    headers = {**admin_headers, "X-Operator-Id": op}
    assert (await client.get(URL, headers=headers)).json() == []

    on = await client.put(
        f"{URL}/cl", json={"enabled": True, "reason": "Meta la activó en Chile"}, headers=headers
    )
    assert on.status_code == 200, on.text
    assert [c["country"] for c in on.json()] == ["CL"]
    assert on.json()[0]["enabled_by"] == f"operator:{email}", "la persona, no un id"

    for eu in ("ES", "NO", "IS", "RE", "AX"):
        refused = await client.put(
            f"{URL}/{eu}", json={"enabled": True, "reason": "prueba"}, headers=headers
        )
        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "eu_country_not_allowed"
    assert {"ES", "DE", "FR", "IT", "NO", "IS", "LI"} <= EU_EEA

    no_reason = await client.put(f"{URL}/MX", json={"enabled": True}, headers=headers)
    assert no_reason.status_code == 422, "cada cambio lleva su motivo"

    off = await client.put(
        f"{URL}/CL", json={"enabled": False, "reason": "Meta la retiró"}, headers=headers
    )
    assert off.json() == []
    actions = (
        await db_session.scalars(
            sa.select(AuditLog.action)
            .where(AuditLog.target == "country:CL")
            .order_by(AuditLog.created_at)
        )
    ).all()
    assert list(actions) == ["whatsapp.login_beta.enabled", "whatsapp.login_beta.disabled"]


async def test_without_an_operator_nothing_changes(
    client: Any, admin_headers: dict[str, str]
) -> None:
    resp = await client.put(
        f"{URL}/CL", json={"enabled": True, "reason": "x" * 5}, headers=admin_headers
    )
    assert resp.status_code in (400, 401, 403), "sin la persona de Auphere no se cambia"
    assert (await client.get(URL, headers=admin_headers)).json() == []
