# Evidencia — spec 022

Una entrada por iteración. Cada una dice qué se midió, con qué, y qué salió.

| Iteración | Fichero | Estado |
|---|---|---|
| 1 · Meta, la API y la tarjeta (H1) | `iteracion-1.md` | cerrada 2026-09-30 (local); CE-002 en staging |
| 2 · el agente (H3) | `iteracion-2.md` | cerrada 2026-09-30 (local) |
| 3 · el alta lo ofrece (H2) | `iteracion-3.md` | cerrada 2026-09-30 (local); CE-004 en staging |

## Puertas de cierre

| Puerta | Cómo se comprueba |
|---|---|
| Licencias | `locks-at-open.sha256` igual al cerrar; `git diff origin/develop` sobre los locks vacío |
| Medidor | `test_the_catalog_costs_nothing_the_meter_sees` (T003) |
| Aislamiento | `tests/isolation/test_channel_catalog_scope.py` (T004) |
