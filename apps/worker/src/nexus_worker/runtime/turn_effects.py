"""Efectos de un turno, como mucho una vez — spec 047, T035 (requisitos 1.3 y 1.6).

Un turno que se reintenta vuelve a correr el grafo entero: el modelo vuelve a
pedir la reserva, el enlace de pago, la respuesta… Cada acción con efecto pasa
por ``turn_effects`` con la clave ``{turno}:{acción}:{n}`` —la n-ésima vez que el
turno la hace—, única por cliente:

- **Herramientas con efecto** (``tool_once``). La clave se toma **antes** de
  ejecutar: si ya estaba, el reintento recibe lo que contestó la primera vez y
  la herramienta no corre. Si la herramienta dice que no hizo nada (un error),
  la clave se suelta y el reintento puede probar otra vez. Si el worker murió a
  mitad de una herramienta, la clave queda sin resultado y el reintento **no**
  la repite: «como mucho una vez» gana a «al menos una vez».
- **La respuesta** (``claim_reply``). La fila del saliente y su clave se
  escriben en la misma transacción: o están las dos o ninguna. Un reintento
  que vuelve a escribir la respuesta se queda con la fila de la primera vez.
- **El cobro del turno** no pasa por aquí: el débito es ``channel:{turno}`` en
  el libro, idempotente, y el turno conserva su ``turn_id`` en cada intento.

Fuera de un turno de canal (el Playground, el Companion, los crons) no hay
turno en el contexto y todo corre como siempre.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import require_current_tenant, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.runtime.turns import TurnRef, as_dict, current_turn

log = structlog.get_logger(__name__)

#: ``contracts/events.md`` §5, ``turn.effect``: qué clase de efecto es.
_EFFECT_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("reservas.", "reserve"),
    # Spec 048: retired, but it still books for the versions that name it.
    ("booking.", "reserve"),
    ("queue.", "reserve"),
    ("woocommerce.build_checkout_link", "send_link"),
    ("payments.", "send_link"),
    ("billing.register_payment", "charge"),
    ("billing.add_charge", "charge"),
)


def effect_for_tool(tool: str) -> str:
    for prefix, effect in _EFFECT_BY_PREFIX:
        if tool.startswith(prefix):
            return effect
    return "tool"


_CLAIM_SQL = sa.text(
    """
    INSERT INTO turn_effects (tenant_id, turn_id, effect, idempotency_key)
    VALUES (:tenant, :t, :effect, :key)
    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
    RETURNING id
    """
)
_PRIOR_SQL = sa.text("SELECT result FROM turn_effects WHERE idempotency_key = :key")
_STORE_SQL = sa.text(
    "UPDATE turn_effects SET result = CAST(:result AS jsonb) WHERE idempotency_key = :key"
)
_RELEASE_SQL = sa.text("DELETE FROM turn_effects WHERE idempotency_key = :key AND result IS NULL")


def _log(ref: TurnRef, *, effect: str, key: str, replayed: bool) -> None:
    log.info(
        "turn.effect",
        tenant_id=str(ref.tenant_id),
        agent_id=str(ref.agent_id) if ref.agent_id else None,
        turn_id=str(ref.turn_id),
        effect=effect,
        idempotency_key=key,
        replayed=replayed,
    )


async def _claim(
    session: AsyncSession, ref: TurnRef, *, effect: str, key: str
) -> tuple[bool, dict[str, Any] | None]:
    """``(True, None)`` si la clave es nuestra; ``(False, resultado previo)`` si
    ya la había tomado un intento anterior."""
    inserted = await session.scalar(
        _CLAIM_SQL, {"tenant": ref.tenant_id, "t": ref.turn_id, "effect": effect, "key": key}
    )
    if inserted is not None:
        return True, None
    return False, as_dict(await session.scalar(_PRIOR_SQL, {"key": key}))


async def tool_once(*, tool: str, run: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Ejecuta una herramienta con efecto como mucho una vez por turno."""
    ref = current_turn()
    if ref is None:
        return await run()
    effect = effect_for_tool(tool)
    key = f"{ref.turn_id}:{tool}:{ref.next_ordinal(tool)}"
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
        mine, prior = await _claim(session, ref, effect=effect, key=key)
    if not mine:
        _log(ref, effect=effect, key=key, replayed=True)
        if prior is not None:
            return {**prior, "replayed": True}
        # Un intento anterior la empezó y no llegó a anotar el resultado (murió
        # a mitad). Puede haber ocurrido: no se repite.
        log.warning("turn.effect_uncertain", tenant_id=str(ref.tenant_id), idempotency_key=key)
        return {
            "tool": tool,
            "status": "skipped:already_attempted",
            "replayed": True,
            "result": {
                "note": (
                    "Esta acción ya se intentó en este turno y puede haberse hecho. "
                    "No la repitas: comprueba su estado o dile al cliente que lo revisa una persona."
                )
            },
        }
    try:
        envelope = await run()
    except BaseException:
        await _release(ref, key)
        raise
    if envelope.get("status") == "ok":
        async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
            await session.execute(
                _STORE_SQL, {"key": key, "result": json.dumps(envelope, default=str)}
            )
    else:
        # La herramienta dice que no hizo nada: el reintento puede probar.
        await _release(ref, key)
    _log(ref, effect=effect, key=key, replayed=False)
    return envelope


async def _release(ref: TurnRef, key: str) -> None:
    try:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, ref.tenant_id):
            await session.execute(_RELEASE_SQL, {"key": key})
    except Exception as exc:  # pragma: no cover - lo peor: el reintento no la repite
        log.warning("turn.effect_release_failed", idempotency_key=key, error=str(exc))


async def claim_reply(session: AsyncSession) -> tuple[str, uuid.UUID | None] | None:
    """La clave de la siguiente respuesta del turno, en la transacción de quien
    la escribe. ``None`` fuera de un turno de canal.

    Devuelve ``(clave, None)`` si esta respuesta es nueva —quien llama escribe la
    fila y anota su id con ``record_reply``— o ``(clave, id)`` si un intento
    anterior ya la escribió: quien llama devuelve esa fila y no escribe otra.
    """
    ref = current_turn()
    if ref is None or ref.tenant_id != require_current_tenant():
        return None
    key = f"{ref.turn_id}:reply:{ref.next_ordinal('reply')}"
    mine, prior = await _claim(session, ref, effect="reply", key=key)
    _log(ref, effect="reply", key=key, replayed=not mine)
    if mine:
        return key, None
    raw = (prior or {}).get("message_id")
    return key, uuid.UUID(str(raw)) if raw else None


async def record_reply(session: AsyncSession, key: str, message_id: uuid.UUID) -> None:
    await session.execute(
        _STORE_SQL, {"key": key, "result": json.dumps({"message_id": str(message_id)})}
    )
