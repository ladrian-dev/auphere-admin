"""Los helpers puros del código de emparejamiento — spec 002, Requisito 3.

Viven en ``core`` y no en ``services`` porque los usa el repositorio, y
``repositories`` no puede importar ``services`` sin cerrar un ciclo. Aquí no hay
IO: alfabeto, generación, normalización y hash.

**El alfabeto se puede dictar en voz alta**: sin ``0/O``, ``1/I/L`` ni ``U/V``.
30^8 ~ 6,6e11 combinaciones vivas diez minutos.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL = timedelta(minutes=10)


def generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def display_code(code: str) -> str:
    """``K7MP4XQ2`` → ``K7MP-4XQ2``. Lo que se enseña, no lo que se guarda."""
    return f"{code[:4]}-{code[4:]}"


def normalize_code(raw: str) -> str | None:
    """Mayúsculas, sin guiones ni espacios; ``None`` si no tiene la forma."""
    cleaned = "".join(ch for ch in raw.upper() if ch not in "- \t")
    if len(cleaned) != CODE_LENGTH or any(ch not in ALPHABET for ch in cleaned):
        return None
    return cleaned


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


__all__ = [
    "ALPHABET",
    "CODE_LENGTH",
    "CODE_TTL",
    "display_code",
    "generate_code",
    "hash_code",
    "normalize_code",
]
