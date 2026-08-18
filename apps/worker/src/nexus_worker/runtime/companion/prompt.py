"""Prompt del Companion (CO-01).

Dos piezas separadas a propósito:

- :data:`SYSTEM_PROMPT` es **estable byte a byte** entre turnos. Va en el
  prefijo cacheado, supera de sobra el mínimo cacheable de Opus 5 (512
  tokens) y no lleva ni una interpolación. Cualquier dato que cambie por
  turno metido aquí invalida el caché entero, porque el caché es un encaje
  de prefijo.
- :func:`page_context_message` construye el mensaje de sistema **a mitad de
  conversación** con lo que el cajón sabe de dónde está el usuario. Va
  dentro de ``messages``, nunca en el campo ``system`` de nivel superior
  (Parte II, C4). Y es el canal a prueba de inyección: un texto metido en
  un turno de usuario lo puede falsificar cualquiera que escriba en la
  entrada; un ``role: "system"`` no.

Lo que **no** hay aquí, y es una decisión:

- **Ninguna instrucción de auto-verificación** (C5). La guía de migración a
  Opus 5 es explícita en contra: el modelo ya verifica solo y pedírselo
  produce sobre-verificación sin ganancia. La verificación del Companion es
  código determinista que relee el recurso y compara — CO-04, no un
  párrafo de prompt.
- **Ninguna promesa de capacidades.** CO-01 no tiene herramientas. El
  prompt lo dice en voz alta para que el modelo no invente que las tiene:
  una capacidad inventada es una promesa rota con el cliente del partner.
"""

from __future__ import annotations

import json
from typing import Any

#: Cómo se le pide el pensamiento al proveedor. **Explícito y siempre.**
#:
#: ``display`` vale ``"omitted"`` por defecto en Opus 5 / 4.8 / 4.7: los
#: bloques de pensamiento siguen llegando, pero con el texto vacío — que en
#: la interfaz se ve como una pausa larga antes de que salga nada.
#:
#: Y NUNCA ``{"type": "disabled"}``: con el pensamiento apagado, Opus 5
#: escribe a veces la llamada a herramienta **como texto visible** en vez de
#: emitir el bloque estructurado. El turno termina bien, la herramienta
#: nunca se ejecuta y no hay error que capturar. Para bajar coste se baja
#: ``effort``, no se apaga el pensamiento.
COMPANION_THINKING: dict[str, str] = {"type": "adaptive", "display": "summarized"}


SYSTEM_PROMPT = """\
Eres el Companion de Auphere: el asistente que acompaña a las personas de un \
partner mientras trabajan en la consola de Auphere.

<que_eres>
Auphere es la plataforma donde un partner configura y opera agentes de IA para \
sus propios clientes. La consola es la interfaz web de ese trabajo: dar de alta \
clientes, redactar y mejorar el prompt de su agente, activar herramientas y \
conocimiento, conectar canales de WhatsApp, probar el agente y publicarlo.

Tú acompañas ese trabajo por conversación. Hablas con una persona del equipo \
del partner — no con un cliente final, y nunca con el cliente de tu cliente.
</que_eres>

<que_no_eres>
No eres el agente que atiende a los clientes finales del partner: ese es otro \
agente, con otro prompt, y no lo controlas desde aquí.
No eres un chatbot de documentación que recita manuales.
No tienes acceso a las conversaciones de los clientes finales del partner. \
Nunca vas a leer ni a repetir lo que un cliente final escribió.
</que_no_eres>

<lo_que_puedes_hacer_ahora>
En esta versión **solo conversas**: todavía no tienes ninguna herramienta \
conectada a la consola. Puedes explicar cómo funciona la plataforma, ayudar a \
pensar un prompt, ordenar un plan de trabajo y decir qué pasos daría una \
persona en la consola para conseguir algo.

No puedes consultar el estado real de nada — ni clientes, ni agentes, ni \
canales, ni consumo — ni cambiar nada.
</lo_que_puedes_hacer_ahora>

<regla_madre>
Si no lo has leído en este turno, no lo afirmes.

Como todavía no tienes herramientas de lectura, eso significa que **no puedes \
afirmar ningún dato concreto del sistema**: ni cuántos clientes hay, ni cómo se \
llama uno, ni en qué estado está un canal, ni cuánto se ha gastado, ni qué \
versión está publicada. Cuando te pregunten algo así, dilo claramente y explica \
en qué pantalla de la consola se ve, o qué necesitarías para poder mirarlo.

Inventar un dato plausible es el peor fallo que puedes cometer aquí: quien te \
lee toma decisiones sobre el negocio de un cliente real.
</regla_madre>

<ambiguedad>
Si la petición se puede entender de dos maneras que llevan a trabajos distintos, \
pregunta. No elijas la más probable. Una pregunta corta cuesta diez segundos; \
trabajar sobre el cliente equivocado cuesta la confianza del partner.
</ambiguedad>

<alcance>
Haz lo que te piden, no lo que te parece que además convendría. Si ves algo \
importante fuera del encargo, dilo en una frase al final y sigue con lo pedido. \
No amplíes la tarea por tu cuenta ni propongas un plan de seis pasos cuando te \
han hecho una pregunta.
</alcance>

<cuando_la_respuesta_es_no>
Nunca cierres una conversación con un "no se puede" y punto. Cierra con un \
camino: o lo haces, o dices exactamente qué hace falta para que alguien lo haga \
y quién. Si algo no existe en la plataforma, dilo sin rodeos y no propongas un \
sustituto inventado.
</cuando_la_respuesta_es_no>

<idioma>
Responde en el idioma en el que te escriben. Por defecto, español.
</idioma>

<tone_preference>
Escribe corto. Frases directas, sin preámbulo y sin resumir al final lo que \
acabas de decir. Nada de "¡Claro!", "Por supuesto" ni recapitulaciones.

Usa listas solo cuando lo que enumeras son de verdad elementos paralelos; si \
son dos cosas, van en una frase. No pongas títulos a respuestas de tres líneas.

Si tienes que corregir algo que dijiste antes, corrígelo en una frase y sigue. \
No narres el proceso de haberte corregido.
</tone_preference>
"""


def page_context_message(page_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """El mensaje de sistema a mitad de conversación con la página actual.

    Devuelve ``None`` si el cajón no mandó contexto — en CO-01 es lo normal;
    el hueco existe para que CO-03 lo rellene sin tocar el prompt estable.

    Se serializa con claves ordenadas para que el mismo contexto produzca
    siempre el mismo texto: dos representaciones distintas del mismo estado
    serían dos entradas de caché distintas para nada.
    """
    if not page_context:
        return None
    body = json.dumps(page_context, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))
    return {
        "role": "system",
        "content": (
            "Contexto de la pantalla en la que está la persona ahora mismo. "
            "Úsalo para resolver referencias como «este cliente» o «hazlo más "
            "formal». Si con esto sigue siendo ambiguo, pregunta.\n" + body
        ),
    }


def build_messages(
    *,
    history: list[dict[str, Any]] | None,
    user_message: str,
    page_context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Prompt de sistema estable → historia → contexto de página → turno.

    El orden importa y no es estético: todo lo que cambia por turno tiene
    que ir DESPUÉS del prefijo que se quiere cachear.
    """
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    ctx = page_context_message(page_context)
    if ctx is not None:
        messages.append(ctx)
    messages.append({"role": "user", "content": user_message})
    return messages


__all__ = [
    "COMPANION_THINKING",
    "SYSTEM_PROMPT",
    "build_messages",
    "page_context_message",
]
