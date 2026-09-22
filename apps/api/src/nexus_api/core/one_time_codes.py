"""Códigos de un solo uso que una persona puede dictar en voz alta.

Esto era ``core/pairing_codes.py``, y el nombre venía de su primer uso. Al
retirar el emparejamiento (spec 012) resultó que **no era suyo**: los códigos de
sesión de la spec 009 usaban el mismo generador, y borrar el módulo habría roto
el inicio de sesión de la aplicación. Lo cazó
``tests/isolation/test_39_no_pairing_code_path.py`` —el barrido que afirma que
el código de emparejamiento no existe— antes de que llegara a ninguna parte.

Así que el módulo se queda, con el nombre que describe lo que hace y no quién lo
estrenó. Un nombre que se refiere al primer llamante es un nombre que miente en
cuanto hay un segundo.

Vive en ``core`` y no en ``services`` porque lo usan repositorios, y
``repositories`` no puede importar ``services`` sin cerrar un ciclo. Aquí no hay
IO: alfabeto, generación, normalización y hash.

**El alfabeto se puede dictar en voz alta**: sin ``0/O``, ``1/I/L`` ni ``U/V``.
30^8 ≈ 6,6e11 combinaciones vivas diez minutos.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

#: Sin caracteres que se confundan al dictarlos o al teclearlos.
ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL = timedelta(minutes=10)


def generate_code() -> str:
    """Un código nuevo. ``secrets``, no ``random``: esto es una credencial."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def display_code(code: str) -> str:
    """``K7MP4XQ2`` → ``K7MP-4XQ2``. Lo que se enseña, no lo que se guarda."""
    return f"{code[:4]}-{code[4:]}" if len(code) == CODE_LENGTH else code


def normalize_code(code: str) -> str | None:
    """Lo que una persona teclea → el código, o ``None`` si no lo es.

    Tolera el guion de la presentación y las minúsculas, porque las dos son
    formas de escribir el mismo código y rechazarlas sería castigar por cómo se
    copió.
    """
    cleaned = code.replace("-", "").replace(" ", "").upper()
    if len(cleaned) != CODE_LENGTH or any(c not in ALPHABET for c in cleaned):
        return None
    return cleaned


def hash_code(code: str) -> str:
    """SHA-256 del código normalizado. En reposo solo vive esto."""
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
