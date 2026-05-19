"""Operator authentication for the QA Playground endpoints.

Phase 3 ships a minimal scheme on top of the existing admin Bearer token:

    Authorization: Bearer <NEXUS_ADMIN_TOKEN>
    X-Operator-Id: <uuid>

The Bearer token still proves "this request comes from Auphere staff" —
without it, no admin endpoint works. The ``X-Operator-Id`` header
identifies *which* staff member is the actor, so the qa.* tables (RLS by
operator_id) can scope rows correctly and two operators inspecting the
same tenant never see each other's threads.

Better Auth (Block G) will replace this with a real session-derived
identity and the ``qa_operator`` role check. Until then, the header is
trusted because it's protected by the same Bearer secret the admin
panel uses to talk to the API.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status

from nexus_api.core.security import require_admin_token


def require_qa_operator(
    _token: str = Depends(require_admin_token),
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> uuid.UUID:
    """FastAPI dependency. Returns the operator UUID.

    Order matters:
      1. ``require_admin_token`` validates the Bearer; 401 if missing/bad.
      2. We require ``X-Operator-Id`` and parse it as a UUID; 400 if
         missing or malformed.

    Returning the UUID (not a tuple with the token) lets handlers use it
    as ``actor`` in audit rows without re-parsing the header.
    """
    if not x_operator_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Operator-Id header",
        )
    try:
        return uuid.UUID(x_operator_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be a UUID",
        ) from exc
