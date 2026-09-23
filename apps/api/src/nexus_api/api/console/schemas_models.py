"""Cuerpos del catálogo cerrado de modelos en ``/console/*``.

El partner sale del principal. El cuerpo de escritura solo admite
``model_id``; ``partner_id`` u otra clave extra es 422.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ModelWeightsOut(BaseModel):
    """Pesos de cuota por carril (spec 007), tal cual los cobra el medidor."""

    input: float
    cache_read: float
    output: float


class ConsoleModelOut(BaseModel):
    model_id: str
    display_name: str
    #: Spec 016 (R5.1): peso de salida normalizado al menor de la lista —
    #: «xN créditos». Entero; el más económico es 1.
    relative_cost: int = 1
    weights: ModelWeightsOut = Field(
        default_factory=lambda: ModelWeightsOut(input=1, cache_read=1, output=1)
    )


class ClientModelOut(BaseModel):
    client_ref: str
    role: str
    model_id: str | None = None
    display_name: str | None = None
    is_bound: bool = False
    #: Spec 016 (R5.3): ``False`` cuando el plan ya no incluye el modelo
    #: enlazado. Sin binding es ``True``: no hay nada que desautorizar.
    allowed: bool = True
    #: Lo que responde cuando no hay binding (o el binding no está
    #: permitido): el defecto de la plataforma, para que la pantalla lo nombre.
    fallback_model_id: str
    fallback_display_name: str


class ModelIn(BaseModel):
    """Solo el id. El cliente es ``{ref}``; el partner sale del principal."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=64)
