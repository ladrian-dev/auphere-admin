"""Quién hace cada trabajo — el registro de manejadores por ``kind`` (spec 047).

Un manejador es una corrutina que recibe un :class:`JobContext` y devuelve el
resultado del trabajo (un ``dict``, un :class:`JobOutcome` con su coste, o
nada). Para fallar con un motivo que la consola sabe decir, lanza
:class:`JobFailed` con su código; cualquier otra excepción queda como
``internal``.

Cada tipo se registra **una vez**, con su plazo. Si el manejador no termina en
él, el consumidor lo cancela y el trabajo queda ``failed``/``timeout``. Los
tipos son los de la tabla (``JOB_KINDS``): un tipo que la base rechazaría no
llega a registrarse.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from nexus_api.db.models.jobs import JOB_KINDS
from nexus_api.services.jobs import TIMEOUT

#: Los códigos que pone el propio consumidor; los demás son de cada manejador.
#: ``timeout`` es el mismo que escribe la caducidad perezosa de la API.
INTERNAL = "internal"
NO_HANDLER = "no_handler"
INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class StartedJob:
    """Lo que el consumidor sabe de un trabajo al empezarlo."""

    job_id: uuid.UUID
    tenant_id: uuid.UUID
    kind: str
    agent_id: uuid.UUID | None = None
    created_by: str | None = None
    draft_revision: int | None = None


class ProgressSink(Protocol):
    async def progress(
        self,
        tenant_id: uuid.UUID,
        job_id: uuid.UUID,
        *,
        step: str | None = None,
        block: dict[str, Any] | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class JobContext:
    """Lo que recibe un manejador: el trabajo y cómo contar que avanza.

    El cliente viene de la fila que la API escribió con su contexto; el
    manejador abre con él sus propias transacciones (RLS) y nunca lo toma de
    otra parte.
    """

    job: StartedJob
    _sink: ProgressSink = field(repr=False)

    @property
    def job_id(self) -> uuid.UUID:
        return self.job.job_id

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.job.tenant_id

    @property
    def kind(self) -> str:
        return self.job.kind

    @property
    def agent_id(self) -> uuid.UUID | None:
        return self.job.agent_id

    async def progress(
        self, *, step: str | None = None, block: dict[str, Any] | None = None
    ) -> bool:
        """Anota el paso actual o un bloque terminado (``{"key": …}``).
        ``False`` si el trabajo ya no está en marcha: caducó o se interrumpió, y
        el manejador puede dejar de trabajar para nadie."""
        return await self._sink.progress(self.tenant_id, self.job_id, step=step, block=block)


@dataclass(frozen=True)
class JobOutcome:
    """El final de un trabajo que salió bien, con lo que costó."""

    result: dict[str, Any] = field(default_factory=dict)
    cost_micros: int = 0


class JobFailed(Exception):
    """Un fallo con nombre (``unreachable``, ``blocked``…), y lo gastado hasta él."""

    def __init__(self, code: str, *, cost_micros: int = 0) -> None:
        if not code:
            raise ValueError("a job failure needs a code")
        super().__init__(code)
        self.code = code
        self.cost_micros = cost_micros


JobHandler = Callable[[JobContext], Awaitable[JobOutcome | dict[str, Any] | None]]


@dataclass(frozen=True)
class HandlerSpec:
    kind: str
    handler: JobHandler
    timeout_s: float


class JobRegistry:
    """Un manejador por tipo de trabajo, con su plazo."""

    def __init__(self) -> None:
        self._specs: dict[str, HandlerSpec] = {}

    def register(self, kind: str, handler: JobHandler, *, timeout_s: float) -> None:
        if kind not in JOB_KINDS:
            raise ValueError(f"unknown job kind: {kind!r}")
        if kind in self._specs:
            raise ValueError(f"job kind already has a handler: {kind!r}")
        if timeout_s <= 0:
            raise ValueError("a job handler needs a positive timeout")
        self._specs[kind] = HandlerSpec(kind=kind, handler=handler, timeout_s=timeout_s)

    def handler(self, kind: str, *, timeout_s: float) -> Callable[[JobHandler], JobHandler]:
        """Decorador: ``@registry.handler("agent_draft", timeout_s=120)``."""

        def _register(fn: JobHandler) -> JobHandler:
            self.register(kind, fn, timeout_s=timeout_s)
            return fn

        return _register

    def get(self, kind: str) -> HandlerSpec | None:
        return self._specs.get(kind)

    def kinds(self) -> tuple[str, ...]:
        return tuple(self._specs)


#: El registro que usa ``jobs-consumer`` en producción. Cada bloque registra
#: aquí los manejadores de sus tipos al importarse.
default_registry = JobRegistry()


__all__ = [
    "INTERNAL",
    "INTERRUPTED",
    "NO_HANDLER",
    "TIMEOUT",
    "HandlerSpec",
    "JobContext",
    "JobFailed",
    "JobHandler",
    "JobOutcome",
    "JobRegistry",
    "ProgressSink",
    "StartedJob",
    "default_registry",
]
