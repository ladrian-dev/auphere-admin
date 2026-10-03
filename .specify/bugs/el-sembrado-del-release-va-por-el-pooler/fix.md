# Bug Fix: el release habla con la base directa, entero

- **Slug**: el-sembrado-del-release-va-por-el-pooler
- **Fixed**: 2026-10-03
- **Assessment**: ./assessment.md
- **Status**: applied; pendiente de ver un `deploy-staging` en verde
- **Excepción**: hotfix P0 de la regla nº1 (`docs/spec-driven-development.md`).
  La tubería de despliegue estaba caída y el mismo fallo abortaba el despliegue
  a producción. **Queda debiendo la spec retroactiva (48 h).**

## Summary

`alembic upgrade head` y el sembrado de conectores corren en la misma tarea y
leían URLs distintas: Alembic la directa, el sembrador la del pooler. En
staging el nombre del pooler es de Service Connect y la tarea de migración no
está en ese namespace, así que no resuelve. Ahora hay un motor explícito para
el release —`get_direct_engine()`— que lee la misma URL que Alembic, y el
sembrador lo usa.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/db/base.py` | modificado | `get_direct_engine()`: `database_url_direct or database_url`, sin los `connect_args` del pooler (no hay pooler delante) y con pool de uno (es una pasada). Entra también en `reset_engine_cache` y `dispose_engine` |
| `apps/api/scripts/seed_connectors.py` | modificado | pide `get_direct_engine()` en vez de `get_engine()` |
| `apps/api/scripts/release.sh` | modificado | la cabecera documentaba una sola variable y la que manda es la otra; ahora dice cuál y por qué |
| `apps/api/tests/unit/test_release_uses_direct_db.py` | añadido | la pieza (dos casos: con pooler y sin él) y el **cableado** |

## Verification

Rojo antes de verde, y en dos pasos a propósito:

1. Sin el arreglo: `ImportError` en la colección — prueba que falta el nombre,
   nada más.
2. Con `get_direct_engine()` puesto y el sembrador **todavía** desviado:
   `2 passed, 1 failed`. Los dos verdes son la pieza; el rojo es el cableado.
   Ese es el fallo que se desplegó, y es el que la prueba caza.
3. Con el arreglo entero: `3 passed`.

Además: `ruff`, `ruff format` y `mypy --strict` sobre `nexus_api` en verde
(349 archivos), y `./scripts/verify.sh` completo.

**Lo que esto NO prueba.** Que el despliegue pase. La diferencia entre las dos
URLs es inobservable sin un pooler delante, así que ninguna prueba local puede
cubrirla — es justo la razón por la que el defecto llegó a staging con todo
verde. La comprobación de verdad es el próximo `deploy-staging`: el paso «run
migration task» tiene que terminar en `migration exit code: 0` y «roll
services» dejar de saltarse.
