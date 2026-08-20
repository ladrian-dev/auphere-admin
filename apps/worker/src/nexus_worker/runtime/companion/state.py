"""Estado del grafo del Companion (CO-01).

Deliberadamente plano y serializable: lo escribe el checkpointer de
Postgres en cada frontera de nodo, y un estado con objetos vivos dentro no
se puede reanudar en otro proceso — que es justo lo que hay que poder
hacer cuando la API se reinicia a mitad de run.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypedDict

# ── fases del proceso (§7 de la investigación) ─────────────────────────
#
# El modelo elige el CONTENIDO de cada fase; que la fase ocurra lo decide
# el grafo. CO-01 cablea las tres primeras; el resto llega con CO-04.
PHASE_UNDERSTAND = "understand"
PHASE_INVESTIGATE = "investigate"
#: CO-04. Las cuatro que faltaban del §2.8 del contrato. ``intake`` se declara
#: aunque el expediente completo sea CO-06: la fase existe en cuanto se emite
#: ``intake.missing``, y el enum tiene que estar cerrado desde el principio o
#: la interfaz acaba con una tabla distinta a la del backend.
PHASE_INTAKE = "intake"
PHASE_PLAN = "plan"
PHASE_EXECUTE = "execute"
PHASE_VERIFY = "verify"
#: CO-06 (§2 del contrato v2). El paso 8 del §7: el trabajo desemboca en una
#: publicación, la verificación del paso 7 salió verde y el Companion prepara
#: la **segunda confirmación** con el diff contra la versión activa delante
#: (R5). **No** es "aplicar un ``kind: publish``" — eso pasa en ``execute``,
#: como cualquier otra escritura.
PHASE_PUBLISH = "publish"
PHASE_RESPOND = "respond"
PHASE_AWAITING = "awaiting"
PHASE_DONE = "done"

#: Etiqueta humana de cada fase.
#:
#: Está en español y no pasa por i18n, y eso es deliberado: **la interfaz no
#: pinta ``label``**, pinta ``phase`` traducido por su propia línea. Esto
#: sobrevive por compatibilidad con CO-01 y porque es lo que hace legibles
#: los logs de un turno sin tener que abrir el frontend.
PHASE_LABELS: dict[str, str] = {
    PHASE_UNDERSTAND: "Entendiendo",
    PHASE_INVESTIGATE: "Investigando",
    PHASE_INTAKE: "Preguntando",
    PHASE_PLAN: "Planificando",
    PHASE_AWAITING: "Esperándote",
    PHASE_EXECUTE: "Ejecutando",
    PHASE_VERIFY: "Verificando",
    PHASE_PUBLISH: "Publicando",
    PHASE_RESPOND: "Respondiendo",
    PHASE_DONE: "Listo",
}

#: El enum cerrado del §2 del contrato v2, **en orden**. Y el orden no es
#: decorativo: es el del §7 de la investigación, y es lo que convierte E2
#: ("las fases no saltan hacia atrás") en una comparación de enteros en vez
#: de en una lista de transiciones que alguien tiene que mantener a mano.
PHASE_ORDER: tuple[str, ...] = (
    PHASE_UNDERSTAND,
    PHASE_INVESTIGATE,
    PHASE_INTAKE,
    PHASE_PLAN,
    PHASE_AWAITING,
    PHASE_EXECUTE,
    PHASE_VERIFY,
    PHASE_PUBLISH,
    PHASE_RESPOND,
    PHASE_DONE,
)

#: **El rango es POR RUN, nunca por hilo.** Es la frase que deshace la
#: contradicción aparente del §2 del contrato v2 (§19.5): ``publish`` va
#: después de ``verify`` y antes de ``respond`` dentro del run que ejecuta el
#: cambio —ahí el Companion *anuncia* que esto desemboca en una publicación y
#: la ofrece—, y la publicación se propone en el **run siguiente**, que
#: arranca limpio en ``understand`` y llega a ``awaiting`` por su propio
#: camino. Es PLAN-CO-04 D3: una acción por run, y un segundo paso es un turno
#: nuevo. Si alguien vuelve a leer el rango como si fuera del hilo, concluirá
#: que ``publish → awaiting`` es un salto hacia atrás y deshará esto.
PHASE_RANK: dict[str, int] = {phase: i for i, phase in enumerate(PHASE_ORDER)}


class PhaseViolation(RuntimeError):
    """Una transición que el proceso del §7 no admite.

    Se lanza, no se registra. Es un error de programación —el grafo no
    tiene ningún camino que la produzca— y lo que protege es demasiado
    caro para avisar y seguir: la única transición ilegal declarada es
    entrar en ``execute`` sin haber pasado por ``awaiting``, que es
    escribir sin haber preguntado.
    """


#: Fases a las que solo se puede entrar desde una fase concreta.
#:
#: Es la regla R3 ("toda escritura pasa por propose → interrupt → apply")
#: dicha en el motor. Hoy es inalcanzable por construcción del grafo, y esa
#: es la razón de tenerla: un reordenado futuro de nodos que se saltara la
#: confirmación rompería el turno en vez de escribir sin preguntar. La
#: barrera de verdad (C4: la acción tiene que estar ``confirmed``) sigue
#: donde estaba.
PHASE_ENTRY_REQUIRES: dict[str, str] = {PHASE_EXECUTE: PHASE_AWAITING}


class PhaseTracker:
    """Quien decide que la fase **ocurra** (§7).

    Uno por run, construido con la fase que traiga el estado. Tres reglas,
    y las tres son mecanismo y no disciplina:

    - **hacia atrás no se emite.** Un nodo puede pedir una fase anterior
      —el bucle de herramientas lo hacía— y el tracker la ignora. Es la
      garantía E2;
    - **repetida no se emite**, para que la píldora del cajón no parpadee;
    - **``execute`` exige venir de ``awaiting``**, o lanza.

    No conoce el protocolo: recibe la función que emite. Así se prueba sin
    LangChain delante.
    """

    def __init__(
        self,
        emit: Callable[[str, dict[str, Any]], Awaitable[None]],
        *,
        current: str | None = None,
    ) -> None:
        self._emit = emit
        self._current = current if current in PHASE_RANK else None

    @property
    def current(self) -> str | None:
        return self._current

    def would_advance(self, phase: str) -> bool:
        """¿Emitir esta fase sería avanzar? Sin efectos."""
        if phase not in PHASE_RANK:
            return False
        if self._current is None:
            return True
        return PHASE_RANK[phase] > PHASE_RANK[self._current]

    async def enter(self, phase: str) -> bool:
        """Anuncia la fase si toca. Devuelve si la emitió."""
        if phase not in PHASE_RANK:
            raise PhaseViolation(f"fase desconocida: {phase!r}")
        required = PHASE_ENTRY_REQUIRES.get(phase)
        if required is not None and self._current != required:
            raise PhaseViolation(
                f"no se puede entrar en {phase!r} desde {self._current!r}: exige {required!r}"
            )
        if not self.would_advance(phase):
            return False
        self._current = phase
        await self._emit("phase.changed", {"phase": phase, "label": PHASE_LABELS[phase]})
        return True


class CompanionState(TypedDict, total=False):
    """Lo que viaja entre nodos.

    ``page_context`` es lo que el cajón sabe de dónde está el usuario
    (ruta, cliente, pestaña). **No se interpola en el prompt de sistema**:
    viaja como mensaje ``role: "system"`` a mitad de la conversación. El
    caché de Anthropic es un encaje de prefijo, así que un dato que cambia
    en cada turno metido al principio tira todo lo que viene detrás — y
    además, un texto dentro de un turno de usuario lo puede falsificar
    cualquiera que escriba en la entrada, mientras que un ``role: system``
    no (Parte II, C4).
    """

    thread_id: str
    # Rol, partner y permisos del principal. Es contexto para responder
    # ("no puedes publicar con tu rol"), NUNCA una fuente de autorización:
    # quien autoriza es el router ``/console/*`` que la herramienta llama.
    principal: dict[str, Any]
    page_context: dict[str, Any] | None
    # Turnos anteriores del hilo, en forma de mensajes de proveedor.
    history: list[dict[str, Any]]
    user_message: str
    mode: str

    phase: str
    answer: str
    model: str
    # ``input_tokens`` de la ÚLTIMA llamada — es el tamaño real de la
    # ventana consumida en ese momento, medido por el proveedor. Es lo que
    # alimenta el medidor de contexto; estimarlo por caracteres sería
    # mentira y se nota (§12.3).
    last_input_tokens: int
    #: Entrada **facturable** acumulada del turno: ``prompt_tokens`` menos lo
    #: que vino de caché. No es lo mismo que la ventana (ver arriba) y no
    #: debe usarse para medirla.
    total_input_tokens: int
    total_output_tokens: int
    # Desglose de caché del turno. Existe para poder valorar el turno en
    # dólares con las tarifas de ``model_profiles`` —donde la lectura de
    # caché cuesta una décima parte de la entrada— sin volver a llamar al
    # proveedor ni recomponerlo desde los logs.
    total_cache_read: int
    total_cache_write: int
    #: Pasadas del bucle de modelo consumidas en el turno. Es el numerador de
    #: "cuánto trabajo costó esto" y lo que delata un turno que se atasca
    #: alternando dos lecturas.
    total_steps: int

    # ── CO-02 ──────────────────────────────────────────────────────────
    # Mensajes acumulados del bucle de herramientas: el mensaje del
    # asistente de cada paso y los resultados de las herramientas. Se
    # guardan porque el checkpointer tiene que poder reanudar el turno a
    # mitad del bucle, no solo entre turnos.
    tool_messages: list[dict[str, Any]]
    # Llamadas ejecutadas y lecturas con éxito en ESTE turno. La segunda es
    # el numerador de la regla R1 (sin lectura no hay afirmación).
    tool_calls_made: int
    reads_done: int
    # Veredicto de R1, calculado por el motor al cerrar el turno. Viaja al
    # cajón dentro de ``run.completed``.
    unsupported: bool

    # ── CO-04 ──────────────────────────────────────────────────────────
    # La acción puesta en ``proposed`` por el nodo ``plan``, si la hubo. Va
    # en el estado —y no solo en la base— porque el checkpointer tiene que
    # poder reanudar el turno en otro proceso: la tarea que emitió el
    # ``hitl.requested`` puede llevar quince minutos muerta cuando llegue la
    # confirmación.
    action_id: str
    action_kind: str
    # Lo que devolvió el ``interrupt()``: ``{decision, note, by, at}``. La
    # decisión la escribe la API en la fila ANTES de reanudar; esto es lo que
    # el modelo necesita ver para reaccionar al motivo de un rechazo.
    hitl: dict[str, Any]
    # Resultado de la verificación determinista. El nodo ``respond`` lo lee
    # para no afirmar que algo quedó hecho cuando la relectura dice que no.
    verify: dict[str, Any]

    # ── CO-06 ──────────────────────────────────────────────────────────
    # **El expediente es del HILO, no del run** (§3.4 del contrato v2).
    #
    # No hay tabla nueva ni endpoint: el checkpointer está indexado por
    # ``thread_id`` (``config.configurable.thread_id`` en el driver), así que
    # una clave del estado sobrevive entre turnos y la sirve igual otro
    # proceso. Que es exactamente lo que pide la regla del §3.4: un slot
    # respondido no se vuelve a preguntar.
    #
    # ``{"answers": {work_kind: {key: valor}}, "asked": {work_kind: [key]},
    #   "facts": {…}}``. Los valores salen de los argumentos con los que el
    # modelo llamó a ``console.propose_*``, nunca de interpretar la prosa de
    # la persona: adivinar un slot es el fallo que el §7.1 existe para evitar.
    intake: dict[str, Any]
    # Cómo fue la aplicación de la acción confirmada. R4 pide decir
    # exactamente qué quedó aplicado, y para decirlo hay que saberlo: sin
    # esto, el nodo de cierre solo veía "no hay verificación" y tenía que
    # deducir el resto.
    execute: dict[str, Any]


#: Canales que son del RUN y no del hilo. El nodo ``understand`` los borra al
#: arrancar un turno nuevo.
#:
#: Existe porque el checkpoint es del hilo: sin esta limpieza, el ``hitl`` de
#: una confirmación anterior sigue en el estado y el turno siguiente responde
#: dos veces —una por el bucle y otra informando de una acción que ya se
#: contó—. Medido, no supuesto. ``understand`` no corre en un ``resume``, así
#: que el run de continuación no se ve afectado.
RUN_SCOPED_DEFAULTS: dict[str, Any] = {
    "hitl": {},
    "verify": {},
    "execute": {},
    "action_id": "",
    "action_kind": "",
    "tool_messages": [],
    "answer": "",
    "unsupported": False,
}


__all__ = [
    "PHASE_AWAITING",
    "PHASE_DONE",
    "PHASE_ENTRY_REQUIRES",
    "PHASE_EXECUTE",
    "PHASE_INTAKE",
    "PHASE_INVESTIGATE",
    "PHASE_LABELS",
    "PHASE_ORDER",
    "PHASE_PLAN",
    "PHASE_PUBLISH",
    "PHASE_RANK",
    "PHASE_RESPOND",
    "PHASE_UNDERSTAND",
    "PHASE_VERIFY",
    "RUN_SCOPED_DEFAULTS",
    "CompanionState",
    "PhaseTracker",
    "PhaseViolation",
]
