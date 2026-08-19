"""El enmascarado de PII, la capa que faltaba con nombre (CO-07 · §24).

Regla que ordena todas las expectativas de abajo: **enmascarar es dejar
suficiente para correlacionar y no lo bastante para contactar.** Una máscara
que borra del todo hace inútil el dato y empuja al modelo a pedir el
original, que es exactamente lo que no se quiere.
"""

from __future__ import annotations

import pytest

from nexus_api.core.guardrails.pii import (
    contains_pii,
    mask_email,
    mask_person_name,
    mask_phone,
    scrub_pii,
)

pytestmark = pytest.mark.evals


def test_the_local_part_goes_and_the_domain_stays() -> None:
    """El dominio es lo que le dice al partner "esto es de tu equipo" o
    "esto es de fuera", y no identifica a nadie."""
    assert mask_email("maria.gonzalez@facelad.com") == "m…z@facelad.com"
    assert mask_email("a@facelad.com") == "a…@facelad.com"
    assert mask_email("") == ""


def test_the_contract_shape_of_an_invitation_preview() -> None:
    """§3.4 del contrato: ``{"email_masked": "m…a@facelad.com", ...}``."""
    assert mask_email("maria@facelad.com") == "m…a@facelad.com"


def test_a_phone_keeps_enough_to_match_a_spreadsheet_row() -> None:
    assert mask_phone("+56912345678") == "+5691***5678"
    assert mask_phone("12345678") == "12***"
    assert mask_phone(None) == ""


def test_a_person_becomes_initials() -> None:
    """Bastan para hablar de la conversación sin poner el nombre completo de
    un cliente final en el chat de su proveedor (CP-21)."""
    assert mask_person_name("María González") == "M. G."
    assert mask_person_name("  ana  ") == "A."
    assert mask_person_name("") == ""


def test_free_text_gets_scrubbed() -> None:
    """El caso real: un motivo de rechazo de Meta que cita la plantilla."""
    raw = "Rejected: the sample cites ana.perez@clinicaboreal.com and +34600112233."
    out = scrub_pii(raw)
    assert "ana.perez@clinicaboreal.com" not in out
    assert "+34600112233" not in out
    assert "clinicaboreal.com" in out, "el dominio se queda: es contexto, no identidad"
    assert contains_pii(out) is False


def test_masking_is_idempotent() -> None:
    """Se aplica en más de un sitio del camino. Si la segunda pasada volviera
    a enmascarar lo enmascarado, el dato se destruiría por acumulación."""
    once = scrub_pii("escribe a ana@x.com o llama al +34600112233")
    assert scrub_pii(once) == once


def test_a_date_is_not_a_phone_number() -> None:
    """El falso positivo que de verdad aparece: el Companion lee fechas en
    casi todas las lecturas, y un enmascarador que se las come deja el
    contexto inservible."""
    text = "La última publicación fue el 2026-07-30 y la anterior el 2026-06-01."
    assert scrub_pii(text) == text
    assert contains_pii(text) is False


def test_an_amount_is_not_a_phone_number() -> None:
    assert scrub_pii("Van 1.200,50 USD este mes") == "Van 1.200,50 USD este mes"


def test_contains_pii_is_the_affirmative_form_of_the_check() -> None:
    """Un caso de eval no comprueba que se llamó a ``scrub_pii``: comprueba
    que en lo que sale no queda PII. Es la diferencia entre probar la
    implementación y probar la propiedad."""
    assert contains_pii("escribe a ana@x.com") is True
    assert contains_pii("llama al +34 600 11 22 33") is True
    assert contains_pii("no hay nada aquí") is False
    assert contains_pii(None) is False


def test_the_new_layer_agrees_with_the_masker_already_in_production() -> None:
    """``services/direct_messages.mask_phone`` lleva tiempo en los logs. La
    capa nueva adopta su formato en vez de estrenar uno: dos formatos de
    máscara para el mismo dato hacen imposible cruzar un log con otro."""
    from nexus_api.services.direct_messages import mask_phone as legacy

    for phone in ("+56912345678", "+34600112233", "1234", "12345678"):
        assert mask_phone(phone) == legacy(phone)
