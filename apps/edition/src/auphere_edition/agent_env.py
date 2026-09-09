"""El ambiente del proceso del agente — Requisito 7.4.

*Ninguna credencial de cliente final entra nunca en el ambiente de un agente.*
La constitución no le pone matices, así que aquí tampoco.

**Lista blanca, no saneado.** El sustrato arranca sus procesos con
`env = {**os.environ}` y quita cinco variables de AWS y GPG; todo lo demás pasa.
En la beta 2 ese entorno es el del partner: sus claves de despliegue, sus tokens,
lo que tenga. Una lista negra ahí es una lista de lo que se nos ocurrió, no de lo
que hay — y lo que no se nos ocurra viaja.

Así que se parte de **nada** y se añade lo poco que un proceso necesita para
correr. Y aun así se revisa el valor: un nombre permitido no compra el derecho a
llevar un secreto dentro.
"""

from __future__ import annotations

import re

#: Lo mínimo para que un proceso arranque y hable el idioma del partner.
#: Deliberadamente corta; hay un test que se queja si crece.
ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR"}
)

#: Formas de credencial que se reconocen a simple vista. La lista no pretende ser
#: exhaustiva —no puede serlo— sino cazar el error honesto: alguien que reexporta
#: una variable sin pensar. Lo que de verdad contiene el riesgo es la lista blanca.
_CREDENTIAL_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk_(live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
)


class CredentialLeak(RuntimeError):
    """Un valor con forma de credencial iba a entrar en el ambiente del agente."""


def build_agent_env(source: dict[str, str]) -> dict[str, str]:
    """Construye el ambiente del agente desde cero.

    Falla cerrado: si algo con forma de credencial aparece **incluso en una
    variable permitida**, se levanta en vez de recortarse. Recortar en silencio
    dejaría a alguien creyendo que su secreto viajó cuando no, o al revés.
    """
    env: dict[str, str] = {}
    for key in sorted(ALLOWED_ENV_KEYS):
        value = source.get(key)
        if value is None:
            continue
        for shape in _CREDENTIAL_SHAPES:
            if shape.search(value):
                raise CredentialLeak(
                    f"la variable {key} contiene algo con forma de credencial; "
                    "no entra en el ambiente del agente"
                )
        env[key] = value
    return env


__all__ = ["ALLOWED_ENV_KEYS", "CredentialLeak", "build_agent_env"]
