"""Esquemas de ``/console/auth/google/*`` — spec 006, Requisito 5."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GoogleStartIn(BaseModel):
    #: Para qué se pulsó el botón. Viaja firmado dentro del `state`, así que la
    #: vuelta sabe de dónde venía sin fiarse del navegador.
    intent: Literal["login", "signup"] = "login"


class GoogleStartOut(BaseModel):
    authorization_url: str


class GoogleCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=2048)


class GoogleCallbackOut(BaseModel):
    """Dos desenlaces y sólo dos.

    ``session`` — la persona ya tiene partner y entra.
    ``signup_pending`` — la identidad es buena pero falta nombrar la empresa,
    así que sigue por el mismo camino que el alta con contraseña.
    """

    outcome: Literal["session", "signup_pending"]
    session_token: str | None = None
    expires_at: str | None = None
    signup_token: str | None = None
