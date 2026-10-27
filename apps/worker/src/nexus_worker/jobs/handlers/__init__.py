"""Los manejadores de los trabajos largos, uno por ``kind`` (spec 047).

Importar este paquete los registra en ``default_registry``, que es el que usa
``jobs-consumer``; ``nexus_worker.jobs`` lo importa al final de su
``__init__``. Un tipo nuevo es un módulo nuevo aquí y su línea de import.

- ``client_read``: la lectura de la web y de las redes de un cliente (T049).
"""

from __future__ import annotations

from nexus_worker.jobs.handlers import client_read

__all__ = ["client_read"]
