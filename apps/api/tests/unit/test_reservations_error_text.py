"""/cso (apéndice): lo que los crons de Reservas escriben en el log y en
``reservation_outbox.last_error`` no lleva datos de nadie.

El texto de un error de SQLAlchemy incluye la sentencia y sus parámetros: el
teléfono y el nombre del cliente final acababan en los logs."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from nexus_api.services.reservations.automation import error_text


def test_a_database_error_keeps_only_its_types() -> None:
    exc = IntegrityError(
        "INSERT INTO customers (identifier, name) VALUES (%s, %s)",
        ("+56911112222", "Ana Pérez"),
        Exception("duplicate key value violates unique constraint"),
    )
    text = error_text(exc)
    assert "+56911112222" not in text and "Ana" not in text
    assert text == "IntegrityError: Exception"


def test_any_other_error_keeps_its_message_short() -> None:
    assert error_text(RuntimeError("x" * 500), limit=20) == "RuntimeError: xxxxxx"
