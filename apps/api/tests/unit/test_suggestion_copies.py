"""Spec 047, T217 (revisión de seguridad del 2026-10-30) — la prueba de una
sugerencia no copia un mensaje de verdad.

``copies_a_message`` compara por n-gramas de palabras (sin mayúsculas, tildes ni
puntuación): copia quien comparte con un mensaje del lote casi todo lo suyo o casi
todo lo del mensaje. Una frase corta y corriente no cuenta como copia.
"""

from __future__ import annotations

from nexus_api.services.improvement.suggestions import copies_a_message

SAID = (
    "Mi hija tiene alergia a la penicilina y la última vez le pusieron una inyección "
    "que la dejó fatal toda la semana.",
    "Hola, ¿dónde puedo aparcar?",
)


def test_a_copied_sentence_is_a_copy_whatever_its_case_and_accents() -> None:
    assert copies_a_message(SAID[0].upper().replace("Ú", "U"), SAID)
    assert copies_a_message("mi hija tiene alergia a la penicilina y la ultima vez", SAID)


def test_a_message_inside_a_longer_text_is_a_copy() -> None:
    persona = (
        "Una madre preocupada que escribe tarde. Cuenta: «mi hija tiene alergia a la "
        "penicilina y la última vez le pusieron una inyección que la dejó fatal toda la "
        "semana». Quiere cita para el martes."
    )
    assert copies_a_message(persona, SAID)


def test_a_paraphrase_or_a_common_phrase_is_not_a_copy() -> None:
    assert not copies_a_message(
        "Una clienta avisa de que su hija es alérgica a un antibiótico.", SAID
    )
    assert not copies_a_message("Hola, ¿dónde puedo aparcar el coche?", SAID)
    assert not copies_a_message("", SAID)
    assert not copies_a_message("Pregunta una vez y da las gracias.", ())
