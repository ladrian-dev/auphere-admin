# Quickstart: comprobar la spec 058

## En local

Con Postgres y Redis arriba (`docker compose up -d`):

```bash
cd apps/worker && uv run pytest tests/unit/test_gate_order_audience.py -q
cd apps/api && uv run pytest tests/integration/test_dispatcher_058_audience_first.py -q
cd apps/api && uv run pytest tests/integration/test_dispatcher_058_release_wait.py -q
cd apps/api && uv run pytest tests/integration/test_audience_cleanup.py -q
cd apps/api && uv run pytest tests/isolation/test_058_audience_cleanup_per_tenant.py -q
```

Además, las suites que ya cubrían las puertas no pueden romperse:

```bash
cd apps/api && uv run pytest tests/integration/test_dispatcher_persist_first.py tests/integration/test_dispatcher_reason_notices.py -q
cd apps/worker && uv run pytest tests/unit/test_dispatcher_out_of_quota.py -q
```

Y antes de dar nada por hecho:

```bash
./scripts/verify.sh lint
```

## En staging (después de fusionar en `develop`)

1. Un cliente de prueba en pausa con su número en «Solo mi equipo».
2. Escribir desde un número que no es de prueba. Esperado:
   - en `/nexus/staging/runner`, `pipeline.skipped.not_admin` con
     `reason=out_of_audience`;
   - ningún `email.sent` con `kind=inbox_waiting`;
   - la conversación en Conversaciones, no en la Bandeja.
3. Escribir desde un número de prueba. Esperado: espera con «Cliente en pausa» y
   un `email.sent` `inbox_waiting`.
4. La limpieza, en seco y después de verdad, como en
   [contracts/turn-gates.md](contracts/turn-gates.md#el-guion), con
   `ecs exec` en `nexus-staging-api` (memoria «Diagnóstico de prod por logs»).

## En producción (solo después de pasar a `main`, y con permiso de Luis)

- Tras el despliegue: ningún `email.sent` `inbox_waiting` de `flor-y-encanto`
  por contactos fuera de la audiencia (CE-004).
- La limpieza, en seco primero, con una tarea suelta con la definición del
  `migrate` y la orden del guion. Se lanza de verdad solo si la pasada en seco
  da lo esperado (hoy, unas 3 conversaciones de Flor y Encanto).
