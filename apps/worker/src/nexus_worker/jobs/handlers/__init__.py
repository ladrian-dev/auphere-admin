"""Los manejadores de los trabajos largos, uno por ``kind`` (spec 047).

Importar este paquete los registra en ``default_registry``, que es el que usa
``jobs-consumer``; ``nexus_worker.jobs`` lo importa al final de su
``__init__``. Un tipo nuevo es un módulo nuevo aquí y su línea de import.

- ``client_read``: la lectura de la web y de las redes de un cliente (T049).
- ``agent_draft``: «Generar borrador», el constructor de agentes (T079).
- ``tests``: la suite de un agente, tres pasadas por prueba (T086).
- ``publish``: «Guardar», la puerta y la publicación (T093).
- ``client_builder``: «Completar con el constructor», la ficha propuesta (T098).
"""

from __future__ import annotations

from nexus_worker.jobs.handlers import (
    agent_draft,
    agent_publish,
    agent_tests,
    client_builder,
    client_read,
)

__all__ = [
    "agent_draft",
    "agent_publish",
    "agent_tests",
    "client_builder",
    "client_read",
]
