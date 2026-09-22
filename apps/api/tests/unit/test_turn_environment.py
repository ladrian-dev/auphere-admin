"""Qué día es, y dónde — spec 015, Requisito 5.

Un teammate no recibía la fecha por ningún lado, así que la deducía de lo que
aprendió al entrenarse. **El agente de canal de esta misma plataforma sí la
recibe**, y no por casualidad: el 2026-08-19 el agente de cobranza ofreció
``(ejemplo: 2025-08-30)`` como formato de vencimiento, quien administraba copió
el ejemplo, y se creó una cuenta real con un año de retraso.

Dos cosas que este bloque **no** comparte con el de identidad, y son la razón de
que sean dos y no uno:

* La identidad va en la **posición 2** y se cachea — es estable dentro del hilo.
* El entorno va **justo antes del turno** y no se cachea — cambia cada minuto.
  Meterlo arriba invalidaría el corte 2 en cada turno y no habría ahorro que
  defender.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from nexus_worker.runtime.companion.prompt import build_messages
from nexus_worker.runtime.turn_clock import OWNER_PERSON, now_note

pytestmark = pytest.mark.unit

_AHORA = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)  # jueves


# ── qué lleva ───────────────────────────────────────────────────────────


def test_it_carries_the_date_the_weekday_the_iso_and_the_zone() -> None:
    nota = now_note("America/Caracas", now=_AHORA, owner=OWNER_PERSON)

    assert "jueves" in nota
    assert "24/09/2026" in nota
    assert "2026-09-24" in nota, "el ISO, para que no haya que interpretar el formato"
    assert "America/Caracas" in nota


def test_it_forbids_deducing_the_year_from_the_model_s_own_knowledge() -> None:
    """La frase es la misma que ya usa el agente de canal. No se reescribe."""
    nota = now_note("America/Caracas", now=_AHORA, owner=OWNER_PERSON)

    assert "NUNCA deduzcas el año ni la fecha de tu propio conocimiento" in nota
    assert "referencias relativas" in nota


def test_the_zone_belongs_to_the_person_not_to_a_business() -> None:
    """Decirle «la zona horaria del negocio» a quien habla con su teammate
    sería mentir por descuido: el teammate trabaja para una persona."""
    del_teammate = now_note("Europe/Madrid", now=_AHORA, owner=OWNER_PERSON)
    del_canal = now_note("Europe/Madrid", now=_AHORA)

    assert "de la persona con la que hablas" in del_teammate
    assert "del negocio" in del_canal, "el texto del canal no cambia"


# ── el caso feo, que no es el camino feliz ──────────────────────────────


@pytest.mark.parametrize("zona", ["", "   ", "Marte/Olympus", "no-es-una-zona", "UTC+5"])
def test_a_broken_zone_falls_back_to_utc_and_says_so(zona: str) -> None:
    """R5.5. **Si el test solo prueba una zona válida, no prueba el requisito.**

    Lo que no puede pasar es ninguna de estas dos: que el turno reviente, o que
    se finja saber la hora local. Decir UTC en voz alta es peor que la verdad y
    mejor que una mentira.
    """
    nota = now_note(zona, now=_AHORA, owner=OWNER_PERSON)

    assert "UTC" in nota, "tiene que DECIR que está en UTC, no callarlo"
    assert "15:30" in nota
    assert zona.strip() not in nota or zona.strip() == "", (
        "no puede seguir nombrando una zona que no supo resolver"
    )


# ── dónde va ────────────────────────────────────────────────────────────


def test_the_environment_sits_right_before_the_person_s_turn() -> None:
    entorno = now_note("Europe/Madrid", now=_AHORA, owner=OWNER_PERSON)
    msgs = build_messages(
        history=[{"role": "user", "content": "antes"}],
        user_message="hola",
        page_context=None,
        identity="Eres Sofía…",
        environment=entorno,
    )

    assert msgs[-1] == {"role": "user", "content": "hola"}
    assert msgs[-2]["role"] == "system"
    assert msgs[-2]["content"] == entorno


def test_identity_and_environment_do_not_share_a_message() -> None:
    """Quieren sitios opuestos: una lo más al principio, el otro lo más fresco.

    Juntarlas obliga a elegir mal para una de las dos — y si el entorno subiera
    a la posición 2, invalidaría el corte 2 del caché en **cada** turno.
    """
    msgs = build_messages(
        history=None,
        user_message="hola",
        page_context=None,
        identity="Eres Sofía…",
        environment="Fecha y hora…",
    )
    sistemas = [m for m in msgs if m["role"] == "system"]

    assert len(sistemas) == 3, "prefijo, identidad y entorno: tres, y separados"
    assert msgs[1]["content"] == "Eres Sofía…"
    assert msgs[-2]["content"] == "Fecha y hora…"


def test_without_an_environment_the_turn_is_what_it_was() -> None:
    con_hueco = build_messages(history=None, user_message="hola", page_context=None)
    assert [m["role"] for m in con_hueco] == ["system", "user"]


# ── la máquina y el cliente ─────────────────────────────────────────────


def test_it_says_whether_the_machine_is_there() -> None:
    from nexus_worker.runtime.turn_clock import turn_environment

    con = turn_environment(timezone_name="Europe/Madrid", machine_present=True, now=_AHORA)
    sin = turn_environment(timezone_name="Europe/Madrid", machine_present=False, now=_AHORA)

    assert "está conectada" in con
    assert "no está conectada" in sin
    assert "Sigue con lo que no la necesite" in sin, (
        "saber que no puede ejecutar no basta: tiene que saber qué hacer en su lugar"
    )


def test_the_client_zone_is_named_as_well_never_instead() -> None:
    """R5.4. Son dos datos distintos y el requisito pide los dos."""
    from nexus_worker.runtime.turn_clock import turn_environment

    texto = turn_environment(
        timezone_name="Europe/Madrid",
        client_timezone="America/Caracas",
        machine_present=False,
        now=_AHORA,
    )

    assert "Europe/Madrid" in texto, "la de la persona no puede desaparecer"
    assert "America/Caracas" in texto
    assert "sin cambiar la tuya" in texto


def test_the_same_zone_is_not_repeated_twice() -> None:
    from nexus_worker.runtime.turn_clock import turn_environment

    texto = turn_environment(
        timezone_name="Europe/Madrid",
        client_timezone="Europe/Madrid",
        machine_present=False,
        now=_AHORA,
    )

    assert texto.count("Europe/Madrid") == 1
