# Bug Assessment: un cliente final puede hacerse programar recordatorios de pago sin tope

- **Slug**: recordatorios-sin-tope
- **Created**: 2026-10-22
- **Source**: pasted text (apéndice del `/cso --diff` de las specs 043/045, 2026-10-22,
  confianza 5, por debajo del umbral del informe)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> `notification.schedule_reminder` has no cap on how many reminders one end
> customer can get scheduled, how far ahead, or which WhatsApp templates (paid
> sends) it may use. Since el-recordatorio-programado-no-sale was fixed the
> reminders really go out, so an end customer can prompt the agent into many
> paid template sends to themselves.

La entrega de consolas-web lo dejó en «Para después»: «`notification.schedule_reminder`
no tiene tope de cantidad ni de plantillas (el bug del recordatorio lo hace
funcionar)».

## Symptom

Un cliente final que escribe al agente puede pedirle «recuérdame esto cada
hora», «mándame un recordatorio por cada día del año» o «prográmame la
plantilla de la promo para mañana», y la herramienta acepta cualquier número de
recordatorios, a cualquier fecha y con cualquier plantilla. Cada recordatorio
que sale es una plantilla de WhatsApp que Meta cobra al negocio por mensaje
(los recordatorios casi siempre salen fuera de la ventana de 24 h, donde
también se cobran las de utilidad; las de marketing se cobran siempre).

Lo esperado: un tope por cliente y por día, un horizonte máximo y una lista de
plantillas que el negocio permite usar como recordatorio. Pasado cualquiera de
los tres, la herramienta se niega con un error que el agente puede explicar.

## Reproduction

1. Un tenant con `notification.schedule_reminder` entre las herramientas del
   agente (las semillas de barbería, dental, clínica, spa, etc. la traen como
   requerida).
2. El cliente pide N recordatorios. El agente llama N veces a
   `notification.schedule_reminder` con `run_at` arbitrario (también a 5 años)
   y `template_name` arbitrario (también una plantilla de marketing o de
   cobranza).
3. Resultado: N filas `scheduled_jobs(kind='reminder', status='pending')`. Con el
   arreglo de `el-recordatorio-programado-no-sale` (rama de consolas-web) el
   cron las despacha a su hora → N envíos de plantilla facturados.

Comprobado en código; no hace falta ejecución para verlo: `ScheduleReminder.run`
no consulta nada antes de insertar.

## Suspected Code Paths

- `apps/mcp/src/nexus_mcp/servers/notification/tools.py:494-531` —
  `ScheduleReminder.run` solo comprueba que la conversación exista e inserta la
  fila. Sin recuento, sin horizonte, sin lista de plantillas.
- `apps/mcp/src/nexus_mcp/servers/notification/schemas.py:52-59` —
  `ScheduleReminderInput`: `run_at` sin límites y `template_name` libre
  (1–120 caracteres).
- `apps/worker/src/nexus_worker/streams/reminder_cron.py` — despacha todo lo
  vencido sin mirar cuántos van para el mismo cliente. No es donde va el
  arreglo: el cron no conoce la intención y aplicar el tope ahí descartaría
  recordatorios que el agente ya confirmó al cliente.

## Root Cause Hypothesis

La herramienta nació (bloque D) como persistencia pura, cuando el cron no
existía y luego no funcionaba; nadie llegó a pagar por un recordatorio, así que
el abuso no tenía coste. Con el cron arreglado, la decisión de gastar la toma el
LLM a petición de quien escribe, que es justo la parte que no es de confianza.
**Confianza: alta.**

## Proposed Remediation

**Preferred**: tres guardas en la herramienta, antes de insertar, configurables
por agente en `policies.scheduled_reminders` del agente que contesta en el
número de la conversación (la misma resolución que `payments.request_review`:
`agent_for_channel` + versión activa).

```json
"scheduled_reminders": {
  "templates": ["recordatorio_cita"],
  "max_per_customer_per_day": 3,
  "max_days_ahead": 30
}
```

1. **Plantillas**: `template_name` debe estar en `templates`. Sin la clave o con
   la lista vacía, la herramienta se niega («este negocio no tiene plantillas de
   recordatorio activadas»). Falla cerrado.
2. **Por cliente y día**: como mucho `max_per_customer_per_day` recordatorios
   programados para el mismo cliente (`conversations.customer_id`, todas sus
   conversaciones) en las últimas 24 h móviles, contados por `created_at`. Los
   cancelados no cuentan: no salen. Defecto 3, techo duro 10.
3. **Horizonte**: `run_at` como mucho `max_days_ahead` días en el futuro.
   Defecto 30, techo duro 365.
4. El recuento va bajo `pg_advisory_xact_lock` por (tenant, cliente), como el
   tope de companion: sin él, dos llamadas simultáneas leen el mismo recuento y
   pasan las dos.
5. La descripción de la herramienta enuncia los límites para que el agente no
   los descubra a golpe de error, y cada error dice qué hacer.

**Alternatives**:
- *Lista derivada de Meta (solo plantillas de categoría UTILITY aprobadas en la
  WABA del tenant), sin configuración.* Ataría la herramienta a una llamada a la
  Graph API en cada programación, y el espejo local `whatsapp_template_status`
  no guarda la categoría (el webhook no la trae). Además seguiría permitiendo
  programar una plantilla de cobranza o de reservas como «recordatorio».
- *Columna nueva en `tenants`.* Exige migración mientras 031/043 añaden las
  suyas en paralelo (choque de cabezas de alembic) y una pantalla para
  editarla. `policies` ya es el sitio de la configuración por agente
  (`payment_review`, `reminders` de cobranza, `booking.max_advance_days`).
- *Topar en el cron.* Ver arriba: el cliente ya oyó «te lo recuerdo».

**Files likely to change**:
- `apps/mcp/src/nexus_mcp/servers/notification/tools.py`
- `apps/api/tests/integration/mcp/test_schedule_reminder_limits.py` (nuevo)
- `apps/api/tests/integration/mcp/test_servers_happy_path.py` (sus dos usos de
  la herramienta necesitan la política)

**Tests to add or update**:
- Sin política → se niega y no escribe fila.
- Plantilla fuera de la lista → se niega; dentro → se programa.
- `run_at` a 31 días con el defecto → se niega; con `max_days_ahead: 180`, a
  90 días → se programa; `max_days_ahead: 5000` se queda en 365.
- Cuarto recordatorio del mismo cliente en 24 h → se niega; cuenta las otras
  conversaciones del cliente; los cancelados y los de hace más de 24 h no
  cuentan; otro cliente no se ve afectado; `max_per_customer_per_day: 1000` se
  queda en 10.
- Dos programaciones simultáneas con un hueco libre → solo una pasa.
- Política del agente asignado al número, no la del principal.

## Decisión (dueño: Luis)

Tomada con criterio propio según su pauta de avanzar sin aprobaciones
intermedias; queda para su revisión al final. Lo que más conviene que confirme
es el punto 1:

- **Falla cerrado sin lista.** Ningún recordatorio de agente ha salido nunca en
  producción (el cron los marcaba `FAILED`), así que no se rompe nada que hoy
  funcione; y cada plantilla de recordatorio hay que crearla y aprobarla en Meta
  para la WABA del cliente de todas formas: nombrarla en la política es parte de
  ese mismo alta. Un nombre por defecto en código sería adivinar uno que quizá
  no existe en su WABA.
- **3 al día por cliente.** Una cita pide dos (24 h y 1 h antes); una
  reprogramación cancela esas dos y crea otras dos, que no suman porque los
  cancelados no cuentan.
- **30 días.** Igual que `booking.max_advance_days` de las semillas. Una
  clínica con controles a 6 meses lo sube en su política; el techo de 365
  acota una política mal escrita.
- **Pasado permitido.** Un `run_at` ya vencido sale en el siguiente tick, como
  hoy; prohibirlo rompería el caso de la cita a menos de 24 h y el tope diario
  ya lo acota.

## Risks & Considerations

- **Al fusionar con la rama de consolas-web** (`agitated-robinson-dd06ff`): su
  `test_reminder_scheduled_by_the_tool_is_sent` programa con la herramienta sin
  política y pasará a fallar. Arreglo de cinco líneas: sembrar
  `policies.scheduled_reminders.templates` con su plantilla.
- Tras fusionar, ningún tenant envía recordatorios de agente hasta que se le
  configure la lista. No hay pantalla para `policies.scheduled_reminders`: se
  pone por la API de versiones de agente. Pendiente de producto.
- **Hallazgo relacionado, fuera de alcance**: `notification.send_template`
  también está entre las herramientas requeridas de las semillas y no tiene ni
  lista ni tope. Dentro de la ventana de 24 h las plantillas de utilidad son
  gratis, pero las de marketing se cobran: el mismo abuso, más estrecho.
- El tope es por cliente: quien controle muchos números puede multiplicarlo,
  pero cada número tiene que escribir primero (y eso ya cuesta al atacante y
  pasa por el medidor).

## Open Questions

Ninguna bloqueante. La decisión de arriba queda para revisión del dueño.
