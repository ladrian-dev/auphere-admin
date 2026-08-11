"""Per-partner token-bucket rate limiting on Redis (ADR-028, WP-30).

One bucket per (partner, surface). Capacity doubles as burst headroom;
refill rate is the partner's configured per-minute limit. The whole
check-and-consume is a single Lua script so concurrent API replicas
can't race the counter.

**Fail-closed with degradation (WP-30).** Hasta la Fase 3 esto era
fail-open documentado: si Redis se caía, cada partner quedaba sin
límite. Aceptable con un partner conocido; no con la API abierta, donde
el limitador es lo único entre una integración con un bucle mal escrito
y la factura de LLM de Auphere.

Ahora, sin Redis, el cubo se lleva **en memoria y por réplica**. Eso no
es el límite configurado: con N réplicas el techo global pasa a ser N
veces el de cada una. Por eso la cuota de reserva se divide entre
``rate_limit_fallback_replicas`` (el máximo de réplicas de la política
de autoescalado de WP-24), de modo que:

- en el peor caso —todas las réplicas arriba y todas recibiendo tráfico—
  el techo global coincide aproximadamente con el límite configurado;
- en el caso normal, con menos réplicas, se aplica un límite MÁS
  estricto que el configurado.

Es la dirección correcta del error: durante una caída de Redis se
prefiere frenar de más a no frenar. La degradación se cuenta en una
métrica propia porque el operador tiene que enterarse **aunque no se
rechace ni una petición** — mientras dure, el número que se está
aplicando ya no es el que dice la configuración.

El cubo en memoria NO sustituye a Redis cuando Redis funciona: solo se
consulta en la rama de excepción, así que el camino normal sigue siendo
una llamada y el estado sigue siendo compartido entre réplicas.
"""

from __future__ import annotations

import threading
import time

import structlog
from redis.asyncio import Redis

from nexus_api.config import get_settings
from nexus_api.core.otel_metrics import record_rate_limit_degraded

log = structlog.get_logger(__name__)

# KEYS[1] = bucket key
# ARGV = capacity, refill_per_second, now (epoch seconds), cost
# Returns 1 if allowed (token consumed), 0 if rejected.
# ``now`` is read from the Redis server clock (``TIME``) by the caller
# and passed in, so every API replica refills against the same clock —
# process-local clocks would each refill independently and multiply the
# effective limit. Passing it as ARGV keeps the script deterministic.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

tokens = math.min(capacity, tokens + (now - ts) * refill_per_sec)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Idle buckets self-clean once full again: capacity/refill seconds.
redis.call('EXPIRE', key, math.ceil(capacity / refill_per_sec) * 2)
return allowed
"""


# ── cubo de reserva en memoria ────────────────────────────────────────

# Cota del diccionario. Las claves son (partner, superficie), así que en
# la práctica son decenas; el tope existe para que una caída larga de
# Redis con claves inesperadas no se convierta en una fuga de memoria en
# el proceso que además está degradado.
_FALLBACK_MAX_BUCKETS = 10_000

_fallback: dict[str, tuple[float, float]] = {}
_fallback_lock = threading.Lock()


def _allow_in_memory(key: str, *, per_minute: float, cost: float) -> bool:
    """Cubo de fichas local al proceso. Misma aritmética que el Lua, con
    ``time.monotonic()`` en vez del reloj de Redis: aquí no hay nada que
    sincronizar entre réplicas, que es justo la limitación que se asume.

    El lock es un ``threading.Lock`` y no un ``asyncio.Lock`` a
    propósito: la sección crítica es aritmética pura sin ``await``, así
    que no puede ceder el control, y un lock de threading protege además
    del caso de un worker con varios hilos.
    """
    if per_minute <= 0:
        return False
    refill_per_sec = per_minute / 60.0
    now = time.monotonic()
    with _fallback_lock:
        tokens, ts = _fallback.get(key, (per_minute, now))
        tokens = min(per_minute, tokens + (now - ts) * refill_per_sec)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        if key not in _fallback and len(_fallback) >= _FALLBACK_MAX_BUCKETS:
            # Lleno: no se admiten claves nuevas en vez de desalojar. El
            # desalojo devolvería un cubo lleno al siguiente que llame,
            # que es exactamente el fail-open que esto viene a quitar.
            return False
        _fallback[key] = (tokens, now)
    return allowed


def reset_fallback_for_tests() -> None:
    with _fallback_lock:
        _fallback.clear()


async def allow(
    redis: Redis,
    *,
    key: str,
    per_minute: int,
    cost: int = 1,
    surface: str = "unknown",
) -> bool:
    """True if the request fits the bucket. ``per_minute`` is both the
    sustained rate and the burst capacity.

    ``surface`` solo se usa para etiquetar métricas; no cambia el
    cálculo.
    """
    if per_minute <= 0:
        return False
    try:
        seconds, micros = await redis.time()
        now = float(seconds) + float(micros) / 1e6
        result = await redis.eval(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            per_minute,
            per_minute / 60.0,
            now,
            cost,
        )
        return bool(int(result))
    except Exception as exc:
        replicas = max(1, get_settings().rate_limit_fallback_replicas)
        # El techo por réplica nunca baja de 1: con un límite configurado
        # muy bajo, dividirlo daría cero y cerraría la superficie entera
        # por una caída de Redis. Frenar de más, no cortar del todo.
        share = max(1.0, per_minute / replicas)
        allowed = _allow_in_memory(key, per_minute=share, cost=cost)
        record_rate_limit_degraded(surface=surface)
        log.error(
            "rate_limit.redis_unavailable_degraded",
            key=key,
            surface=surface,
            error=str(exc),
            configured_per_minute=per_minute,
            per_replica_per_minute=share,
            allowed=allowed,
        )
        return allowed


def mint_bucket_key(partner_id: str) -> str:
    return f"rl:partner:{partner_id}:mint"


def embed_bucket_key(partner_id: str) -> str:
    return f"rl:partner:{partner_id}:embed"


def broadcast_bucket_key(partner_id: str) -> str:
    """Server-to-server broadcast surface. Its own bucket so a partner
    hammering sends cannot starve its own provisioning calls (or the
    other way round) — the limits are tuned per surface, not shared."""
    return f"rl:partner:{partner_id}:broadcast"
