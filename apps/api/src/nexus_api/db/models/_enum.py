"""Helpers for declaring Postgres ENUMs that store the enum's `value`.

By default SQLAlchemy stores the enum's `.name`. The migrations create the
Postgres types with the lowercase `.value`s, so models must opt in via
`values_callable`.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=enum.Enum)


def pg_enum(enum_cls: type[E], *, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda x: [e.value for e in x],
        validate_strings=True,
    )
