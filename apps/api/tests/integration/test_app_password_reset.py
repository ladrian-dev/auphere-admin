"""Spec 031 · R1.7 (enmienda del 2026-10-20) — «¿Olvidaste tu contraseña?»
desde la app (tarea T116).

Es el mismo servicio que la web (``POST /console/password-reset``), sin la BFF
delante: misma respuesta exista o no la cuenta, sin correo si no hay cuenta, el
mismo tope por dirección y que el tope no se note.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.services.password_reset import REQUESTS_PER_WINDOW
from tests.conftest import make_console_account

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

RESET = "/app/password-reset"


def _mail_sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return sent


async def test_with_and_without_an_account_the_answer_is_identical(
    client, db_session, monkeypatch
) -> None:
    sent = _mail_sink(monkeypatch)
    email = f"valeria-{uuid.uuid4().hex[:8]}@minegocio.test"
    await make_console_account(db_session, email=email)

    known = await client.post(RESET, json={"email": email.upper()})
    unknown = await client.post(
        RESET, json={"email": f"nadie-{uuid.uuid4().hex[:8]}@minegocio.test"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content
    # Solo a quien tiene cuenta, y con el enlace de la página web.
    assert len(sent) == 1
    assert email in str(sent[0].get("to"))
    assert "/reset/" in sent[0]["html"]


async def test_the_cap_answers_like_any_other_request(client, db_session, monkeypatch) -> None:
    sent = _mail_sink(monkeypatch)
    email = f"valeria-{uuid.uuid4().hex[:8]}@minegocio.test"
    await make_console_account(db_session, email=email)

    first = await client.post(RESET, json={"email": email})
    rest = [await client.post(RESET, json={"email": email}) for _ in range(8)]

    assert {r.status_code for r in [first, *rest]} == {202}
    assert {r.content for r in rest} == {first.content}
    assert len(sent) <= REQUESTS_PER_WINDOW


async def test_something_that_is_not_an_email_is_refused_the_same_for_anyone(
    client, monkeypatch
) -> None:
    _mail_sink(monkeypatch)

    one = await client.post(RESET, json={"email": "no-es"})
    other = await client.post(RESET, json={"email": "@@"})

    assert one.status_code == other.status_code == 422
