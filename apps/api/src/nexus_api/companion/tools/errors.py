"""Del código HTTP del router a algo que el modelo pueda usar (CO-02).

Un volcado de excepción dentro del contexto es peor que inútil: el modelo
lo repite al usuario o se inventa una alternativa. Lo que necesita es
**qué pasó y qué hacer a continuación**, en una frase.

El 404 es opaco a propósito y su mensaje no distingue "no existe" de "es de
otro partner" (garantía C1). Si lo distinguiera, el Companion sería un
oráculo para averiguar la cartera de clientes de la competencia probando
referencias.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolError:
    """Lo que ve el modelo cuando una herramienta no puede responder."""

    code: str
    message: str

    def as_payload(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


UNKNOWN_CLIENT = (
    "No hay ningún cliente con esa referencia bajo este partner. "
    "Puede que la referencia no sea la correcta: usa console.list_clients "
    "para verlas y pregunta al usuario cuál quiere. No supongas."
)


def translate_status(status_code: int, detail: str | None, *, tool: str) -> ToolError:
    """Traduce la respuesta del router. ``detail`` es el del router, que ya
    está escrito para un humano — se conserva cuando aporta (409, 422)."""
    if status_code == 404:
        return ToolError("unknown_client", UNKNOWN_CLIENT)
    if status_code == 403:
        return ToolError(
            "forbidden",
            "El rol de la persona con la que hablas no permite esta consulta. "
            "Díselo con naturalidad y no lo intentes por otro camino: no lo hay.",
        )
    if status_code == 409:
        return ToolError(
            "conflict",
            (detail or "El estado actual no permite esta consulta.")
            + " Es una respuesta válida sobre cómo está la plataforma, no un fallo.",
        )
    if status_code == 422:
        return ToolError(
            "bad_arguments",
            f"Los argumentos de {tool} no son válidos: {detail or 'revisa el esquema'}. "
            "Corrígelos y vuelve a llamar una sola vez.",
        )
    if status_code == 429:
        return ToolError(
            "rate_limited",
            "Demasiadas consultas seguidas. Termina con lo que ya has leído en vez de reintentar.",
        )
    if status_code == 401:
        return ToolError(
            "unauthenticated",
            "La sesión de esta persona ya no vale. Pídele que recargue la consola.",
        )
    return ToolError(
        "unavailable",
        "La plataforma no respondió a esta consulta. Dilo tal cual — no inventes "
        "el dato ni des una cifra aproximada.",
    )


TIMEOUT = ToolError(
    "timeout",
    "La consulta tardó demasiado y se abandonó. Dilo y sigue con lo que tengas; "
    "no supongas el resultado.",
)


__all__ = ["TIMEOUT", "UNKNOWN_CLIENT", "ToolError", "translate_status"]
