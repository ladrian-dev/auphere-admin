# Bug Verification: la DLQ de entrantes no tiene salida y su alarma se queda encendida

- **Slug**: dlq-sin-salida
- **Tested**: 2026-11-03 (local, base propia `nexus_test_dlq`; AWS solo en lectura)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

El defecto ya no se reproduce en lo que se puede ejercer sin escribir en un entorno:
una entrada nueva produce una transición aunque queden viejas, y la herramienta
lista, descarta y reinyecta contra un Redis real. **`partial` porque la tarea de ECS
y la transición de la alarma en AWS no se han ejercido**: el encargo prohíbe escribir
ahí, y eso es lo que falta por ver en staging. Sin regresiones.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes) | `test_old_entries_alert_once…`, `test_a_new_dead_message_fires…` sobre el código sin tocar | fail, como se esperaba | Una alerta por hora; la nueva, 1 transición en vez de 2 |
| Reproducción (después) | Las mismas | pass | Con la ventana real leída de `alarms.tf` |
| Worker tocado | `pytest` de watcher, contrato, `test_dlq*`, bootstrap, claimer, `consumer_*` | pass | 125 passed. `test_bootstrap_split` incluido: el vigilante es una tarea periódica |
| Idempotencia, con base | `pytest tests/integration/test_dlq_reinject.py` | pass | 6 passed. Con `test_turn_coalescing` y `test_no_raw_xadd`: 22 |
| ¿La prueba detecta el fallo? | Desactivar `provider_message_id` en `accept_inbound` | fail, como se esperaba | Revertido |
| Orden real, Redis real | `python -m nexus_worker.ops.dlq` contra Redis 8.4 local, base 13, datos inventados | pass | `list`, ensayo, `discard`, `reinject`; `XADD` + `XDEL` en `MULTI`, `XRANGE (id` |
| Vigilante, Redis real | `process_tick` con `get_redis()` | pass | Avisa, calla una hora después, avisa con la nueva, calla |
| Lint y tipos | `./scripts/verify.sh lint` | pass | «Todo verde». `terraform fmt -check` también |
| Plan de Terraform | `terraform plan -lock=false -target='…["dlq_entries"]'`, staging y prod | pass, sin aplicar | Staging: 1 a cambiar, solo la descripción. Prod: 1 a crear |
| Lanzar la tarea de ECS | `./scripts/ops/dlq.sh staging list` | not-run | Escribe en AWS. Probado contra un `aws` de mentira, y las partes de lectura contra AWS real |
| Transición real de la alarma | Historial de `nexus-staging-platform-alert-dlq-entries` | not-run | Hace falta desplegar y que muera un mensaje |
| Suites completas | `./scripts/verify.sh py` | skipped | Solo lo tocado, por encargo |

## Output Excerpts

```
assert [1, 1, 1, 1, 1, 1, ...] == [1, 0, 0, 0, 0, 0, ...]    # antes
AssertionError: el mensaje nuevo avisa, con la vieja dentro
assert 1 == 2                                                # antes
125 passed, 4 warnings in 10.11s                             # después, worker
22 passed, 1 warning in 45.71s                               # después, con base
Todo verde. La tubería debería pasar.
```

```json
{"entry_id": "1793742826345-0", "tenant_id": "88c0…", "source_stream": "nexus:inbound:standard",
 "age": "60d 0h", "attempts": 5, "cause": "value too long", "reason": "prueba local",
 "deleted": true, "event": "ops.dlq.discarded", "level": "warning"}
```

## Residual Risks

- **Una entrada dentro de las 3 h siguientes a un aviso no manda otro correo.** Es lo que dice R9.5; queda escrito en `docs/dlq.md` y en el propio correo.
- **Sin recordatorio.** De una entrada ya avisada no se vuelve a avisar: si nadie actúa, se queda. Es el precio de dejar de sonar cada hora, y `list` es el sitio donde mirarlo.
- **`scheduler` caído:** no suena mientras esté caído. Avisa al volver.
- **La antigüedad de una entrada que murió dos veces** cuenta desde la reinyección, así que la barrera de 24 h no ve la edad original. Para llegar ahí ya hubo que decidir reinyectarla.
- **La imagen no se ha construido.** `hatch` empaqueta `src/nexus_worker` entero y el `PYTHONPATH` de la imagen lo incluye, pero `nexus_worker.ops` no se ha visto dentro de una imagen.
- **Probado en Redis, no en Valkey:** los comandos son básicos (`XRANGE`, `XADD`, `XDEL`, `MULTI`, `XINFO GROUPS`), y el `scheduler` ya usa los de lectura.

## Recommendation

Fusionar en `develop` cuando T035 de la 051 esté comprobada (desde este arreglo
`dlq_entries` ya no repite), y cerrar el bug tras ver en staging, en este orden: que
`./scripts/ops/dlq.sh staging list` devuelve la entrada del 31 de octubre, y que la
alarma pasa a OK unas 3 h después del primer registro con ella dentro. Los comandos
están en `docs/dlq.md`.
