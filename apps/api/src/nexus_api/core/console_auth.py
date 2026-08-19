"""Partner-console authentication for the ``/console/*`` surface
(PLAN-CONSOLE-V1, CP-03).

The console is a Next.js BFF (``apps/console``). The browser only ever
holds a Better Auth session cookie; the BFF resolves *who* (user) and
*where* (partner + role, from ``partner_memberships``) and mints, per
backend call, a **60-second EdDSA JWT**::

    {iss: "nexus-console", aud: "nexus-api", sub: <user_id>,
     partner_id: <uuid>, role: <role>, jti: <unique>, iat, exp}

This module is the other half. Per request:

1. Bearer → decode with the console's PUBLIC key (Ed25519). Signature,
   ``iss``, ``aud``, ``exp``, ``iat`` and required claims are checked by
   PyJWT; ``exp - iat`` is additionally capped at
   ``console_jwt_max_ttl_seconds`` so a token cannot claim a longer life
   than the BFF is allowed to mint.
2. ``jti`` anti-replay: ``SET NX`` in Redis for the token's lifetime. A
   second presentation of the same token is refused even inside its 60
   seconds. If Redis is unavailable the check degrades to a bounded
   per-replica memory set (same philosophy as ``core/rate_limit.py``):
   the replay window is then bounded by the token's own expiry.
3. **The backend never trusts the console for authorization.** The
   claimed ``partner_id`` is re-checked against ``partner_memberships``
   (active row for exactly ``sub`` + ``partner_id``), the partner must be
   ``active`` and ``console_enabled``, and the **role comes from the
   database row**, not from the token. A compromised BFF can therefore
   only ever act as the memberships that really exist.
4. Permissions are a fixed map from *named role* → capabilities. The
   endpoint declares what it needs (``require_console_principal(
   "clients:write")``); anything else is 403.

Two dependency factories:

- :func:`require_console_principal` — the normal case, yields a
  :class:`ConsolePrincipal` (partner + membership + role).
- :func:`require_console_service` — for the two pre-membership flows
  (look up / accept an invitation) where there is a signed BFF but no
  partner yet. The token carries ``svc: "console"`` and no ``partner_id``.

Failure codes: 401 for anything wrong with the credential (missing,
malformed, expired, replayed, bad signature), 403 for a valid credential
that is not allowed (no membership, suspended partner, console off for
the partner, missing permission), 503 when the console is switched off
platform-wide. Nothing here reveals *why* a membership did not resolve.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.db.models import (
    Partner,
    PartnerMembership,
    PartnerRole,
    PartnerStatus,
)
from nexus_api.repositories.partner import PartnerRepository
from nexus_api.repositories.partner_membership import PartnerMembershipRepository

log = structlog.get_logger(__name__)

JWT_ALGORITHM = "EdDSA"
_SERVICE_CLAIM = "console"


# ── permissions ────────────────────────────────────────────────────────

_O, _A, _B, _AN, _BI = (
    PartnerRole.OWNER.value,
    PartnerRole.ADMIN.value,
    PartnerRole.BUILDER.value,
    PartnerRole.ANALYST.value,
    PartnerRole.BILLING.value,
)

#: permission → roles that hold it. This IS the authorization model of the
#: console v1 (PLAN-CONSOLE-V1 §3). Roles are named after jobs; adding a
#: permission is adding a row here, and ``GET /console/me`` publishes the
#: resolved list so the frontend never keeps its own copy.
PERMISSIONS: dict[str, frozenset[str]] = {
    "partner:read": frozenset({_O, _A, _B, _AN, _BI}),
    "clients:read": frozenset({_O, _A, _B, _AN}),
    "clients:write": frozenset({_O, _A, _B}),
    "clients:delete": frozenset({_O, _A}),
    "agents:read": frozenset({_O, _A, _B, _AN}),
    "agents:write": frozenset({_O, _A, _B}),
    "channels:read": frozenset({_O, _A, _B, _AN}),
    "channels:write": frozenset({_O, _A, _B}),
    # Metadata only — bodies never leave the backend (C8).
    "conversations:read": frozenset({_O, _A, _B, _AN}),
    "usage:read": frozenset({_O, _A, _B, _AN, _BI}),
    "audit:read": frozenset({_O, _A, _AN}),
    "team:read": frozenset({_O, _A, _B, _AN, _BI}),
    "team:manage": frozenset({_O, _A}),
    "keys:read": frozenset({_O, _A, _B}),
    "keys:manage": frozenset({_O, _A}),
    "billing:read": frozenset({_O, _BI}),
    "billing:manage": frozenset({_O, _BI}),
    # Playground turns spend the partner's QA cap (0082) — builders may run it.
    "playground:run": frozenset({_O, _A, _B}),
    # Usage alert thresholds and recipients (CP-24).
    "usage:manage": frozenset({_O, _A}),
    # Knowledge documents/URLs of a client (CP-15).
    "knowledge:read": frozenset({_O, _A, _B, _AN}),
    "knowledge:write": frozenset({_O, _A, _B}),
    # The console Companion (CO-01). Same three roles as ``playground:run``
    # and for the same two reasons: it spends the partner's LLM budget, and
    # from CO-04 it writes — through the very same ``/console/*`` routers,
    # so an ``analyst`` still gets the router's 403 for anything it may not
    # do. This permission gates the DOOR, not the actions behind it.
    "companion:use": frozenset({_O, _A, _B}),
}


def permissions_for(role: str) -> frozenset[str]:
    return frozenset(p for p, roles in PERMISSIONS.items() if role in roles)


# ── principals ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConsolePrincipal:
    """A verified console request: who, in which partner, with what role.

    ``role`` and ``permissions`` come from the membership row, never
    from the token. ``jti`` is kept for audit correlation.
    """

    user_id: str
    partner: Partner
    membership: PartnerMembership
    role: str
    jti: str

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.role)

    @property
    def actor(self) -> str:
        """Audit-log actor string.

        Normally ``console:<e-mail>`` — the e-mail is what a human reads in
        the audit page ("maria@facelad.com published v7").

        **When the call comes from the Companion it is ``companion:<user_id>``
        instead** (CO-04). A write the agent made must not look, in the audit
        log, exactly like one the person made by hand: they are different
        events even when the same person is behind both. The person stays
        recoverable — ``companion.actions.decided_by`` holds whoever
        confirmed it, and that row is what the audit page joins against.

        The branch reads the in-process actor rather than a flag on the
        principal because that variable is the *only* thing that can tell a
        Companion call apart, and it is set exclusively by the tool runner,
        inside the run's task, after a real principal has been verified. The
        identity check (``user_id``) is what stops a stale outer actor from
        relabelling an unrelated request.
        """
        actor = _in_process_actor.get()
        if actor is not None and actor.user_id == self.user_id:
            return f"companion:{self.user_id}"
        return f"console:{self.membership.email}"


@dataclass(frozen=True)
class ConsoleService:
    """A verified BFF call with no partner context (invitation flows)."""

    jti: str


# ── in-process actor (Companion, CO-02) ────────────────────────────────
#
# Las herramientas del Companion llaman a los MISMOS routers ``/console/*``
# que la interfaz, por HTTP en proceso (``ASGITransport``). Lo que no
# pueden llevar es el Bearer del navegador: el token de consola vive 60
# segundos y su ``jti`` se quema en la primera presentación
# (:func:`consume_jti`), mientras que un run del Companion dura minutos y
# hace decenas de llamadas. Y minar uno nuevo exigiría meter la clave
# PRIVADA de la consola en la API, que hoy solo tiene la pública — una
# capacidad nueva (fabricar la identidad de cualquier miembro de cualquier
# partner) a cambio de nada, porque el llamante y el llamado son el mismo
# proceso.
#
# Lo que se propaga es el sujeto, no una credencial. Y **solo** se salta la
# verificación criptográfica y el anti-replay, que son exactamente los dos
# controles cuya razón de ser es el tramo BFF→API por red. Todo lo demás
# corre igual, y eso es lo que hace que esto no sea autorización nueva:
#
#   - la membresía se RELEE de la base de datos en cada llamada, así que un
#     miembro expulsado a mitad de run deja de poder leer;
#   - el partner tiene que seguir activo y con la consola habilitada;
#   - el rol sale de la fila, nunca de un claim;
#   - el permiso que declara la ruta se comprueba igual, así que un
#     ``analyst`` recibe el mismo 403 que recibiría desde el navegador.
#
# Por qué una cabecera forjada no lo enciende: uvicorn crea una tarea por
# petición a partir del contexto RAÍZ del servidor, no del de otra
# petición. La variable solo la fija :func:`acting_as`, dentro de la tarea
# del run y después de que un principal real se haya verificado.
# ``tests/isolation/test_companion_tool_scope.py`` lo fija como garantía.


@dataclass(frozen=True)
class InProcessActor:
    """Quién actúa en una llamada interna. No es una credencial: es el
    sujeto que la petición externa ya verificó."""

    user_id: str
    partner_id: uuid.UUID
    #: Correlación de auditoría. Se distingue a simple vista de un ``jti``
    #: de token real porque lleva prefijo.
    jti: str


_in_process_actor: ContextVar[InProcessActor | None] = ContextVar(
    "console_in_process_actor", default=None
)


def current_in_process_actor() -> InProcessActor | None:
    return _in_process_actor.get()


@contextmanager
def acting_as(actor: InProcessActor) -> Iterator[InProcessActor]:
    """Ejecuta lo de dentro como ``actor`` para las llamadas en proceso.

    Se restaura SIEMPRE, incluso si la llamada lanza: una variable de
    contexto que sobrevive a su bloque es exactamente el fallo que haría
    peligroso este mecanismo.
    """
    token = _in_process_actor.set(actor)
    try:
        yield actor
    finally:
        _in_process_actor.reset(token)


# ── token decoding ─────────────────────────────────────────────────────


def _unauthorized(detail: str = "Invalid console token") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def decode_console_token(token: str) -> dict[str, Any]:
    """Verify signature/claims and return the payload. Raises 401 on any
    problem. Pure function of settings + token — no I/O."""
    settings = get_settings()
    public_key = settings.console_jwt_public_key.strip()
    if not public_key:
        # Fail closed and loud: nothing can authenticate without a key.
        log.error("console_auth.no_public_key")
        raise _unauthorized()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key=public_key,
            algorithms=[JWT_ALGORITHM],
            audience=settings.console_jwt_audience,
            issuer=settings.console_jwt_issuer,
            leeway=settings.console_jwt_leeway_seconds,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Console token expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized() from None

    exp, iat = payload.get("exp"), payload.get("iat")
    if not isinstance(exp, int | float) or not isinstance(iat, int | float):
        raise _unauthorized()
    if exp - iat > settings.console_jwt_max_ttl_seconds:
        # A token minted with a longer life than the BFF is allowed to
        # issue: even if validly signed, it is not one of ours.
        raise _unauthorized("Console token lifetime exceeds policy")
    jti = payload.get("jti")
    if not isinstance(jti, str) or not (8 <= len(jti) <= 64):
        raise _unauthorized()
    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise _unauthorized()
    return payload


# ── jti anti-replay ────────────────────────────────────────────────────

_JTI_KEY_PREFIX = "console:jti:"
_FALLBACK_MAX = 50_000
_seen_jti: dict[str, float] = {}
_seen_lock = threading.Lock()


def _remember_in_memory(jti: str, ttl: float) -> bool:
    """Per-replica fallback. Returns True if ``jti`` was not seen. Bounded:
    when full, expired entries are purged; if still full the token is
    REFUSED (fail closed — a full table under Redis outage is not a
    situation to be generous in)."""
    now = time.monotonic()
    with _seen_lock:
        if jti in _seen_jti and _seen_jti[jti] > now:
            return False
        if len(_seen_jti) >= _FALLBACK_MAX:
            for k in [k for k, exp in _seen_jti.items() if exp <= now]:
                del _seen_jti[k]
            if len(_seen_jti) >= _FALLBACK_MAX:
                return False
        _seen_jti[jti] = now + ttl
        return True


def reset_replay_cache_for_tests() -> None:
    with _seen_lock:
        _seen_jti.clear()


async def consume_jti(redis: Redis, jti: str, *, ttl_seconds: int) -> bool:
    """Mark ``jti`` as used. True the first time, False on replay."""
    try:
        stored = await redis.set(_JTI_KEY_PREFIX + jti, "1", ex=ttl_seconds, nx=True)
        return bool(stored)
    except Exception as exc:  # pragma: no cover - exercised via monkeypatch
        log.warning("console_auth.redis_unavailable_degraded", error=str(exc))
        return _remember_in_memory(jti, float(ttl_seconds))


# ── shared verification steps ──────────────────────────────────────────


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise _unauthorized("Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise _unauthorized("Missing bearer token")
    return token


def _require_console_switch() -> None:
    if not get_settings().console_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Partner console is disabled",
        )


async def _verify_bearer(authorization: str | None, redis: Redis) -> dict[str, Any]:
    _require_console_switch()
    payload = decode_console_token(_bearer(authorization))
    settings = get_settings()
    ttl = int(payload["exp"] - payload["iat"]) + settings.console_jwt_leeway_seconds
    if not await consume_jti(redis, payload["jti"], ttl_seconds=max(ttl, 1)):
        log.warning("console_auth.replayed_jti", jti=payload["jti"], sub=payload["sub"])
        raise _unauthorized("Console token already used")
    return payload


# ── dependencies ───────────────────────────────────────────────────────


def require_console_principal(
    *required: str,
) -> Callable[..., Awaitable[ConsolePrincipal]]:
    """Dependency factory: ``Depends(require_console_principal("clients:read"))``.

    Every permission named must be held by the resolved role. With no
    arguments the dependency only authenticates and resolves the
    membership (use ``partner:read`` for the ``/me`` style endpoints).
    """
    for perm in required:
        if perm not in PERMISSIONS:  # programming error, caught at import
            raise ValueError(f"unknown console permission: {perm!r}")

    async def _dependency(
        authorization: str | None = Header(default=None, alias="Authorization"),
        session: AsyncSession = Depends(get_db_session),
        redis: Redis = Depends(get_redis),
    ) -> ConsolePrincipal:
        actor = _in_process_actor.get()
        if actor is not None:
            # Llamada de una herramienta del Companion contra su propio
            # proceso. Se salta la firma y el anti-replay (ver arriba); la
            # membresía, el estado del partner, el rol y el permiso siguen
            # comprobándose abajo, con el mismo código.
            _require_console_switch()
            partner_id, user_id, jti = actor.partner_id, actor.user_id, actor.jti
        else:
            payload = await _verify_bearer(authorization, redis)
            if payload.get("svc") == _SERVICE_CLAIM:
                raise _forbidden("Service token cannot act as a principal")
            raw_partner = payload.get("partner_id")
            try:
                partner_id = uuid.UUID(str(raw_partner))
            except (ValueError, TypeError, AttributeError):
                raise _unauthorized() from None
            user_id = payload["sub"]
            jti = payload["jti"]

        async with session.begin():
            membership = await PartnerMembershipRepository(session).get_active(partner_id, user_id)
            partner = await PartnerRepository(session).get(partner_id) if membership else None
        if membership is None or partner is None:
            # Unknown user, suspended member, other partner: one answer.
            raise _forbidden("No active membership for this partner")
        if partner.status != PartnerStatus.ACTIVE.value:
            raise _forbidden("Partner is suspended")
        if not partner.console_enabled:
            raise _forbidden("Console is not enabled for this partner")

        role = membership.role
        if actor is None and payload.get("role") not in (None, role):
            # Stale claim (role changed since the session resolved it).
            # The DB wins; log so a busy loop of these is visible.
            log.info("console_auth.role_claim_stale", claimed=payload.get("role"), actual=role)
        held = permissions_for(role)
        missing = [p for p in required if p not in held]
        if missing:
            raise _forbidden(f"Role {role!r} lacks permission: {', '.join(missing)}")

        structlog.contextvars.bind_contextvars(
            partner=partner.slug, console_user=membership.email, console_role=role
        )
        return ConsolePrincipal(
            user_id=user_id,
            partner=partner,
            membership=membership,
            role=role,
            jti=jti,
        )

    return _dependency


def require_console_service() -> Callable[..., Awaitable[ConsoleService]]:
    """Dependency factory for the invitation endpoints: a signed BFF token
    with ``svc: "console"`` and no partner. Same signature / expiry /
    replay rules; no membership lookup."""

    async def _dependency(
        authorization: str | None = Header(default=None, alias="Authorization"),
        redis: Redis = Depends(get_redis),
    ) -> ConsoleService:
        payload = await _verify_bearer(authorization, redis)
        if payload.get("svc") != _SERVICE_CLAIM or payload.get("partner_id") is not None:
            raise _forbidden("Endpoint requires a console service token")
        return ConsoleService(jti=payload["jti"])

    return _dependency


__all__ = [
    "JWT_ALGORITHM",
    "PERMISSIONS",
    "ConsolePrincipal",
    "ConsoleService",
    "InProcessActor",
    "acting_as",
    "consume_jti",
    "current_in_process_actor",
    "decode_console_token",
    "permissions_for",
    "require_console_principal",
    "require_console_service",
    "reset_replay_cache_for_tests",
]
