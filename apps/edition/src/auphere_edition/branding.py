"""Las marcas ajenas no viajan — Requisito 9.1.

Apache-2.0 §2 concede el **código**; §6 excluye expresamente los nombres
comerciales. Así que el sustrato se usa entero y su nombre no se usa nada.

**Qué se toca y qué no.** La evaluación lo midió: de las 105.221 apariciones del
`grep`, 24.482 son identificadores internos (`kiro_crew` como módulo). Ésos **no
se tocan** — una ruta de importación no es uso de marca, y renombrarla costaría el
seguimiento aguas arriba, que es la única razón de haber usado el seam. Lo que sí
se toca es lo que el partner ve: 17 apariciones en el catálogo de cadenas inglés,
386 en empaquetado e instaladores, y un puñado de constantes de ruta.

**Y por eso esto existe como código y no como una tarea cerrada.** El sustrato no
tiene una constante central de marca, así que cada actualización puede reintroducir
una marca en superficie visible sin que nadie se entere. Renombrar es un día;
vigilar es siempre.
"""

from __future__ import annotations

import re

PRODUCT_NAME = "Auphere"

#: Formas de la marca ajena tal y como aparecen en superficie visible.
#: `kiro_crew` **no** está: es identificador interno, no marca.
FORBIDDEN_MARKS: tuple[str, ...] = ("Kiro Crew", "KiroCrew", "kirocrew", "Kiro", ".kiro")

#: El separador NO incluye ``_`` a propósito: los identificadores internos usan
#: guion bajo (`kiro_crew`) y ésos no se tocan; las marcas visibles llevan espacio
#: o nada. Confundirlos haría fallar el guardián sobre el código que debe seguir.
_VISIBLE_MARK = re.compile(
    r"(?<![A-Za-z_])\.?kiro[ -]?crew(?![A-Za-z_])|(?<![A-Za-z_])\.?kiro(?![A-Za-z_])",
    re.I,
)


class BrandLeak(RuntimeError):
    """Una marca ajena iba a aparecer donde el partner la ve."""


def assert_no_marks(text: str) -> None:
    """Falla si el texto lleva una marca ajena. Para copy, no para código."""
    match = _VISIBLE_MARK.search(text)
    if match:
        raise BrandLeak(
            f"marca ajena en superficie visible: {match.group(0)!r}. "
            "Apache-2.0 §6 no concede los nombres comerciales."
        )


def scrub_user_facing(text: str) -> str:
    """Sustituye la marca por la nuestra en un texto destinado al partner."""
    return _VISIBLE_MARK.sub(PRODUCT_NAME, text)


__all__ = ["FORBIDDEN_MARKS", "PRODUCT_NAME", "BrandLeak", "assert_no_marks", "scrub_user_facing"]
