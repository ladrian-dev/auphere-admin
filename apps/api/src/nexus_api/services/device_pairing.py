"""El código de emparejamiento — spec 002, Requisito 3 (`contracts/pairing.md`).

**El canal entre la consola y la cáscara es la persona.** La consola enseña un
código; la persona lo teclea en la barra; la barra lo canjea. Por eso el código
tiene que poder leerse en voz alta sin ambigüedad: el alfabeto no tiene ``0/O``,
``1/I/L`` ni ``U/V``… y se enseña en dos grupos de cuatro.

30^8 ~ 6,6e11 combinaciones vivas diez minutos, con cinco intentos por máquina
antes de esperar: la fuerza bruta no llega. Es la forma de las invitaciones
(``hash_invitation_token``, ``secrets``) con un alfabeto que se puede dictar.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis

from nexus_api.core.pairing_codes import (
    ALPHABET,
    CODE_LENGTH,
    CODE_TTL,
    display_code,
    generate_code,
    hash_code,
    normalize_code,
)

#: Cinco fallos por máquina en diez minutos → espera de 60 s que se duplica hasta 15 min.
ATTEMPT_LIMIT = 5
ATTEMPT_WINDOW = timedelta(minutes=10)
BACKOFF_BASE = timedelta(seconds=60)
BACKOFF_MAX = timedelta(minutes=15)


class PairingRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"demasiados intentos; espera {retry_after_seconds} s")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class PairingRateLimiter:
    """Límite de intentos en Redis, por clave de máquina (hostname + IP).

    Dos claves: la cuenta de fallos en la ventana y, si se supera, una espera
    creciente. Un canje **correcto** borra las dos: la máquina ya no es sospechosa.
    """

    redis: Redis

    @staticmethod
    def _keys(machine_key: str) -> tuple[str, str, str]:
        base = f"device:pair:{hashlib.sha256(machine_key.encode()).hexdigest()[:24]}"
        return f"{base}:fails", f"{base}:wait", f"{base}:strikes"

    async def check(self, machine_key: str) -> None:
        _, wait_key, _ = self._keys(machine_key)
        ttl = await self.redis.ttl(wait_key)
        if ttl and ttl > 0:
            raise PairingRateLimited(int(ttl))

    async def record_failure(self, machine_key: str) -> None:
        fails_key, wait_key, strikes_key = self._keys(machine_key)
        fails = await self.redis.incr(fails_key)
        if fails == 1:
            await self.redis.expire(fails_key, int(ATTEMPT_WINDOW.total_seconds()))
        if fails >= ATTEMPT_LIMIT:
            strikes = await self.redis.incr(strikes_key)
            await self.redis.expire(strikes_key, int(BACKOFF_MAX.total_seconds()) * 4)
            wait = min(BACKOFF_BASE * (2 ** (strikes - 1)), BACKOFF_MAX)
            await self.redis.set(wait_key, "1", ex=int(wait.total_seconds()))
            await self.redis.delete(fails_key)

    async def clear(self, machine_key: str) -> None:
        await self.redis.delete(*self._keys(machine_key))


__all__ = [
    "ALPHABET",
    "ATTEMPT_LIMIT",
    "CODE_LENGTH",
    "CODE_TTL",
    "PairingRateLimited",
    "PairingRateLimiter",
    "display_code",
    "generate_code",
    "hash_code",
    "normalize_code",
]
