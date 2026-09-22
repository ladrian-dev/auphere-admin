"""Techo de intentos para un código de un solo uso.

Esto era ``services/device_pairing.py``, y —como el generador que acompañaba—
**no era del emparejamiento**: su limitador lo usan también los códigos de
sesión de la spec 009 (`api/console/session_codes.py` y
`services/session_codes.py`). Retirar el módulo con el código de emparejamiento
habría roto el inicio de sesión de la aplicación; lo cazó la suite al no poder
ni importar doce ficheros.

Se queda, con el nombre de lo que hace. Ver la misma nota en
``core/one_time_codes.py``: un nombre que se refiere al primer llamante miente
en cuanto hay un segundo.

La forma del límite es la que tenía y sigue siendo la correcta: **dos claves**
—los fallos dentro de la ventana, y una espera creciente si se supera— y un
canje correcto borra las dos, porque quien acierta deja de ser sospechoso.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis

#: Cinco fallos en diez minutos → espera de 60 s que se duplica hasta 15 min.
ATTEMPT_LIMIT = 5
ATTEMPT_WINDOW = timedelta(minutes=10)
BACKOFF_BASE = timedelta(seconds=60)
BACKOFF_MAX = timedelta(minutes=15)


class CodeRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"demasiados intentos; espera {retry_after_seconds} s")
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class CodeRateLimiter:
    """Límite de intentos en Redis, por la clave que identifique a quien prueba.

    El prefijo de las claves se conserva (``device:pair:``) a propósito: cambiarlo
    dejaría sin efecto los contadores que hubiera vivos en producción, y un
    limitador que se reinicia al desplegar es un limitador que no limita el día
    que importa.
    """

    redis: Redis

    @staticmethod
    def _keys(key: str) -> tuple[str, str, str]:
        base = f"device:pair:{hashlib.sha256(key.encode()).hexdigest()[:24]}"
        return f"{base}:fails", f"{base}:wait", f"{base}:strikes"

    async def check(self, key: str) -> None:
        _, wait_key, _ = self._keys(key)
        ttl = await self.redis.ttl(wait_key)
        if ttl and ttl > 0:
            raise CodeRateLimited(int(ttl))

    async def record_failure(self, key: str) -> None:
        fails_key, wait_key, strikes_key = self._keys(key)
        fails = await self.redis.incr(fails_key)
        if fails == 1:
            await self.redis.expire(fails_key, int(ATTEMPT_WINDOW.total_seconds()))
        if fails >= ATTEMPT_LIMIT:
            strikes = await self.redis.incr(strikes_key)
            await self.redis.expire(strikes_key, int(BACKOFF_MAX.total_seconds()) * 4)
            wait = min(BACKOFF_BASE * (2 ** (strikes - 1)), BACKOFF_MAX)
            await self.redis.set(wait_key, "1", ex=int(wait.total_seconds()))
            await self.redis.delete(fails_key)

    async def clear(self, key: str) -> None:
        await self.redis.delete(*self._keys(key))


#: Los nombres de antes, para no tocar a sus llamantes en el mismo cambio que
#: retira el emparejamiento. Son alias, no una segunda implementación.
PairingRateLimited = CodeRateLimited
PairingRateLimiter = CodeRateLimiter

__all__ = [
    "ATTEMPT_LIMIT",
    "ATTEMPT_WINDOW",
    "BACKOFF_BASE",
    "BACKOFF_MAX",
    "CodeRateLimited",
    "CodeRateLimiter",
    "PairingRateLimited",
    "PairingRateLimiter",
]
