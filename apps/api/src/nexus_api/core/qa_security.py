"""Operator authentication for the QA Playground endpoints.

Phase 3 ships a minimal scheme on top of the existing admin Bearer token:

    Authorization: Bearer <NEXUS_ADMIN_TOKEN>
    X-Operator-Id: <opaque-string>

The Bearer token still proves "this request comes from Auphere staff" —
without it, no admin endpoint works. The ``X-Operator-Id`` header
identifies *which* staff member is the actor, so the qa.* tables (RLS by
operator_id) can scope rows correctly and two operators inspecting the
same tenant never see each other's threads.

Migration 0026 (Fase 6 follow-up) widened ``operator_id`` from UUID to
TEXT because Better Auth's ``session.user.id`` is a cuid-style short id,
not a UUID. The header is accepted as any non-empty trimmed string; the
RLS policy compares text equality and the WITH CHECK clause enforces
symmetry. Security comes from the Bearer + the policy, not the id shape.

Better Auth (Block G) will replace this with a real session-derived
identity and the ``qa_operator`` role check. Until then, the header is
trusted because it's protected by the same Bearer secret the admin
panel uses to talk to the API.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from nexus_api.core.security import require_admin_token

# Reasonable upper bound for opaque actor ids. Better Auth emits ~24
# chars; we allow up to 120 to match the column width in migration 0026
# and to leave room for future formats. Anything longer is treated as
# malformed.
_MAX_OPERATOR_ID_LEN = 120


def require_qa_operator(
    _token: str = Depends(require_admin_token),
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
) -> str:
    """FastAPI dependency. Returns the operator id (opaque string).

    Order matters:
      1. ``require_admin_token`` validates the Bearer; 401 if missing/bad.
      2. We require ``X-Operator-Id`` (non-empty, trimmed, within length
         bounds); 400 if missing or malformed.

    Returning the string (not a tuple with the token) lets handlers use
    it as ``actor`` in audit rows without re-parsing the header.
    """
    if not x_operator_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Operator-Id header",
        )
    operator_id = x_operator_id.strip()
    if not operator_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must not be blank",
        )
    if len(operator_id) > _MAX_OPERATOR_ID_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"X-Operator-Id must be ≤ {_MAX_OPERATOR_ID_LEN} characters",
        )
    return operator_id
