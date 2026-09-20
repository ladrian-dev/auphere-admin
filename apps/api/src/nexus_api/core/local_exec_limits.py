"""Los techos del viaje de una ejecución local, en un solo sitio.

Vive en ``core/`` y no en ``services/`` por una razón concreta: las
herramientas del Companion **no pueden importar de ``services/``**
(``tests/isolation/test_companion_tools_imports.py``, garantía C2 — una
herramienta llama al router por HTTP en proceso, nunca al servicio). Y el
runner necesita este número tanto como el borde del puente.

Un número que hace falta a los dos lados de una frontera de capas no puede
vivir en ninguno de los dos: se copia, y las copias divergen. Aquí ya pasó —
la aplicación recortaba a 2.048 y el borde afirmaba 2.048 en tres tests
distintos, todos escritos a mano.
"""

from __future__ import annotations

#: Cuánto de la salida de un programa viaja de vuelta al modelo.
#:
#: **Tiene que ser el mismo número que ``OUTPUT_SAMPLE_LIMIT`` de
#: ``apps/desktop/src/executor.ts``**, que es quien recorta primero. Aquí se
#: vuelve a medir en el borde, porque el tope de quien envía no es una garantía.
#:
#: Era 2.048 y no cabía una traza de compilación: el agente recibía el banner de
#: la herramienta y nunca el error, así que ejecutaba a ciegas
#: (``.specify/bugs/el-teammate-no-alcanza-la-maquina/``). Sigue siendo muestra
#: **acotada, no transcripción**, y sigue **sin persistirse** (§III): la
#: auditoría dice qué pasó, nunca qué dijo el comando.
OUTPUT_SAMPLE_CHARS = 16_384

__all__ = ["OUTPUT_SAMPLE_CHARS"]
