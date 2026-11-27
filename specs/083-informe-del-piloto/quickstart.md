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
pnpm --dir apps/console exec vitest run src/components/report src/components/clients/v2
```

## En staging (cuando esté desplegado)

1. Entrar en la consola como owner de Autprod y abrir Jemma's Hair → «Informe».
2. Elegir del 10 de noviembre a hoy. Comprobar a mano tres cifras contra la Bandeja: una conversación tomada y devuelta cuenta «con persona»; un mensaje de la noche cuenta en su día de Caracas; una cancelación hecha por el agente cuenta como del agente.
3. «Imprimir» → guardar como PDF: sin navegación ni filtros, tema claro, barras visibles, dos páginas A4 o menos.
4. Con un analyst del partner, la pestaña está; con un billing, no.

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
