"""Presupuesto: contadores, política y veredicto (WP-20).

El contador vive en Redis y no en Postgres porque se consulta **antes de
gastar, en cada turno**: una consulta agregada sobre ``usage_records``
en el camino crítico costaría más latencia que el propio ahorro. El
consumidor de metering lo incrementa cuando persiste el consumo, así que
el contador va unos segundos por detrás de la realidad — asumido: un
presupuesto que se pasa por unos céntimos no es el problema que esto
viene a resolver.

Dos niveles siempre, ``tenant`` y ``partner``. En el canal de partners
Auphere factura al partner, así que el saldo que corta de verdad es el
suyo agregado; con solo el nivel de tenant, veinte clientes por debajo
de su límite individual hunden el margen del partner sin activar nada.

**Qué hace cada umbral**, y por qué el duro no es "apagar el agente":

- Blando → se degrada (modelo barato, grader apagado). El cliente final
  no nota nada más que, quizá, una respuesta algo menos pulida.
- Duro → no se abren turnos nuevos, pero **se responde igual**, con un
  traspaso a un humano, y se avisa al dueño. Un agente mudo delante de
  los clientes de un tercero es el peor fallo posible de este producto:
  el cliente final no sabe que hay un presupuesto, solo ve que el
  negocio al que escribió no contesta.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

# Medidor agregado: dólares. Los medidores por token también pueden tener
# política, pero el que se consulta en el camino crítico es este.
COST_METER = "cost_usd"

# El contador del día sobrevive al cambio de día para que un turno a las
# 23:59:59 no lea un contador recién nacido; el del mes, al cambio de mes.
_TTL_S = {"day": 48 * 3600, "month": 40 * 24 * 3600}

# La política cambia con una edición del operador, no con un turno.
_POLICY_TTL_S = 60.0


@dataclass(frozen=True)
class BudgetPolicy:
    scope: str
    scope_id: uuid.UUID
    meter: str
    period: str
    soft_limit: Decimal
    hard_limit: Decimal
    soft_action: str


@dataclass(frozen=True)
class BudgetVerdict:
    """Qué hacer con este turno."""

    # ``ok`` | ``soft`` (degradar) | ``hard`` (no abrir turno)
    level: str
    # Qué política lo disparó, para el log y para el mensaje al dueño.
    scope: str | None = None
    period: str | None = None
    spent: Decimal | None = None
    limit: Decimal | None = None
    soft_action: str = "downgrade"

    @property
    def is_hard(self) -> bool:
        return self.level == "hard"

    @property
    def degrade_model(self) -> bool:
        return self.level == "soft" and self.soft_action in {"downgrade", "both"}

    @property
    def disable_grader(self) -> bool:
        return self.level == "soft" and self.soft_action in {"grader_off", "both"}


def period_bucket(period: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return now.strftime("%Y-%m-%d") if period == "day" else now.strftime("%Y-%m")


def counter_key(scope: str, scope_id: uuid.UUID, meter: str, period: str, bucket: str) -> str:
    return f"nexus:budget:{scope}:{scope_id}:{meter}:{period}:{bucket}"


async def add_spend(
    redis: Redis,
    *,
    scope: str,
    scope_id: uuid.UUID,
    amount: Decimal,
    meter: str = COST_METER,
    now: datetime | None = None,
) -> None:
    """Suma gasto a los contadores del día y del mes. Nunca lanza.

    Perder un incremento retrasa un corte; romper la ingesta de consumo
    pierde el dato de facturación, que es irrecuperable.
    """
    if amount <= 0:
        return
    try:
        for period in ("day", "month"):
            key = counter_key(scope, scope_id, meter, period, period_bucket(period, now=now))
            await redis.incrbyfloat(key, float(amount))
            await redis.expire(key, _TTL_S[period])
    except Exception as exc:
        log.warning("budget.increment_failed", scope=scope, scope_id=str(scope_id), error=str(exc))


async def _spent(redis: Redis, key: str) -> Decimal:
    raw = await redis.get(key)
    if raw is None:
        return Decimal(0)
    try:
        return Decimal(raw.decode() if isinstance(raw, bytes) else str(raw))
    except Exception:
        return Decimal(0)


# ── políticas ─────────────────────────────────────────────────────────

_POLICIES_SQL = sa.text(
    """
    SELECT scope, scope_id, meter, period, soft_limit, hard_limit, soft_action
      FROM budget_policies
     WHERE active IS TRUE AND scope = :scope AND scope_id = :sid
    """
)

_policy_cache: dict[tuple[str, uuid.UUID], tuple[float, list[BudgetPolicy]]] = {}


async def load_policies(scope: str, scope_id: uuid.UUID) -> list[BudgetPolicy]:
    """Políticas activas de un ámbito. Sin ámbito de tenant: es
    configuración de plataforma, como ``model_profiles``."""
    cached = _policy_cache.get((scope, scope_id))
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < _POLICY_TTL_S:
        return cached[1]
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            rows = (
                await session.execute(_POLICIES_SQL, {"scope": scope, "sid": str(scope_id)})
            ).all()
    except Exception as exc:
        # Sin política legible NO se corta. Un fallo de lectura que dejara
        # mudo a un agente convertiría un problema de base de datos en una
        # caída de servicio de cara al cliente final.
        log.warning("budget.policy_load_failed", scope=scope, error=str(exc))
        return cached[1] if cached else []

    policies = [
        BudgetPolicy(
            scope=r[0],
            scope_id=r[1],
            meter=r[2],
            period=r[3],
            soft_limit=r[4],
            hard_limit=r[5],
            soft_action=r[6],
        )
        for r in rows
    ]
    _policy_cache[(scope, scope_id)] = (now, policies)
    return policies


def invalidate_policies() -> None:
    _policy_cache.clear()


# ── veredicto ─────────────────────────────────────────────────────────


async def evaluate(
    redis: Redis,
    *,
    tenant_id: uuid.UUID,
    partner_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> BudgetVerdict:
    """Veredicto para el turno que está a punto de empezar.

    Gana el más restrictivo de todos los ámbitos y periodos: si el
    partner está en duro, da igual que el tenant esté holgado — el que
    paga es el partner.
    """
    scopes: list[tuple[str, uuid.UUID]] = [("tenant", tenant_id)]
    if partner_id is not None:
        scopes.append(("partner", partner_id))

    worst = BudgetVerdict("ok")
    for scope, scope_id in scopes:
        for policy in await load_policies(scope, scope_id):
            key = counter_key(
                scope, scope_id, policy.meter, policy.period, period_bucket(policy.period, now=now)
            )
            try:
                spent = await _spent(redis, key)
            except Exception as exc:
                # Mismo criterio que arriba: sin contador no se corta.
                log.warning("budget.counter_read_failed", scope=scope, error=str(exc))
                continue

            if spent >= policy.hard_limit:
                # El duro es terminal: no hace falta seguir mirando.
                return BudgetVerdict(
                    "hard",
                    scope=scope,
                    period=policy.period,
                    spent=spent,
                    limit=policy.hard_limit,
                    soft_action=policy.soft_action,
                )
            if spent >= policy.soft_limit and worst.level == "ok":
                worst = BudgetVerdict(
                    "soft",
                    scope=scope,
                    period=policy.period,
                    spent=spent,
                    limit=policy.soft_limit,
                    soft_action=policy.soft_action,
                )
    return worst
