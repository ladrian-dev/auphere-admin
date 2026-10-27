"""El turno de una conversación: agrupación, candado y reintento — spec 047, ola 1.

Requisitos 1.1 a 1.3 (research D9 y D43). Tres piezas:

1. **La cola diferida (Redis).** Cada entrante, ya guardado, programa el turno
   de su conversación a ``ahora + ventana`` en un conjunto ordenado por
   vencimiento, deduplicado por conversación (``schedule_turn``). Cada mensaje
   empuja el vencimiento —la ventana cuenta desde el último—, con un tope
   (``max_wait_ms``) para que un contacto que no para de escribir reciba
   respuesta igual. El que recoge un turno vencido (``pop_due``) no lo borra:
   lo aparca más adelante (``VISIBILITY_MS``) y solo lo borra al terminar
   (``settle``). Si el worker muere a mitad, el turno vuelve a vencer solo.
2. **El candado (Postgres).** ``claim_turn`` toma, con
   ``pg_advisory_xact_lock`` por conversación, todos sus entrantes sin
   ``turn_id`` y les pone el del turno (el id del primero). El turno deja un
   registro en ``turn_effects`` (``{turno}:turn``) con su estado y un
   **arriendo**: mientras está vigente, otro worker que llegue a la misma
   conversación se encuentra «ocupada» y vuelve a intentarlo tras la ventana.
   El candado de la base solo se sostiene lo que dura la toma: detrás hay
   PgBouncer en modo transaction, y un candado de sesión —o una transacción
   abierta durante las llamadas al modelo— se quedaría con una conexión del
   pool por turno en vuelo.
3. **El reintento.** Un turno que falla deja su registro en ``running`` con el
   arriendo vencido; el siguiente intento lo retoma **con el mismo
   ``turn_id``** y los mismos mensajes, y cada efecto pasa por
   ``turn_effects`` (``runtime/turn_effects.py``), así que nada se repite. A
   los ``MAX_TURN_ATTEMPTS`` intentos el turno se da por perdido y la
   conversación pasa a una persona.

La verdad del turno —qué mensajes tomó, en qué estado está— es la base. Redis
solo dice cuándo mirar: si perdiera la cola, los mensajes siguen en la base sin
``turn_id`` y el siguiente entrante de la conversación los recoge.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

#: El registro del turno en ``turn_effects``: ``{turn_id}:turn``.
TURN_EFFECT = "turn"
#: Lo que dura el arriendo de un turno sin renovarlo. El turno lo renueva cada
#: ``HEARTBEAT_S`` mientras corre; un worker muerto lo deja vencer.
LEASE_S = 120
HEARTBEAT_S = 30
#: Intentos de un turno antes de darlo por perdido (el mismo tope que la DLQ).
MAX_TURN_ATTEMPTS = 5
#: Un entrante sin turno más viejo que esto no se toma: son los mensajes de
#: antes de la 0176 (todos con ``turn_id`` NULL) y no se contestan tarde.
UNTAKEN_HORIZON = timedelta(minutes=15)
#: Dónde buscar el turno en curso de una conversación (por sus mensajes).
RECENT_TURNS = timedelta(hours=1)
#: La ráfaga más larga que se agrupa, en ventanas.
MAX_WAIT_WINDOWS = 5
#: Lo que se aparca un turno recogido: un poco más que su arriendo.
VISIBILITY_MS = (LEASE_S + 30) * 1000

DUE_PREFIX = "nexus:turns:due"


class TurnRetry(Exception):
    """El turno falló y se reintentará con el mismo ``turn_id``."""

    def __init__(self, turn_id: uuid.UUID, attempt: int, error: str) -> None:
        super().__init__(f"turn {turn_id} attempt {attempt} failed: {error}")
        self.turn_id = turn_id
        self.attempt = attempt
        self.error = error


@dataclass
class TurnRef:
    """El turno en curso. Viaja en un ``ContextVar`` para que las herramientas y
    la persistencia de la respuesta sepan a qué turno pertenecen sus efectos."""

    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    turn_id: uuid.UUID
    attempt: int = 1
    message_ids: tuple[uuid.UUID, ...] = ()
    agent_id: uuid.UUID | None = None
    _ordinals: dict[str, int] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.turn_id}:{TURN_EFFECT}"

    def next_ordinal(self, action: str) -> int:
        """La n-ésima vez que el turno hace ``action``. Un reintento empieza de
        cero, así que su primera reserva es la primera reserva del original."""
        n = self._ordinals.get(action, 0) + 1
        self._ordinals[action] = n
        return n


_current: ContextVar[TurnRef | None] = ContextVar("nexus_turn", default=None)


def current_turn() -> TurnRef | None:
    return _current.get()


@contextlib.contextmanager
def turn_scope(ref: TurnRef) -> Iterator[TurnRef]:
    token = _current.set(ref)
    try:
        yield ref
    finally:
        _current.reset(token)


@dataclass(frozen=True)
class Claim:
    """``claimed`` (el turno es tuyo), ``busy`` (otro lo está corriendo) o
    ``none`` (no hay nada que tomar: otro turno ya se llevó los mensajes)."""

    kind: str
    turn: TurnRef | None = None
    retry: bool = False


_LOCK_SQL = sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))")

# El turno vivo de la conversación, si lo hay: se llega por los ``turn_id`` de
# sus entrantes recientes (índice por conversación) al registro de cada turno
# (índice único por clave). Sin columna nueva en ``conversations``.
_RUNNING_SQL = sa.text(
    """
    SELECT te.turn_id,
           te.result,
           COALESCE((te.result->>'lease_until')::timestamptz > now(), false) AS leased
      FROM turn_effects te
     WHERE te.effect = 'turn'
       AND te.result->>'state' = 'running'
       AND te.idempotency_key IN (
             SELECT DISTINCT m.turn_id::text || ':' || 'turn'
               FROM messages m
              WHERE m.conversation_id = :c
                AND m.direction = 'inbound'
                AND m.turn_id IS NOT NULL
                AND m.created_at > now() - make_interval(secs => :recent))
     ORDER BY te.created_at
     LIMIT 1
     FOR UPDATE OF te
    """
)

_UNTAKEN_SQL = sa.text(
    """
    SELECT id
      FROM messages
     WHERE conversation_id = :c
       AND direction = 'inbound'
       AND turn_id IS NULL
       AND created_at > now() - make_interval(secs => :horizon)
     ORDER BY created_at, id
    """
)

_TAKE_SQL = sa.text(
    """
    UPDATE messages
       SET turn_id = :t
     WHERE conversation_id = :c
       AND id = ANY(CAST(:ids AS uuid[]))
       AND turn_id IS NULL
    """
)

_TURN_MESSAGES_SQL = sa.text(
    "SELECT id FROM messages WHERE conversation_id = :c AND turn_id = :t "
    "AND direction = 'inbound' ORDER BY created_at, id"
)

_RECORD_SQL = sa.text(
    """
    INSERT INTO turn_effects (tenant_id, turn_id, effect, idempotency_key, result)
    VALUES (:tenant, :t, 'turn', :key, CAST(:result AS jsonb))
    """
)

_PATCH_SQL = sa.text(
    """
    UPDATE turn_effects
       SET result = COALESCE(result, '{}'::jsonb) || CAST(:patch AS jsonb)
     WHERE effect = 'turn' AND idempotency_key = :key
    """
)

_TOUCH_SQL = sa.text("UPDATE conversations SET last_turn_at = now() WHERE id = :c")


def _lease_until() -> str:
    return (datetime.now(UTC) + timedelta(seconds=LEASE_S)).isoformat()


def as_dict(raw: Any) -> dict[str, Any] | None:
    """Un ``jsonb`` leído con SQL de texto llega como cadena o como dict según el
    driver: los dos valen."""
    if isinstance(raw, str):
        raw = json.loads(raw)
    return raw if isinstance(raw, dict) else None


async def claim_turn(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Claim:
    """Toma el turno de la conversación, si se puede (ver el docstring del módulo).

    En orden, bajo el candado:
    1. un turno vivo con el arriendo vigente → ``busy``;
    2. un turno vivo con el arriendo vencido (su worker murió o falló) → se
       retoma: mismo ``turn_id``, mismos mensajes, un intento más;
    3. si no, los entrantes sin turno → un turno nuevo, o ``none`` si no hay.
    """
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(_LOCK_SQL, {"k": f"turn:{conversation_id}"})
        running = (
            await session.execute(
                _RUNNING_SQL,
                {"c": conversation_id, "recent": RECENT_TURNS.total_seconds()},
            )
        ).first()
        if running is not None:
            turn_id, record, leased = running
            if leased:
                return Claim("busy")
            attempt = int((as_dict(record) or {}).get("attempt") or 1) + 1
            await session.execute(
                _PATCH_SQL,
                {
                    "key": f"{turn_id}:{TURN_EFFECT}",
                    "patch": json.dumps({"attempt": attempt, "lease_until": _lease_until()}),
                },
            )
            ids = tuple(
                r[0]
                for r in (
                    await session.execute(_TURN_MESSAGES_SQL, {"c": conversation_id, "t": turn_id})
                ).all()
            )
            await session.execute(_TOUCH_SQL, {"c": conversation_id})
            log.warning(
                "turn.retried",
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                turn_id=str(turn_id),
                attempt=attempt,
            )
            return Claim(
                "claimed",
                TurnRef(tenant_id, conversation_id, turn_id, attempt=attempt, message_ids=ids),
                retry=True,
            )

        ids = tuple(
            r[0]
            for r in (
                await session.execute(
                    _UNTAKEN_SQL,
                    {"c": conversation_id, "horizon": UNTAKEN_HORIZON.total_seconds()},
                )
            ).all()
        )
        if not ids:
            return Claim("none")
        turn_id = ids[0]
        await session.execute(_TAKE_SQL, {"t": turn_id, "c": conversation_id, "ids": list(ids)})
        await session.execute(
            _RECORD_SQL,
            {
                "tenant": tenant_id,
                "t": turn_id,
                "key": f"{turn_id}:{TURN_EFFECT}",
                "result": json.dumps(
                    {
                        "conversation_id": str(conversation_id),
                        "state": "running",
                        "attempt": 1,
                        "messages": len(ids),
                        "lease_until": _lease_until(),
                    }
                ),
            },
        )
        await session.execute(_TOUCH_SQL, {"c": conversation_id})
    return Claim("claimed", TurnRef(tenant_id, conversation_id, turn_id, message_ids=ids))


async def _patch(ref: TurnRef, patch: dict[str, Any]) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
        await session.execute(_PATCH_SQL, {"key": ref.key, "patch": json.dumps(patch)})


async def finish_turn(ref: TurnRef, *, state: str, reason: str | None = None) -> None:
    """Cierra el registro: ``done`` (contestó), ``gated`` (una puerta no dejó
    contestar, con su motivo) o ``failed`` (se agotaron los intentos)."""
    patch: dict[str, Any] = {
        "state": state,
        "lease_until": None,
        "finished_at": datetime.now(UTC).isoformat(),
    }
    if reason:
        patch["reason"] = reason
    await _patch(ref, patch)


async def release_for_retry(ref: TurnRef, *, error: str) -> None:
    """El intento falló: el registro sigue vivo con el arriendo vencido, para
    que el siguiente intento lo retome en cuanto llegue."""
    await _patch(ref, {"lease_until": datetime.now(UTC).isoformat(), "last_error": error[:300]})


async def keep_alive(ref: TurnRef) -> None:
    """Renueva el arriendo mientras el turno corre. Se cancela al acabar."""
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        try:
            await _patch(ref, {"lease_until": _lease_until()})
        except Exception as exc:  # pragma: no cover - el turno sigue igual
            log.warning("turn.heartbeat_failed", turn_id=str(ref.turn_id), error=str(exc))


# ── La cola diferida ─────────────────────────────────────────────────────────


def due_queue(stream: str) -> str:
    """Una cola por stream: un turno de un cliente prioritario lo recoge su
    propio pool de runners, como su mensaje (WP-10)."""
    return f"{DUE_PREFIX}:{stream}"


def member_for(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    return f"{tenant_id}:{conversation_id}"


def parse_member(member: str | bytes) -> tuple[uuid.UUID, uuid.UUID]:
    raw = member.decode() if isinstance(member, bytes) else member
    tenant, conversation = raw.split(":", 1)
    return uuid.UUID(tenant), uuid.UUID(conversation)


def max_wait_ms(window_ms: int) -> int:
    return window_ms * MAX_WAIT_WINDOWS


# KEYS[1] cola, KEYS[2] primer mensaje de la ráfaga; ARGV: miembro, ahora,
# ventana, espera máxima. Debounce con tope, atómico.
_SCHEDULE_LUA = """
local since = redis.call('HGET', KEYS[2], ARGV[1])
if not since then
  since = ARGV[2]
  redis.call('HSET', KEYS[2], ARGV[1], since)
end
local due = math.min(tonumber(ARGV[2]) + tonumber(ARGV[3]), tonumber(since) + tonumber(ARGV[4]))
redis.call('ZADD', KEYS[1], due, ARGV[1])
return 1
"""

# Recoge los vencidos y los aparca hasta ``ahora + visibilidad``.
_POP_LUA = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, tonumber(ARGV[2]))
local token = tonumber(ARGV[1]) + tonumber(ARGV[3])
for _, m in ipairs(due) do
  redis.call('ZADD', KEYS[1], token, m)
  redis.call('HDEL', KEYS[2], m)
end
return due
"""

# Borra el turno de la cola solo si nadie lo ha vuelto a programar mientras
# corría: un mensaje nuevo cambia su vencimiento y tiene que tener su turno.
_SETTLE_LUA = """
local s = redis.call('ZSCORE', KEYS[1], ARGV[1])
if s and tonumber(s) == tonumber(ARGV[2]) then
  return redis.call('ZREM', KEYS[1], ARGV[1])
end
return 0
"""


def _since_key(queue: str) -> str:
    return f"{queue}:since"


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


async def schedule_turn(
    redis: Redis,
    *,
    queue: str,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    window_ms: int,
    now_ms: int | None = None,
) -> None:
    """Programa (o empuja) el turno de la conversación."""
    now = _now_ms() if now_ms is None else now_ms
    await redis.eval(
        _SCHEDULE_LUA,
        2,
        queue,
        _since_key(queue),
        member_for(tenant_id, conversation_id),
        str(now),
        str(window_ms),
        str(max_wait_ms(window_ms)),
    )


async def pop_due(
    redis: Redis, *, queue: str, limit: int, now_ms: int | None = None
) -> tuple[list[str], int]:
    """Los turnos vencidos, ya aparcados. Devuelve los miembros y la marca con la
    que se aparcaron (lo que ``settle`` comprueba)."""
    now = _now_ms() if now_ms is None else now_ms
    raw = await redis.eval(
        _POP_LUA, 2, queue, _since_key(queue), str(now), str(limit), str(VISIBILITY_MS)
    )
    members = [m.decode() if isinstance(m, bytes) else str(m) for m in (raw or [])]
    return members, now + VISIBILITY_MS


async def settle(redis: Redis, *, queue: str, member: str, token: int) -> bool:
    removed = await redis.eval(_SETTLE_LUA, 1, queue, member, str(token))
    return bool(removed)


async def reschedule(redis: Redis, *, queue: str, member: str, at_ms: int) -> None:
    await redis.zadd(queue, {member: at_ms})
