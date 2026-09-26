"""Spec 017 (R5.1, R5.6): cada capacidad tiene nombre de negocio.

Un partner no distingue una herramienta de una habilidad, y `booking.create`
no le dice nada. El mapa de `capability_names` es lo que convierte el
catálogo interno en algo que se puede leer sin saber cómo está hecho por
dentro.

Este fichero fija la **forma** del mapa y su cobertura de las habilidades,
que son un bundle estático e importable. La cobertura de las herramientas
vive en `tests/integration/test_capability_names_cover_catalog.py`, porque el
catálogo no es un fichero: lo siembran las migraciones y, además,
`scripts/seed_connectors.py`. La única fuente fiable es la base; un test
unitario tendría que copiar esa lista, y una copia se desfasa en silencio,
que es exactamente lo que este test existe para impedir.
"""

from __future__ import annotations

from nexus_api.api.console.capability_names import (
    CAPABILITY_NAMES,
    FUNCTIONS,
    business_name,
    function_of,
    sectors_of,
)

# Los seis grupos de la pantalla (R5.1). Si alguien añade un séptimo, este
# test y la pantalla tienen que enterarse a la vez.
EXPECTED_FUNCTIONS = {"appointments", "orders", "messages", "escalation", "knowledge", "other"}


def test_the_six_functions_are_the_ones_the_screen_groups_by() -> None:
    assert set(FUNCTIONS) == EXPECTED_FUNCTIONS


def test_every_entry_is_readable_in_both_languages() -> None:
    """Una entrada sin traducción es una entrada que enseña el nombre técnico
    a alguien que no sabe qué es. Falla aquí antes que en pantalla."""
    for key, entry in CAPABILITY_NAMES.items():
        for lang in ("es", "en"):
            name = entry["name"][lang]
            assert name.strip(), f"{key} no tiene nombre en {lang}"
            assert name != key, f"{key} repite su nombre técnico como nombre de negocio en {lang}"
            assert not name.endswith("."), (
                f"{key}: el nombre no es una frase, no lleva punto ({lang})"
            )
            desc = entry["description"][lang]
            assert desc.strip(), f"{key} no tiene descripción en {lang}"
            assert desc[0].isupper(), f"{key}: la descripción empieza en minúscula ({lang})"


def test_every_entry_belongs_to_one_of_the_six_functions() -> None:
    for key, entry in CAPABILITY_NAMES.items():
        assert entry["function"] in EXPECTED_FUNCTIONS, f"{key} cae en «{entry['function']}»"


def test_every_skill_in_the_bundle_has_a_name() -> None:
    from nexus_api.services.skills_catalog import list_skills

    for skill in list_skills():
        name = skill["name"] if isinstance(skill, dict) else skill.name
        assert ("skill", name) in CAPABILITY_NAMES, (
            f"la habilidad {name} no tiene nombre de negocio"
        )


def test_business_name_falls_back_to_the_technical_name_instead_of_breaking() -> None:
    """Una capacidad nueva que aún no esté en el mapa debe **verse**, no
    desaparecer ni tumbar la pantalla: el catálogo puede adelantarse a las
    traducciones, y esconderla sería peor que enseñarla fea."""
    assert business_name("no.existe.todavia", "tool", "es") == "no.existe.todavia"
    assert function_of("no.existe.todavia", "tool") == "other"
    assert sectors_of("no.existe.todavia", "tool", ["booking"]) == []


def test_business_name_reads_the_language_asked_for() -> None:
    assert business_name("booking.create_appointment", "tool", "es") == "Reservar una cita"
    assert business_name("booking.create_appointment", "tool", "en") == "Book an appointment"


def test_sectors_come_from_the_tags_that_name_a_vertical() -> None:
    """Una etiqueta como `booking` describe lo que hace; `barbershop` dice
    para quién es. Solo las segundas filtran por sector (R5.2)."""
    assert sectors_of("queue.join_queue", "tool", ["queue", "barbershop"]) == ["barbershop"]
    # Sin vertical entre las etiquetas, la capacidad es común a todos.
    assert sectors_of("notification.send_text", "tool", ["notification"]) == []
    # Una etiqueta desconocida no inventa un sector.
    assert sectors_of("x.y", "tool", ["inventada"]) == []


def test_a_skill_of_one_vertical_declares_it() -> None:
    """Las habilidades no traen etiquetas de catálogo, así que su sector lo
    dice el mapa."""
    assert sectors_of("pre-op-screening", "skill", []) != []
