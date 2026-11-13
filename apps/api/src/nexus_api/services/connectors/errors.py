"""Errores del catálogo de conectores que comparten el servicio y la regla de
disponibilidad (spec 060), sin que uno importe al otro."""

from __future__ import annotations


class ConnectorNotFound(LookupError):
    pass


def not_found_message(slug: str) -> str:
    """El mismo texto para un conector que no existe y para uno no disponible
    para el partner del cliente: distinguirlos sería un oráculo (spec 060, 5.1)."""
    return f"connector slug not found in catalog: {slug!r}"


__all__ = ["ConnectorNotFound", "not_found_message"]
