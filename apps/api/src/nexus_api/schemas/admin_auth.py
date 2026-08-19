"""Modelos de ``/admin/auth/*`` — identidad del panel de operador (ADR-034).

Regla propia de este módulo, igual que en su gemelo de la consola:
**ninguna respuesta lleva ``password`` ni ``password_hash``**. La contraseña
solo viaja de entrada; el token de sesión solo sale.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from nexus_api.services.identity import PASSWORD_MAX_LENGTH
from nexus_api.services.operator_identity import OperatorAccess, OperatorRole

#: Los dos estados que el panel sabe pintar. ``ok`` = panel; ``disabled`` =
#: página "sin acceso". Son dos y no cuatro porque el panel no tiene
#: pertenencia que resolver: ADR-009 lo define como god-mode del equipo.
#: El tipo vive en el servicio; aquí solo se le pone nombre local.
OperatorAccessLiteral = OperatorAccess


class OperatorOut(BaseModel):
    """Quién es el operador, tal y como lo pinta el panel.

    ``id`` sale como cadena porque es lo que el BFF manda de vuelta en la
    cabecera ``X-Operator-Id`` de los endpoints del QA Playground, que
    aíslan por ``app.operator_id`` (TEXT).
    """

    id: str
    email: str
    display_name: str | None
    locale: str
    access: OperatorAccessLiteral
    #: Portado de ``auth.user.role``. El BFF lo usa para gatear el QA
    #: Playground, que es lo único que el rol decide.
    role: OperatorRole


class OperatorLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: A propósito NO es ``EmailStr``. Entrar es buscar una fila, no validar
    #: un correo: un validador más estricto que el que creó la cuenta deja
    #: cuentas imposibles de usar (``EmailStr`` rechaza TLDs reservados como
    #: ``.test``, que es justo lo que usan los entornos de desarrollo).
    email: str = Field(min_length=3, max_length=255)
    # Sin mínimo aquí a propósito: el mínimo es de la CREACIÓN de la cuenta.
    # Exigirlo al entrar convertiría "contraseña corta" en un 422 distinto
    # del 401, que es exactamente el oráculo que este endpoint evita.
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class OperatorLoginOut(BaseModel):
    """El token opaco de sesión y quién lo tiene. El panel lo guarda en una
    cookie ``HttpOnly`` y no vuelve a verlo nadie más."""

    token: str
    expires_at: datetime
    operator: OperatorOut


class OperatorSessionIn(BaseModel):
    """El token va en el CUERPO, no en la query: una cadena que abre la
    sesión no debe acabar en el log de accesos de ningún proxy."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=256)


class OperatorSessionOut(BaseModel):
    """``operator=null`` significa "no hay sesión", que para el BFF es una
    respuesta normal —enseña el login—, no un fallo de credencial."""

    operator: OperatorOut | None = None
