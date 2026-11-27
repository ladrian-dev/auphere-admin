# Verlo funcionar en local

Con la base de la feature y un cliente sembrado, en unos minutos.

## 1. La base

```bash
cd apps/api
createdb nexus_test_082
DATABASE_URL=postgresql+asyncpg://localhost/nexus_test_082 uv run alembic upgrade head
```

La 0245 crea `schedules` y `schedule_runs` con RLS forzada, amplía los cuatro `CHECK` y deja la función `due_schedules`.

Comprobación rápida de que la RLS quedó donde tiene que quedar:

```bash
uv run pytest tests/isolation/test_21_rls_covers_every_tenant_table.py tests/isolation/test_43_force_and_composite_fk_sweep.py -q
```

Las dos tablas nuevas entran solas en ese barrido. Si alguna se escapó, la suite lo dice por su nombre.

## 2. Un cliente con un agente que atiende

El fixture de la feature siembra lo mismo que la maqueta: un cliente en `America/Santiago` con dos agentes, uno atendiendo y otro en pausa, y una bolsa con saldo.

```bash
uv run python -m tests.fixtures.seed_082
```

## 3. Una rutina, ejecutada a mano

```bash
curl -X POST localhost:8000/console/clients/muna/schedules \
  -H "Authorization: Bearer $CONSOLE_TOKEN" -H 'content-type: application/json' \
  --data '{"agent_id":"'$AGENT'","name":"Altas de ayer","instruction":"Dime cuántos pedidos entraron ayer y cuáles siguen sin pagar.","cadence":"daily","local_time":"09:00","email":false}'
```

```bash
curl -X POST localhost:8000/console/clients/muna/schedules/$ID/run \
  -H "Authorization: Bearer $CONSOLE_TOKEN"
```

Responde `202` con su `run_id`. El historial, en cuanto el runner lo recoja:

```bash
curl localhost:8000/console/clients/muna/schedules/$ID/runs -H "Authorization: Bearer $CONSOLE_TOKEN"
```

Lo que hay que ver ahí: `status` en `done`, la respuesta en texto, `tools_used` con lo que usó y `cost` con lo que costó. Y en la bolsa del cliente, un asiento `debit_schedule` por ese importe.

## 4. Que se dispare sola

El disparador va en la familia del scheduler:

```bash
cd apps/worker && uv run nexus-scheduler
```

Para no esperar a mañana, se adelanta el vencimiento a mano:

```sql
SET app.tenant_id = '<tenant>';
UPDATE schedules SET next_run_at = now() - interval '1 minute' WHERE id = '<id>';
```

En el siguiente tic aparece una ejecución nueva con `trigger: "schedule"`, y `next_run_at` queda en el día siguiente a las 09:00 de Santiago, que en invierno austral no es la misma hora UTC que en verano. Eso es justo lo que prueban las unitarias de `when.py`.

## 5. La frontera, a ojo

La comprobación que de verdad importa, y que conviene hacer a mano una vez:

```bash
cd apps/api && uv run pytest tests/isolation/test_082_schedule_turn_has_no_end_customer.py -q
```

Barre el registro entero de herramientas y comprueba que ninguna que exija `conversation_id` llega a ofrecerse en un turno de rutina. Si alguien añade mañana una herramienta que hable con un cliente final, esa suite se pone roja antes de que llegue a producción.

## 6. La consola

```bash
pnpm --filter @auphere/console dev
```

En `/schedules`: elegir cliente, la lista con sus filtros, el alta como panel lateral y el detalle con el hilo. Un cliente sin ninguna rutina enseña el estado vacío, no una tabla en blanco.
