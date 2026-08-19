"""El expediente — pedirle a la persona lo que solo ella sabe (CO-06, §7.1).

Cada tipo de trabajo declara sus campos obligatorios. El Companion **no
avanza a planificar con campos vacíos**: emite ``intake.missing`` y el
turno termina preguntando.

Tres decisiones que están aquí y no en el prompt, porque en el prompt son
una sugerencia:

1. **El catálogo es cerrado** (§3.3 del contrato v2). Los ``key`` son
   estables; el ``label`` y el ``why`` son la caída por defecto cuando la
   interfaz no tiene copy propio.
2. **El expediente es del hilo.** Vive en ``CompanionState["intake"]``, que
   el checkpointer indexa por ``thread_id``: un dato dado en el turno 1 no
   se vuelve a pedir en el turno 3, aunque el turno 3 lo sirva otro
   proceso. No hay tabla nueva y no hay endpoint (§3.4).
3. **Los deducibles no se preguntan nunca.** Plantilla, prompt inicial,
   herramientas del vertical, el resto del Embedded Signup, el resto del
   diff, la configuración del conector: no están en el catálogo, así que no
   hay forma de preguntarlos. Preguntar un deducible es ruido y erosiona la
   disposición de la persona a contestar lo que sí importa.

Y una que cuesta explicar pero que evita un atasco de los caros — ver
:func:`is_enforceable`.
"""

from __future__ import annotations

from typing import Any

# ── los cinco trabajos (§3.2 del contrato v2) ──────────────────────────

WORK_CREATE_CLIENT = "create_client"
WORK_CONNECT_WHATSAPP = "connect_whatsapp"
WORK_CHANGE_PROMPT = "change_prompt"
WORK_ENABLE_CONNECTOR = "enable_connector"
WORK_PUBLISH = "publish"

#: Enum cerrado. Un tipo de trabajo que no esté aquí **no emite
#: ``intake.missing``**: pasa directo a planificar. Añadir uno es cambio de
#: contrato.
WORK_KINDS: tuple[str, ...] = (
    WORK_CREATE_CLIENT,
    WORK_CONNECT_WHATSAPP,
    WORK_CHANGE_PROMPT,
    WORK_ENABLE_CONNECTOR,
    WORK_PUBLISH,
)

#: ``ActionKind`` (la columna del §3.1 de la v1.1) → tipo de trabajo.
#:
#: ``connect_whatsapp`` no aparece: **no hay ninguna herramienta que proponga
#: conectar WhatsApp** — el alta va por el Embedded Signup, no por una
#: ``propose_*``. Se declara igual en :data:`SLOT_CATALOG` porque el contrato
#: lo declara, pero hoy es inalcanzable y está anotado en ``PLAN-CO-06.md``.
WORK_KIND_BY_ACTION: dict[str, str] = {
    "client": WORK_CREATE_CLIENT,
    "prompt": WORK_CHANGE_PROMPT,
    "tools": WORK_ENABLE_CONNECTOR,
    "publish": WORK_PUBLISH,
}

#: Herramienta que trae cada trabajo. Es de dónde salen los valores del
#: expediente y contra quién se mide la satisfacibilidad.
TOOL_BY_WORK_KIND: dict[str, str] = {
    WORK_CREATE_CLIENT: "console.propose_client",
    WORK_CHANGE_PROMPT: "console.propose_prompt",
    WORK_ENABLE_CONNECTOR: "console.propose_tools",
    WORK_PUBLISH: "console.propose_publish",
}


# ── el catálogo cerrado de slots (§3.3 del contrato v2) ────────────────


def _slot(
    key: str,
    label: str,
    why: str,
    examples: list[str],
    *,
    required_when: str | None = None,
) -> dict[str, Any]:
    """Un hueco del expediente, en la forma literal del §2.2 de la v1.1.

    ``examples`` es **siempre** lista, posiblemente vacía, nunca ``None``.
    ``required_when`` no sale por el evento: es del motor.
    """
    slot: dict[str, Any] = {
        "key": key,
        "label": label,
        "why": why,
        "examples": list(examples),
        "required": True,
    }
    if required_when is not None:
        slot["required_when"] = required_when
    return slot


#: Lo que hay que saber por tipo de trabajo, literal del §3.3.
#:
#: ``forbidden_behaviour`` es obligatorio **a propósito y no se puede
#: saltar**: es el campo que nadie escribe y el que causa los incidentes.
#: Preguntarlo siempre cuesta diez segundos; no preguntarlo cuesta una
#: conversación con el cliente final de un cliente. Es la garantía E1.
SLOT_CATALOG: dict[str, tuple[dict[str, Any], ...]] = {
    WORK_CREATE_CLIENT: (
        _slot(
            "name",
            "Nombre comercial del cliente",
            "Es como lo verá el equipo del partner en toda la consola.",
            ["Clínica Boreal", "Barbería Cultor"],
        ),
        _slot(
            "vertical",
            "A qué se dedica el cliente",
            "Decide la plantilla de arranque y las herramientas que tienen sentido.",
            ["Clínica estética", "Barbería", "Inmobiliaria"],
        ),
        _slot(
            "timezone",
            "Zona horaria del cliente",
            "Sin ella el horario de atención se calcula mal y el agente responde a deshora.",
            ["America/Caracas", "Europe/Madrid"],
        ),
        _slot(
            "language",
            "Idioma principal de atención",
            "Es en el que hablará con los clientes finales por defecto.",
            ["es", "en", "pt"],
        ),
        _slot(
            "forbidden_behaviour",
            "Qué NO debe hacer el agente",
            "Es el campo que nadie escribe y el que causa los incidentes.",
            ["No dar precios por WhatsApp", "No agendar sin seña"],
        ),
    ),
    WORK_CONNECT_WHATSAPP: (
        _slot(
            "phone_number",
            "Número de WhatsApp que se va a conectar",
            "Es el número que verán los clientes finales; equivocarlo se nota fuera.",
            ["+58 412 000 0000"],
        ),
        _slot(
            "number_owner",
            "De quién es el número",
            "Un número prestado o compartido bloquea el alta a mitad del proceso.",
            ["Del cliente", "Del partner"],
        ),
        _slot(
            "channel_role",
            "Para qué es este canal",
            (
                "Con más de un canal activo y ningún rol asignado, el envío se "
                "rechaza. Etiquetar tiene que ocurrir ANTES de conectar el segundo "
                "número, no después."
            ),
            ["Agente", "Notificaciones"],
            # Condicional: solo si el cliente ya tiene otro canal activo.
            required_when="other_channel_active",
        ),
    ),
    WORK_CHANGE_PROMPT: (
        _slot(
            "failing_behaviour",
            "Qué comportamiento concreto falla",
            "Un prompt cambiado a ciegas rompe lo que funcionaba.",
            ["Da precios cuando le preguntan por el bótox"],
        ),
        _slot(
            "real_example",
            "Un ejemplo real de la conversación",
            "Sin el caso concreto, el cambio se hace sobre una suposición.",
            ["«¿cuánto cuesta?» → «son 120 $»"],
        ),
    ),
    WORK_ENABLE_CONNECTOR: (
        _slot(
            "connector_consent",
            "Consentimiento del cliente para conectar su cuenta",
            "El conector entra en datos del cliente: sin su OK, no se toca.",
            ["El cliente autorizó conectar su agenda"],
        ),
    ),
    WORK_PUBLISH: (
        _slot(
            "ai_disclosure_decision",
            "Decisión sobre la revelación de IA",
            "Es lo que verán los clientes finales al primer mensaje, y no se puede desactivar.",
            ["Se mantiene la revelación por defecto"],
        ),
    ),
}


# ── el expediente como estado del hilo (§3.4) ──────────────────────────


def empty_ledger() -> dict[str, Any]:
    return {"answers": {}, "asked": {}, "facts": {}}


def _answers(ledger: dict[str, Any], work_kind: str) -> dict[str, Any]:
    answers = ledger.get("answers")
    if not isinstance(answers, dict):
        return {}
    entry = answers.get(work_kind)
    return entry if isinstance(entry, dict) else {}


def slot_keys(work_kind: str) -> tuple[str, ...]:
    return tuple(s["key"] for s in SLOT_CATALOG.get(work_kind, ()))


def record_answers(
    ledger: dict[str, Any] | None, work_kind: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Guarda del expediente lo que el modelo acaba de entregar.

    Solo entran claves del catálogo cerrado y solo con valor no vacío: el
    expediente no es un búfer de la conversación, y un ``system_prompt``
    entero dentro de él sería contexto pagado dos veces.

    Devuelve un expediente **nuevo**: el estado del grafo se serializa en
    cada frontera de nodo y mutar el que ya está dentro es la forma barata
    de que un checkpoint no coincida con lo que se emitió.
    """
    keys = slot_keys(work_kind)
    if not keys:
        return dict(ledger) if ledger else empty_ledger()

    fresh = empty_ledger()
    if ledger:
        fresh = {
            "answers": {k: dict(v) for k, v in (ledger.get("answers") or {}).items()},
            "asked": {k: list(v) for k, v in (ledger.get("asked") or {}).items()},
            "facts": dict(ledger.get("facts") or {}),
        }
    given = {
        key: str(arguments.get(key)).strip()
        for key in keys
        if str(arguments.get(key) or "").strip()
    }
    if given:
        fresh["answers"].setdefault(work_kind, {}).update(given)
    return fresh


def record_asked(ledger: dict[str, Any] | None, work_kind: str, keys: list[str]) -> dict[str, Any]:
    """Anota qué se preguntó, para no repetir el mismo chip."""
    fresh = record_answers(ledger, work_kind, {})
    asked = fresh["asked"].setdefault(work_kind, [])
    for key in keys:
        if key not in asked:
            asked.append(key)
    return fresh


def missing_slots(ledger: dict[str, Any] | None, work_kind: str) -> list[dict[str, Any]]:
    """Los huecos que **siguen** faltando, según el expediente del hilo.

    Un slot condicional (``required_when``) solo cuenta si el hecho está
    puesto a ``True``. Sin el hecho no se pregunta: preguntar un condicional
    sin condición es preguntar un deducible, y el §3.3 lo prohíbe.
    """
    answers = _answers(ledger or {}, work_kind)
    facts = (ledger or {}).get("facts") or {}
    out: list[dict[str, Any]] = []
    for slot in SLOT_CATALOG.get(work_kind, ()):
        condition = slot.get("required_when")
        if condition is not None and not facts.get(condition):
            continue
        if str(answers.get(slot["key"]) or "").strip():
            continue
        out.append({k: v for k, v in slot.items() if k != "required_when"})
    return out


def ledger_note(ledger: dict[str, Any] | None) -> dict[str, Any] | None:
    """Lo que la persona ya contestó, al final de ``messages``.

    Mismo mecanismo que ``budget_note`` y por la misma razón: se **añade**,
    no reescribe nada y no toca el prompt de sistema, así que el prefijo
    cacheado sigue encajando.

    Sirve para el caso que si no se cae: el modelo vuelve a proponer en un
    turno posterior y manda solo el dato nuevo; sin esta nota la herramienta
    ve los otros vacíos y la persona tendría que repetirse. Dice
    explícitamente que son datos **que ella dio**, no material para deducir
    los que faltan.
    """
    answers = (ledger or {}).get("answers") or {}
    lines: list[str] = []
    for work_kind in WORK_KINDS:
        given = answers.get(work_kind)
        if not isinstance(given, dict) or not given:
            continue
        labels = {s["key"]: s["label"] for s in SLOT_CATALOG.get(work_kind, ())}
        for key, value in given.items():
            lines.append(f"- {labels.get(key, key)}: {value}")
    if not lines:
        return None
    return {
        "role": "system",
        "content": (
            "Datos que la persona YA te dio en esta conversación. Reutilízalos "
            "tal cual cuando vuelvas a proponer, en vez de volver a "
            "preguntárselos. No deduzcas de aquí los que sigan faltando.\n" + "\n".join(lines)
        ),
    }


# ── la puerta (garantía E1) ────────────────────────────────────────────


def is_enforceable(work_kind: str, specs: list[dict[str, Any]] | None) -> bool:
    """¿Se puede exigir el expediente de este trabajo sin atascarlo?

    La puerta del §3.2 bloquea el paso a ``plan`` mientras falte un
    obligatorio. Para que eso sea una puerta y no un atasco, la persona
    tiene que tener **por dónde entregar el dato**: cada ``key`` obligatoria
    tiene que ser un parámetro que la herramienta acepte.

    Hace falta de verdad. Hoy ``console.propose_prompt`` no acepta
    ``failing_behaviour`` ni ``real_example``, y ``console.propose_publish``
    no acepta ``ai_disclosure_decision``. Exigirlos bloquearía **para
    siempre** todo cambio de prompt y toda publicación, porque el modelo no
    tendría forma de entregarlos.

    Se calcula leyendo el catálogo que el grafo ya recibe, no con una lista
    escrita a mano: el día que esos parámetros existan, la puerta se
    enciende sola y sin tocar este archivo.
    """
    keys = slot_keys(work_kind)
    if not keys:
        return False
    tool = TOOL_BY_WORK_KIND.get(work_kind)
    if tool is None:
        return False
    params = _tool_params(specs, tool)
    if params is None:
        return False
    return all(key in params for key in keys)


def _tool_params(specs: list[dict[str, Any]] | None, tool: str) -> set[str] | None:
    for spec in specs or ():
        function = spec.get("function")
        if not isinstance(function, dict) or function.get("name") != tool:
            continue
        parameters = function.get("parameters")
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        return set(properties) if isinstance(properties, dict) else set()
    return None


def blocking_slots(
    ledger: dict[str, Any] | None,
    action_kind: str | None,
    specs: list[dict[str, Any]] | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """¿Esta propuesta puede pasar a ``plan``?

    Devuelve ``(work_kind, huecos)``. Con huecos no vacíos, el turno va a
    ``intake`` y el nodo ``plan`` **no corre**: no se persiste fila, no se
    emite ``hitl.requested`` y no hay nada que confirmar. Es la garantía E1,
    y falla en el motor — ninguna frase del prompt la puede saltar.
    """
    work_kind = WORK_KIND_BY_ACTION.get(str(action_kind or ""))
    if work_kind is None or not is_enforceable(work_kind, specs):
        return work_kind, []
    return work_kind, missing_slots(ledger, work_kind)


__all__ = [
    "SLOT_CATALOG",
    "TOOL_BY_WORK_KIND",
    "WORK_CHANGE_PROMPT",
    "WORK_CONNECT_WHATSAPP",
    "WORK_CREATE_CLIENT",
    "WORK_ENABLE_CONNECTOR",
    "WORK_KINDS",
    "WORK_KIND_BY_ACTION",
    "WORK_PUBLISH",
    "blocking_slots",
    "empty_ledger",
    "is_enforceable",
    "ledger_note",
    "missing_slots",
    "record_answers",
    "record_asked",
    "slot_keys",
]
