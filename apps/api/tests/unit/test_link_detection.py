"""Spec 047, T043 — la detección de enlaces del alta (requisitos 4.2, 5.1 y 5.2).

Lo que se escribe en «Información adicional» se lee al vuelo y cada hallazgo
sale como un chip con su destino en la ficha («Irá a la ficha:»). Es una
función pura: sin red, sin base, sin reloj. Se fija:

- detecta webs (con y sin esquema), ``@usuarios`` y enlaces de Instagram,
  Facebook, TikTok, LinkedIn, YouTube, X y Threads;
- **un correo no es una web**, y la arroba de un correo no es un usuario;
- un ``@`` suelto se propone como Instagram, con la opción de cambiar la red;
- un nombre de archivo o un número con punto no son una web;
- y las sugerencias de nicho no sustituyen lo escrito.
"""

from __future__ import annotations

import pytest

from nexus_api.services.business.links import DetectedLink, detect_links, social_url
from nexus_api.services.business.profile import NICHE_MAX, merge_niche_suggestion

pytestmark = pytest.mark.unit


def _by_network(found: list[DetectedLink]) -> dict[str, DetectedLink]:
    return {link.network: link for link in found}


# ── webs ────────────────────────────────────────────────────────────────────


def test_the_prototype_text_gives_a_web_and_an_instagram() -> None:
    found = detect_links("cultorbarber.com · @cultorbarber")
    assert [(f.network, f.value) for f in found] == [
        ("web", "cultorbarber.com"),
        ("instagram", "@cultorbarber"),
    ]
    web, insta = found
    assert web.kind == "web" and web.target == "website"
    assert web.url == "https://cultorbarber.com"
    assert insta.kind == "social" and insta.target == "links"
    assert insta.handle == "@cultorbarber"
    assert insta.url == "https://www.instagram.com/cultorbarber"


@pytest.mark.parametrize(
    ("text", "value", "url"),
    [
        ("https://www.cultorbarber.com/", "cultorbarber.com", "https://www.cultorbarber.com"),
        (
            "http://cultorbarber.com/servicios",
            "cultorbarber.com/servicios",
            "http://cultorbarber.com/servicios",
        ),
        (
            "Visítanos en WWW.Flor-y-Encanto.CL.",
            "flor-y-encanto.cl",
            "https://www.flor-y-encanto.cl",
        ),
        ("(cafeorigen.com.mx)", "cafeorigen.com.mx", "https://cafeorigen.com.mx"),
    ],
)
def test_a_web_is_found_with_or_without_scheme(text: str, value: str, url: str) -> None:
    (web,) = detect_links(text)
    assert web.network == "web"
    assert web.value == value
    assert web.url == url


@pytest.mark.parametrize(
    "text",
    [
        "escríbenos a hola@cultorbarber.com",
        "reservas: <reservas@flor-y-encanto.cl>",
        "marta.lopez+citas@gmail.com",
    ],
)
def test_an_email_is_not_a_web_nor_a_handle(text: str) -> None:
    assert detect_links(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "adjunto carta.pdf y foto.jpg",
        "precio 12.50 o 3.5 kg",
        "versión v2.0",
        "plantilla_final.docx",
    ],
)
def test_files_and_numbers_are_not_webs(text: str) -> None:
    assert detect_links(text) == []


def test_an_email_next_to_a_web_keeps_only_the_web() -> None:
    found = detect_links("cultorbarber.com — citas en hola@cultorbarber.com")
    assert [(f.network, f.value) for f in found] == [("web", "cultorbarber.com")]


# ── redes ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "network", "handle", "url"),
    [
        (
            "https://www.instagram.com/cultorbarber/",
            "instagram",
            "@cultorbarber",
            "https://www.instagram.com/cultorbarber",
        ),
        (
            "facebook.com/CultorBarber",
            "facebook",
            "@CultorBarber",
            "https://www.facebook.com/CultorBarber",
        ),
        (
            "https://www.tiktok.com/@cultor.barber",
            "tiktok",
            "@cultor.barber",
            "https://www.tiktok.com/@cultor.barber",
        ),
        (
            "linkedin.com/company/cultor-barber",
            "linkedin",
            None,
            "https://www.linkedin.com/company/cultor-barber",
        ),
        (
            "https://youtube.com/@cultorbarber",
            "youtube",
            "@cultorbarber",
            "https://www.youtube.com/@cultorbarber",
        ),
        ("https://x.com/cultorbarber", "x", "@cultorbarber", "https://x.com/cultorbarber"),
        ("twitter.com/cultorbarber", "x", "@cultorbarber", "https://x.com/cultorbarber"),
        (
            "https://www.threads.net/@cultorbarber",
            "threads",
            "@cultorbarber",
            "https://www.threads.net/@cultorbarber",
        ),
    ],
)
def test_each_network_link_is_recognised(
    text: str, network: str, handle: str | None, url: str
) -> None:
    (link,) = detect_links(text)
    assert link.network == network
    assert link.kind == "social"
    assert link.target == "links"
    assert link.handle == handle
    assert link.url == url
    assert link.guessed is False
    assert link.alternatives == ()


def test_a_network_link_is_never_a_web() -> None:
    found = detect_links("cultorbarber.com y instagram.com/cultorbarber")
    assert [f.network for f in found] == ["web", "instagram"]


def test_a_post_link_is_kept_without_a_handle() -> None:
    (link,) = detect_links("mira https://www.instagram.com/p/C1x2y3/")
    assert link.network == "instagram"
    assert link.handle is None
    assert link.url == "https://www.instagram.com/p/C1x2y3"


def test_a_lone_handle_is_proposed_as_instagram_and_can_change() -> None:
    (link,) = detect_links("síguenos en @flor.y.encanto")
    assert link.network == "instagram"
    assert link.handle == "@flor.y.encanto"
    assert link.guessed is True
    # Se propone Instagram, y se puede cambiar a otra red que use @usuario.
    assert "instagram" not in link.alternatives
    assert {"tiktok", "x", "threads", "youtube"} <= set(link.alternatives)
    assert "web" not in link.alternatives


def test_a_lone_handle_already_linked_is_not_repeated() -> None:
    found = detect_links("@cultorbarber · https://www.tiktok.com/@cultorbarber")
    assert [(f.network, f.handle, f.guessed) for f in found] == [("tiktok", "@cultorbarber", False)]


def test_duplicates_collapse_and_order_is_kept() -> None:
    found = detect_links(
        "cultorbarber.com, https://cultorbarber.com/ e instagram.com/cultorbarber "
        "@cultorbarber @otra_cuenta"
    )
    assert [(f.network, f.value) for f in found] == [
        ("web", "cultorbarber.com"),
        ("instagram", "@cultorbarber"),
        ("instagram", "@otra_cuenta"),
    ]
    assert _by_network(found)["web"].url == "https://cultorbarber.com"


def test_an_empty_text_finds_nothing() -> None:
    assert detect_links("") == []
    assert detect_links("Barbería de barrio con 2 sedes") == []


def test_the_social_url_of_a_changed_network() -> None:
    """Cambiar la red de un ``@`` suelto rehace su enlace."""
    assert social_url("tiktok", "@cultorbarber") == "https://www.tiktok.com/@cultorbarber"
    assert social_url("x", "cultorbarber") == "https://x.com/cultorbarber"
    assert social_url("threads", "@cultorbarber") == "https://www.threads.net/@cultorbarber"
    assert social_url("youtube", "@cultorbarber") == "https://www.youtube.com/@cultorbarber"
    assert social_url("linkedin", "@cultor") is None


# ── las sugerencias de nicho no sustituyen lo escrito ─────────────────────────


def test_a_niche_suggestion_fills_an_empty_field() -> None:
    assert merge_niche_suggestion("", "Barbería") == "Barbería"
    assert merge_niche_suggestion("   ", "Barbería") == "Barbería"


def test_a_niche_suggestion_is_added_to_what_was_written() -> None:
    merged = merge_niche_suggestion("De barrio con 2 sedes", "Barbería")
    assert merged.startswith("De barrio con 2 sedes")
    assert "Barbería" in merged


def test_a_niche_suggestion_already_there_changes_nothing() -> None:
    assert merge_niche_suggestion("Barbería de barrio", "barbería") == "Barbería de barrio"


def test_a_niche_suggestion_that_does_not_fit_keeps_the_text() -> None:
    long = "x" * (NICHE_MAX - 3)
    assert merge_niche_suggestion(long, "Barbería") == long
