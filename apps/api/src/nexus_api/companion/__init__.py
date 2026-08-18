"""Piezas del Companion que viven en la API (CO-02).

El grafo vive en ``nexus_worker.runtime.companion`` y su superficie HTTP en
``nexus_api.api.console.companion``. Aquí está lo que el grafo no puede
tener sin dejar de ser agnóstico: las herramientas que llaman a los routers
``/console/*``.

Plan de construcción: ``docs/companion/PLAN-CO-02.md``.
"""
