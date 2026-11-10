"""Los sectores del constructor — spec 047 (requisitos 4.2, 17.8, 21.1 y 57).

Los 6 grupos de plantillas con nombre de negocio (más «Otro») que acordó la spec
046, y los mismos 6 sectores de la batería común de pruebas (T090).

Desde la enmienda del 2026-10-29 (requisito 57, research D46) el sector de un
cliente **lo identifica un modelo y vive en la ficha** (``services/business/
sector.py``); nadie lo vuelve a clasificar del nicho. Aquí queda la lista cerrada
de claves y la regla de respaldo de palabras enteras, para cuando no hay modelo.
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

#: Las claves que puede tener el sector de una ficha (requisito 57.1): una guía de
#: Auphere u «otro». Es la lista cerrada contra la que se valida lo que dice el
#: modelo (57.7) y lo que manda la consola (``sector_unknown``).
SECTOR_KEYS: Final[tuple[str, ...]] = (*SECTORS, OTHER)

# La regla de respaldo (requisito 57.4, research D46): **palabras enteras**, no
# fragmentos. «Despacho de abogados» caía en clínica porque contiene «spa»; con
# palabras enteras no. Solo la usa ``services/business/sector.py`` cuando no hay
# modelo, y lo que da se guarda con confianza baja hasta que el modelo lo vuelva a
# identificar. Lo dudoso (psicóloga, veterinaria, gimnasio, óptica…) se queda en
# «otro»: mejor sin guía que con la de otro oficio.
_WORDS: Final[tuple[tuple[str, frozenset[str]], ...]] = (
    (
        "barberia_peluqueria",
        frozenset(
            {
                "barber", "barbers", "barbershop", "barberia", "barberias", "barbero",
                "barberos", "peluqueria", "peluquerias", "peluquero", "peluquera",
                "peluqueros", "estilista", "estilistas", "unas", "manicura", "manicure",
                "pedicura", "manicurista",
            }
        ),
    ),
    (
        "clinica",
        frozenset(
            {
                "clinica", "clinicas", "dental", "dentales", "dentista", "dentistas",
                "odontologia", "odontologo", "odontologa", "ortodoncia", "estetica",
                "esteticas", "medico", "medica", "medicos", "medicina", "fisioterapia",
                "fisioterapeuta", "fisio", "spa", "podologia", "podologo", "dermatologia",
            }
        ),
    ),
    (
        "restaurante",
        frozenset(
            {
                "restaurante", "restaurantes", "cafe", "cafeteria", "cafeterias", "bar",
                "bares", "pizzeria", "pizzerias", "panaderia", "pasteleria", "comida",
                "comidas", "cocina", "tapas", "marisqueria", "asador", "heladeria",
            }
        ),
    ),
    (
        "mayorista",
        frozenset({"mayorista", "mayoristas", "mayor", "distribuidor", "distribuidora"}),
    ),
    (
        "tienda",
        frozenset(
            {
                "tienda", "tiendas", "comercio", "ecommerce", "boutique", "floristeria",
                "flores", "ropa", "zapateria", "libreria", "ferreteria", "joyeria",
            }
        ),
    ),
    (
        "servicios_profesionales",
        frozenset(
            {
                "abogado", "abogados", "abogada", "abogadas", "despacho", "bufete",
                "asesor", "asesora", "asesoria", "asesores", "consultor", "consultora",
                "consultoria", "contable", "contabilidad", "gestoria", "inmobiliaria",
                "academia", "escuela", "taller", "cobranza", "seguros", "notaria",
                "arquitecto", "arquitectura", "laboralista", "laboralistas",
            }
        ),
    ),
)  # fmt: skip


def _plain(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )


def sector_of_text(*texts: str | None) -> str:
    """La regla de respaldo: el primer sector con una palabra entera en el texto
    (el nicho primero, después la información); si ninguno, «otro»."""
    for text in texts:
        words = set(re.findall(r"[a-z0-9]+", _plain(text or "")))
        for key, vocabulary in _WORDS:
            if words & vocabulary:
                return key
    return OTHER


def sector_name(key: str) -> str:
    return SECTORS.get(key, OTHER_NAME)


def has_guide(key: str | None) -> bool:
    """Si el sector tiene guía de Auphere (sus pruebas del sector y, con la T201,
    su guía para el constructor). «Otro» no: el constructor genera una para el
    cliente (requisito 58.4)."""
    return key in SECTORS


__all__ = [
    "OTHER",
    "OTHER_NAME",
    "SECTORS",
    "SECTOR_KEYS",
    "TEMPLATE_SECTOR",
    "has_guide",
    "sector_name",
    "sector_of_text",
]
