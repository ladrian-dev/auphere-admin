# La cola de mensajes muertos

Un mensaje de cliente que falla **5 veces** al guardarse sale de su stream y se aparca en `nexus:inbound:dlq`, con todos sus campos y por qué murió. Así no bloquea a los demás, pero **nadie va a contestarlo** hasta que un operador decida. Este documento explica cómo se decide.

Lo que llega a la DLQ es casi siempre el fallo de **guardar**: la base caída, un valor que no cabe en una columna. Un turno que falla después de guardar no viene aquí: se reintenta en su cola y, a los 5 intentos, pasa a una persona. La excepción es una entrada rescatada por el `stream-claimer`, que corre su turno ahí mismo y puede acabar aquí si ese turno falla.

## Cómo te enteras

El vigilante de la plataforma (`platform_watcher`, en el `scheduler`) mira la cola cada minuto y registra un `platform_alert` `dlq_entries` **una vez por cada tanda de entradas nuevas**. La alarma `nexus-<entorno>-platform-alert-dlq-entries` lo convierte en correo:

- **Una entrada nueva avisa aunque queden viejas.** Las de agosto no tapan a las de hoy.
- **De una entrada ya avisada no se vuelve a avisar.** No hay recordatorio: si la dejas ahí, ahí sigue.
- **Lo que muere en las 3 h siguientes va en el mismo aviso.** La alarma sigue en ALARM, cuenta las 3 h desde la última entrada nueva, y vuelve a OK sola, sin mandar nada, queden o no entradas dentro.
- **Si el `scheduler` estaba caído, avisa al volver.** La marca es el id de la última entrada avisada (`nexus:alert:dlq:last_alerted_id`). Si se pierde, avisa una vez de más de lo que haya. Por lo mismo, el primer minuto tras desplegar esto en un entorno registra una vez las que ya hubiera, y luego calla.

En staging la alarma existe y no manda nada (spec 051, R9.9).

## Antes de empezar

- Hace falta el perfil `nexus` de AWS (`AWS_PROFILE` elige otro).
- La herramienta va en la imagen del worker: existe en un entorno cuando el código ha llegado a él. `develop` para staging, `main` para producción. Antes de eso, la tarea acaba con `No module named nexus_worker.ops`.
- Cada orden es una tarea de ECS suelta, con la definición y la red del `scheduler`. Tarda cerca de un minuto. Es lo que hay: Valkey solo se alcanza desde la VPC y el `api` de producción no tiene ECS Exec.
- **Sin `--yes` no escribe nada.** El ensayo es el mismo comando sin `--yes`.

## Mirar

```bash
./scripts/ops/dlq.sh staging list
./scripts/ops/dlq.sh prod list
./scripts/ops/dlq.sh prod list --older-than 30d
./scripts/ops/dlq.sh prod list --newer-than 24h
./scripts/ops/dlq.sh prod list --id 1787773302370-0
```

Cada entrada sale como una línea `ops.dlq.entry`, y al final `ops.dlq.summary` con los totales por negocio y por causa:

```json
{"entry_id": "1787773302370-0", "tenant_id": "…", "source_stream": "nexus:inbound:standard",
 "age": "69d 2h", "age_s": 5969525, "attempts": 5, "cause": "password authentication failed",
 "event": "ops.dlq.entry"}
```

- **Nunca salen el cuerpo, el teléfono, el nombre ni el `wamid`** (lleva el teléfono codificado). La causa se recorta a su primera línea y se enmascaran comillas y números, porque un error de SQLAlchemy arrastra los parámetros del INSERT.
- **`age` cuenta desde que el mensaje llegó**, no desde que se aparcó. Es lo que importa para decidir. Una entrada que se reinyectó y volvió a morir cuenta desde la reinyección.
- `--older-than` y `--newer-than` también filtran por esa antigüedad. Los filtros se suman.

## Decidir

| Lo que ves | Qué hacer |
|---|---|
| Causa arreglada, mensaje de hace menos de 24 h | **Reinyectar** |
| Causa sin arreglar | Nada todavía. Reinyectada, volvería a morir |
| Más de 24 h | **Descartar**, y si el cliente importa, que le escriba una persona |
| Un negocio de prueba o borrado | **Descartar** |

Por qué 24 h: una entrada que nunca llegó a guardarse se trata como un mensaje recién llegado. Eso pone `conversations.last_inbound_at` en ahora, y la plataforma cree abierta la ventana de 24 h de Meta cuando lleva tiempo cerrada. Además coloca el mensaje después de lo que el cliente escribió luego, el adjunto ya caducó, y el cliente recibe la respuesta a algo que no recuerda. Y si la fila ya la borró la retención (`data_retention_cron` tira particiones enteras de `messages`), un mensaje contestado parecerá nuevo y se contestará otra vez. Por eso `reinject` se niega salvo `--allow-stale`.

## Descartar

```bash
# Ensayo: qué borraría
./scripts/ops/dlq.sh staging discard --id 1793467140000-0
./scripts/ops/dlq.sh prod discard --older-than 30d

# De verdad
./scripts/ops/dlq.sh staging discard --id 1793467140000-0 --yes --reason "prueba de staging, valor demasiado largo"
./scripts/ops/dlq.sh prod discard --older-than 30d --yes --reason "rotación de Aurora del 26-ago: demasiado tarde para contestar"
```

## Reinyectar

```bash
# Ensayo: qué movería y qué se negaría a mover
./scripts/ops/dlq.sh staging reinject --newer-than 24h
./scripts/ops/dlq.sh prod reinject --id 1787773302370-0

# De verdad
./scripts/ops/dlq.sh staging reinject --newer-than 24h --yes --reason "arreglado en 09d579ef"
./scripts/ops/dlq.sh prod reinject --id 1787773302370-0 --yes --reason "arreglado en 09d579ef"

# Con más de 24 h, sabiendo lo de arriba
./scripts/ops/dlq.sh prod reinject --id 1787773302370-0 --allow-stale --yes --reason "…"
```

Republica los campos originales en `dlq_source_stream`, sin los `dlq_*`, y borra la entrada de la DLQ en una sola transacción. Es la última copia del mensaje: o se mueve entera, o se queda.

Se niega, y lo dice en `ops.dlq.refused` con su motivo:

| `refusal` | Qué significa |
|---|---|
| `stale` | Más de 24 h. Se salta con `--allow-stale` |
| `source_stream_not_consumed` | El stream de origen no es de entrantes, o no tiene el grupo `nexus-worker`: nadie lo leería |
| `missing_fields` | Falta un campo que el consumidor exige: la acusaría y la tiraría sin decir nada |
| `no_provider_message_id` | Sin él, el consumidor no distingue un duplicado de un mensaje nuevo: podría contestar dos veces |

Las dos últimas no se pueden saltar. Quedan para `discard`.

### Qué pasa después

El consumidor la lee como cualquier otra, y pasa las mismas puertas: negocio en pausa, sin saldo, agente sin publicar. **No contesta dos veces**, y lo fija `apps/api/tests/integration/test_dlq_reinject.py`:

| Estado del mensaje | Qué pasa | Respuestas |
|---|---|---|
| Nunca se guardó | Fila nueva y turno | Una, ahora |
| Ya contestado, o con el turno en curso | Lo encuentra por `provider_message_id`, no hay nada que tomar | Ninguna más |
| Guardado sin turno, hace menos de 15 min | El turno lo toma | Una |
| Guardado sin turno, hace más de 15 min | No se toma (`UNTAKEN_HORIZON`) | **Ninguna**: está en la bandeja, y es una persona quien lo ve |

Si vuelve a fallar 5 veces, vuelve a la DLQ con id nuevo y **vuelve a avisar**, como cualquier entrada nueva.

## Comprobar lo que se hizo

La orden termina enseñando sus líneas y sale con el código de la tarea:

| Código | Significa |
|---|---|
| 0 | Hecho (o ensayado) |
| 1 | Falló. `ops.dlq.failed` dice por qué. Lo que ya estaba hecho, hecho está |
| 2 | Orden mal escrita. No se tocó nada |
| 3 | Hizo menos de lo pedido: alguna negativa, o un `--id` que no existe |

Cada escritura deja `ops.dlq.discarded` u `ops.dlq.reinjected` con id, negocio, antigüedad y motivo, en `/nexus/<entorno>/scheduler`. Para verlas después, en Logs Insights:

```
filter event in ["ops.dlq.discarded", "ops.dlq.reinjected", "ops.dlq.refused"]
| fields @timestamp, event, entry_id, tenant_id, age, reason, refusal
| sort @timestamp desc
```

## Sin el envoltorio

Lo que hace `scripts/ops/dlq.sh`, por si hay que hacerlo a mano. En `bash`: en zsh, las comillas de `--overrides` y las variables sin partir dan problemas.

```bash
ENV=prod   # o staging
NET=$(aws ecs describe-services --profile nexus --region eu-south-2 \
  --cluster nexus-$ENV --services nexus-$ENV-scheduler \
  --query 'services[0].networkConfiguration' --output json)

aws ecs run-task --profile nexus --region eu-south-2 \
  --cluster nexus-$ENV --task-definition nexus-$ENV-scheduler \
  --launch-type FARGATE --started-by ops-dlq \
  --network-configuration "$NET" \
  --overrides '{"containerOverrides":[{"name":"scheduler","command":["python","-m","nexus_worker.ops.dlq","list"]}]}' \
  --query 'tasks[0].taskArn' --output text
```

El flujo de registros es `scheduler/scheduler/<id de la tarea>`, en `/nexus/<entorno>/scheduler`.

## Lo que este documento no cubre

Hay otras colas muertas sin aviso ni salida: `nexus:usage:dlq` (consumo), `nexus:billing:events:dlq` (facturación) y `<stream>:dlq` de `meta_coexistence.py`. La herramienta no las toca: reinyectar dinero no es lo mismo que reinyectar un mensaje.
