# Quickstart: probar el informe del piloto

## En local

```bash
cd apps/api
NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_083 \
NEXUS_REDIS_URL=redis://localhost:6379/13 \
uv run pytest tests/unit/test_083_cycles.py tests/integration/console/test_client_report.py \
  tests/integration/improvement/test_suggestions.py tests/isolation/test_client_report_scope.py \
  tests/isolation/test_console_scope.py -q
```

```bash
pnpm --dir apps/console exec vitest run src/components/metrics src/components/clients/v2
```

## En staging (cuando esté desplegado)

*Enmendado el 2026-11-27: las cifras están en Métricas, no en una pestaña del cliente.*

1. Entrar en la consola como owner de Autprod, abrir **Métricas** y elegir Jemma's Hair y 30 días. `/clients/jemma-hair/report` tiene que llevar al mismo sitio.
2. Comprobar a mano tres cifras contra la Bandeja:
   - una conversación tomada y devuelta cuenta «con persona»;
   - un mensaje de la noche cuenta en su día y su hora de Caracas;
   - una cancelación hecha por el agente cuenta como del agente.
3. Las diferencias frente a los 30 días anteriores, y las gráficas por hora y por día de la semana, cuadran con lo que se ve en la Bandeja.
4. En la sección, «Imprimir → Guardar como PDF» desde el diálogo de Chrome: solo la sección, sin dinero del partner, tema claro, barras visibles y dos A4 o menos.
5. Con un analyst del partner, la sección está; con un billing, solo el dinero.

## Comprobación de consistencia (`/speckit-analyze`, 2026-11-26)

| Requisito | Tareas | Estado |
|---|---|---|
| 1 (página, filtros, periodo, permisos, zona) | T006, T007, T011, T013, T014 | cubierto |
| 2 (ciclos) | T001, T002, T008 | cubierto |
| 3 (sin persona por historial) | T002, T008 | cubierto |
| 4 (primera respuesta) | T002, T008 | cubierto |
| 5 (incidencias y freno) | T002, T010 | cubierto |
| 6 (agenda y recordatorios) | T002, T010 | cubierto |
| 7 (gasto) | T002, T010 | cubierto |
| 8 (presentación e impresión) | T005, T013, T016, T017 | cubierto |
| 9 (Rendimiento) | T003, T009 | cubierto |
| 10 (aislamiento) | T004, T011, T015 | cubierto |

Sin marcas `[NEEDS CLARIFICATION]`. Spec, plan y tareas usan los mismos nombres (`cause`, `period_cycles`, `build_spans`) y las mismas decisiones (D1–D14).
