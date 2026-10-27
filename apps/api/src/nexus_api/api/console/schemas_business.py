"""Esquemas del alta en tres datos y de la lectura de la web — spec 047 (T048, T049).

``contracts/console-api.md`` §2 y §3. Ninguna respuesta lleva ids internos del
cliente ni texto de un cliente final (C8): los chips son lo que la persona
escribió, las sugerencias de nicho son nichos del propio partner y la lectura
viaja como cuentas y códigos (``test_console_scope.py``).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from nexus_api.db.models.business import INFO_MAX, NICHE_MAX, NICHE_MIN
from nexus_api.services.business.profile import NAME_MAX, NAME_MIN, is_valid_timezone

from .schemas import JobOut

Network = Literal["web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads"]
NicheGroup = Literal["beauty", "health", "aesthetics", "food", "retail", "services", "other"]
WalletCurrency = Literal["EUR", "USD"]

Name = Annotated[str, StringConstraints(min_length=NAME_MIN, max_length=NAME_MAX)]
Niche = Annotated[str, StringConstraints(min_length=NICHE_MIN, max_length=NICHE_MAX)]
Info = Annotated[str, StringConstraints(max_length=INFO_MAX)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class LinkChoiceIn(BaseModel):
    """Un chip como lo dejó la persona: ``{network, url?, handle?}``. Sirve
    para cambiar la red de un ``@`` suelto o quitar un hallazgo."""

    model_config = ConfigDict(extra="forbid")

    network: Network
    url: str | None = Field(default=None, max_length=300)
    handle: str | None = Field(default=None, max_length=31)


class ClientNewIn(BaseModel):
    """``POST /console/clients`` de la consola nueva (requisito 4.1): tres datos
    y, si la persona los tocó, los de «Más ajustes». Lo que no llega se deduce
    (4.5). Sin plantilla ni agente: crear un cliente nunca crea un agente."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    niche: Niche
    info: Info | None = None
    country: Country | None = None
    timezone: str | None = Field(default=None, max_length=64)
    price_currency: Currency | None = None
    wallet_currency: WalletCurrency | None = None
    eu_only: bool | None = None
    #: Los chips que quedaron. Sin ellos, los que se detecten en ``info``.
    links: list[LinkChoiceIn] | None = Field(default=None, max_length=20)

    @field_validator("name", "niche", mode="before")
    @classmethod
    def _one_line(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("info", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("timezone")
    @classmethod
    def _iana(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_timezone(value):
            raise ValueError("not an IANA time zone")
        return value


class ClientNewOut(BaseModel):
    """``201`` del alta: la referencia del cliente y si se lanzó la lectura."""

    ref: str
    name: str
    status: Literal["active"]
    #: Ya había un cliente con ese nombre en el partner: avisa, no bloquea (4.6).
    duplicate_name: bool
    #: La lectura de su web o sus redes, si tenía alguna (4.4).
    read_job_id: uuid.UUID | None = None


class LinkDetectionIn(BaseModel):
    """Lo escrito en «Información adicional» y lo que el navegador sabe (la
    última fuente de la deducción)."""

    model_config = ConfigDict(extra="forbid")

    info: Info
    browser_timezone: str | None = Field(default=None, max_length=64)
    browser_locale: str | None = Field(default=None, max_length=35)


class DetectedLinkOut(BaseModel):
    kind: Literal["web", "social"]
    network: Network
    #: Lo que enseña el chip.
    value: str
    url: str | None
    handle: str | None
    #: Su destino en la ficha: la web del negocio o sus redes.
    target: Literal["website", "links"]
    #: Un ``@`` suelto propuesto como Instagram.
    guessed: bool
    #: Las redes a las que se puede cambiar.
    alternatives: list[Network]


class DeducedSettingsOut(BaseModel):
    """«Más ajustes» relleno, y de dónde salió el país."""

    country: str | None
    timezone: str
    price_currency: str | None
    wallet_currency: WalletCurrency
    eu_only: bool
    source: Literal["web", "phone", "partner", "browser", "default"]


class LinkDetectionOut(BaseModel):
    links: list[DetectedLinkOut]
    deduced: DeducedSettingsOut


class NicheSuggestionOut(BaseModel):
    """De una plantilla, su clave (el texto es de la consola); de los más
    usados del partner, el nicho y cuántos clientes lo tienen."""

    source: Literal["template", "used"]
    key: str | None = None
    group: NicheGroup | None = None
    value: str | None = None
    uses: int = 0


class NicheSuggestionsOut(BaseModel):
    items: list[NicheSuggestionOut]


class ClientReadOut(BaseModel):
    """La tarjeta de lectura del Panel (requisito 14.7): el último trabajo
    ``client_read`` y qué tiene el cliente para leer."""

    job: JobOut | None
    #: La web, como la enseña el chip (``cultorbarber.com``).
    website: str | None
    networks: list[Network]


__all__ = [
    "ClientNewIn",
    "ClientNewOut",
    "ClientReadOut",
    "DeducedSettingsOut",
    "DetectedLinkOut",
    "LinkChoiceIn",
    "LinkDetectionIn",
    "LinkDetectionOut",
    "NicheSuggestionOut",
    "NicheSuggestionsOut",
]
