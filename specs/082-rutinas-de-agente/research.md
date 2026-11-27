# Fase 0 — lo que ya existe y las decisiones de diseño

Levantamiento hecho el 2026-11-27 contra el repositorio, no de memoria. Cada afirmación lleva dónde se comprobó.

## 1. Lo que ya existe y se reutiliza

| Pieza | Dónde | Qué resuelve de esta spec |
|---|---|---|
| Cola de trabajos | `apps/api/src/nexus_api/db/models/jobs.py`, `apps/worker/src/nexus_worker/jobs/` | El ejecutor. Una fila por trabajo, RLS por cliente, clave compuesta al agente, latido, caducidad perezosa y `cost_micros`. Una ejecución de rutina es un `kind` más. |
| Cobro a la bolsa | `services/wallet/bags.py:545`, `services/wallet/turns.py` | `debit_turn` ya recibe el `kind` del asiento y la misma `usage_ref` no cobra dos veces. `charge_tests` es el molde literal de `charge_schedule`. |
| Medidor por origen | `db/models/usage_record.py:128` | `USAGE_LINE_BY_SOURCE` reparte lo medido por partida. Un origen nuevo es una entrada más. |
| Partidas de Consumo | `services/wallet/usage_lines.py` | Las partidas que paga la bolsa no se calculan de lo medido: salen de los asientos de la bolsa. Rutinas se suma ahí. |
| Hora local del negocio | `streams/cobranza_reminder_cron.py`, `tenants.timezone` | La zona está en la ficha del cliente y ya hay un cron que dispara en hora local. |
| Pausa con motivo | `services/agent_states.py` | Distingue la pausa de una persona de la del sistema, y solo el sistema deshace la suya. El estado de la rutina se calca de aquí. |
| Permisos por conexión | `services/activations.py` | Tres valores por activación: solo leer, preguntar antes de escribir, y leer y escribir. Devuelve `ToolPolicy(blocked, needs_approval)`. |
| Aprobación durable | `services/tool_approvals.py` | «Preguntar antes de escribir» existe: hash de la acción, consulta al dueño y ejecución una sola vez al aprobar. |
| Avisos y correo | `db/models/console_notification.py`, `services/email_notices.py` | Vocabulario cerrado de avisos y una plantilla genérica de titular, frase y botón. |

## 2. El hueco: un turno de agente sin cliente final

**D1. El turno de rutina no reutiliza el grafo de conversación.**

El grafo (`runtime/pipeline.py`) está construido alrededor de una conversación: clasifica intención, enruta a `book | queue | info | escalate`, formatea burbujas de WhatsApp y puede escalar a una persona. `runtime/turns.py` agrupa entrantes y toma un candado por conversación. Nada de eso aplica a una rutina.

Lo que sí se reutiliza, pieza a pieza: el `AgentBundle` (`runtime/agent_loader.py`), la política de operador y el conocimiento (`runtime/console_context.py`), la resolución de modelo, el `dispatch` con lista blanca, y la contabilidad del turno.

*Alternativa descartada*: meter una rama más en el grafo. Se descartó porque obliga a que cada nodo sepa que puede no haber conversación, y el grafo es la pieza más cara de romper del sistema.

**D2. La frontera de herramientas no se inventa: ya está en el esquema.**

`_tool_requires_conversation` (`runtime/pipeline.py:1859`) mira si `conversation_id` está entre los obligatorios de la herramienta. En una rutina no hay conversación que inyectar, así que esas herramientas quedan fuera por construcción. Son, hoy, exactamente las que hablan con un cliente final: `escalate.*`, los diez `notification.send_*`, `payments.request_review` y `operator.consult_owner`.

Esto coincide con la frontera que el owner ya cerró cuando descartó la salida a WhatsApp, y refuerza la garantía 8 en vez de aflojarla.

**D3. Una rutina hereda el permiso de la activación, sin degradarlo ni ampliarlo** *(Pedro, 2026-11-27)*.

Lo que se ejecuta sale de `activations._load_tool_policy`: solo leer deja las de lectura, leer y escribir deja escribir.

**D4. Mientras no exista la pregunta desde la consola, lo que pide aprobación se trata como bloqueado, y la ejecución lo dice.**

`tool_approvals.gate` exige `conversation_id` y pregunta al dueño del negocio por su canal de avisos, leyendo «sí» o «no» de un mensaje. En una rutina no hay conversación, la pregunta tendría que ir a la consola y la respuesta sería un botón. Es una pieza con su propio diseño —a quién se le pregunta, cómo se congela y se reanuda la ejecución— y va en su spec.

Hasta entonces, en un turno de rutina `blocked` absorbe `needs_approval`, la ejecución queda `partial` y escribe qué no pudo hacer. Es la línea del plan con fecha de caducidad.

*Alternativa descartada*: callarlo. Un informe al que le falta una parte y no lo dice es peor que no tenerlo.

## 3. El disparador

**D5. Barrido por vencimiento, no recorrido por cliente.**

`next_run_at` se materializa en la fila al guardar y al cerrar cada ejecución. El cron lee lo vencido de un índice parcial y despacha.

*Alternativa descartada*: el patrón del cron de cobranza, que recorre cliente a cliente comparando su hora local. Sirve para un barrido diario con granularidad de hora. Aquí los tics son por minuto y el coste sería una consulta por cliente y por tic.

**D6. El descubrimiento va por una función `SECURITY DEFINER`.**

Con RLS forzada, una sesión sin cliente puesto no ve ninguna fila. La función devuelve `(tenant_id, schedule_id, scheduled_for)` de lo vencido y nada más: ni instrucción, ni respuestas, ni nombres. A partir de ahí, cada ejecución abre su transacción con su cliente puesto, como hace el consumidor de la cola.

Es el mismo patrón que `job_tenant`, que ya existe para que la consola llegue a un trabajo por su id.

**D7. Lo que impide el disparo doble es una clave única, no un candado.**

`UNIQUE (tenant_id, schedule_id, scheduled_for)` en `schedule_runs`. Dos réplicas que lleguen a la misma rutina en el mismo minuto intentan crear la misma fila y una de las dos pierde. El advisory lock de la familia del scheduler ya evita el caso normal: esto cubre el rollout, cuando hay dos réplicas a propósito.

**D8. El cambio de hora, resuelto en una función pura.**

`services/schedules/when.py`, sin base de datos, con `zoneinfo`:

- La hora local que **no existe** ese día (el reloj se adelanta) corre a la primera que sí existe.
- La hora local que **ocurre dos veces** (el reloj se atrasa) se ejecuta una sola vez: se toma el primer instante absoluto.
- Si el negocio cambia de zona, se recalcula `next_run_at` de sus rutinas.

Es la pieza con más casos límite y la más barata de probar, porque no toca nada.

## 4. Fallos, intentos y ejecuciones

**D9. El intento es un trabajo nuevo. La ejecución es la fila que los agrupa.**

La cola no reintenta un manejador que falló, y es deliberado: *«un trabajo cuesta dinero y su fallo suele repetirse»* (`jobs/consumer.py`). Lo único que reintenta sola es la reclamación de una réplica muerta.

Así que los tres intentos no van dentro del trabajo: cada intento es un trabajo nuevo encolado, y los tres cuelgan de la misma fila de `schedule_runs`, que es lo que el partner ve como una ejecución. El contador que pausa la rutina cuenta ejecuciones, nunca intentos.

**D10. La ventana de gracia es de una hora y manda sobre los intentos.**

Pasada la hora de la ejecución, no se lanza ningún intento más, queden o no. Nadie quiere a las dos de la tarde el informe de las nueve.

## 5. El estado de la rutina

**D11. El estado que se guarda es la intención del partner. Lo que se ve es el efectivo.**

En la fila viven `active | paused | archived` y, si está pausada, el motivo. El estado efectivo es ese cruzado con el del agente y con el saldo de la bolsa, y se calcula al leer. Una rutina de un agente en pausa no se ejecuta aunque su fila diga `active`.

Esto evita el problema de todo estado replicado: que el agente vuelva y la rutina se quede pegada en pausa porque nadie corrió el proceso que la despierta.

La pausa que pone una persona es distinta: esa se guarda con motivo `manual` y el sistema no la deshace, exactamente como ya se hace con los agentes.

## 6. El dinero

**D12. Un origen, una partida, un asiento.**

- `usage_records.source = "schedule"`, con su entrada en `USAGE_LINE_BY_SOURCE` apuntando a la partida `schedules`.
- Asiento `debit_schedule` en la bolsa, por `bags.debit_turn(kind=...)`, que ya acepta el parámetro.
- `charge_schedule` en `services/wallet/schedules.py`, calcado de `charge_tests`: **no suma al tope del agente**, porque ese tope habla de lo que gasta atendiendo, pero sí pausa a los agentes si la bolsa llega a cero, porque sin dinero no hay turno que cobrar.

**D13. La partida se ve siempre sobre la bolsa del cliente. En la pantalla de Consumo del partner, pendiente del owner.**

Es la marca de aclaración que la spec deja abierta (criterio 9.6). El diseño no cambia según la respuesta: `LINES` y `PAYER` crecen igual. Lo que cambia es si la pantalla la pinta.

## 7. La auditoría

**D14. No hace falta migración en `audit_log`.**

La tabla tiene `actor`, `action`, `target` y `after_json`. El origen de la acción y la rutina que la causó caben en `after_json`, y el `actor` sigue nombrando a la persona que creó la rutina, que es quien autorizó el permiso. Distinguir una escritura de rutina de una de conversación es una consulta sobre ese campo, no una columna nueva.

## 8. Lo que se miró y se dejó fuera

- **`nexus-scheduler` como servicio de horarios**: no lo es. Son unos 36 crons escritos a mano con su advisory lock. Sirve como sitio donde colgar el barrido, no como base.
- **La recurrencia de los packs UCM** (`packs/cron.py`): solo diaria, con ámbito de partner, y sus ejecuciones no las corre nadie. Ramal muerto, no se toca.
- **`scheduled_jobs`**: es una cola de un solo disparo por cliente, con su propio enum cerrado y su propio cron de recordatorios. Se podría haber colgado de ahí el preset «una vez», pero mezclaría dos ciclos de vida distintos en una tabla que ya tiene valores retirados que Postgres no deja quitar.
- **El mundo simulado** (`nexus_worker.simulation`): es lo que usan las pruebas y el playground. Una rutina es lo contrario: mundo real, herramientas reales.
