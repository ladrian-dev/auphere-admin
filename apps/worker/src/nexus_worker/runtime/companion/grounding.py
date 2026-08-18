"""Regla R1 — sin lectura no hay afirmación (CO-02, §9.1).

El primero de los mecanismos anti-alucinación de la investigación, y uno de
los tres que son **código** y no prompt: si la respuesta contiene un dato
del sistema y en el turno no se ejecutó ninguna lectura que lo respalde, el
turno se marca ``unsupported`` y el evento terminal lo señala. Se mide como
métrica, no solo como aviso.

Por qué el detector es estrecho
-------------------------------
El riesgo de un detector amplio es el contrario del que parece. Marcar de
más convierte el aviso en ruido —el usuario aprende a ignorarlo— y la
métrica en basura, porque deja de distinguir el fallo real del "te lo
explico en 3 pasos". Así que se marca **solo** cuando se cumplen las dos
cosas:

1. en el turno no hubo **ninguna lectura con éxito**; y
2. la respuesta encaja con uno de seis patrones estrechos de afirmación
   factual.

Un turno que sí leyó nunca se marca: ahí la comprobación de si el dato
concreto sale de la lectura concreta no la puede hacer una expresión
regular, y fingir que sí sería peor que no comprobar.
"""

from __future__ import annotations

import re

#: Unidades del dominio. Un número pegado a una de estas es una afirmación
#: sobre el sistema, no una enumeración.
_UNITS = (
    "tokens?|mensajes?|conversaciones?|clientes?|canales?|plantillas?|"
    "documentos?|agentes?|miembros?|llamadas?"
)

#: Verbos de estado seguidos de un estado de la plataforma.
_STATES = (
    "activ[oa]s?|publicad[oa]s?|conectad[oa]s?|rechazad[oa]s?|aprobad[oa]s?|"
    "pendientes?|suspendid[oa]s?|en pausa|caducad[oa]s?"
)

FACTUAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("percentage", re.compile(r"\d+(?:[.,]\d+)?\s*%")),
    ("money", re.compile(r"(?:[$€]\s?\d|USD\s?\d|\d[\d.,]*\s?(?:USD|EUR|dólares|euros))")),
    ("count_with_unit", re.compile(rf"\b\d[\d.,]*\s+(?:{_UNITS})\b", re.IGNORECASE)),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\s+de\s+[a-záéíóú]+\b", re.IGNORECASE)),
    ("version", re.compile(r"\bv\d+\b")),
    (
        "state_claim",
        re.compile(
            rf"\b(?:está|están|sigue|siguen|quedó|quedaron|aparece|aparecen)\s+"
            rf"(?:{_STATES})\b",
            re.IGNORECASE,
        ),
    ),
)


def factual_claims(answer: str) -> list[str]:
    """Los patrones que dispararon, por nombre. Vacío si ninguno."""
    return [name for name, pattern in FACTUAL_PATTERNS if pattern.search(answer)]


def is_unsupported(answer: str, *, reads_done: int) -> bool:
    """¿El turno afirma un dato del sistema sin haber leído nada?"""
    if reads_done > 0:
        return False
    return bool(factual_claims(answer))


__all__ = ["FACTUAL_PATTERNS", "factual_claims", "is_unsupported"]
