"""Esquemas de ``/console/auth/google/*`` — spec 006, Requisito 5."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GoogleAvailableOut(BaseModel):
    """¿Se puede ofrecer Google? **Una respuesta, no un efecto.**

    Existe porque preguntarlo con ``/start`` acuñaba un PKCE que nadie iba a
    consumir: el botón preguntaba al montar y volvía a llamar al pulsar, así
    que cada visita a ``/login`` —pública— dejaba una clave de diez minutos en
    Redis. Un verbo que escribe no sirve para una pregunta.
    """

    available: bool


class GoogleStartIn(BaseModel):
    #: Para qué se pulsó el botón. Viaja firmado dentro del `state`, así que la
    #: vuelta sabe de dónde venía sin fiarse del navegador.
    intent: Literal["login", "signup"] = "login"
    #: A dónde volver después de entrar — spec 009, fallo 1.
    #:
    #: **Sólo una ruta del mismo origen**, y se valida aquí porque viajará
    #: FIRMADA dentro del `state`: si se colara un `https://malo.example/`, el
    #: callback lo devolvería con nuestra propia firma a favor del atacante. Es
    #: decir, un redirector abierto con el sello de la casa.
    #:
    #: El patrón es el mismo que ya usa `/login` para su `from`: una sola barra
    #: inicial y ninguna contrabarra — los navegadores tratan `/\evil.com` como
    #: una URL relativa al protocolo.
    return_to: str | None = Field(default=None, max_length=512)

    @field_validator("return_to")
    @classmethod
    def _solo_una_ruta_del_mismo_origen(cls, value: str | None) -> str | None:
        """Un validador y no un `pattern` porque pydantic valida con el motor de
        Rust, que **no admite lookahead** — y porque aquí conviene poder decir
        en voz alta qué se rechaza y por qué.

        Los tres casos que importan, y los tres son el mismo ataque:

        * `https://malo.example/` — otro origen, sin disimulo.
        * `//malo.example/` — relativo al protocolo: el navegador lo trata como
          `https://malo.example/`.
        * `/\malo.example` — algunos navegadores tratan la contrabarra como
          barra, así que equivale al anterior.
        """
        if value is None:
            return None
        if not value.startswith("/"):
            raise ValueError("return_to tiene que ser una ruta")
        if value[1:2] in ("/", "\\"):
            raise ValueError("return_to no puede salir del origen")
        if "\\" in value:
            raise ValueError("return_to no puede llevar contrabarras")
        return value


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
    #: A dónde volver, si el inicio de sesión lo empezó alguien que iba a otro
    #: sitio. Sale del `state` **firmado**, no de la URL: los parámetros del
    #: callback los pone Google (spec 009, fallo 1).
    return_to: str | None = None
    session_token: str | None = None
    expires_at: str | None = None
    signup_token: str | None = None
