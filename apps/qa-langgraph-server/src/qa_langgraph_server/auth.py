"""Custom authentication for the QA LangGraph Server.

Validates the same credentials the ``/qa/*`` HTTP endpoints accept:

    Authorization: Bearer <NEXUS_ADMIN_TOKEN>
    X-Operator-Id: <uuid>

Plus a third value the agent run needs:

    X-QA-Thread-Id: <uuid>   (optional on thread.create, required on runs)

The handler sets THREE contextvars per request:
  - ``app.operator_id`` (via ``operator_context``)
  - ``app.tenant_id``   (via ``tenant_context``)
  - ``current_qa_thread`` (via ``qa_thread_context``)

A single graph instance serves concurrent runs from different operators
safely because every contextvar mutation is scoped to the asyncio task.

Better Auth (Block G) will eventually replace the static Bearer with a
session-derived identity; the handler signature stays the same.
"""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from dataclasses import dataclass

from langgraph_sdk import Auth
from nexus_api.config import get_settings

auth = Auth()


@dataclass(frozen=True)
class QAOperatorUser:
    """Concrete implementation of LangGraph's ``BaseUser`` protocol.

    LangGraph stores the returned object per-request and exposes it to
    the graph through ``runtime.server_info.user``. We expose the
    operator UUID as both ``identity`` and ``display_name`` so traces
    have something readable to show in Langfuse.
    """

    operator_id: str

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self.operator_id

    @property
    def identity(self) -> str:
        return self.operator_id

    @property
    def permissions(self) -> Sequence[str]:
        return ("qa_operator",)


@auth.authenticate
async def authenticate(headers: dict[str, bytes | str]) -> QAOperatorUser:
    """LangGraph Server hook — runs once per request before the graph.

    We accept either bytes (HTTP) or str (testing) header values, since
    different transports normalise the case differently. Anything not
    pasted is treated as missing.
    """
    bearer = _h(headers, "authorization")
    if not bearer or not bearer.lower().startswith("bearer "):
        raise Auth.exceptions.HTTPException(status_code=401, detail="Missing bearer token")
    token = bearer.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, get_settings().admin_token):
        raise Auth.exceptions.HTTPException(status_code=401, detail="Invalid admin token")

    op_raw = _h(headers, "x-operator-id")
    if not op_raw or not op_raw.strip():
        raise Auth.exceptions.HTTPException(
            status_code=400, detail="Missing or blank X-Operator-Id header"
        )
    operator_id = op_raw.strip()
    # Migration 0026 widened ``qa.*.operator_id`` from UUID to TEXT to
    # accept Better Auth's cuid-style ids verbatim. Length cap mirrors
    # ``core/qa_security.py::_MAX_OPERATOR_ID_LEN`` so the server and
    # the qa-api agree on what's acceptable.
    if len(operator_id) > 120:
        raise Auth.exceptions.HTTPException(
            status_code=400, detail="X-Operator-Id must be ≤ 120 characters"
        )

    # Identity object that LangGraph stores per request. Whatever we put
    # in ``identity`` is available to the graph through
    # ``runtime.server_info.user``; we expose just the operator id
    # because the rest is in contextvars set below.
    return QAOperatorUser(operator_id=operator_id)


def _h(headers: dict[bytes, bytes] | dict[str, bytes | str], name: str) -> str | None:
    """Case-insensitive header lookup that tolerates bytes keys + values.

    LangGraph API (langgraph_api.auth.custom) passes ``dict[bytes, bytes]``
    coming straight from the ASGI scope. Tests sometimes pass
    ``dict[str, str]`` for readability. Handle both — comparing keys as
    bytes-normalised lowercase.
    """
    name_b = name.lower().encode("ascii")
    for k, v in headers.items():
        kb = k.encode("ascii") if isinstance(k, str) else k
        if kb.lower() == name_b:
            return v.decode("utf-8", errors="ignore") if isinstance(v, bytes) else str(v)
    return None
