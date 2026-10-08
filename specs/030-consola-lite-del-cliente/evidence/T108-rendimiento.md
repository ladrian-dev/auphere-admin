# T108 — Rendimiento de la Bandeja y del Panel lite

**Fecha:** 2026-10-08 · **Rama:** `030-consola-lite-del-cliente` (sobre `6c7b9857`)
**Prueba:** `apps/api/tests/integration/test_lite_performance.py` (marca `slow`;
corre en la suite normal y en la tubería).

## Cómo se midió

- Un cliente con **5.000 conversaciones** y **10.000 mensajes** (una de cada
  diez esperando a una persona), sembrados con inserciones masivas y `ANALYZE`.
- La API real dentro del proceso (`httpx` sobre ASGI) contra el Postgres 16 de
  pruebas en Docker, en el portátil de desarrollo. Sin red ni navegador.
- Una llamada de calentamiento y 20 medidas por caso; p95 con
  `statistics.quantiles(n=20)`.

## Resultado

| Caso | p50 | p95 | Límite |
|---|---|---|---|
| Bandeja, primera página | 23 ms | 165 ms | 1,5 s (CE-007) |
| Bandeja, «Necesita humano» | 23 ms | 25 ms | 1,5 s |
| Bandeja, búsqueda | 28 ms | 31 ms | 1,5 s |
| Panel lite (`/console/lite/home`) | 32 ms | 44 ms | 1 s |

La prueba comprueba además que la página trae 50 conversaciones, que hay
cursor para la siguiente y que el contador de «Necesita humano» da 500.

## Lo que no mide

- **Extremo a extremo.** CE-007 cuenta red, BFF y navegador. Hay margen de
  sobra (165 ms frente a 1,5 s), pero el número de staging es el que vale (T110).
- **La latencia de un mensaje nuevo** (CE-004, < 5 s): depende del worker, de
  Redis y del SSE. Se mide en staging en el recorrido del quickstart (T110).
