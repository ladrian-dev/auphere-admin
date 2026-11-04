# Bug Assessment: la DLQ de entrantes no tiene salida y su alarma se queda encendida

- **Slug**: dlq-sin-salida
- **Created**: 2026-11-03
- **Source**: pasted text (encargo de Luis, comprobado con Logs Insights el 2026-11-03)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> La DLQ no tiene salida. Mientras quede una sola entrada, la alarma
> `nexus-*-platform-alert-dlq-entries` sigue en ALARM, y un mensaje de cliente
> nuevo que muera **no produce ninguna transición, así que nadie se entera**.
> Además, un aviso que suena cada hora durante meses enseña a ignorarlo.

Lo medido hoy con `consumer.dead_lettered`, 120 días:

- Producción: 25 entradas, del 2026-08-26 19:41 al 2026-08-27 00:13 UTC, con
  `password authentication failed`: el incidente de rotación de contraseña de
  Aurora. Ya no es un fallo vivo.
- Staging: 1 entrada del 2026-10-31 17:19, `StringDataRightTruncationError`.

## Symptom

`platform_watcher` registra `platform_alert` `dlq_entries` cada hora mientras
`XLEN nexus:inbound:dlq > 0`, y dice «revisar y reinyectar», cosa que no se
puede hacer con nada del repo. Como las entradas no salen nunca, la alarma de
CloudWatch recibe un punto cada hora, su ventana es de 3 h y no vuelve a OK: la
primera entrada la enciende para siempre.

Lo esperado: un mensaje que muere **hoy** avisa aunque haya otros de hace dos
meses, y el operador tiene un comando para mirarlos y decidir.

## Reproduction

1. Con una entrada vieja en `nexus:inbound:dlq`, correr `process_tick` a lo largo
   de un día: registra una alerta por hora (`DEDUP_TTL_S = 3600`).
2. Pasar esos registros por la regla de la alarma (300 s × 36, un punto): OK →
   ALARM en el primero, y ninguna transición más.
3. Añadir una entrada nueva: el registro de esa hora es igual que el anterior y
   no hay transición. **Nadie recibe nada.**
4. Buscar con qué sacar la entrada: no existe (ver el barrido).

Estado real de la alarma, leído hoy de AWS (solo lectura):

| Alarma | Estado | Desde |
|---|---|---|
| `nexus-staging-platform-alert-dlq-entries` | ALARM, `actions_enabled = false` | 2026-11-03 21:01 UTC |
| `nexus-prod-platform-alert-dlq-entries` | no existe aún (T036 de la 051) | — |

## El barrido: por qué se afirma que no hay salida

Con `git grep` sobre **todo lo versionado en `origin/develop`**, no sobre el
checkout parcial de este worktree:

| Dónde | Qué se buscó | Resultado |
|---|---|---|
| `apps/`, `scripts/`, `infra/`, `docs/`, `.github/`, `specs/` | `dlq`, `dead.?letter` | Solo escriben `consumer._dead_letter` (entrantes), `metering/consumer.py`, `billing/process_event.py` y `meta_coexistence.py`. Solo lee `platform_watcher` (`XLEN`) |
| Lo mismo | `xdel`, `xtrim`, `replay`, `reinyect`, `re-?inject`, `requeue`, `re-?publish`, `redrive`, `inbound:dlq` | Ningún `XDEL` ni `XTRIM` en todo el repo. Los `replay`/`requeue` son otra cosa: saneamiento del webhook, `direct_messages`, `owner_fanout`. «Reinyectar» solo aparece en el aviso, en la descripción de la alarma y en un SKILL de medicina estética |
| `apps/admin`, `apps/console`, `apps/api/src`, `packages/` | `dlq`, `dead.?letter`, «cola muerta» | 0 resultados: no hay pantalla ni endpoint |
| `apps/api/RUNBOOK.md` | `dlq`, `stream`, `redis`, playbooks | No lo cita: tiene playbooks de `isolation`, `alert_whatsapp_burst_v1` y `alert_cost_threshold_v1` |
| `scripts/`, `scripts/ops/` | todo | Solo `prueba-plantilla-muna.sh`, que no toca streams |
| `xrange`, `xrevrange` fuera de pruebas | | Solo `companion_streaming.py`, sobre otras claves |
| ECS Exec en prod | `ecs_exec_services` en `cluster_iam.tf` | `[]` en prod; en staging, solo `api` |

La única salida posible hoy es abrir `redis-cli` dentro de la VPC, que en prod no
se puede hacer. El docstring de `_dead_letter` promete «an operator can replay
it by re-publishing the original fields to the source stream», y nunca se
escribió el cómo.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/streams/platform_watcher.py:125-140`: alerta por
  `XLEN > 0` con dedupe por hora. Es lo que enciende la alarma para siempre.
- `apps/worker/src/nexus_worker/streams/consumer.py:509-541`: `_dead_letter`, con
  el payload y los campos `dlq_*`, y su promesa.
- `infra/terraform/30-observability/alarms.tf:205`: la descripción dice «no avisa
  si crece», o sea, que el defecto ya estaba visto y asumido.
- `docs/correos.md:64-68`: lo documenta como comportamiento normal.

## Root Cause Hypothesis

Son dos piezas de la misma falta. WP-04 creó la DLQ como aparcamiento, sin
escribir la salida. La spec 051 movió el aviso a CloudWatch con una condición de
**estado** (hay entradas), que solo vale para algo que se arregla solo o que
alguien puede vaciar. Sobre una cola que no se puede vaciar, una alarma de estado
se apaga una sola vez: nunca. **Confianza: alta**, se reproduce con la regla de
la alarma y se ve en el estado real de staging.

## ¿Un turno reinyectado se responde dos veces?

Leído en `accept_inbound` (`dispatcher.py:275-340`) y `claim_turn` (`turns.py`),
y fijado después con prueba de integración contra la base.

La idempotencia existe, y tiene dos capas: `provider_message_id` evita la segunda
fila y `messages.turn_id` evita el segundo turno. Solo se contesta un mensaje con
`turn_id IS NULL` y `created_at` de hace menos de 15 min (`UNTAKEN_HORIZON`).

| Estado de la entrada al reinyectar | Qué pasa | Respuestas |
|---|---|---|
| Nunca se guardó (los 25 de prod: sin base no hubo fila) | Fila nueva, con `created_at = ahora`, y turno | Una, **ahora** |
| Guardada y con turno (contestada o en curso) | `duplicate=True`, programa el turno, `claim_turn` no encuentra nada que tomar. Si el turno seguía vivo, se retoma con el mismo `turn_id` y `turn_effects` no repite efectos | Ninguna más |
| Guardada sin turno, hace < 15 min | `duplicate=True`, y el turno la toma | Una |
| Guardada sin turno, hace > 15 min | `duplicate=True`, `Claim("none")` | Ninguna: el mensaje está en la bandeja, sin respuesta |
| Sin `provider_message_id` | No hay con qué detectar el duplicado | **Podría contestar dos veces.** Ningún publicador vivo lo emite (`meta`, `meta_social`, `tiktok` lo ponen; `publish_inbound` no tiene llamadas), pero la herramienta se niega |
| Fila ya borrada por la retención (`drop_expired_partitions`) | Parece nueva | **Podría contestar dos veces.** La cubre la barrera de 24 h |
| Se reinyecta dos veces | `XADD` y `XDEL` van en la misma transacción (Valkey sin cluster: `num_cache_clusters`, sin `num_node_groups`) | La segunda no encuentra la entrada |

**El riesgo no es el doble turno: es contestar tarde.** Una entrada que nunca se
guardó se trata como un mensaje recién llegado, así que:

- `accept_inbound` pone `conversations.last_inbound_at = ahora`, y con eso la
  plataforma cree que la ventana de 24 h de Meta está abierta cuando no lo está:
  la respuesta y lo que venga después fallan o se ofrecen mal;
- `created_at = ahora` coloca un mensaje de hace dos meses después de los que el
  cliente escribió luego;
- el `media_provider_id` caducó y el adjunto degrada a texto;
- el cliente recibe la respuesta a algo que ya no recuerda.

Por eso `reinject` **se niega a mover entradas de más de 24 h** salvo con
`--allow-stale`, que es la decisión explícita de hacerlo igualmente. Es lo que
Luis dice de los 25 de prod («no tiene sentido»), convertido en barrera para que
no dependa de acordarse.

## Proposed Remediation

### 1. Cómo avisar de una entrada nueva

Medido con las 25 marcas reales de prod y un tick por minuto
(`platform_alert` llegó por primera vez a las 22:01, dos horas y veinte después
de la primera muerte, según `specs/051-correos-con-oficio/evidence/alarma-calibracion.md`).
«Aviso» es un paso de OK a ALARM. Es un techo, igual que aquella calibración.

| Alternativa | Registros, 27-ago a 3-nov | Avisos del incidente (3 h) | Un mensaje nuevo con los 25 dentro | Si el vigilante está caído más que el umbral |
|---|---|---:|---:|---|
| Hoy: `XLEN > 0`, cada hora | 1658 | 1 | **0** | Avisa al volver |
| **A. Marca por id** | 6 | 1 | **1** | Avisa al volver |
| B. Entrada más nueva con menos de 1 h | 6 | 1 | 1 | **Se pierde** |
| C. Crecimiento por contador (`XLEN` > marca) | 6 | 1 | 1 si no hay descartes; **0** si se descarta a la vez | Avisa al volver |
| D. Métrica directa sobre `consumer.dead_lettered` | 25 | 1 | 1 | Avisa siempre: no pasa por el `scheduler` |

**Se elige A**, una marca con el id de la última entrada de la que se avisó
(`nexus:alert:dlq:last_alerted_id`):

- **B pierde mensajes en silencio.** Sin estado, depende de que el vigilante esté
  vivo cuando la entrada aún es joven, y el 26 de agosto tardó 2 h 20 min en
  registrar nada. Si aquel incidente hubiera acabado a las 20:36, B no habría
  avisado nunca; A avisa a las 22:01. Staging lo haría a diario: aparca el
  `scheduler` 6 h cada noche.
- **C se rompe con la propia herramienta.** Descartar baja el contador: 25
  descartadas y 1 nueva en el mismo minuto dan 1 < 25, y no avisa. Un id de stream
  no retrocede aunque se borren entradas.
- **D es la más robusta**, porque ni siquiera depende del `scheduler`, pero no
  sirve de nada hasta aplicar Terraform en los dos entornos, retira un tipo de
  `platform_alert` y cambia T035 y T036 de la 051 a medio hacer. Queda como mejora
  posible, no como arreglo de esto.
- **Si se pierde la marca**, A avisa una vez de más. Ese es el lado bueno del
  fallo: ruido una vez, nunca silencio. Por lo mismo, el primer tick tras
  desplegar registra una vez, y luego calla.

**Cómo encaja con la ventana de 3 h.** No se toca, y R9.5 de la 051 ya lo dice:
«avisa cuando empieza, y otra vez solo si vuelve a registrarse tras tres horas sin
hacerlo». Con la marca, el vigilante registra solo cuando hay algo nuevo, así que:

- la alarma pasa a ALARM con la primera entrada nueva y a OK 3 h después de la
  última, sin que nadie vacíe la cola;
- **una entrada que llega dentro de esas 3 h no manda otro correo**: va con el
  aviso anterior, y estira la ventana. Es el mismo incidente, o alguien ya tiene
  un correo sin atender que le lleva a `list`, donde la verá. Una ventana de 5 min
  daría hasta 12 correos por el incidente de agosto; una de 1 h daría 1, con 2 h
  menos de ángulo muerto. Se podría bajar, pero R9.5 dice tres y aquí no hace falta.

No cambia el número de la ventana, ni los filtros, ni el contrato de los tipos.
Solo cambia el **texto** de la alarma (`terraform apply -target`, sin efecto en su
evaluación).

### 2. La herramienta

**Un módulo del worker, `python -m nexus_worker.ops.dlq`**, y un envoltorio local
`scripts/ops/dlq.sh <staging|prod> …`.

- Corre como orden en una tarea de ECS (`run-task` con `containerOverrides`), con
  la definición del `scheduler`: misma imagen, mismo `NEXUS_REDIS_URL`, y sus
  líneas caen en `/nexus/<entorno>/scheduler`. Comprobado en AWS, solo lectura:
  el contenedor se llama `scheduler` y es el único esencial (`adot` no), así que
  la tarea para al acabar la orden; el flujo de registros es
  `scheduler/scheduler/<id de tarea>`; y la red sale de
  `describe-services` del propio `scheduler`.
- Fuera de `nexus_worker.streams`, porque ese paquete importa `consumer` en su
  `__init__` y con él todo el grafo. Una herramienta que solo habla con Redis no
  tiene por qué cargarlo.
- El envoltorio existe porque un motivo con espacios dentro de un JSON dentro de
  `--overrides`, pegado en zsh, es la forma segura de equivocarse en producción.
- `list`, `discard` y `reinject`. En seco por defecto; escribir exige `--yes` y
  `--reason`, y `discard`/`reinject` exigen selección (`--id`, `--older-than`,
  `--newer-than` o `--all`), de modo que el ensayo es el mismo comando sin `--yes`.
- `reinject` republica en `dlq_source_stream`, sin `dlq_*`, en una transacción con
  el `XDEL`. Se niega si el stream de origen no es de entrantes o no tiene el grupo
  `nexus-worker` (se quedaría sin consumir, y es la última copia del mensaje), si
  falta un campo que el consumidor exige, si no hay `provider_message_id`, y si
  tiene más de 24 h, esto último salvo `--allow-stale`.
- **Nunca sale el cuerpo ni los teléfonos.** Ni `content`, ni `user_id`, ni
  `customer_*`, ni el `wamid`, que lleva el teléfono codificado dentro. Tampoco
  `dlq_error` tal cual: un error de SQLAlchemy arrastra `[parameters: (...)]` con
  esos datos, así que la causa se recorta a su primera línea y se enmascaran los
  números largos.
- Cada escritura deja `ops.dlq.discarded` u `ops.dlq.reinjected` con id, tenant,
  antigüedad y motivo. La antigüedad cuenta desde que el mensaje llegó
  (`dlq_source_entry_id`), no desde que se aparcó.

**Files likely to change**:

- `apps/api/src/nexus_api/core/streams.py`: el nombre de la DLQ y los streams de
  entrada, en un solo sitio.
- `apps/worker/src/nexus_worker/ops/__init__.py`, `apps/worker/src/nexus_worker/ops/dlq.py`: nuevos.
- `apps/worker/src/nexus_worker/streams/consumer.py`: el nombre, nada más.
- `apps/worker/src/nexus_worker/streams/platform_watcher.py`: la marca y el texto.
- `infra/terraform/30-observability/alarms.tf`: texto y comentario.
- `scripts/ops/dlq.sh`: nuevo.
- `docs/dlq.md`: nuevo. `docs/correos.md`, `apps/api/RUNBOOK.md`: lo que cambia.
- `specs/051-correos-con-oficio/tasks.md` y `evidence/alarma-calibracion.md`: T035
  y T037 hablan de que la alarma siga en ALARM.

**Tests to add or update**:

- `apps/worker/tests/unit/test_platform_watcher.py`: una entrada vieja avisa una
  vez y calla; una nueva avisa con viejas dentro; simulación de la alarma con su
  ventana real; descartar no tapa una nueva; perder la marca avisa una vez.
- `apps/worker/tests/unit/test_dlq_tool.py`: lista sin datos personales, filtros,
  seco por defecto, descarte y reinyección con su registro, negativas, ida y
  vuelta por el consumidor.
- `apps/worker/tests/unit/test_dlq_script.py`: el envoltorio contra un `aws` de
  mentira.
- `apps/worker/tests/unit/test_platform_alarms_contract.py`: la alarma dice qué
  hacer y cabe en los 1024 caracteres de CloudWatch.
- `apps/api/tests/integration/test_dlq_reinject.py`: la tabla de arriba, contra la
  base de verdad.

## Risks & Considerations

- **T035 de la 051 mira justo esto.** Comprueba que `dlq-entries` «sigue en ALARM
  entre dos repeticiones», y tras este arreglo la DLQ deja de repetir. Hay que
  cerrarla antes de desplegar esto a staging, o medirla con otro tipo. T037 («sigue
  en ALARM») cambia de sentido, y se reescribe en el mismo cambio.
- **Aislamiento.** `ops/dlq.py` lee entradas de todos los negocios porque es una
  herramienta de operador, y no recibe ningún `tenant_id` de nadie: republica la
  entrada con el suyo. No toca ninguna de las 7 garantías ni corre en la ruta del
  producto. Sin dependencias nuevas.
- **La herramienta solo existe donde se haya desplegado.** Las imágenes usan
  etiquetas móviles (`nexus-worker:staging`, `:prod`), y en producción no estará
  hasta fusionar en `main`. Los 25 de prod esperan a eso.
- **Reinyectar no reabre lo que cerró una puerta**: el turno pasa por las mismas
  puertas (negocio en pausa, sin saldo…) que un mensaje normal, y una entrada que
  vuelve a fallar vuelve a la DLQ con id nuevo, y avisa.

## Fuera de alcance, y sin aviso hoy

Hay otras tres colas muertas que nadie vigila ni puede vaciar:
`nexus:usage:dlq`, `nexus:billing:events:dlq` y `<stream>:dlq` en
`meta_coexistence.py`. No son mensajes de cliente, pero la primera y la segunda son
consumo y dinero. Se avisa a Luis; no se tocan aquí.

## Open Questions

Ninguna que bloquee. La decisión sobre las 26 entradas existentes es de Luis y se
ejecuta después.
