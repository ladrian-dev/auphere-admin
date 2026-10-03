"""Esquemas de ``/console/password-reset`` — spec 011.

**Ningún campo de respuesta permite averiguar si una dirección tiene cuenta**
(R1.3). No hay ``created``, ni ``existed``, ni un id, ni un ``expires_at``:
cualquiera de ellos convertiría la ruta de pedir en un oráculo de qué
direcciones están registradas, que es justo lo que la spec compra.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from nexus_api.services.console_identity import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class PasswordResetStartIn(BaseModel):
    """Sólo la dirección.

    **Sin ``locale``, a diferencia del alta**, y la razón la dio el recorrido a
    mano: los dos correos de este circuito van a la persona **dueña de la
    cuenta**, que no tiene por qué ser quien rellenó el formulario. Dejar que
    el cuerpo de la petición eligiera el idioma permitiría a un desconocido
    decidir en qué lengua le llega un correo sobre su contraseña a otra
    persona. El idioma sale de la cuenta, que es de quien lo va a leer.

    En el alta sí viene en el cuerpo, y ahí es correcto: no hay cuenta todavía
    a la que preguntárselo.
    """

    email: EmailStr


class PasswordResetStartOut(BaseModel):
    """Idéntica en los cuatro caminos: con cuenta, sin cuenta, con el envío
    caído y pasado el tope."""

    status: Literal["sent"] = "sent"


class PasswordResetFinishIn(BaseModel):
    #: Las mismas reglas de validez que el alta (R2.1). El mínimo se declara
    #: aquí **y** lo vuelve a comprobar ``console_identity.validate_password``:
    #: el esquema es para el mensaje, el servicio es la regla.
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class PasswordResetFinishOut(BaseModel):
    """**Sin token de sesión, y es la decisión D-5.**

    Restablecer acaba de cerrar todas las sesiones de esta persona. Abrir una
    nueva en el mismo acto contradiría lo que se acaba de hacer y dejaría la
    duda de si la revocación alcanzó a todas. Que entre ella, con su contraseña
    nueva, es la prueba de que el circuito funciona.
    """

    status: Literal["reset"] = "reset"
