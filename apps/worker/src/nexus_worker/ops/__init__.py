"""Herramientas de operador: órdenes sueltas, no servicios.

Se lanzan con ``python -m nexus_worker.ops.<herramienta>`` en una tarea de ECS. No
importan ``nexus_worker.streams``, cuyo ``__init__`` carga el consumidor y con él
todo el grafo.
"""
