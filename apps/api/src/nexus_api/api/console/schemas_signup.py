"""Esquemas de ``/console/signup/*`` — spec 006.

**Ningún campo de respuesta permite enumerar correos** (Requisito 1.2). La
respuesta del alta es siempre la misma exista o no la dirección; lo que cambia
es el correo que llega, no lo que ve quien llama.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupStartIn(BaseModel):
    email: EmailStr
    locale: Literal["es", "en"] = "es"


class SignupStartOut(BaseModel):
    """Idéntica para un correo nuevo y para uno que ya tiene cuenta.

    No lleva ``created``, ni ``existed``, ni un id: cualquiera de esas tres
    cosas convertiría este endpoint en un oráculo de qué direcciones están
    registradas.
    """

    status: Literal["sent"] = "sent"


class SignupLookupOut(BaseModel):
    """Lo que la página del enlace necesita para decidir qué pintar."""

    email: EmailStr
    provider: Literal["google"] | None = None
    expires_at: str


class SignupCompleteIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    #: Ausente cuando la solicitud vino de un proveedor: esa cuenta nace sin
    #: contraseña y no se le inventa una.
    password: str | None = Field(default=None, min_length=12, max_length=256)
    display_name: str | None = Field(default=None, max_length=255)


class SignupCompleteOut(BaseModel):
    session_token: str
    #: Cuándo caduca la sesión. Va aquí para que la cookie del BFF caduque
    #: **con** la sesión y no con un TTL de respaldo que puede discrepar: una
    #: cookie viva sobre una sesión muerta es un 401 cuya causa no se ve.
    expires_at: str
    partner_slug: str
    role: Literal["owner"] = "owner"
