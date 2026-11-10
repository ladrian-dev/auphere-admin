"""El horario del negocio: una forma canónica y un lector que entiende las que
hay guardadas (bug ``horario-del-negocio-en-tres-formas``).

Cada forma de abajo existe en alguna parte del repo o de la base:

- la del asistente del panel de operador: ``"09:00-18:00"`` o ``"closed"``;
- la que esperaba la disponibilidad del agente: ``{"start", "end"}``;
- la de la semilla de Boreal: ``{"open", "close"}`` o ``None``;
- la de la consola (spec 019): ``{"from", "to"}`` o ``None``;
- y la canónica: una lista de tramos ``{"from", "to"}`` por día.
"""

from __future__ import annotations

from datetime import time

import pytest

from nexus_api.services.business_hours import (
    WEEKDAYS,
    BusinessHoursError,
    canonical_business_hours,
    parse_business_hours,
)


def _week(value: object) -> dict[str, object]:
    return {d: value for d in WEEKDAYS}


@pytest.mark.parametrize(
    "raw_day",
    [
        "09:00-18:00",
        {"start": "09:00", "end": "18:00"},
        {"open": "09:00", "close": "18:00"},
        {"from": "09:00", "to": "18:00"},
        [{"from": "09:00", "to": "18:00"}],
    ],
)
def test_every_stored_shape_reads_the_same(raw_day: object) -> None:
    hours = parse_business_hours(_week(raw_day))
    assert hours is not None
    assert hours["monday"] == [(time(9, 0), time(18, 0))]


@pytest.mark.parametrize("closed", ["closed", None, [], ""])
def test_closed_day_has_no_ranges(closed: object) -> None:
    raw = {**_week("10:00-19:00"), "sunday": closed}
    hours = parse_business_hours(raw)
    assert hours is not None
    assert hours["sunday"] == []
    assert hours["saturday"] == [(time(10, 0), time(19, 0))]


def test_missing_day_in_configured_hours_is_closed() -> None:
    hours = parse_business_hours({"monday": "10:00-19:00"})
    assert hours is not None
    assert hours["monday"] == [(time(10, 0), time(19, 0))]
    # Un horario configurado no abre un día que no nombra.
    assert hours["sunday"] == []
    assert hours["tuesday"] == []


def test_split_day_keeps_both_ranges_in_order() -> None:
    hours = parse_business_hours(
        {
            **_week([]),
            "friday": [{"from": "20:00", "to": "23:00"}, {"from": "13:00", "to": "16:00"}],
        }
    )
    assert hours is not None
    assert hours["friday"] == [(time(13, 0), time(16, 0)), (time(20, 0), time(23, 0))]


@pytest.mark.parametrize("raw", [None, {}, {"label": "Lun-Sáb 10-19"}, "10-19", 7])
def test_no_hours_configured_is_none(raw: object) -> None:
    # Sin ningún día nombrado no hay horario: el llamante decide qué hacer.
    assert parse_business_hours(raw) is None


@pytest.mark.parametrize(
    "garbage",
    ["9 a 18", "18:00-09:00", {"start": "25:00", "end": "26:00"}, {"from": "09:00"}, 42],
)
def test_unreadable_day_reads_as_closed(garbage: object) -> None:
    # Lo que no se entiende no se ofrece: fallar cerrado, no abrir de 10 a 19.
    hours = parse_business_hours({**_week("10:00-19:00"), "wednesday": garbage})
    assert hours is not None
    assert hours["wednesday"] == []


def test_canonical_form_names_every_day() -> None:
    out = canonical_business_hours({"monday": "09:00-18:00", "sunday": "closed"})
    assert set(out) == set(WEEKDAYS)
    assert out["monday"] == [{"from": "09:00", "to": "18:00"}]
    assert out["sunday"] == []
    assert out["tuesday"] == []


def test_canonical_form_is_a_fixed_point() -> None:
    once = canonical_business_hours(_week({"open": "08:30", "close": "13:00"}))
    assert canonical_business_hours(once) == once


def test_canonical_rejects_what_it_cannot_read() -> None:
    # Al escribir, la API no adivina: devuelve 422.
    with pytest.raises(BusinessHoursError):
        canonical_business_hours({"monday": "9 a 18"})
    with pytest.raises(BusinessHoursError):
        canonical_business_hours(
            {"monday": [{"from": "10:00", "to": "12:00"}, {"from": "11:00", "to": "13:00"}]}
        )
    with pytest.raises(BusinessHoursError):
        canonical_business_hours({"lunes": "09:00-18:00"})


def test_a_label_alone_is_no_hours_and_is_kept() -> None:
    # fix.md (desviaciones): `{"label"}` sin días es «sin horario», y la etiqueta
    # se guarda porque `agent_configs` la lee para el prompt. No son siete días
    # cerrados.
    stored = canonical_business_hours({"label": "Lun-Sáb 10-19"})
    assert stored == {"label": "Lun-Sáb 10-19"}
    assert parse_business_hours(stored) is None
    assert canonical_business_hours({}) == {}


def test_the_label_survives_next_to_the_days() -> None:
    out = canonical_business_hours({"monday": "09:00-18:00", "label": "L 9-18"})
    assert out["label"] == "L 9-18"
    assert out["monday"] == [{"from": "09:00", "to": "18:00"}]
    assert canonical_business_hours(out) == out
    with pytest.raises(BusinessHoursError):
        canonical_business_hours({"label": 7})


# ── spec 045: la etiqueta y «¿abierto ahora?» ────────────────────────────────

D = chr(0x2013)  # la raya corta de los tramos


def test_label_groups_days_that_open_the_same() -> None:
    from nexus_api.services.business_hours import business_hours_label

    hours = parse_business_hours(
        {
            **{d: "09:00-19:00" for d in WEEKDAYS[:5]},
            "saturday": "09:00-14:00",
            "sunday": "closed",
        }
    )
    assert hours is not None
    assert (
        business_hours_label(hours, "es") == f"Lunes a viernes 09:00{D}19:00, sábados 09:00{D}14:00"
    )
    assert (
        business_hours_label(hours, "en")
        == f"Monday to Friday 09:00{D}19:00, Saturdays 09:00{D}14:00"
    )


def test_label_says_both_ranges_and_every_day() -> None:
    from nexus_api.services.business_hours import business_hours_label

    hours = parse_business_hours(
        _week([{"from": "13:00", "to": "16:00"}, {"from": "20:00", "to": "23:00"}])
    )
    assert hours is not None
    assert business_hours_label(hours, "es") == f"Todos los días 13:00{D}16:00 y 20:00{D}23:00"


def test_label_of_a_closed_week_is_none() -> None:
    from nexus_api.services.business_hours import business_hours_label

    hours = parse_business_hours(_week("closed"))
    assert hours is not None
    assert business_hours_label(hours, "es") is None


def test_is_open_at_uses_the_business_timezone() -> None:
    from datetime import UTC, datetime

    from nexus_api.services.business_hours import is_open_at

    hours = parse_business_hours({**_week("closed"), "monday": "09:00-18:00"})
    assert hours is not None
    tz = "America/Santiago"
    # 2026-10-26 es lunes. 12:00 en Santiago (UTC-3) = 15:00 UTC.
    assert is_open_at(hours, tz, datetime(2026, 10, 26, 15, 0, tzinfo=UTC)) is True
    # 08:30 en Santiago = 11:30 UTC: aún cerrado.
    assert is_open_at(hours, tz, datetime(2026, 10, 26, 11, 30, tzinfo=UTC)) is False
    # 18:00 es el cierre: fuera.
    assert is_open_at(hours, tz, datetime(2026, 10, 26, 21, 0, tzinfo=UTC)) is False
    # Martes, cerrado.
    assert is_open_at(hours, tz, datetime(2026, 10, 27, 15, 0, tzinfo=UTC)) is False
