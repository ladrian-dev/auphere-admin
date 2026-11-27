# Fase 1 — el modelo

Migración **0245**. Dos tablas nuevas por cliente, cuatro listas que crecen y una función de descubrimiento.

## `schedules` — la rutina

Lo que el partner configura una vez.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **La columna por la que la alcanza la RLS.** |
| `agent_id` | uuid | |
| `name` | varchar(60) | Obligatorio (requisito 2.1). |
| `instruction` | text | Obligatorio, tope de 2.000 por `CHECK`. |
| `cadence` | varchar(16) | `daily · weekly · monthly · once`. |
| `weekdays` | smallint[] | Solo `weekly`. **Lunes 0, domingo 6**: la convención de `datetime.weekday()` y de `WEEKDAYS` en `services/business_hours.py`. La maqueta numera al revés porque es JavaScript, así que la consola traduce al enviar y al pintar. |
| `day_of_month` | smallint | Solo `monthly`. `CHECK` entre 1 y 28 (requisito 3.1). |
| `run_date` | date | Solo `once`. |
| `local_time` | time | La hora del negocio. **Sin zona**: la zona se lee de `tenants.timezone` al calcular, no se duplica aquí. |
| `email` | boolean | Si además sale por correo (requisito 10.3). |
| `state` | varchar(16) | `active · paused · archived`. Es la intención del partner, no el estado efectivo. |
| `pause_reason` | varchar(32) | `manual · agent_unavailable · no_balance · failures`. Nulo si no está pausada. |
| `next_run_at` | timestamptz | Materializado. Nulo cuando no hay próxima. |
| `consecutive_failures` | smallint | Cuenta **ejecuciones**, nunca intentos (requisito 7.5). A cero en cuanto una acaba bien. |
| `created_by` | varchar(160) | La persona. Es a quien le llega el correo. |
| `created_at`, `updated_at` | timestamptz | |

**Restricciones**

- `FORCE ROW LEVEL SECURITY`, con la política por `tenant_id` de siempre.
- `UNIQUE (tenant_id, id)`, para que otras tablas puedan apuntar con clave compuesta.
- `FOREIGN KEY (tenant_id, agent_id) → agents(tenant_id, id) ON DELETE CASCADE`: una rutina no puede apuntar al agente de otro cliente (requisito 1.1).
- `CHECK` de coherencia por periodicidad: `weekly` exige al menos un día, `monthly` exige `day_of_month`, `once` exige `run_date`, y las columnas que no son de esa periodicidad van nulas.
- `CHECK (state <> 'paused' OR pause_reason IS NOT NULL)`: una pausa sin motivo no se guarda.

**Índices**

- `(tenant_id, agent_id)` para la pestaña Rutinas de la ficha del agente.
- **Parcial** sobre `next_run_at` `WHERE state = 'active' AND next_run_at IS NOT NULL`: es el que sostiene el barrido.

## `schedule_runs` — la ejecución

Una fila por vez que la rutina corre, con sus intentos dentro.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid | |
| `tenant_id` | uuid | **La columna de la RLS.** |
| `schedule_id` | uuid | |
| `scheduled_for` | timestamptz | La hora que le tocaba, en absoluto. |
| `trigger` | varchar(16) | `schedule · manual`, para distinguir «Ejecutar ahora» (requisito 6.2). |
| `status` | varchar(16) | `running · done · partial · failed · skipped`. |
| `attempts` | smallint | Hasta 3 (requisito 7.2). |
| `instruction` | text | **La instrucción con la que se ejecutó**, no la de ahora (requisito 15.2). |
| `answer` | text | La respuesta, como texto legible. |
| `tools_used` | jsonb | Lo que usó, para pintarlo en el hilo. |
| `withheld` | jsonb | Lo que no se pudo ofrecer y por qué. Es lo que hace honesto el estado `partial`. |
| `duration_ms` | integer | |
| `cost_micros` | bigint | Cien milésimas de USD, como la cola de trabajos. |
| `error_code`, `error_detail` | varchar(64), text | Solo si falló. |
| `job_id` | uuid | El trabajo del intento en curso. |
| `started_at`, `finished_at` | timestamptz | |

**Restricciones**

- `FORCE ROW LEVEL SECURITY`.
- `FOREIGN KEY (tenant_id, schedule_id) → schedules(tenant_id, id) ON DELETE CASCADE`.
- **`UNIQUE (tenant_id, schedule_id, scheduled_for)`**: lo que impide que dos réplicas disparen la misma ejecución (requisito 7.7). Las manuales llevan su propio instante, así que no chocan.
- `CHECK ((status IN ('done','partial','failed','skipped')) = (finished_at IS NOT NULL))`.
- `CHECK (status <> 'failed' OR error_code IS NOT NULL)`, igual que los trabajos.
- `CHECK (status <> 'partial' OR withheld IS NOT NULL)`: parcial sin decir qué faltó no se guarda.

**Índice**: `(tenant_id, schedule_id, scheduled_for DESC)`, que es como se lee el hilo.

**Retención**: la misma ventana que los mensajes (requisito 12.2). La técnica la elige quien implemente: la tabla es pequeña y un borrado por lotes basta, pero eso se decide en `tasks.md`, no aquí.

## Lo que crece en lo que ya existe

| Dónde | Qué se añade |
|---|---|
| `ck_jobs_kind` | `schedule_run`, y `JOB_KINDS` en `db/models/jobs.py`. |
| `ck_usage_source` | `schedule`, y la entrada `"schedule": "schedules"` en `USAGE_LINE_BY_SOURCE`. |
| `ck_client_wallet_entries_kind` | `debit_schedule`, y `SPEND_KINDS` en `services/wallet/bags.py`. |
| `usage_lines.py` | La partida `schedules` en `LINES`, con `PAYER` a `client_bag` y su asiento en `_BAG_ENTRY`. |
| `NotificationKind` | `schedule.run.done`, `schedule.run.partial`, `schedule.run.failed` y `schedule.paused`. |
| `PERMISSIONS` (`core/console_auth.py`) | `schedules:read` y `schedules:write`, con los mismos roles que hoy tienen `agents:read` y `agents:write`. |

Ninguna de estas listas obliga a tocar datos existentes: todas son ampliaciones de un `CHECK` o de una constante.

## La función del barrido

```sql
due_schedules(limit integer)
  RETURNS TABLE (tenant_id uuid, schedule_id uuid, scheduled_for timestamptz)
  SECURITY DEFINER
```

Devuelve las rutinas activas cuyo `next_run_at` ya venció, en orden de vencimiento. **Solo identificadores y horas**: ni instrucción, ni nombre, ni respuesta. A partir de ahí el disparador abre una transacción por ejecución con su cliente puesto, como hace el consumidor de la cola.

Es el mismo patrón que `job_tenant`, que ya existe para que la consola llegue a un trabajo por su id sin romper la RLS.

## Lo que no se guarda

- **Nada de ningún cliente final.** Una rutina no tiene conversación, ni contacto, ni teléfono. Si alguna vez una columna de estas tablas necesitara nombrar a una persona de fuera, es señal de que el diseño se torció.
- **La zona horaria**, que vive en la ficha del cliente y se lee al calcular.
- **El estado efectivo**, que se calcula cruzando el de la fila con el del agente y el saldo de la bolsa.
