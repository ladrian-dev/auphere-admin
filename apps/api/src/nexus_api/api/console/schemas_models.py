"""Cuerpos del catálogo cerrado de modelos en ``/console/*``.

El partner sale del principal. El cuerpo de escritura solo admite
``model_id``; ``partner_id`` u otra clave extra es 422.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
    #: Spec 065 (T023): ``openai`` · ``anthropic`` y la gama (``max`` · ``balanced`` · ``economy``).
    provider: str | None = None
    line: str | None = None


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


# ── Spec 065: el modelo de cada agente (contracts/api.md) ────────────────────


class ModelEstimateOut(BaseModel):
    """Lo que costaría una respuesta de este agente con un modelo, estimado."""

    #: Cien milésimas de la moneda (como el resto de la consola).
    amount_micros: int
    currency: str = "USD"
    #: ``agent_7d`` (consumo real del agente) · ``nominal`` (sin consumo).
    basis: str


class AgentModelChoiceOut(BaseModel):
    model_id: str
    display_name: str
    #: ``partner`` · ``operator``.
    set_by: str
    set_at: datetime | None = None


class AgentModelEffectiveOut(BaseModel):
    model_id: str
    display_name: str
    #: ``agent`` · ``agent_operator`` · ``version`` · ``platform``.
    source: str
    #: ``None`` · ``retired`` (ya no se ofrece) · ``operator`` (fuera de la lista del partner).
    outside_offer: str | None = None
    estimate: ModelEstimateOut | None = None


class AgentModelOptionOut(BaseModel):
    model_id: str
    display_name: str
    #: ``openai`` · ``anthropic``.
    provider: str
    #: ``max`` · ``balanced`` · ``economy``.
    line: str
    estimate: ModelEstimateOut | None = None


class AgentModelOut(BaseModel):
    agent_id: uuid.UUID
    #: ``None``: el agente sigue el modelo por defecto de Auphere.
    choice: AgentModelChoiceOut | None
    effective: AgentModelEffectiveOut
    #: Del más barato al más caro.
    options: list[AgentModelOptionOut]
    #: ``None`` · ``chosen_model_cannot_run_agent``.
    notice: str | None = None
    can_change: bool


class AgentModelIn(BaseModel):
    """Solo el modelo. El cliente es ``{ref}`` y el agente ``{agent_id}``; ``null`` vuelve al
    modelo por defecto de Auphere."""

    model_config = ConfigDict(extra="forbid")

    model_id: str | None = Field(default=None, min_length=1, max_length=64)
