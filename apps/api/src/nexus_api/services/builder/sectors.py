"""Los sectores del constructor — spec 047 (requisitos 4.2, 17.8 y 21.1).

Los 6 grupos de plantillas con nombre de negocio (más «Otro») que acordó la spec
046, y los mismos 6 sectores de la batería común de pruebas (T090). Un nicho
escrito a mano se lleva a su sector por palabras; lo que no casa es «Otro».
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Clave → nombre de negocio, en el orden en que se enseñan.
SECTORS: Final[dict[str, str]] = {
    "barberia_peluqueria": "Barbería y peluquería",
    "clinica": "Clínica dental y estética",
    "restaurante": "Restaurante y cafetería",
    "tienda": "Tienda y comercio online",
    "servicios_profesionales": "Servicios profesionales",
    "mayorista": "Mayorista",
}
OTHER: Final = "otro"
OTHER_NAME: Final = "Otro"

#: Cada plantilla de ``services/templating/seeds`` en su grupo.
TEMPLATE_SECTOR: Final[dict[str, str]] = {
    "barbershop_v1": "barberia_peluqueria",
    "beauty_salon_v1": "barberia_peluqueria",
    "nail_studio_v1": "barberia_peluqueria",
    "dental_v1": "clinica",
    "clinica_v1": "clinica",
    "aesthetic_clinic_v1": "clinica",
    "medspa_v1": "clinica",
    "spa_v1": "clinica",
    "restaurante_v1": "restaurante",
    "woocommerce_sales_v1": "tienda",
    "inventario_v1": "tienda",
    "cobranza_v1": "servicios_profesionales",
    "generic_v1": OTHER,
}

_WORDS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "barberia_peluqueria",
        re.compile(r"barber|peluquer|salon de belleza|unas|manicur|estetica capilar"),
    ),
    (
        "clinica",
        re.compile(r"clinic|dental|dentist|odontolog|estetic|medic|fisio|spa|psicolog|veterin"),
    ),
    (
        "restaurante",
        re.compile(r"restaur|cafe|cafeteria|bar\b|pizzer|panader|pasteler|comida|cocina"),
    ),
    ("mayorista", re.compile(r"mayorist|por mayor|distribuid|al por mayor")),
    ("tienda", re.compile(r"tienda|comercio|ecommerce|e-commerce|online|boutique|flor|ropa|venta")),
    (
        "servicios_profesionales",
        re.compile(r"abogad|asesor|consult|contab|inmobili|academ|escuela|taller|cobranz|seguro"),
    ),
)


def _plain(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )


def sector_of_niche(niche: str | None) -> str:
    plain = _plain(niche or "")
    for key, pattern in _WORDS:
        if pattern.search(plain):
            return key
    return OTHER


def sector_name(key: str) -> str:
    return SECTORS.get(key, OTHER_NAME)


__all__ = ["OTHER", "OTHER_NAME", "SECTORS", "TEMPLATE_SECTOR", "sector_name", "sector_of_niche"]
