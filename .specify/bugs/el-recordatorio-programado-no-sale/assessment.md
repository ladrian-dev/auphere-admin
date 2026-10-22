# Bug Assessment: el recordatorio que programa el agente nunca sale

- **Slug**: el-recordatorio-programado-no-sale
- **Created**: 2026-10-22
- **Source**: pasted text (lectura de dominio de Reservas, KB
  `research/2026-10-22-reservas-y-consola-customers/lecturas/reservas-dominio.md` §7.3.2)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> Recordatorios que no salen (probable). `notification.schedule_reminder` guarda
> `template_name` (`apps/mcp/src/nexus_mcp/servers/notification/tools.py:519`),
> pero `apps/worker/src/nexus_worker/streams/reminder_cron.py:119` lee
> `template`, así que el job acaba en `FAILED`. La prueba
> (`apps/api/tests/integration/channels/test_reminder_cron.py:41`) siembra
> `template` a mano y no lo detecta.

## Symptom

Todo recordatorio que el agente programa con `notification.schedule_reminder`
llega a su hora y el cron lo marca `FAILED` con «payload missing 'template'
and/or 'conversation_id'». El cliente final no recibe nada y nadie se entera:
no hay aviso, solo una fila fallida en `scheduled_jobs`.

Lo esperado: a su hora, el cron envía la plantilla con los parámetros que el
agente eligió.

## Reproduction

1. El agente llama a `notification.schedule_reminder` con
   `template_name="reminder_24h"`, `parameters={"name": "Ana"}` y `run_at` en el
   pasado inmediato.
2. Corre un tick de `reminder_cron._process_pending`.
3. Resultado: el job pasa a `FAILED`, sin mensaje saliente.

La prueba existente no lo ve porque siembra el payload a mano con las claves que
el cron espera (`template`, `params`, `language`), no con las que escribe la
herramienta.

## Suspected Code Paths

- `apps/mcp/src/nexus_mcp/servers/notification/tools.py:513-518` — escribe
  `template_name` y `parameters`.
- `apps/worker/src/nexus_worker/streams/reminder_cron.py:118-129` — lee
  `template` y `params`/`parameters`; ignora `language`.
- `apps/api/tests/integration/channels/test_reminder_cron.py:30-55` — siembra
  la forma del cron, no la de la herramienta.

## Root Cause Hypothesis

Dos piezas escritas por separado (bloque D la herramienta, bloque F el cron)
con nombres distintos para la misma clave, y una prueba del cron que fija la
forma del cron en vez de la del productor. **Confianza: alta.**

## Proposed Remediation

**Preferred**: el cron lee lo que escribe el productor.

1. `reminder_cron._dispatch_one` lee `template_name` (la clave que escribe la
   herramienta) y, por compatibilidad con filas antiguas o sembradas a mano,
   `template`; los parámetros de `parameters` o `params`; y pasa `language` si
   viene.
2. Una constante compartida con las claves del payload, para que productor y
   consumidor no puedan volver a divergir sin que una prueba lo vea.
3. La prueba nueva programa el recordatorio **con la herramienta** y deja que lo
   envíe el cron.

**Alternatives**:
- *Cambiar la herramienta para que escriba `template`.* Arregla las filas
  nuevas, pero las pendientes ya guardadas con `template_name` seguirían
  fallando; y el nombre de la herramienta (`template_name`) es el del resto de
  la API.

**Files likely to change**:
- `apps/worker/src/nexus_worker/streams/reminder_cron.py`
- `apps/api/tests/integration/channels/test_reminder_cron.py`

**Tests to add or update**:
- Integración: `schedule_reminder` + un tick del cron → `SENT` y una fila
  saliente con `template_payload` de la plantilla y los parámetros pedidos.
- La forma antigua (`template`/`params`/`language`) sigue enviándose.

## Risks & Considerations

- **No se reenvían los fallidos.** Todo recordatorio que falló por esto ya había
  vencido (el cron solo toca los vencidos): enviarlo tarde sería peor que no
  enviarlo. Se deja como está.
- **Hallazgo relacionado, fuera de alcance**: un job que falla al despachar
  suma `attempts` y se reintenta cada 30 s sin tope. Lo recoge la spec 043, que
  construye los recordatorios de Reservas sobre este cron.

## Open Questions

Ninguna.
