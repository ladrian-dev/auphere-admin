"""Cuerpos del catálogo cerrado de modelos en ``/console/*``.

El partner sale del principal. El cuerpo de escritura solo admite
``model_id``; ``partner_id`` u otra clave extra es 422.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConsoleModelOut(BaseModel):
    model_id: str
    display_name: str


class ClientModelOut(BaseModel):
    client_ref: str
    role: str
    model_id: str | None = None
    display_name: str | None = None
    is_bound: bool = False


class ModelIn(BaseModel):
    """Solo el id. El cliente es ``{ref}``; el partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=64)
