"""Los datos de un cliente final en un texto — spec 047, T176 (requisito 52.5;
research D35; garantía 8).

Un **detector**, no una anonimización (research D34: no hay anonimización fiable
de texto libre). Busca, en lo que escribe la persona del cliente y en la
paráfrasis:

- correos;
- documentos: DNI y NIE de España, RUT de Chile, CPF de Brasil y CURP de México;
- teléfonos: de 8 a 15 cifras, con prefijo o sin él y con sus separadores;
- el nombre del contacto de la conversación: cada palabra de su nombre de tres
  letras o más, sin distinguir mayúsculas ni tildes.

Dice **dónde** (tipo y posiciones), nunca **qué**: quien llama no guarda el dato
otra vez ni lo devuelve. Con :func:`scrub`, la paráfrasis que escribe el modelo
sale con cada hallazgo cambiado por su marca («[teléfono]»).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final, Literal

PiiKind = Literal["email", "document", "phone", "name"]

#: Lo que deja :func:`scrub` en el sitio de cada hallazgo.
MARKS: Final[dict[str, str]] = {
    "email": "[correo]",
    "document": "[documento]",
    "phone": "[teléfono]",
    "name": "[nombre]",
}
#: El orden en que se resuelven los solapes: un DNI no es además un teléfono.
_PRIORITY: Final[tuple[str, ...]] = ("email", "document", "phone", "name")

_EMAIL: Final = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_DOCUMENTS: Final = (
    re.compile(r"(?<!\w)\d{8}[-\s]?[A-HJ-NP-TV-Z](?!\w)", re.I),  # DNI
    re.compile(r"(?<!\w)[XYZ][-\s]?\d{7}[-\s]?[A-HJ-NP-TV-Z](?!\w)", re.I),  # NIE
    re.compile(r"(?<!\w)\d{1,2}\.?\d{3}\.?\d{3}-[\dkK](?!\w)"),  # RUT
    re.compile(r"(?<!\w)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\w)"),  # CPF
    re.compile(r"(?<!\w)[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d(?!\w)"),  # CURP
)
_PHONE: Final = re.compile(r"(?<![\w.,])\+?\(?\d[\d\s().\-]{6,}\d(?![\w])")
_PHONE_DIGITS: Final = (8, 15)
#: Lo que tiene cifras de teléfono y no lo es: horas («10.00-14.00») y fechas.
_NOT_PHONE: Final = (
    re.compile(r"\d{1,2}[.:]\d{2}\s*-\s*\d{1,2}[.:]\d{2}"),
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),
    re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"),
)
_NAME_MIN: Final = 3


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int

    def to_json(self, field: str) -> dict[str, Any]:
        return {"field": field, "kind": self.kind, "start": self.start, "end": self.end}


def _fold(text: str) -> str:
    """Minúsculas y sin tildes, **con la misma longitud**: las posiciones valen
    para el texto original."""
    out: list[str] = []
    for char in text:
        base = "".join(
            c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
        ).lower()
        out.append(base if len(base) == 1 else char.lower())
    return "".join(out)


def _name_tokens(names: Iterable[str | None]) -> list[str]:
    tokens: set[str] = set()
    for name in names:
        for word in re.findall(r"\w+", _fold(name or "")):
            if len(word) >= _NAME_MIN and not word.isdigit():
                tokens.add(word)
    return sorted(tokens, key=len, reverse=True)


def _raw(text: str, names: Iterable[str | None]) -> list[Finding]:
    found: list[Finding] = [Finding("email", m.start(), m.end()) for m in _EMAIL.finditer(text)]
    for pattern in _DOCUMENTS:
        found += [Finding("document", m.start(), m.end()) for m in pattern.finditer(text)]
    for match in _PHONE.finditer(text):
        value = match.group()
        digits = sum(c.isdigit() for c in value)
        if any(p.fullmatch(value.strip()) for p in _NOT_PHONE):
            continue
        if _PHONE_DIGITS[0] <= digits <= _PHONE_DIGITS[1]:
            found.append(Finding("phone", match.start(), match.end()))
    folded = _fold(text)
    for token in _name_tokens(names):
        pattern = re.compile(rf"(?<!\w){re.escape(token)}(?!\w)")
        found += [Finding("name", m.start(), m.end()) for m in pattern.finditer(folded)]
    return found


def _merge_names(found: list[Finding], text: str) -> list[Finding]:
    """«Lucía Pérez» es un nombre, no dos."""
    out: list[Finding] = []
    for item in found:
        last = out[-1] if out else None
        if (
            last is not None
            and last.kind == item.kind == "name"
            and not text[last.end : item.start].strip()
        ):
            out[-1] = Finding("name", last.start, item.end)
        else:
            out.append(item)
    return out


def detect(text: str | None, *, names: Iterable[str | None] = ()) -> list[Finding]:
    """Los hallazgos de ``text``, sin solapes y en orden. ``names``: el nombre
    del contacto de la conversación."""
    if not text:
        return []
    kept: list[Finding] = []
    for item in sorted(_raw(text, list(names)), key=lambda f: _PRIORITY.index(f.kind)):
        if all(item.end <= k.start or item.start >= k.end for k in kept):
            kept.append(item)
    return _merge_names(sorted(kept, key=lambda f: f.start), text)


def scrub(text: str, found: list[Finding]) -> str:
    """``text`` con cada hallazgo cambiado por su marca."""
    out = text
    for item in sorted(found, key=lambda f: f.start, reverse=True):
        out = out[: item.start] + MARKS[item.kind] + out[item.end :]
    return out


def locate(
    fields: dict[str, str | None], *, names: Iterable[str | None] = ()
) -> list[dict[str, Any]]:
    """Los hallazgos de varios campos, como los guarda ``inbox_corrections.pii``."""
    listed = list(names)
    return [
        item.to_json(field) for field, text in fields.items() for item in detect(text, names=listed)
    ]


__all__ = ["MARKS", "Finding", "PiiKind", "detect", "locate", "scrub"]
