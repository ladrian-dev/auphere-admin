# Bug Fix: el LISTEN del dispatcher de salida no conecta nunca en producción

- **Slug**: listener-de-salida-no-conecta
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied (rama `hotfix/prod-2026-10-22`, sin desplegar)

## Summary

El listener conecta con `asyncpg.connect(**_asyncpg_connect_kwargs())`: el URL
se descompone con el parser de SQLAlchemy (`make_url().translate_connect_args()`
más la query), el mismo camino que ya usan el resto de las conexiones. Sigue
prefiriendo `database_url_direct` frente al pooler.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/streams/outbound.py` | modified | `_asyncpg_dsn` → `_asyncpg_connect_kwargs` |
| `apps/worker/tests/unit/test_outbound_listen_dsn.py` | modified test | las tres pruebas de antes, adaptadas; contraseñas con `[`, `]`, `#`, `?`; y asyncpg real hasta el socket |

## Cómo comprobarlo tras desplegar

`outbound.listener.connected` aparece una vez por arranque, y
`outbound.listener.reconnecting` desaparece de `/nexus/prod/egress`.
