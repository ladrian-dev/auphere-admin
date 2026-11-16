"""Errores del cliente de Quédate (spec 061, enmienda del 2026-11-16).

Cada uno hereda del error HTTP compartido, como los de Amigable. Los propios:
``QuedateForbidden`` (403: la API del agente aísla por clave, y lo ajeno no es una
credencial mala) y ``QuedateConflict`` (409).
"""

from __future__ import annotations

from nexus_mcp.http import (
    HTTPConnectorAuthError,
    HTTPConnectorError,
    HTTPConnectorNotFound,
    HTTPConnectorRateLimited,
    HTTPConnectorUnavailable,
    HTTPConnectorValidationError,
)


class QuedateError(HTTPConnectorError):
    """Base de todos los errores del cliente de Quédate."""


class QuedateAuthError(HTTPConnectorAuthError, QuedateError):
    """401: la clave no vale."""


class QuedateForbidden(QuedateError):
    """403: la clave vale, pero ese anfitrión o anuncio no es suyo (Quédate aísla por
    clave). No es una credencial mala: no se marca la conexión para reautorizar."""


class QuedateNotFound(HTTPConnectorNotFound, QuedateError):
    """404."""


class QuedateConflict(QuedateError):
    """409: por ejemplo, fechas no disponibles al cotizar."""


class QuedateValidationError(HTTPConnectorValidationError, QuedateError):
    """Otro 4xx. ``field`` es el primer campo que Quédate señala, si lo señala."""

    def __init__(
        self, message: str, *, status_code: int | None = None, field: str | None = None
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.field = field


class QuedateRateLimited(HTTPConnectorRateLimited, QuedateError):
    """429 tras el reintento acotado."""


class QuedateUnavailable(HTTPConnectorUnavailable, QuedateError):
    """5xx o fallo de transporte tras los reintentos."""


__all__ = [
    "QuedateAuthError",
    "QuedateConflict",
    "QuedateError",
    "QuedateForbidden",
    "QuedateNotFound",
    "QuedateRateLimited",
    "QuedateUnavailable",
    "QuedateValidationError",
]
