"""Validate and normalise paths sent by the LLM to the Memory tool.

Two jobs:

1. **Reject anything that escapes the ``/memories/`` namespace.** The LLM
   is free to generate any string; the backend has to refuse traversal
   (``..``, percent-encoded ``%2e%2e``, absolute paths) and any prefix
   that is not ``/memories/``. We do this here AND in a DB ``CHECK``
   constraint (defence in depth — see migration 0032).
2. **Resolve the ``customer/me/...`` alias** to the actual ``customer_id``
   of the running turn. This is the seam that keeps cross-customer
   isolation: the model writes a path with ``me``, the validator rewrites
   it to the current turn's customer UUID, and only THEN does the SQL
   query run. The LLM never sees another customer's id, so it cannot
   craft a path that targets them.

Allowed shapes (after resolution):

  /memories/customer/{uuid}/...    ← per-customer files
  /memories/tenant/...             ← tenant-wide files

Anything else raises :class:`PathValidationError`. The error message is
plain English so the LLM, on seeing it as a tool_result, can correct
itself without leaking implementation details.
"""

from __future__ import annotations

import uuid
from urllib.parse import unquote


class PathValidationError(ValueError):
    """Raised when a path the LLM wants to touch is unsafe or unparseable.

    The error message becomes the ``tool_result`` content that goes back
    into the model's context — so it MUST be safe to surface to the LLM
    (no UUIDs of other customers, no operator-only hints).
    """


_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/memories/customer/",
    "/memories/tenant/",
    # Bare ``/memories`` (no trailing slash) and ``/memories/`` are the
    # listing entry points the LLM uses via the ``view`` command.
    "/memories",
)

_CUSTOMER_ME_PREFIX = "/memories/customer/me"


def _looks_like_traversal(path: str) -> bool:
    """Detect path traversal attempts in any encoding the LLM might use.

    The Memory tool docs are explicit that paths come straight from the
    model. ``..`` is the obvious one, but the model could plausibly try
    URL-encoded forms (``%2e%2e``) or Windows separators after a recent
    web search; we decode once and check the literal segments.
    """
    decoded = unquote(path)
    # Normalise separators so a ``\..\`` doesn't sneak past a ``/..`` check.
    normalised = decoded.replace("\\", "/")
    return any(segment in ("..", ".") for segment in normalised.split("/"))


def validate_and_resolve_path(path: str, *, customer_id: uuid.UUID | None) -> str:
    """Return a canonical path safe to use as a SQL key.

    - Rejects empty / non-string input.
    - Rejects anything not starting with ``/memories/`` (or the bare
      ``/memories`` listing root).
    - Rejects path traversal in any encoding.
    - Resolves ``/memories/customer/me`` to
      ``/memories/customer/{customer_id}``. If there is no customer in
      scope (e.g. a tenant-only call path), refuses with a clear message.
    - Refuses to dereference ``/memories/customer/{other_uuid}/...``
      that does not match ``customer_id``. The Memory tool semantics
      treat that as "does not exist" — we surface it as such (NOT as
      "permission denied", which would leak the existence of other
      customers).

    The path is returned with a normalised single leading ``/`` and NO
    trailing slash (except for the bare ``/memories`` root which is
    returned as ``/memories``).
    """
    if not isinstance(path, str) or not path:
        raise PathValidationError("path must be a non-empty string")

    if _looks_like_traversal(path):
        raise PathValidationError("path contains traversal segments ('..' or '.') and is rejected")

    if path == "/memories" or path == "/memories/":
        return "/memories"

    if not any(path.startswith(p) for p in _ALLOWED_PREFIXES):
        raise PathValidationError("path must start with /memories/customer/ or /memories/tenant/")

    # Strip a trailing slash so equal paths compare equal in SQL.
    normalised = path.rstrip("/") or "/memories"

    # Resolve "me" alias. The LLM is encouraged to use ``me`` in the
    # system prompt so it does not need to know the customer's UUID;
    # without that aliasing we would have to either expose the id (bad)
    # or surface the path as-is (the SQL would never match).
    if normalised == _CUSTOMER_ME_PREFIX or normalised.startswith(_CUSTOMER_ME_PREFIX + "/"):
        if customer_id is None:
            raise PathValidationError(
                "the 'me' alias requires a customer in the current turn; "
                "use /memories/tenant/... for tenant-wide memories"
            )
        suffix = normalised[len(_CUSTOMER_ME_PREFIX) :]
        return f"/memories/customer/{customer_id}{suffix}"

    # Bare ``/memories/customer`` (or ``/memories/customer/``) without
    # a "me" alias or a UUID — refuse: it would imply "list all
    # customers" which would leak existence. The LLM should use
    # ``/memories/customer/me`` for its own scope.
    if normalised == "/memories/customer":
        raise PathValidationError(
            "missing customer identifier after /memories/customer/ (use /memories/customer/me)"
        )

    # Explicit ``/memories/customer/{uuid}/...`` — refuse anything that
    # does not match the current turn's customer. Surface as "does not
    # exist" (not "permission denied") so we do not leak the existence
    # of other customers.
    if normalised.startswith("/memories/customer/"):
        rest = normalised[len("/memories/customer/") :]
        first = rest.split("/", 1)[0]
        if not first:
            raise PathValidationError("missing customer identifier after /memories/customer/")
        try:
            target = uuid.UUID(first)
        except ValueError as exc:
            raise PathValidationError(
                "customer identifier after /memories/customer/ must be 'me' or a UUID"
            ) from exc
        if customer_id is None or target != customer_id:
            # Same wording as a missing-path response so the LLM cannot
            # probe for the existence of other customers' memories.
            raise PathValidationError(f"path '{path}' does not exist")
        return normalised

    # /memories/tenant/... — nothing to resolve, just hand it back
    # without the trailing slash.
    return normalised


__all__ = ["PathValidationError", "validate_and_resolve_path"]
