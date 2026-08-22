"""Registro de runs del Companion — log durable en Redis Streams (CO-01).

Este módulo es la corrección **C1** de la Parte II de la investigación:
*el run no muere con la conexión*. El playground (``api/qa_streaming.py``)
guarda sus eventos en un ``deque(maxlen=256)`` dentro del proceso, con 60 s
de retención. Para el playground vale: un turno dura segundos y su
transcripción vive en la memoria del navegador. Para el Companion no: un
turno puede durar minutos, el búfer rota, y ``resume.gap`` deja al usuario
mirando una pantalla en blanco porque no hay historial al que volver.

Aquí el log **es** el estado::

    POST …/runs   →  202 {run_id}                    (arranca y devuelve YA)
                     └─ asyncio.Task ─► grafo ─► publish(evento)
                                                     │
                             Redis Stream companion:run:{id}
                                    (MAXLEN aproximado + TTL)
                                                     │
    GET …/events?since_seq=N ── XRANGE ──────────────┤   historial (REST)
    GET …/stream?since_seq=N ── XRANGE + XREAD BLOCK ┘   SSE en vivo

Consecuencias, todas buscadas:

- **El SSE es un lector puro.** Cualquier réplica sirve cualquier stream y
  la reanudación es exacta (se filtra por ``seq``), no *best-effort*. Eso
  elimina de golpe la necesidad de sesiones pegajosas en el balanceador.
- **Cerrar el portátil, cambiar de pestaña o perder el wifi dejan de ser
  incidentes.** El trabajo sigue; el cajón lo recoge donde estaba.
- **Cerrar el ``fetch`` NO cancela.** Cancelar es un acto explícito:
  ``DELETE …/runs/{id}``, que marca la fila y levanta una bandera que el
  driver ve aunque el run corra en otra réplica.

El catálogo cerrado
-------------------
``COMPANION_EVENTS`` mapea nombre de evento → claves permitidas en su
payload, y :func:`publish` **rechaza** lo que no está y **elimina** las
claves no declaradas. No es cosmética: es el guardián de la decisión C8.

El recorrido genérico de ``tests/isolation/test_console_scope.py`` no puede
proteger este camino, porque el historial se sirve como
``{seq, event, data}`` con ``data`` sin propiedades declaradas — los
payloads son heterogéneos por diseño y un modelo tipado obligaría a
declarar ``text`` como propiedad, que es justo lo que ese test prohíbe. En
vez de ampliar su lista blanca global (que cegaría la comprobación en los
otros ~60 endpoints de la consola), el guardián se construye aquí, es
específico y es más fuerte: ninguna clave del catálogo puede llamarse como
el cuerpo de un mensaje de un cliente final, y ``text`` solo se admite en
los eventos que el propio Companion redacta. Lo prueba
``tests/isolation/test_companion_no_customer_bodies.py``.

Y es **código determinista**, no una instrucción al modelo (C5).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog
from redis.asyncio import Redis

from nexus_api.api.qa_streaming import PING_INTERVAL_SECONDS, SSEEvent, _json_default
from nexus_api.config import get_settings
from nexus_api.core.otel_metrics import record_companion
from nexus_api.core.streams import xadd_capped
from nexus_api.db.models.companion import (
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_ERROR,
    RUN_PAUSED,
)

log = structlog.get_logger(__name__)


# ── catálogo cerrado de eventos ────────────────────────────────────────
#
# CO-01 emite estos. CO-02 (herramientas), CO-03 (cajón) y CO-04 (HITL)
# añaden los suyos AQUÍ y con la misma regla: si una clave nueva pudiera
# llevar el cuerpo de un mensaje de un cliente final, el test de
# aislamiento se pone rojo antes de que llegue a producción.

COMPANION_EVENTS: dict[str, frozenset[str]] = {
    # ciclo de vida
    "run.started": frozenset({"run_id", "thread_id", "started_at"}),
    # ``unsupported`` es el veredicto de la regla R1 (sin lectura no hay
    # afirmación). Va aquí y no en un evento propio por dos motivos: solo se
    # conoce al cerrar el turno, y este evento se emite SIEMPRE, incluso si
    # el run falla — así la métrica no tiene agujeros.
    "run.completed": frozenset({"run_id", "ended_at", "status", "error", "unsupported"}),
    # ``gap_kind`` y no ``reason``: el playground llama ``reason`` a este
    # campo, pero ``reason`` está en la lista de nombres que podrían llevar
    # el texto de un cliente final (un motivo de rechazo de Meta, por
    # ejemplo) y el guardián de C8 lo rechaza — con razón, porque el
    # guardián no puede saber que aquí solo caben tres cadenas fijas.
    # Renombrar es más barato y más honesto que abrir una excepción.
    "resume.gap": frozenset({"gap_kind", "since_seq", "available_from"}),
    "ping": frozenset({"ts"}),
    # proceso (§7): la píldora de estado del cajón
    "phase.changed": frozenset({"phase", "label"}),
    # transcripción — redactada POR EL COMPANION, nunca por un cliente final
    "text.delta": frozenset({"message_id", "text"}),
    "reasoning.delta": frozenset({"message_id", "text"}),
    # herramientas (CO-02). ``args`` lleva SOLO lo que el modelo escribió
    # —una referencia de cliente, unos días—, nunca contenido leído: el
    # resultado de la herramienta no viaja por el stream, va al contexto del
    # modelo. Por eso ninguna clave de aquí puede llevar el cuerpo de un
    # mensaje de un cliente final.
    "tool.call.started": frozenset({"tool_call_id", "name", "label", "args"}),
    "tool.call.completed": frozenset(
        {"tool_call_id", "name", "ok", "latency_ms", "error", "citation_id"}
    ),
    # La cita es lo que sostiene R1: un dato con su procedencia. ``claim`` es
    # la etiqueta de lo que se leyó ("Consumo del partner (client_ref=boreal)"),
    # redactada por el catálogo del Companion — no texto de nadie más.
    "citation": frozenset({"citation_id", "claim", "source", "fetched_at"}),
    # proceso y confirmación humana (CO-04). Las claves son LITERALES del §2
    # de ``docs/companion/CONTRACT-V1.md`` y no se tocan: el catálogo elimina
    # en silencio lo que no declara, así que una clave con otro nombre no
    # llega al navegador y no hay error que lo delate.
    "plan.proposed": frozenset({"plan_id", "steps", "risk", "reversible", "estimated_tokens"}),
    # Lo que falta y solo sabe el cliente. ``slots`` es una lista de
    # ``{key, label, why, examples, required}``; ``key`` es un identificador
    # estable y la interfaz puede tener copy propio por cada uno.
    #
    # ``work_kind`` es de la v2 (§3.1 de ``CONTRACT-V2.md``) y lo emite el
    # nodo del expediente (CO-06). Existe porque la interfaz titula el grupo
    # de chips ("Para crear el cliente me faltan…") y sin él tendría que
    # deducir el tipo de trabajo parseando prefijos de ``key``, que es
    # adivinar. Enum cerrado: create_client · connect_whatsapp ·
    # change_prompt · enable_connector · publish.
    "intake.missing": frozenset({"slots", "work_kind"}),
    # ``preview`` y no ``payload``: ``payload`` está en la lista de nombres
    # prohibidos del recorrido de OpenAPI, y aunque este catálogo sea otro
    # guardián, usar el mismo vocabulario en los dos evita que alguien
    # "arregle" uno rompiendo el otro.
    "hitl.requested": frozenset(
        {"action_id", "kind", "title", "preview", "diff", "impact", "expires_at"}
    ),
    # ``note`` en singular: ``notes`` está prohibido y ``reason`` también.
    # No es cosmética — el motivo de un rechazo VUELVE al modelo, así que
    # esta clave lleva texto escrito por la persona del partner (nunca por un
    # cliente final del partner, que es lo que el guardián protege).
    "hitl.resolved": frozenset({"action_id", "decision", "by", "at", "note"}),
    # Lo produce código determinista que relee y compara (C5). Ni un
    # subagente ni una instrucción de "revisa tu trabajo".
    #
    # ``trial`` es de la v2 (§7 de ``CONTRACT-V2.md``) y lo emite CO-05: el
    # resultado de haber probado la acción en un hilo de playground antes de
    # publicar. Tres reglas duras que valen aunque el emisor aún no exista:
    # ``null`` es "esta acción no admite prueba" y ``{"ran": false}`` es
    # "admite prueba y no se hizo" —no son lo mismo—, y **nunca lleva la
    # respuesta del agente borrador**: lleva la sonda que redacta el
    # Companion, aserciones con nombre estable y el ``thread_id`` del
    # playground, donde ya hay autorización para leer la conversación.
    "verify.result": frozenset({"action_id", "checks", "ok", "trial"}),
    # escalado a soporte (CO-08, §4.5). Hace falta porque el identificador
    # NACE al aplicar: sin evento, la interfaz no tiene de dónde sacarlo
    # para pintar la tarjeta. Se emite en ``execute``, después del 2xx de
    # ``console.apply`` y antes de ``verify.result``, y la interfaz lo ata a
    # la tarjeta de ``hitl.requested`` por ``action_id`` —igual que hace con
    # ``hitl.resolved``—, no añade una tarjeta suelta.
    #
    # ``category``, ``topic`` y ``sla`` son identificadores estables; la
    # frase que ve el usuario ("te respondemos en horario laboral") la
    # escribe la interfaz. Ninguna clave de aquí puede llevar texto de un
    # cliente final: ``topic`` es un slug y el resto son enums y un
    # identificador.
    "support.ticket": frozenset({"action_id", "ticket_ref", "category", "topic", "sla"}),
    # medidores
    # ``input_tokens`` es la entrada de **cuota** del turno —uncached +
    # 0.1 x cache_read, C3—, no la ventana: esa va en ``context.updated``
    # y es el prefijo entero. El desglose de caché y las pasadas viajan aquí
    # porque son lo que permite valorar el turno en dólares y ver si el caché
    # está funcionando; sin ellos, el panel solo puede decir "gastó algo".
    "cost.updated": frozenset(
        {"input_tokens", "output_tokens", "cache_read", "cache_write", "steps", "model"}
    ),
    "context.updated": frozenset({"input_tokens", "max_context", "percent", "compacted", "model"}),
    "budget.updated": frozenset(
        {"used", "cap", "remaining", "percent", "exhausted", "period", "resets_at"}
    ),
    # El CORTE por presupuesto (CO-08, §6.4). Separado de ``budget.updated``
    # a propósito: aquel sigue emitiéndose en cada turno y sigue llevando
    # ``exhausted``, pero la interfaz tiene que poder distinguir "vas por el
    # 98 %" de "aquí se paró el trabajo". Son dos mensajes distintos y se
    # pintan distinto — y el segundo NO es un error: el hilo sigue ahí, la
    # historia sigue ahí, y lo desbloquea subir un número.
    "budget.paused": frozenset({"used", "cap", "period", "resets_at", "scope"}),
}

#: Los dos únicos eventos donde ``text`` es legítimo: son las palabras del
#: propio Companion. Cualquier otro uso es un cuerpo de mensaje ajeno.
COMPANION_AUTHORED_EVENTS: frozenset[str] = frozenset({"text.delta", "reasoning.delta"})


class UnknownCompanionEvent(ValueError):
    """Se intentó publicar un evento fuera del catálogo."""


def sanitise_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Deja solo las claves que el catálogo declara para ``event``.

    Filtrar en vez de fallar es deliberado: una clave de más en un payload
    es un descuido de quien emite, y tirar el turno entero por eso sería
    peor que entregarlo limpio. Lo que **sí** falla es un evento
    desconocido — ahí no hay forma segura de adivinar qué es publicable.
    """
    allowed = COMPANION_EVENTS.get(event)
    if allowed is None:
        raise UnknownCompanionEvent(f"evento fuera del catálogo del Companion: {event!r}")
    dropped = [k for k in data if k not in allowed]
    if dropped:
        # ``event`` es la clave reservada del mensaje en structlog.
        log.warning("companion.event.keys_dropped", sse_event=event, keys=dropped)
    return {k: v for k, v in data.items() if k in allowed}


# ── claves de Redis ────────────────────────────────────────────────────

RUN_KEY_PREFIX = "companion:run:"

#: Entradas conservadas por run. Un turno con respuesta larga produce del
#: orden de mil deltas; 10.000 deja holgura de un orden de magnitud sin que
#: un run desbocado pueda crecer sin límite.
RUN_LOG_MAXLEN = 10_000

#: Vida del log de un run. El historial que importa a largo plazo está en
#: ``companion.messages``; esto es el detalle de un turno, que solo se
#: reproduce mientras alguien puede estar reconectando.
RUN_LOG_TTL_SECONDS = 24 * 3600

#: Cada cuántos eventos el driver comprueba la bandera de cancelación en
#: Redis. Es lo que hace que un ``DELETE`` servido por OTRA réplica pare el
#: trabajo; en la propia réplica el ``task.cancel()`` es inmediato.
CANCEL_POLL_EVERY_EVENTS = 25


def run_key(run_id: uuid.UUID) -> str:
    return f"{RUN_KEY_PREFIX}{run_id}"


def cancel_key(run_id: uuid.UUID) -> str:
    return f"{RUN_KEY_PREFIX}{run_id}:cancel"


# ── publicación ────────────────────────────────────────────────────────


async def publish(
    redis: Redis,
    run_id: uuid.UUID,
    *,
    seq: int,
    event: str,
    data: dict[str, Any],
) -> None:
    """Añade un evento al log durable del run.

    ``seq`` lo asigna el escritor, que es único por run (una tarea), así que
    un contador en memoria basta y es determinista. El id de entrada de
    Redis se usa solo como cursor de ``XREAD``; ``seq`` es el contrato con
    el cliente y lo que hace exacta la reanudación.
    """
    payload = sanitise_payload(event, data)
    key = run_key(run_id)
    await xadd_capped(
        redis,
        key,
        {
            "seq": str(seq),
            "event": event,
            "data": json.dumps(payload, default=_json_default, separators=(",", ":")),
        },
        maxlen=RUN_LOG_MAXLEN,
    )
    # EXPIRE por evento y no solo al crear: un run largo renueva su ventana
    # y no se queda sin log mientras aún está trabajando.
    await redis.expire(key, RUN_LOG_TTL_SECONDS)


#: Una entrada del stream: ``(id, campos)``. Los stubs de redis-py declaran
#: claves y valores como ``bytes | str`` porque el cliente puede estar
#: configurado sin decodificación; el nuestro decodifica (``decode_responses``),
#: así que se estrecha en un solo sitio en vez de repartir ``cast`` por todo
#: el módulo.
StreamEntry = tuple[str, dict[str, str]]


def _entries(raw: Any) -> list[StreamEntry]:
    return [
        (str(entry_id), {str(k): str(v) for k, v in fields.items()}) for entry_id, fields in raw
    ]


def _decode(fields: dict[str, str]) -> SSEEvent:
    try:
        data = json.loads(fields.get("data") or "{}")
    except ValueError:  # pragma: no cover - defensivo
        data = {}
    return SSEEvent(
        seq=int(fields.get("seq") or 0),
        event=fields.get("event") or "unknown",
        data=data if isinstance(data, dict) else {},
    )


async def read_events(
    redis: Redis,
    run_id: uuid.UUID,
    *,
    since_seq: int = 0,
    limit: int = 500,
) -> tuple[list[SSEEvent], int | None]:
    """Historial del run por REST: los eventos con ``seq > since_seq``.

    Devuelve ``(eventos, primer_seq_disponible)``. El segundo valor solo
    viene cuando el log rotó por delante de ``since_seq`` — el cliente
    entonces sabe que hay un hueco y de dónde puede seguir, en vez de
    quedarse con un ``resume.gap`` sin salida.
    """
    raw = _entries(await redis.xrange(run_key(run_id), "-", "+"))
    if not raw:
        return [], None
    events = [_decode(fields) for _entry_id, fields in raw]
    first_seq = events[0].seq
    gap_from = first_seq if since_seq > 0 and since_seq + 1 < first_seq else None
    return [e for e in events if e.seq > since_seq][:limit], gap_from


#: Devuelve el estado terminal del run si ya lo es, o ``None`` si sigue vivo.
TerminalCheck = Callable[[], Awaitable[str | None]]


async def subscribe(
    redis: Redis,
    run_id: uuid.UUID,
    *,
    since_seq: int = 0,
    terminal_check: TerminalCheck | None = None,
) -> AsyncIterator[str]:
    """SSE en formato de cable, leyendo el log durable.

    Reproduce desde ``since_seq`` y sigue en vivo. Sale al ver el evento
    terminal — o, si el proceso que lo arrancó murió sin escribirlo,
    cuando ``terminal_check`` diga que la fila ya está cerrada. Sin esa
    segunda salida el cajón se quedaría haciendo *ping* para siempre
    contra un run que ya nadie está ejecutando.
    """
    key = run_key(run_id)
    delivered = since_seq
    last_id = "0-0"

    raw = _entries(await redis.xrange(key, "-", "+"))
    if not raw:
        # Ni log ni run: expiró, nunca existió, o el id es de otro. El
        # endpoint ya comprobó la propiedad, así que aquí solo puede ser lo
        # primero. El cliente refresca el hilo por REST.
        yield SSEEvent(seq=0, event="resume.gap", data={"gap_kind": "run_log_expired"}).to_wire()
        return

    first_seq = int(raw[0][1].get("seq") or 0)
    if since_seq > 0 and since_seq + 1 < first_seq:
        yield SSEEvent(
            seq=0,
            event="resume.gap",
            data={"gap_kind": "log_rotated", "since_seq": since_seq, "available_from": first_seq},
        ).to_wire()

    for entry_id, fields in raw:
        last_id = entry_id
        ev = _decode(fields)
        if ev.seq > delivered:
            delivered = ev.seq
            yield ev.to_wire()
            if ev.event == "run.completed":
                return

    block_ms = int(PING_INTERVAL_SECONDS * 1000)
    while True:
        batch: Any = await redis.xread({key: last_id}, block=block_ms, count=200) or []
        if not batch:
            # Sin novedades: heartbeat para que ningún proxy cierre (el ALB
            # cierra las conexiones ociosas a los 60 s por defecto).
            yield SSEEvent(seq=0, event="ping", data={"ts": time.time()}).to_wire()
            if terminal_check is not None:
                status = await terminal_check()
                if status is not None:
                    yield SSEEvent(
                        seq=0,
                        event="run.completed",
                        data={"run_id": str(run_id), "ended_at": time.time(), "status": status},
                    ).to_wire()
                    return
            continue
        for _stream, items in batch:
            for entry_id, fields in _entries(items):
                last_id = entry_id
                ev = _decode(fields)
                if ev.seq <= delivered:
                    continue
                delivered = ev.seq
                yield ev.to_wire()
                if ev.event == "run.completed":
                    return


# ── ciclo de vida de un run en proceso ─────────────────────────────────


@dataclass
class CompanionRunHandle:
    """Lo que el proceso que arrancó el run guarda mientras dura.

    A diferencia del ``RunHandle`` del playground, esto **no es el estado
    del run** — el estado es el log de Redis. Aquí solo vive lo que un
    proceso necesita para seguir escribiendo: el contador de secuencia, la
    tarea que se puede cancelar y los totales que cierran la fila.
    """

    run_id: uuid.UUID
    thread_id: uuid.UUID
    principal_id: str
    redis: Redis
    task: asyncio.Task[None]
    seq: int = 0
    events_since_cancel_poll: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    #: Desglose de caché y pasadas del turno. Sirven para valorar el turno en
    #: dólares al cerrarlo y para ver si el prefijo se está cacheando de
    #: verdad — con ``cache_read`` a cero en todas las llamadas, no lo está.
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_steps: int = 0
    last_input_tokens: int = 0
    model: str | None = None
    final_status: str | None = None
    final_error: str | None = None
    cancel_requested: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        """Publica un evento con el siguiente ``seq`` y comprueba, cada
        tantos, si alguien pidió cancelar desde otra réplica."""
        self.seq += 1
        await publish(self.redis, self.run_id, seq=self.seq, event=event, data=data)
        self.events_since_cancel_poll += 1
        if self.events_since_cancel_poll >= CANCEL_POLL_EVERY_EVENTS:
            self.events_since_cancel_poll = 0
            if await self.redis.exists(cancel_key(self.run_id)):
                self.cancel_requested = True
                raise asyncio.CancelledError


class CompanionDriver(Protocol):
    async def __call__(self, handle: CompanionRunHandle) -> None: ...


OnComplete = Callable[[CompanionRunHandle], Awaitable[None]]

#: Runs vivos EN ESTE PROCESO. Solo sirve para cancelar rápido y para el
#: reaper de arranque; nadie lee eventos de aquí.
_local_runs: dict[uuid.UUID, CompanionRunHandle] = {}


def local_handle(run_id: uuid.UUID) -> CompanionRunHandle | None:
    return _local_runs.get(run_id)


async def start_run(
    *,
    redis: Redis,
    run_id: uuid.UUID,
    thread_id: uuid.UUID,
    principal_id: str,
    driver: CompanionDriver,
    on_complete: OnComplete | None = None,
) -> CompanionRunHandle:
    """Registra el run y lanza el driver. Devuelve enseguida: el POST
    responde 202 y el trabajo sigue pase lo que pase con la conexión."""
    loop = asyncio.get_running_loop()
    placeholder: asyncio.Task[None] = loop.create_task(asyncio.sleep(0))
    handle = CompanionRunHandle(
        run_id=run_id,
        thread_id=thread_id,
        principal_id=principal_id,
        redis=redis,
        task=placeholder,
    )
    _local_runs[run_id] = handle
    handle.task = loop.create_task(
        _run_with_lifecycle(handle, driver, on_complete),
        name=f"companion-run-{run_id}",
    )
    return handle


#: Turnos que corren A LA VEZ en este proceso, sea de quien sea. El semáforo
#: se crea perezosamente porque tiene que atarse al event loop que ya está
#: corriendo: construirlo al importar lo ataría al de importación, que en los
#: tests no es el mismo.
_process_semaphore: asyncio.Semaphore | None = None


class CompanionBusy(RuntimeError):
    """No hubo hueco en el proceso dentro del plazo."""


@contextlib.asynccontextmanager
async def _process_slot() -> AsyncGenerator[None]:
    """Un hueco de ejecución, con plazo.

    Si no lo hay dentro de ``companion_queue_timeout_s`` se lanza
    :class:`CompanionBusy` y el turno cierra con un error que dice qué pasó.
    Esperar sin plazo sería peor: el cajón se queda quieto sin explicación y
    el reaper acaba matando el run igual cuando cumple su techo de duración,
    con lo que la persona habría esperado para nada.
    """
    global _process_semaphore
    settings = get_settings()
    limit = settings.companion_max_process_runs
    if limit <= 0:  # pragma: no cover - configuración de emergencia
        yield
        return
    if _process_semaphore is None or _process_semaphore._value > limit:
        _process_semaphore = asyncio.Semaphore(limit)
    sem = _process_semaphore
    try:
        await asyncio.wait_for(sem.acquire(), timeout=settings.companion_queue_timeout_s)
    except TimeoutError:
        log.warning("companion.process_slot_timeout", limit=limit)
        raise CompanionBusy(
            "El Companion está atendiendo demasiados turnos a la vez. "
            "Vuelve a intentarlo en unos segundos."
        ) from None
    try:
        yield
    finally:
        sem.release()


def reset_process_semaphore_for_tests() -> None:
    """Suelta el semáforo entre tests: cada uno trae su propio event loop y
    un semáforo atado al anterior bloquearía para siempre."""
    global _process_semaphore
    _process_semaphore = None


async def _run_with_lifecycle(
    handle: CompanionRunHandle,
    driver: CompanionDriver,
    on_complete: OnComplete | None,
) -> None:
    """Abre con ``run.started``, corre el driver y cierra con
    ``run.completed``. El evento terminal es lo que hace que un lector sepa
    que puede irse; sin él, cada cajón abierto se queda colgado.

    La **única** vez que no se cierra es cuando el grafo se paró en un
    ``interrupt()`` esperando a una persona (CO-04): ese turno no ha
    terminado, solo está quieto. Ver el ``finally``.
    """
    await handle.emit(
        "run.started",
        {
            "run_id": str(handle.run_id),
            "thread_id": str(handle.thread_id),
            "started_at": time.time(),
        },
    )

    status = RUN_COMPLETED
    error: str | None = None
    try:
        # Freno de proceso. El tope de tres turnos por miembro no acota nada
        # global: con N personas trabajando son 3·N tareas en ESTE proceso,
        # cada una con hasta 25 llamadas de herramienta que abren su propia
        # transacción. El pool son 10+20 conexiones por réplica y lo comparte
        # el webhook de WhatsApp — o sea, once personas a la vez bastan para
        # que el camino que gana el dinero espere por una conexión.
        #
        # Se adquiere DENTRO de la tarea y no antes del 202: el turno ya está
        # aceptado y con su fila escrita; lo que se serializa es el trabajo,
        # no la aceptación. Y con plazo, porque un run que espera indefinido
        # es un cajón parado sin explicación — y el reaper lo mataría igual
        # al cumplir su techo de duración.
        async with _process_slot():
            await driver(handle)
    except asyncio.CancelledError:
        status = RUN_CANCELLED
        # No se re-lanza: queremos que el ``finally`` escriba el evento
        # terminal y cierre la fila antes de que la tarea se dé por
        # cancelada. La intención ya la registró ``cancel()``.
    except Exception as exc:
        status = RUN_ERROR
        error = str(exc)
        log.exception("companion.run_failed", run_id=str(handle.run_id))
    finally:
        handle.final_status = status
        handle.final_error = error
        # **La única excepción al "cierra SIEMPRE".** Si el grafo se detuvo en
        # un ``interrupt()``, la tarea termina pero el TURNO no: hay una
        # persona mirando una tarjeta de confirmación. Publicar aquí
        # ``run.completed`` cerraría su stream y le diría que el trabajo
        # acabó, que es justo lo contrario de lo que pasa.
        #
        # El evento terminal lo escribe el ``resume``, en la otra punta de la
        # espera. Si nadie decide, la acción caduca a los quince minutos, el
        # run deja de estar aparcado y el reaper lo cierra solo — se cura sin
        # cron y sin dejar la fila abierta para siempre.
        #
        # ``on_complete`` sí corre: aparca la fila con los tokens y la
        # respuesta parcial, para que el gasto de este turno cuente contra el
        # tope aunque la confirmación no llegue nunca.
        # CO-08 §6.3: un turno cortado por el tope mensual SÍ cierra, y
        # cierra con ``status="paused"``. Manda sobre el aparcado: si el
        # trabajo se paró de verdad, no está esperando a una persona.
        if handle.extras.get("budget_paused") and status == RUN_COMPLETED:
            status = RUN_PAUSED
            handle.final_status = status
        parked = (
            bool(handle.extras.get("awaiting_action"))
            and status == RUN_COMPLETED
            and not handle.extras.get("budget_paused")
        )
        if not parked:
            with contextlib.suppress(Exception):
                await publish(
                    handle.redis,
                    handle.run_id,
                    seq=handle.seq + 1,
                    event="run.completed",
                    data={
                        "run_id": str(handle.run_id),
                        "ended_at": time.time(),
                        "status": status,
                        # Veredicto de R1. Va en el evento terminal porque
                        # este se emite SIEMPRE — también si el turno falló—,
                        # así que la métrica no tiene agujeros.
                        "unsupported": bool(handle.extras.get("unsupported")),
                        **({"error": error} if error else {}),
                    },
                )
                handle.seq += 1
            # Los contadores del turno (§11 de CONTRACT-V2) van justo aquí y
            # no en el driver: este bloque se ejecuta SIEMPRE —también si el
            # turno falló—, así que la razón no tiene agujeros. Un run
            # aparcado no cuenta: su turno todavía no ha terminado, y
            # contarlo dos veces (aquí y al reanudar) inflaría el
            # denominador de R1.
            record_companion("companion.turn.total")
            if handle.extras.get("unsupported"):
                record_companion("companion.turn.unsupported")
        if on_complete is not None:
            try:
                await on_complete(handle)
            except Exception:
                log.exception("companion.on_complete_failed", run_id=str(handle.run_id))
        _local_runs.pop(handle.run_id, None)
        with contextlib.suppress(Exception):
            await handle.redis.delete(cancel_key(handle.run_id))


async def cancel(redis: Redis, run_id: uuid.UUID) -> bool:
    """Pide parar. Levanta la bandera **y**, si el run corre aquí, cancela
    la tarea de inmediato.

    La bandera es lo que hace correcta la cancelación con varias réplicas:
    el ``DELETE`` puede caer en una máquina que no ejecuta ese run. Cerrar
    el ``fetch`` del navegador no llega aquí y por tanto no cancela nada —
    el botón *Detener* del cajón tiene que llamar a este endpoint.
    """
    await redis.set(cancel_key(run_id), "1", ex=RUN_LOG_TTL_SECONDS)
    handle = _local_runs.get(run_id)
    if handle is None:
        return False
    handle.cancel_requested = True
    handle.task.cancel()
    return True


async def append_terminal_event(
    redis: Redis, run_id: uuid.UUID, *, status: str, error: str | None = None
) -> None:
    """Cierra el log de un run que quedó huérfano (reinicio de la API).

    El ``seq`` sale de la última entrada del log, no de cero: un lector
    reconectado con ``since_seq`` tiene que ver este evento como el
    siguiente y no como un duplicado del principio.
    """
    raw = _entries(await redis.xrange(run_key(run_id), "-", "+"))
    last_seq = int(raw[-1][1].get("seq") or 0) if raw else 0
    await publish(
        redis,
        run_id,
        seq=last_seq + 1,
        event="run.completed",
        data={
            "run_id": str(run_id),
            "ended_at": time.time(),
            "status": status,
            **({"error": error} if error else {}),
        },
    )


__all__ = [
    "COMPANION_AUTHORED_EVENTS",
    "COMPANION_EVENTS",
    "RUN_LOG_MAXLEN",
    "RUN_LOG_TTL_SECONDS",
    "CompanionDriver",
    "CompanionRunHandle",
    "UnknownCompanionEvent",
    "append_terminal_event",
    "cancel",
    "cancel_key",
    "local_handle",
    "publish",
    "read_events",
    "run_key",
    "sanitise_payload",
    "start_run",
    "subscribe",
]
