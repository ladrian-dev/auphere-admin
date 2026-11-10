# Research: La pausa respeta la audiencia

Spec: [spec.md](spec.md). Leído contra `develop` (`10897b90`) el 2026-11-10.

## Lo que hace hoy el código

- `gate_for` (`apps/worker/src/nexus_worker/runtime/dispatcher.py`) devuelve la
  primera puerta que cierra, en este orden:
  1. cliente en pausa, archivado o en alta;
  2. canal en pausa;
  3. canal desconectado;
  4. número solo de envío;
  5. sin versión publicada;
  6. agente en pausa;
  7. **fuera de la audiencia**;
  8. una persona tomó el control.

  La bolsa, el modelo y el presupuesto se miran después (`money_and_model_gate`).
- `out_of_audience` se calcula en `_load_turn` en cada turno, pase lo que pase con
  las demás puertas: `audience_suppresses(gate_audience(canal), policies, remitente)`.
  `policies` es la de la versión `ACTIVE` del agente del turno, también si el
  agente está en pausa (la pausa vive en `agents.lifecycle`, no en la versión).
- `_apply_gate` con `out_of_audience` hace tres cosas:
  - marca los mensajes `skipped_reason = "not_admin"`;
  - no los marca atendidos;
  - llama a `mark_waiting_reason`, que guarda el motivo sin abrir espera
    (`NOT_WAITING`) y no devuelve marca, así que no sale ningún aviso.

  Tampoco hay mensaje de espera ni aviso a los destinatarios de escalado.
- La API ya decide la audiencia **antes** que el estado del cliente para los
  acuses de lectura (`webhooks/meta.py`, `read_receipt_suppressed_not_admin`).
  Solo el canal en pausa va antes.

## D1 — Dónde va la puerta de audiencia

**Decisión**: primera en `gate_for`, salvo en un número solo de envío:
`if facts.out_of_audience and not facts.send_only_channel`. Se quita la
comprobación que iba detrás del agente en pausa, porque ya no la alcanza nadie.
El resto del orden no cambia.

**Por qué**: es el cambio más pequeño que cumple el requisito 1. Las puertas de
estado conservan su orden entre ellas. Un número solo de envío queda exactamente
como hoy (requisito 1.7). La primera condición protege a New Air, que vive en
producción con un número solo de envío: sus entrantes siguen dando
`send_only_channel` y no `not_admin`.

**Alternativas descartadas**:
- *Audiencia primera también para los números solo de envío.* Cambiaría la
  etiqueta y el motivo guardado de New Air y de la línea de avisos de Mouna. La
  spec no lo pide.
- *Dejar el orden y silenciar los avisos en `_apply_gate` cuando el contacto está
  fuera.* La conversación seguiría con el motivo falso (`paused_client`) y
  seguiría siendo «Espera a una persona». Esconde el síntoma y deja la causa.

## D2 — Los códigos de log y de resultado

Con el contacto fuera de la audiencia, la puerta es la de siempre:
`Gate("not_admin", "out_of_audience")`. Los logs pasan de
`pipeline.skipped.tenant_inactive` (u otra puerta de estado) a
`pipeline.skipped.not_admin`. Ningún panel ni alarma cuenta `tenant_inactive`,
porque `infra/` y las alarmas de la plataforma no lo nombran. El cambio es
visible y no rompe nada.

**El aviso de «sin saldo» del cliente** (`client.out_of_quota`) también lo
dispara un turno saltado con motivo `no_balance`. Hoy lo hace también cuando el
contacto está fuera de la audiencia pero el agente está pausado por saldo. Con la
058, ese turno ya no lo dispara, igual que hoy con la bolsa vacía sin pausa,
donde la audiencia ya iba antes. No se pierde: el cron de avisos de la bolsa es
la red de seguridad (spec 016, R2.2, `wallet_alerts`, «si el despachador no llegó
a avisar, lo hace el cron»), y con bolsas el aviso es `client.wallet.empty`, que
no nace de ningún mensaje.

## D3 — Liberar una espera que ya no es cierta (requisito 2)

**Decisión**: una función nueva, `inbox_lifecycle.leave_gate_wait(session,
conversation) -> bool`, que `_apply_gate` llama antes de `mark_waiting_reason`
cuando el motivo es `out_of_audience`. Libera solo si se cumplen tres cosas:
- `status == escalated`;
- `waiting_reason ∈ GATE_REASONS`;
- `assigned_user_id is None`.

Al liberar:
- pone `status = open`;
- graba el evento `released` con `{"why": "out_of_audience", "reason": <anterior>}`;
- devuelve `True`.

Después del commit, `_apply_gate` cierra el aviso pendiente con
`mark_waiting_handled(tenant_id, [conversation_id])` (spec 056) y publica
`conversation.updated` para que la Bandeja se refresque en vivo.

`mark_waiting_reason` gana una guarda, igual que la que ya tiene
`human_takeover`: con `out_of_audience` y la conversación todavía en
`escalated` (no se liberó), **no** cambia el motivo. Hoy lo sobrescribe, y la
Bandeja se queda con una espera cuyo motivo no tiene texto (requisito 2.2).

**Por qué respetar `assigned_user_id`**: es la regla de
`release_escalated_for_tenant` (spec 056): lo que una persona tomó a mano no se
lo quita el sistema.

**Alternativa descartada**: reutilizar `release_reason`, que libera cuando el
agente vuelve a contestar. Esa función pone `waiting_reason = None`, no comprueba
la asignación y el evento dice `gate_open`, que aquí sería falso: la puerta no se
ha abierto.

## D4 — La limpieza (requisito 3)

**Decisión**: una herramienta de operador, no un paso del despliegue.
- El servicio va en `nexus_api.services.audience_cleanup`, con
  `run(factory, *, apply: bool) -> Summary`.
- El guion va en `apps/api/scripts/release_out_of_audience_waits.py`, en seco por
  defecto y con `--apply` para escribir.
- `release.sh` no lo llama (requisito 3.6).

**Cómo**:
- Recorre los tenants (tabla de plataforma, como `auto_pass.run`). Cada uno va en
  su propia transacción bajo `tenant_scoped_session`, y uno que falla se revierte
  solo.
- Para cada conversación `escalated` con `waiting_reason ∈ GATE_REASONS` y sin
  asignar:
  - lee `gate_audience(session, channel_id)`;
  - **solo si `strict`** (requisito 3.3), mira
    `audience_suppresses(audience, None, customer.identifier)`;
  - si está fuera, aplica `leave_gate_wait` y fija `waiting_reason =
    "out_of_audience"`, lo mismo que haría el turno.
- Tras el commit de cada tenant, llama a `mark_waiting_handled(tenant_id, ids)`.
- Logs, sin datos del contacto:
  - por tenant, `inbox.audience_cleanup.tenant` con `tenant_id`, `apply` y
    `released` (o `would_release`);
  - al final, `inbox.audience_cleanup.done` con los totales.
- Va a la base **directa**, como `pass_booking_to_reservas.py`
  (`get_direct_engine`), porque en una tarea suelta el nombre del pooler no
  resuelve.

**Por qué a mano**: el 2026-11-10 Luis quitó del despliegue el paso automático a
Reservas, porque nada debe cambiar el estado de un cliente sin una acción humana
(memoria «Reservas solo a mano»). Esta limpieza solo saca conversaciones de la
Bandeja, pero se ejecuta una vez y la pasada en seco deja ver el resultado antes
de escribir. La pasada en seco es el paso seguro.

**Por qué solo los números con audiencia propia**: en los demás, la audiencia
depende de la política del agente que lleva la conversación, y ese agente puede
ser el destino de una derivación de Recepción (`reception.current_handler`, que
además actualiza estado). Fuera de un turno no se puede saber sin efectos. Todos
los números de WhatsApp, Instagram y Messenger de los partners con la consola
nueva son `strict`, y desde la migración 0204 lo son todos los partners. Flor y
Encanto entra.

**Alternativas descartadas**:
- *Migración de datos.* La audiencia compara teléfonos por sufijo de dígitos
  (`admin_gate._phone_matches`), lo que en SQL es frágil. Además, una migración
  no tiene pasada en seco.
- *Paso en `release.sh`.* Va contra la decisión del 2026-11-10.

## D5 — Hueco anotado, fuera de alcance

Un número **solo de envío** de un cliente **en pausa** también pasa a la Bandeja
y avisa (`paused_client`), porque la pausa del cliente va antes que la puerta de
solo envío. Según la spec 045, a ese número no lo atiende nadie. Es el mismo tipo
de hueco que esta spec, pero nadie lo ha pedido y ningún cliente de producción
está así: New Air y la línea de Mouna están activos. Queda aquí para quien lo
retome. El arreglo sería subir `send_only_channel` por delante de las puertas de
estado.

## D6 — Spec viva

- `docs/consola-lite.md`, «Lo que la spec 047 cambió aquí (ola 1)»: añadir que la
  audiencia se decide antes que cualquier pausa y que una espera de puerta se
  libera cuando el contacto queda fuera.
- `specs/047-la-fabrica-de-agentes/contracts/events.md` §2: una línea que diga que
  `out_of_audience` gana a los motivos de puerta (spec 058).
- `apps/api/RUNBOOK.md`: cómo lanzar la limpieza en staging y en producción.

## D7 — Dependencias y gasto

Ninguna dependencia nueva. No hay llamadas al modelo ni a herramientas de pago.
