# Contrato 043: procesos del worker, avisos y plantillas

**Estado: congelado el 2026-10-22.**

## Crons (familia `scheduler`, contrato de nombres)

Se declaran en `SCHEDULER_TASK_NAMES` y en `scheduler_tasks()` de
`apps/worker/src/nexus_worker/bootstrap.py`, y en `ALL_EXPECTED` de
`apps/worker/tests/unit/test_bootstrap_split.py`. Todos recorren clientes con
`reservation_settings`, cada uno en su `tenant_scoped_session`, con
`FOR UPDATE SKIP LOCKED`.

| Nombre | Tick | Qué hace |
|---|---|---|
| `reservations-cron` | 60 s | (1) encola confirmación/recordatorio a su hora; (2) Aforo: libera las no confirmadas 1 h antes; (3) pasa a `done` lo terminado; (4) caduca entradas de la lista; (5) abre ofertas de Aforo cuando hay sitio y gente que cabe |
| `reservation-outbox-cron` | 10 s | Envía `reservation_outbox`: texto dentro de la ventana de 24 h, plantilla aprobada fuera; sin plantilla o sin teléfono, `skipped` y evento `notify_failed` |
| `reservation-offers-cron` | 15 s | Avanza candidatos al vencer su plazo; cierra ofertas vacías |
| `reservation-calendar-cron` (P3) | 120 s | Lee el ocupado de Google Calendar y escribe los «Ocupado» |

Idempotencia: cada envío tiene `dedupe_key` único (`reminder:{reservation_id}`,
`ask:{reservation_id}:{n}`, `moved:{reservation_id}:{version}`…); cada
transición automática comprueba el estado dentro del candado.

## Cuándo sale cada mensaje al cliente final

| `kind` | Cuándo | Plantilla fuera de 24 h |
|---|---|---|
| `confirmation` | El negocio crea una reserva con teléfono y «avisar» | `reserva_confirmada` |
| `ask_confirmation` | Servicios: 24 h antes si `confirm_enabled` · Aforo: según `confirm_when`. También «Pedir confirmación» a mano | `reserva_pide_confirmacion` |
| `reminder` | Servicios: 24 h antes si `reminder_enabled` y no se pidió confirmación (si se pidió, ese mensaje ya recuerda) | `reserva_recordatorio` |
| `moved` | El negocio la mueve con «avisar» | `reserva_cambiada` |
| `cancelled` | El negocio o el sistema la cancela con «avisar» (incluido el cambio de modo y «liberar») | `reserva_cancelada` |
| `offer` | Oferta de la lista de espera | `reserva_hueco_libre` |
| `offer_won` / `offer_lost` | Respuesta a quien aceptó (le tocó / respondió tarde) | `reserva_confirmada` / sin plantilla (va en la ventana: la persona acaba de escribir) |

Lo que el agente reserva en la conversación lo confirma el propio agente en su
respuesta: no se encola `confirmation`.

## Plantillas

Las aprueba Meta en el número de cada cliente; las da de alta el partner (o
Auphere) como cualquier plantilla de utilidad. Idioma `es`. Variables con
nombre:

| Nombre | Variables (BODY) | Texto de partida |
|---|---|---|
| `reserva_confirmada` | `nombre`, `negocio`, `cuando`, `detalle` | «Hola, {{nombre}}. Tu reserva en {{negocio}} quedó para {{cuando}} ({{detalle}}). Si necesitas cambiarla, escríbenos por aquí.» |
| `reserva_pide_confirmacion` | `nombre`, `negocio`, `cuando`, `detalle` | «Hola, {{nombre}}. Te esperamos en {{negocio}} {{cuando}} ({{detalle}}). ¿Nos confirmas que vienes? Responde SÍ o NO.» |
| `reserva_recordatorio` | `nombre`, `negocio`, `cuando`, `detalle` | «Hola, {{nombre}}. Te recordamos tu reserva en {{negocio}} {{cuando}} ({{detalle}}).» |
| `reserva_cambiada` | `nombre`, `negocio`, `cuando`, `detalle` | «Hola, {{nombre}}. Tu reserva en {{negocio}} cambió: ahora es {{cuando}} ({{detalle}}).» |
| `reserva_cancelada` | `nombre`, `negocio`, `cuando` | «Hola, {{nombre}}. Tu reserva en {{negocio}} para {{cuando}} quedó cancelada. Si quieres otra hora, escríbenos por aquí.» |
| `reserva_hueco_libre` | `nombre`, `negocio`, `cuando`, `detalle`, `minutos` | «Mensaje automático de {{negocio}}: se liberó un hueco {{cuando}} ({{detalle}}). ¿Lo quieres? Responde SÍ en los próximos {{minutos}} minutos y te lo reservamos.» |

`detalle`: Servicios «Corte con Lucía»; Aforo «4 personas» (con la palabra del
tipo). `cuando`: «el jueves 23 a las 20:30».

## Push al negocio (spec 031 + 045)

Tipos nuevos en `NOTICE_KINDS` y en los CHECK de `client_phones.notice_kinds`
y `client_push_events.kind`: `reservas.agent_change`, `reservas.cancelled_today`,
`reservas.waitlist_accepted`. `push_fanout._targets` exige el módulo `reservas`
para ellos. `dedupe_key`: `reservas.agent_change:{reservation_id}:{version}`,
`reservas.cancelled_today:{reservation_id}`, `reservas.waitlist_accepted:{offer_id}`.

Entrega (`services/push_payloads.KIND_CONFIG`): los tres salen por el canal de
Android `reservations_v1` y la categoría de iOS `reservations`, los que crea la
app; interrupción `active`. Prioridad de FCM `high` para `agent_change` y
`cancelled_today`, `normal` para `waitlist_accepted`. Ruta del aviso:
`auphere-customers://reservas/{booking_id}`.

Textos (`services/push_texts.py`), sin nombre del cliente final:

| Tipo | Título | Cuerpo |
|---|---|---|
| `reservas.agent_change` | «Reserva nueva» / «Reserva cambiada» | «El agente reservó para el jueves 23 a las 20:30 · 4 personas» |
| `reservas.cancelled_today` | «Cancelación de hoy» | «Se liberó la reserva de las 20:30 · 4 personas» |
| `reservas.waitlist_accepted` | «Lista de espera» | «Alguien aceptó el hueco de las 10:00» |
