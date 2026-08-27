"""Modelos de ``/console/capabilities`` y ``/console/support/tickets`` (CO-08).

Los nombres de propiedad no son libres. ``tests/isolation/test_console_scope.py``
recorre el OpenAPI de **todas** las rutas ``/console/*`` y rechaza cualquier
propiedad de respuesta que se llame como el cuerpo de un mensaje
(``content``, ``text``, ``body``, ``message``, ``notes``, ``reason``,
``payload``…). La lista blanca global es diminuta —
``{system_prompt, summary, detail}`` — y **no se amplía**: se resta de los
infractores de todas las rutas, así que ensancharla para desbloquear un
carril ciega la comprobación en los otros ~60 endpoints de la consola.

De ahí los nombres de aquí, todos deliberados:

- ``note`` en **singular** (``notes`` está prohibido, ``reason`` también);
- ``need`` y no ``description`` ni ``message``;
- ``checked`` y no ``notes``;
- ``preview``/``topic``/``category``/``sla`` son identificadores, no prosa.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CapabilityOut(BaseModel):
    """Una entrada del documento de capacidades (§5.3 de CONTRACT-V2)."""

    key: str
    family: str
    status: str
    label: str
    note: str | None = None
    #: Solo con ``status='planned'``. Texto corto, **nunca** una fecha
    #: inventada: prometer un día concreto que nadie se comprometió a
    #: cumplir es la forma más cara de perder la confianza de un partner.
    eta: str | None = None
    #: Solo con ``status='retired'``: a dónde se redirige.
    replaced_by: list[str] = Field(default_factory=list)


class CapabilitiesOut(BaseModel):
    version: str
    entries: list[CapabilityOut]


class SupportTicketIn(BaseModel):
    """El cuerpo de ``POST /console/support/tickets``.

    Lo compone la propuesta ya confirmada, no el modelo: entre lo que el
    Companion propuso y esta petición hay una persona que dijo que sí.
    ``partner_id`` no existe aquí: sale de la sesión.
    """

    model_config = ConfigDict(extra="forbid")

    category: str = Field(pattern="^(help|capability)$")
    #: Slug estable con espacio de nombres por familia. Es la clave de
    #: agregación del §25.2: sin ella, "siete partners han pedido Shopify
    #: este trimestre" no se puede consultar.
    topic: str = Field(min_length=3, max_length=60)
    #: Referencia del cliente del partner, o ``null`` si el ticket no es de
    #: un cliente. **Nunca un ``tenant_id``** (§1.2 de CONTRACT-V1).
    client_ref: str | None = Field(default=None, max_length=255)
    need: str = Field(min_length=1, max_length=1_000)
    #: El expediente: lo que el Companion YA leyó, por etiqueta del catálogo
    #: de herramientas. Un ticket sin esto es un ticket sin expediente.
    checked: list[str] = Field(min_length=1, max_length=12)
    alternative: str | None = Field(default=None, max_length=1_000)
    #: §25.4 — la solución puente se etiqueta Y el ticket se abre igual.
    bridge: bool = False


class SupportTicketOut(BaseModel):
    """Lo que devuelve abrir un ticket. Identificador y expectativa (§4.4).

    Sin identificador el ticket es un agujero negro; sin expectativa, el
    partner no sabe si esperar sentado. Los dos son **identificadores
    estables**: la frase que ve el usuario la escribe la interfaz.
    """

    ticket_ref: str
    category: str
    topic: str
    sla: str
    opened_at: datetime


__all__ = [
    "CapabilitiesOut",
    "CapabilityOut",
    "SupportTicketIn",
    "SupportTicketOut",
]
