# Bug Fix: la DLQ de entrantes no tiene salida y su alarma se queda encendida

- **Slug**: dlq-sin-salida
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La DLQ ya tiene salida: `python -m nexus_worker.ops.dlq` (listar, descartar y
reinyectar), lanzable como tarea de ECS con `scripts/ops/dlq.sh`. Y el vigilante
avisa por lo **nuevo**, con una marca por id, de modo que la alarma vuelve a OK
aunque queden entradas viejas y lo siguiente que muera vuelve a avisar.

Nada de esto escribe en Valkey ni en AWS por sí solo: la decisión sobre las 26
entradas existentes y el `apply` del texto de la alarma son de Luis.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/ops/__init__.py` | added | Paquete de herramientas de operador, fuera de `streams` |
| `apps/worker/src/nexus_worker/ops/dlq.py` | added | `list`, `discard`, `reinject` |
| `apps/worker/src/nexus_worker/streams/platform_watcher.py` | modified | Alerta por entradas con id mayor que la marca; la marca se mueve tras avisar; texto con el comando |
| `apps/worker/src/nexus_worker/streams/consumer.py` | modified | El nombre de la cola, de `core/streams`; el docstring apunta a la herramienta |
| `apps/api/src/nexus_api/core/streams.py` | modified | `INBOUND_DLQ_STREAM` e `INBOUND_STREAMS` en un solo sitio |
| `scripts/ops/dlq.sh` | added | `run-task` + espera + líneas del registro + código de salida |
| `infra/terraform/30-observability/alarms.tf` | modified | Solo texto: descripción de `dlq_entries` y comentario. Sin cambios en la ventana |
| `docs/dlq.md` | added | El runbook, con comandos de staging y producción |
| `docs/correos.md` | modified | Cómo se comporta la alarma de la DLQ |
| `apps/api/RUNBOOK.md` | modified | Puntero al runbook |
| `specs/051-correos-con-oficio/tasks.md` | modified | T035 antes de este arreglo; T037 ya no espera ALARM permanente |
| `specs/051-correos-con-oficio/evidence/alarma-calibracion.md` | modified | Anexo fechado; las cifras de la calibración no se tocan |

## Diff Highlights

La condición de la alerta, antes y después:

```python
# Antes: estado. Sobre una cola que nadie vacía, encendida para siempre.
dlq_len = int(await redis.xlen(DLQ_STREAM))
if dlq_len > 0: ...

# Después: novedad. Un id de stream no retrocede aunque se borren entradas.
if mark is not None and _entry_order(newest_id) <= _entry_order(mark):
    return None
```

Reinyectar es una sola transacción, porque es la última copia del mensaje:

```python
async with redis.pipeline(transaction=True) as pipe:
    await xadd_capped(pipe, entry.source_stream, entry.original)
    await pipe.xdel(DLQ_STREAM, entry.entry_id)
    new_id, deleted = await pipe.execute()
```

## Tests Added or Updated

Todas vistas en rojo antes de implementar: `[1, 1, 1, …] == [1, 0, 0, …]` (una
alerta por hora), `assert 1 == 2` (la nueva no produce transición), y `ImportError`
en lo que aún no existía.

- `apps/worker/tests/unit/test_platform_watcher.py`: la vieja avisa una vez y calla; la nueva avisa con viejas dentro; descartar no tapa una nueva; descartar la más nueva no parece una llegada; perder la marca avisa una vez; un fallo al escribir la marca no pierde el aviso; sin datos del mensaje.
- `apps/worker/tests/unit/test_platform_alarms_contract.py`: el defecto de punta a punta con la ventana real de Terraform; la alarma dice el comando; lo que cita existe; toda descripción cabe en 1024.
- `apps/worker/tests/unit/test_dlq_tool.py`: sin cuerpo ni teléfonos (también por la causa), filtros, ensayo, registro de cada escritura, negativas, ida y vuelta por `handle_entry`, y que corre con `python -m` sin cargar LangGraph.
- `apps/worker/tests/unit/test_dlq_script.py`: el envoltorio contra un `aws` de mentira: el JSON de `--overrides`, un motivo con comillas, el código de salida.
- `apps/api/tests/integration/test_dlq_reinject.py`: la tabla de idempotencia del assessment, contra la base de verdad.

## Local Verification

- `uv run --directory apps/api pytest <worker: watcher, contrato, dlq, script, bootstrap, claimer, consumer_*>` → 125 passed.
- `uv run --directory apps/api pytest tests/integration/test_dlq_reinject.py tests/integration/test_turn_coalescing.py tests/unit/test_no_raw_xadd.py` → 22 passed.
- `./scripts/verify.sh lint` → todo verde.
- **Mutación**: con la comprobación de `provider_message_id` desactivada en `accept_inbound`, `test_dlq_reinject.py` falla. Revertido.
- **Orden real contra Redis real** (local, base 13, datos inventados, limpiado después): `list`, ensayo, `discard`, `reinject`, y el vigilante con el mismo cliente de producción. Registros en JSON sin cuerpo ni teléfono; el mensaje vuelve al stream sin `dlq_*`.
- `terraform plan -lock=false -target=…` (sin aplicar): staging, 1 a cambiar, solo la descripción; prod, 1 a crear, porque la alarma aún no existe allí.
- Solo lectura en AWS: definición y red del `scheduler`, parámetros de despliegue, nombre del flujo de registros, historial de la alarma y Logs Insights. Las 26 entradas salieron de `nexus:inbound:standard`, así que `reinject` las aceptaría por stream.

## Deviations from Assessment

- La causa enmascara además los valores entre comillas y `Key (x)=(y)`, no solo los números largos: asyncpg escribe `invalid input for query argument $3: '<valor>'`, y ahí puede ir el cuerpo. Se conserva `<class '…'>`, que es el tipo de error.
- `bash` 3.2 de macOS se comía el `»` tras `$task_arn` y partía un carácter multibyte; lo detectó `test_a_task_that_never_ran_is_a_failure`. Por eso esa variable va con llaves.

## Follow-ups

- La alarma directa sobre `consumer.dead_lettered` (alternativa D) cerraría además el punto ciego del `scheduler` caído.
- `nexus:usage:dlq`, `nexus:billing:events:dlq` y `<stream>:dlq` de `meta_coexistence.py` siguen sin aviso ni salida, y dos de ellas son dinero.
- La causa de staging (`StringDataRightTruncationError`, 31-oct) está sin investigar. Puede seguir viva, y conviene mirarla antes de descartar esa entrada.
