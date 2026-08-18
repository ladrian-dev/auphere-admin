"""Estado del grafo del Companion (CO-01).

Deliberadamente plano y serializable: lo escribe el checkpointer de
Postgres en cada frontera de nodo, y un estado con objetos vivos dentro no
se puede reanudar en otro proceso — que es justo lo que hay que poder
hacer cuando la API se reinicia a mitad de run.
"""

from __future__ import annotations

from typing import Any, TypedDict

# ── fases del proceso (§7 de la investigación) ─────────────────────────
#
# El modelo elige el CONTENIDO de cada fase; que la fase ocurra lo decide
# el grafo. CO-01 cablea las tres primeras; el resto llega con CO-04.
PHASE_UNDERSTAND = "understand"
PHASE_INVESTIGATE = "investigate"
PHASE_RESPOND = "respond"
PHASE_AWAITING = "awaiting"
PHASE_DONE = "done"

#: Etiqueta humana de cada fase. Vive aquí y no en el frontend porque es
#: parte del protocolo de eventos: el cajón pinta lo que le llega.
PHASE_LABELS: dict[str, str] = {
    PHASE_UNDERSTAND: "Entendiendo",
    PHASE_INVESTIGATE: "Investigando",
    PHASE_RESPOND: "Respondiendo",
    PHASE_AWAITING: "Esperándote",
    PHASE_DONE: "Listo",
}


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
    total_input_tokens: int
    total_output_tokens: int

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


__all__ = [
    "PHASE_AWAITING",
    "PHASE_DONE",
    "PHASE_INVESTIGATE",
    "PHASE_LABELS",
    "PHASE_RESPOND",
    "PHASE_UNDERSTAND",
    "CompanionState",
]
