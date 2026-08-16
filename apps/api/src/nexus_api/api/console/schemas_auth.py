"""Modelos de ``/console/auth/*`` — identidad de la consola en la API.

Reglas de la familia (pinchadas por ``tests/isolation/test_console_scope.py``):
ningún cuerpo acepta ``tenant_id``/``partner_id``, ninguna respuesta lleva
ids internos de tenant ni contenido de mensajes. Y una regla propia de este
módulo: **ninguna respuesta lleva ``password`` ni ``password_hash``**. La
contraseña solo viaja de entrada; el token de sesión solo sale.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus_api.services.console_identity import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

#: Los cuatro estados que la consola sabe pintar. ``ok`` = panel; los otros
#: tres = página "sin acceso" (misma semántica que tenía el BFF cuando
#: resolvía la membresía por SQL).
AccessLiteral = Literal["ok", "no_membership", "suspended", "disabled"]


class PrincipalOut(BaseModel):
    """Quién es el usuario y qué puede hacer, tal y como lo pinta la consola.

    Es el equivalente en servidor de lo que antes construía
    ``apps/console/src/lib/principal.ts`` leyendo Postgres. ``partner_id``
    está aquí porque el BFF lo necesita para acuñar el JWT de 60 s de cada
    llamada; NO es un id de tenant (la regla de aislamiento habla de
    tenants, y un partner ya sabe quién es).

    Sin membresía utilizable, ``role`` es ``null``, ``permissions`` va vacío
    y ``console_enabled`` es ``false``: el login **funciona**, la consola
    enseña "sin acceso".
    """

    user_id: uuid.UUID
    email: str
    display_name: str | None
    locale: str
    access: AccessLiteral
    membership_id: uuid.UUID | None = None
    partner_id: uuid.UUID | None = None
    partner_slug: str | None = None
    partner_name: str | None = None
    partner_status: str | None = None
    role: str | None = None
    permissions: list[str] = Field(default_factory=list)
    console_enabled: bool = False


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: A propósito NO es ``EmailStr``. Entrar es buscar una fila, no validar
    #: un correo: un validador más estricto que el que creó la cuenta deja
    #: cuentas imposibles de usar (``EmailStr`` rechaza TLDs reservados como
    #: ``.test``, que es justo lo que usan los entornos de desarrollo). El
    #: formato se valida donde importa: al invitar (``InviteIn``).
    email: str = Field(min_length=3, max_length=255)
    # Sin mínimo aquí a propósito: el mínimo es de la CREACIÓN de la cuenta.
    # Exigirlo al entrar convertiría "contraseña corta" en un 422 distinto
    # del 401, que es exactamente el oráculo que este endpoint evita.
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class LoginOut(BaseModel):
    """El token opaco de sesión y quién lo tiene. La consola lo guarda en
    una cookie ``httpOnly`` y no vuelve a verlo nadie más."""

    token: str
    expires_at: datetime
    principal: PrincipalOut


class SessionIn(BaseModel):
    """El token va en el CUERPO, no en la query: una cadena que abre la
    sesión no debe acabar en el log de accesos de ningún proxy."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)


class SessionOut(BaseModel):
    principal: PrincipalOut


class InvitationAcceptWithPasswordIn(BaseModel):
    """Aceptar una invitación crea la cuenta. El correo NO viene aquí: sale
    de la invitación, que es la única que sabe a quién se invitó."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    display_name: str | None = Field(default=None, max_length=255)
