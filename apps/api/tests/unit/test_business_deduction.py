"""Spec 047, T042/T047 — lo que el alta deduce y lo que sugiere (requisitos 4.2 y 4.5).

«Más ajustes» llega relleno: zona horaria, país, moneda de los precios, moneda
de la bolsa y «Solo UE». Las fuentes van **por este orden**:

1. el dominio de la web y el prefijo de los teléfonos detectados;
2. el país del partner;
3. el navegador.

Y las sugerencias de nicho salen de las plantillas, en los 6 grupos más «Otro»,
y de los nichos más usados del partner, sin restringir lo que se escribe.
Funciones puras.
"""

from __future__ import annotations

import pytest

from nexus_api.services.business.links import detect_links
from nexus_api.services.business.profile import (
    NICHE_GROUPS,
    TEMPLATE_NICHES,
    deduce_settings,
    is_valid_timezone,
    niche_suggestions,
)

pytestmark = pytest.mark.unit


def _deduce(info: str, **kw: object) -> object:
    return deduce_settings(info=info, links=detect_links(info), **kw)  # type: ignore[arg-type]


def test_a_cl_web_proposes_santiago_clp_and_the_partners_bag_currency() -> None:
    """El escenario 4 de la historia 3."""
    d = deduce_settings(info="flor-y-encanto.cl", links=detect_links("flor-y-encanto.cl"))
    assert d.country == "CL"
    assert d.timezone == "America/Santiago"
    assert d.price_currency == "CLP"
    assert d.wallet_currency == "USD"
    assert d.eu_only is False
    assert d.source == "web"


def test_a_spanish_phone_prefix_gives_madrid_eur_and_eu_only() -> None:
    d = deduce_settings(info="Llámanos al +34 600 123 456", links=[])
    assert (d.country, d.timezone, d.price_currency, d.eu_only, d.source) == (
        "ES",
        "Europe/Madrid",
        "EUR",
        True,
        "phone",
    )


def test_the_domain_wins_over_the_phone() -> None:
    info = "cafeorigen.com.mx · +34 600 123 456"
    d = deduce_settings(info=info, links=detect_links(info))
    assert d.country == "MX" and d.source == "web"
    assert d.price_currency == "MXN"


def test_a_generic_domain_falls_through_to_the_phone() -> None:
    info = "cultorbarber.com · +56 9 1234 5678"
    d = deduce_settings(info=info, links=detect_links(info))
    assert d.country == "CL" and d.source == "phone"


def test_the_partners_country_comes_before_the_browser() -> None:
    d = deduce_settings(
        info="Barbería de barrio",
        links=[],
        partner_country="ES",
        browser_timezone="America/Bogota",
        browser_locale="es-CO",
    )
    assert d.country == "ES" and d.source == "partner"
    # La zona del navegador no es de ese país: manda la del país.
    assert d.timezone == "Europe/Madrid"


def test_the_browser_is_the_last_source() -> None:
    d = deduce_settings(info="Barbería de barrio", links=[], browser_timezone="America/Bogota")
    assert (d.country, d.timezone, d.price_currency, d.source) == (
        "CO",
        "America/Bogota",
        "COP",
        "browser",
    )
    by_locale = deduce_settings(info="", links=[], browser_locale="es-AR")
    assert by_locale.country == "AR" and by_locale.price_currency == "ARS"


def test_the_browser_timezone_is_kept_when_it_is_of_that_country() -> None:
    """México tiene varias zonas: si el navegador está en una de ellas, se usa."""
    info = "cafeorigen.com.mx"
    d = deduce_settings(info=info, links=detect_links(info), browser_timezone="America/Tijuana")
    assert d.country == "MX" and d.timezone == "America/Tijuana"


def test_nothing_known_gives_utc_and_no_country() -> None:
    d = deduce_settings(info="", links=[])
    assert d.country is None
    assert d.timezone == "UTC"
    assert d.price_currency is None
    assert d.eu_only is False
    assert d.source == "default"


def test_the_bag_currency_is_the_partners() -> None:
    d = deduce_settings(
        info="cultorbarber.es", links=detect_links("cultorbarber.es"), partner_currency="EUR"
    )
    assert d.wallet_currency == "EUR"
    # Una moneda que la bolsa no admite no se propone.
    assert deduce_settings(info="", links=[], partner_currency="CLP").wallet_currency == "USD"


@pytest.mark.parametrize(
    ("country", "eu"),
    [
        ("ES", True),
        ("PT", True),
        ("NO", True),
        ("IS", True),
        ("GB", False),
        ("CH", False),
        ("CL", False),
        ("US", False),
    ],
)
def test_eu_only_is_on_for_the_eu_and_the_eea(country: str, eu: bool) -> None:
    assert deduce_settings(info="", links=[], partner_country=country).eu_only is eu


@pytest.mark.parametrize(
    ("tz", "ok"),
    [
        ("Europe/Madrid", True),
        ("America/Santiago", True),
        ("UTC", True),
        ("Mars/Olympus", False),
        ("../../etc/passwd", False),
        ("", False),
        ("europe/madrid", False),
    ],
)
def test_only_iana_zones_are_valid(tz: str, ok: bool) -> None:
    assert is_valid_timezone(tz) is ok


# ── sugerencias de nicho ─────────────────────────────────────────────────────


def test_there_are_six_groups_and_other() -> None:
    assert len(NICHE_GROUPS) == 7
    assert NICHE_GROUPS[-1] == "other"
    assert {n.group for n in TEMPLATE_NICHES} <= set(NICHE_GROUPS)


def test_every_template_niche_points_at_a_real_template() -> None:
    from nexus_api.services.templating.seed_templates import list_seed_templates

    real = set(list_seed_templates())
    assert {n.template for n in TEMPLATE_NICHES} <= real


def test_suggestions_without_text_are_the_templates_and_the_most_used() -> None:
    items = niche_suggestions("", used=[("Barbería de barrio", 3), ("Floristería", 5)])
    templates = [i for i in items if i.source == "template"]
    used = [i for i in items if i.source == "used"]
    assert {t.key for t in templates} >= {"barbershop", "dental", "restaurant"}
    assert [u.value for u in used] == ["Floristería", "Barbería de barrio"]
    assert used[0].uses == 5


def test_suggestions_match_the_text_without_accents_or_case() -> None:
    items = niche_suggestions("barberia", used=[("Barbería de barrio", 3), ("Floristería", 5)])
    assert [(i.source, i.key or i.value) for i in items] == [
        ("template", "barbershop"),
        ("used", "Barbería de barrio"),
    ]
    # También en inglés, el otro idioma de la consola.
    assert [i.key for i in niche_suggestions("dental", used=[])] == ["dental"]
    assert [i.key for i in niche_suggestions("nail", used=[])] == ["nail_studio"]


def test_suggestions_never_restrict_what_is_written() -> None:
    """Un nicho que no se parece a nada no tiene sugerencias, y no pasa nada."""
    assert niche_suggestions("escape room con catering", used=[]) == []
