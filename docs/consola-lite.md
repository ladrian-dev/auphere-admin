# La consola lite — spec viva

> Qué existe hoy de la consola del **cliente final** dentro de `apps/console`
> y de `/console/lite/*` en `apps/api`. Nace con la spec
> [030](../specs/030-consola-lite-del-cliente/spec.md) y su porqué está en
> `kb/Auphere/nexus/decisions/ADR-041-consola-lite-del-cliente-final.md`. Se
> actualiza en el mismo commit que cambia lo que describe (constitución §IX).
>
> La misma consola en el teléfono —la app Auphere Customers, spec 031— se
> describe aparte: [app-movil.md](app-movil.md).

## Qué es

La misma consola de partners, abierta a un segundo tipo de persona: el
**usuario de cliente**, atado a un solo cliente (tenant) de un partner. Ve los
módulos que Auphere eligió para su cliente —Panel, Bandeja de entrada,
Consumo— y nada más.

## Acceso desde el admin

Pestaña **Acceso** en la ficha del tenant del admin
(`apps/admin/src/app/(dashboard)/tenants/[id]/access/`), sobre
`/admin/tenants/{tenant_id}/client-access` y `…/client-members`
(`api/admin/client_access.py` → `services/client_access.py`).

- **Elegible**: el tenant está en `partner_tenants` y no está archivado. Los
  directos de Auphere cuelgan de Auphere Internal Partner.
- **Módulos por cliente**: `panel`, `inbox`, `reservas`, `usage`, guardados en
  `client_access.modules` en el orden de la barra. Encendido exige al menos
  uno; la Bandeja exige un WhatsApp conectado **al elegirla**; Reservas exige
  el modo (Servicios o Aforo, y en Aforo el tipo de negocio) la primera vez, y
  cambiarlo con reservas vivas pide decidir qué pasa con ellas
  ([reservas.md](reservas.md#activarlo-panel-de-operador)).
- **Personas**: invitación de un solo uso (hash SHA-256, 21 días) por correo
  y también impresa al operador (`accept_path`). Reenviar retira el enlace
  anterior. Revocar a una persona o apagar el acceso **cierra sus sesiones**
  en la misma transacción.
- **Operador identificado**: cada llamada lleva `X-Operator-Id` (ADR-034); sin
  él, 400. La auditoría escribe `operator:<correo>` con el tenant del cliente,
  y la Auditoría del partner lo enseña como «Auphere».
- **Declara su cliente** (`declare_tenant`, `core/tenant_context.py`): las
  rutas usan la sesión de plataforma —leen `partner_tenants`, que la RLS
  escondería al rol `nexus_app`— y tocan tablas de cliente (`channels`,
  `conversations`). En producción la guarda de aislamiento corta esa consulta
  sin `app.tenant_id` y la pestaña daba 500 (bug `acceso-500-en-produccion`,
  2026-10-12); lo fija `tests/unit/test_admin_client_access_strict_isolation.py`
  con la guarda en modo de corte.
- Siembra local: `apps/api/scripts/dev_seed_client_access.py`.

## Identidad y frontera

- **Tablas propias** (migración 0147): `client_memberships` y
  `client_invitations`, hermanas de las del partner y separadas a propósito.
  Una cuenta es de un partner o de un cliente, nunca de los dos ni de dos
  clientes: lo comprueban la invitación y la aceptación (también la del
  partner) bajo un bloqueo consultivo por correo.
- **Dos puertas**: `require_console_principal` resuelve solo contra
  `partner_memberships`; `require_client_principal` (`core/client_auth.py`)
  solo contra `client_memberships`. El token es el mismo
  (`{sub, partner_id, role: "client"}`); el claim no decide, la tabla sí. No
  exige `partners.console_enabled`.
- **El cliente no es un argumento**: las rutas `/console/lite/*` no llevan
  `ref`; `lite_scope` (`api/console/lite/deps.py`) fija `app.tenant_id` desde
  la membresía.
- **La sesión distingue**: `PrincipalOut.kind` (`partner` | `client`),
  `client_name` y `modules`. En la consola, `Principal` es una unión
  (`PartnerPrincipal` | `ClientPrincipal`); cada página llama a
  `requirePartnerPrincipal` o `requireClientPrincipal(module)` (lo vigila
  `src/app/__tests__/page-guards.test.ts`), y `can()` responde `false` para
  `role: "client"`.
- **Sin pantalla intermedia** (T111): una persona de cliente que escribe a mano
  una ruta que no es suya va a su primer módulo **desde el layout** de
  `(console)`, antes de que empiece el stream (un 307 de verdad). El layout lee
  la ruta de `x-pathname`, que pone `proxy.ts` y que pisa lo que mande el
  navegador; la regla es `clientModuleOfPath` (`lib/principal-access.ts`), y
  el barrido de páginas la ata a las que llaman a `requireClientPrincipal`. Los
  guardias por página siguen siendo la puerta: el layout solo adelanta la
  redirección. Hacía falta porque la del guardia se lanzaba bajo
  `(console)/loading.tsx` y, en las páginas sin `loading.tsx` propio, rompía el
  Router de Next (React #310): un segundo de «This page couldn't load», sin
  traducir, antes del Panel.
- **E2E** (`apps/console/e2e/lite.spec.ts`, proyecto `lite`, T105): como
  persona de cliente, axe sin graves ni críticas en `/`, `/inbox`, el hilo
  abierto y `/usage`, sin desbordes a 360 y 1920 px ni con el texto un 30 % más
  largo, en ES y EN y en claro y oscuro; la frontera, sin errores de página.
  `client.setup.ts` entra una vez: el login admite 10 intentos por minuto y
  correo.
- **Avisos**: `console_notifications.audience` (`partner` | `client`); la campana
  del partner lista `partner`, la del cliente (`/console/lite/notifications`)
  solo `client` de su `external_client_ref`. Una sola lógica (`Viewer`).
- **Barridos**: `tests/isolation/test_lite_route_scope.py` (cada ruta del
  partner da 403 a un cliente y cada ruta lite al partner),
  `test_lite_client_vs_client.py` (dos clientes del mismo partner) y
  `test_21_rls_covers_every_tenant_table.py` (las dos tablas de identidad,
  justificadas).

## Panel y Consumo de un cliente

**Las mismas funciones que la consola del partner, con un solo cliente**, para
que cada cifra coincida al céntimo con la que el partner ve de ese cliente
(lo fijan `test_lite_home.py` y `test_lite_usage.py` comparando con
`/console/home` y `/console/usage/spend?client=`).

- **Panel** (`GET /console/lite/home`, `services/lite_home.py`):
  `tenant_snapshots`, `trend_block`, `review_block`, `credit_burn`,
  `allocations_for` y `spend_block` con `[tenant_id]`. Del libro solo se toman
  las filas del cliente (nunca la clave `None` del Companion). «Esperan a una
  persona» solo con Bandeja; el desglose por agente solo con más de un agente;
  sin semana anterior, sin variación; sin gasto, sin días; sin tope, «sin tope
  asignado». «Necesita tu atención» dice a quién pedir saldo (el partner, o
  Auphere si su slug está en `NEXUS_AUPHERE_PARTNER_SLUGS`) y no ofrece compra.
- **Consumo** (`/console/lite/usage/{summary,spend,detail,export.csv}`):
  `spend_report`, `bucket_report` y `csv_export`, extraídas de
  `api/console/usage.py` sin cambiar la respuesta del partner. Solo tráfico del
  cliente (`source = channel`: el Playground es la prueba del partner). Nada del
  partner entero: ni su saldo, ni lo gastado fuera de clientes, ni su tope de
  mensajes, ni sus alertas. Saldo de solo lectura (C2): sin comprar, sin mover
  topes, sin alertas.
- **Consola**: `/` y `/usage` son las mismas URLs para las dos personas; la
  página pinta `LitePanel` / `LiteUsage` (`components/lite/`) para un cliente.
  El CSV sale por `/api/lite/usage/export` (`proxyClientDownload`, guarda de
  módulo).
- **El doble débito del tope, arreglado** (bug `doble-cobro-del-tope`,
  `.specify/bugs/doble-cobro-del-tope/`). Del 2026-09-02 (2026-09-13 en
  producción) al arreglo, cada turno bajaba el tope del cliente dos veces
  (`debit_wallet` y `debit_allocation`), también sin cobro, y el asiento
  `…:allocation` inflaba el gasto. Ahora el tope solo lo baja `debit_wallet`,
  por lo cobrado; las sumas de gasto ignoran los asientos `…:allocation` que
  quedan en el libro; y la migración `0156` devolvió a cada cliente lo
  descontado de más en su semana. Lo fija
  `tests/integration/test_channel_debit_once.py`.

## La Bandeja de entrada

Solo para un cliente con el módulo `inbox` (y, al elegirlo, un WhatsApp de
Meta conectado). API en `api/console/lite/{inbox,inbox_media,inbox_stream}.py`;
consola en `app/(console)/inbox/` y `components/inbox/`.

**La única parte de la consola que devuelve cuerpos de mensaje** (excepción
a C8, razonada en ADR-041): C8 protege las palabras del cliente final frente
al *partner*; el negocio leyendo sus propias conversaciones no cruza esa
frontera. Lo que impide que sea un agujero:

- solo la alcanza la persona de un cliente con `inbox`
  (`require_client_principal("inbox")`); un miembro del partner o un cliente
  sin el módulo reciben 403 en todas sus rutas
  (`tests/isolation/test_lite_bodies_only_in_inbox.py`);
- todo corre bajo la RLS del cliente: un id de otro cliente es el mismo 404
  que uno inventado (`test_lite_client_vs_client.py`, también para
  conversación, mensaje y respuesta guardada, de lectura y de escritura);
- `test_console_scope.py` deja pasar campos de cuerpo **solo** bajo
  `/console/lite/inbox/` (`BODY_ROUTES_PREFIX`); `tenant_id` nunca.

> **Hallazgo al ampliarlo (2026-10-08).** Hasta la spec 030 el eje C8 de
> `test_console_scope.py` no comprobaba nada: el recorrido empezaba en el
> envoltorio `content → schema` de OpenAPI y no encontraba ninguna propiedad,
> para ninguna ruta (ni respuestas ni cuerpos de petición). Corregido. Lo que
> salió en rutas del partner eran vocabularios cerrados (`Literal`, que ya no
> cuentan) y el error de Meta de un catálogo (`CatalogErrorOut.message`,
> excepción por esquema). El control `test_the_walk_reads_real_responses` se
> pone rojo si el recorrido vuelve a quedarse vacío.

**El ciclo de vida, sin columna de estado nueva** (D11–D14):

| La Bandeja dice | En la fila |
|---|---|
| Responde el agente | `agent_active = true` |
| Necesita humano | `status = ESCALATED` (el agente pidió ayuda) |
| Responde una persona | `agent_active = false` + `assigned_user_id` |
| Resuelta | `status = CLOSED` (+ `closed_at`) |

- **Una conversación por contacto y número**: el alta del worker
  (`persistence/messages.upsert_conversation_for_customer`) toma la última
  fila sea cual sea su estado. Antes buscaba solo `OPEN` y partía en dos una
  conversación que esperaba. `CLOSED` se reabre con el agente y un evento
  `reopened` del contacto (un recordatorio de cobranza reabre como `system`).
- **`last_message_at`** ordena la lista; lo mueven entrantes y salientes y
  nunca baja.
- **Quién responde** (`services/conversation_control.py`, extraído del admin):
  `If-Match` con `agent_active_version`; con una versión vieja, 412 con el
  estado real. Al devolver se deja `takeover_context` y el despachador resume
  al agente lo que escribió la persona (`takeover_messages`: `operator` y
  `member`).
- **Lo que escribe la persona** es un saliente `pending` con
  `actor_kind = "member"` y `actor_id` = **id de la membresía** (UUID; el
  `user_id` de la consola es texto de Better Auth). El despachador de salida lo
  envía y lo mide como cualquier saliente; los archivos van por enlace firmado.
  Precondiciones (409): `not_assigned_to_you`, `window_closed` (24 h desde el
  último entrante), `channel_disconnected`. Adjuntos: JPEG/PNG ≤ 5 MB, PDF ≤
  16 MB (415/413 con el límite), comprobados también en la BFF antes de subir.
- **Eventos** (`conversation_events`): escalado (con motivo y resumen del
  agente), control tomado, devuelta, resuelta, reabierta. Alimentan el hilo y
  la actividad del panel. **Nunca texto de mensajes.**
- **Auditoría** `inbox.*` con `client:<correo>` y sin contenido: longitudes y
  nombres de etiqueta, nunca el texto ni la nota.

**El escalado, en un solo sitio y en dos pasos** (`services/inbox_lifecycle`).
`escalate.escalate_to_human` llama a `mark_waiting` **dentro** de su
transacción (estado, evento y, *solo con Bandeja*, el agente callado) y a
`announce_waiting` **después** del commit (campana `inbox.waiting` con
`audience = client`, correo a las personas activas del cliente, tiempo real;
una vez por escalado). Sin Bandeja el agente sigue respondiendo: nadie la
atendería. Quitar la Bandeja o apagar el acceso devuelve al agente las
conversaciones calladas por un escalado (`release_escalated_for_tenant`); las
que una persona tomó se respetan.

**La nota interna** (`contact_notes`) es del contacto, ≤ 4.000 caracteres, y
**no la lee el agente**: el barrido
`tests/isolation/test_contact_notes_never_reach_agent.py` falla si aparece en
el código del worker o del MCP y comprueba con el despachador real que no
entra en el turno.

**Tiempo real** (`services/inbox_stream.py`): un canal Redis
`inbox:{tenant_id}`; publican el worker (entrante, respuesta del agente,
estado de envío), el escalado del agente (`announce_waiting`), el webhook de
estados de Meta (entregado/leído/fallido) y la API en cada acción de la Bandeja
que cambia lo que se pinta (tomar, devolver, contestar, adjuntar, resolver,
reabrir, etiquetar) — siempre **después** del commit y **sin cuerpo**
(`conversation.updated`, `message.new`, `message.status`). Las rutas lite no
confirman su transacción, la confirma `lite_scope` al cerrarse; por eso dejan el
aviso en `scope.after_commit`, que solo corre si el commit sale bien (un
rollback no avisa de nada) y, con FastAPI 0.136, después de enviar la
respuesta. Lo fija `tests/unit/test_lite_inbox_publish_after_commit.py`: lo
que un suscriptor lee al oír el aviso es lo ya confirmado. La SSE lite
(`GET /console/lite/inbox/stream`, latido cada 15 s, sin transacción abierta)
reenvía solo el canal del cliente de la sesión; la consola vuelve a pedir lo
que cambió. Si la línea cae, la Bandeja dice «Reconectando…». La sesión se
comprueba al abrir la línea, no después: por eso la de un **teléfono** (spec
031) se corta sola a los 5 minutos (`PHONE_LINE_SECONDS`) y un teléfono
cerrado deja de recibir eventos dentro del plazo de R7.2. La de la web no se
corta (lo fija `tests/isolation/test_phone_revocation.py`).

**Consola**: lista de 320 px, hilo flexible y panel de contacto plegable (por
defecto plegado bajo 1280 px, recordado por navegador con respaldo en memoria
si el almacenamiento está bloqueado). Las lecturas y escrituras son Server
Actions (`app/(console)/inbox/actions.ts`); la SSE, los archivos y los
adjuntos pasan por rutas BFF (`app/api/lite/inbox/*`) — el navegador nunca
habla con la API ni ve un enlace de almacenamiento. El envío aparece al
instante (`useOptimistic`) y se retira con el motivo si la API lo rechaza. El
número de no leídas junto a «Bandeja de entrada» y la búsqueda ⌘K de la barra
superior (`components/shell/{use-inbox-unread.ts,lite-search.tsx}`) solo
existen con el módulo.

## Varios agentes por cliente

Spec 030, iteración 3 (R14). Un cliente puede tener varios agentes; cada número
de WhatsApp contesta con uno (`channels.agent_id`) y un agente puede tener
varios números. El conocimiento y los datos del cliente son de todos sus
agentes.

- **Modelo** (`0152`–`0155`): tabla `agents` con RLS `FORCE`, nombre único
  entre los activos sin distinguir mayúsculas, `active | archived` (no se
  borra, §IV). `agent_configs.agent_id` es obligatorio; el relleno creó un
  «Agente principal» por cliente con todas sus versiones, y un trigger lleva a
  él cualquier versión insertada sin agente (Companion, plantillas, admin sin
  agente). Las versiones siguen numeradas **por cliente** (decisión en
  `data-model.md`): promover o revertir archiva solo la activa de ese agente, y
  hay un único activo por agente (índice parcial).
- **Agente principal**: el activo más antiguo. Contesta en los números sin
  agente y es sobre el que actúa todo lo que no nombra uno (Companion, crones
  sin canal, evals).
- **Solo del propio cliente** (`0155`): `agent_configs` y `channels` apuntan a
  `agents` por `(tenant_id, agent_id)`, y el repositorio rechaza un agente que
  no es del cliente (`UnknownAgent`, 404 en el admin). Antes, una clave de una
  columna dejaba que el admin —que recibe `agent_id` por la URL— colgara una
  versión del cliente A de un agente del cliente B.
- **Runtime**: el preludio del webhook y el despachador resuelven el agente del
  número (o el principal); el cargador cachea por `(tenant, agent)`; un número
  de un agente sin versión publicada no contesta (`agent_unpublished`). El
  medidor lleva `agent_id` a `usage_records`, `usage_ledger` y los mensajes del
  agente.
- **Consola del partner**: `GET/POST /console/clients/{ref}/agents`,
  `PATCH …/agents/{id}` (renombrar o archivar: 409 `name_taken`,
  `agent_has_channels`, `last_agent`) y `PATCH …/channels/{id}/agent` (409
  `agent_not_published`, `channel_send_only`, `agent_archived`). Las rutas del
  agente (versiones, borrador, ajustes, herramientas, habilidades,
  capacidades, plantilla y Playground) aceptan `?agent=`; sin él, el
  principal. En la ficha: selector y «Nuevo agente» en Agente, Habilidades y
  Playground (`components/clients/agent-switcher.tsx`), la barra del borrador
  del agente elegido (`agent-draft-bars.tsx`) y «Contesta» en cada número de
  Canales. Las pestañas de un agente conservan `?agent=`. El modelo de lenguaje
  sigue siendo del cliente.
- **Playground**: un hilo fija su agente al crearse; la lista con `?agent=` da
  los de ese agente (los hilos de antes, sin agente, son del principal).
- **Admin**: `/admin/tenants/{id}/agents` y `?agent_id=` en `agent-config`
  (leer, guardar versión y aplicar plantilla); selector y «Nuevo agente» en la
  pestaña Agente.
- **Consola lite**, solo con más de un agente activo: el Panel desglosa el
  gasto del mes por agente (al céntimo, por resto mayor: `split_cents`); el
  Consumo da gasto, conversaciones y parte de cada uno, y su gráfico de gasto
  filtra con `?agent=`; la Bandeja etiqueta cada conversación con el agente de
  su número, lo nombra en la cabecera y filtra con `?agent=`. Con un agente
  nada de eso aparece. `GET /console/lite/me` lista los agentes activos. Lo
  gastado antes de que hubiera agentes es del principal.
- **Pruebas**: `tests/isolation/test_agent_scope_within_tenant.py` (garantías
  2, 4 y 5 entre dos agentes de un cliente, y la referencia a un agente ajeno
  rechazada por la base de datos), `tests/unit/test_agents_api.py`,
  `test_lite_by_agent.py`, `test_agent_versions_per_agent.py`,
  `tests/integration/test_migration_agents.py`; en el worker
  `test_agent_by_channel.py` y `test_agent_metering.py`; en la consola
  `clients/[ref]/__tests__/agent-selector.test.tsx`,
  `clients/[ref]/agents/__tests__/actions.test.ts` e
  `inbox/__tests__/agents.test.tsx`; en el admin
  `agent/__tests__/agent-picker.test.tsx`.
- **Pendiente**: quien publica una promoción sigue avisando por cliente
  (`<tenant_id>`), lo que invalida la caché de todos sus agentes; el suscriptor
  ya entiende `<tenant_id>:<agent_id>`.

## Lo que la spec 031 cambió aquí

- **Un solo orden de módulos**: `GET /console/lite/me` devuelve `nav`, los
  módulos en el orden de la barra (`ClientAccess.ordered_modules()`). La barra
  de la consola (`lite-nav.ts`) y las pestañas de la app lo pintan tal cual;
  ninguna de las dos tiene un `ORDER` propio. `firstModulePath` toma el primero.
- **Enviar no duplica**: `POST …/messages` y `POST …/attachments` aceptan
  `Idempotency-Key` (un UUID). Si la petición se repite con la misma clave, la
  API devuelve el envío ya hecho (200) en vez de mandar otro WhatsApp; un envío
  que falló se reintenta con la misma clave tras volver a comprobar sus
  condiciones; la misma clave con otro texto es un 422
  `idempotency_key_reused`. La consola web genera la clave al enviar y la
  reutiliza si la persona reintenta el mismo texto.
- **Los teléfonos de la persona**: «Tus teléfonos» (`/account/phones`, en el
  menú de la persona de cliente) lista los teléfonos con la sesión abierta en
  la app, con su último uso, y cierra cualquiera tras confirmar. Es una página
  de la persona, no de un módulo: la tiene toda persona de cliente
  (`requireClientAccount`, `CLIENT_ACCOUNT_PATHS`), y el layout la deja pasar
  sin mirar los módulos. En el admin, Acceso → persona → «Teléfonos» lista los
  activos y los últimos cerrados con su motivo, y cierra uno (auditado con el
  operador).
- **La entrada de la app no pasa por la consola**: la app tiene la suya
  (correo y contraseña, o Google, en la API); ver
  [app-movil.md](app-movil.md#entrar-y-quedarse-dentro).


## Lo que la spec 045 cambió aquí

Spec [`045-consola-customers-mejoras-y-beta`](../specs/045-consola-customers-mejoras-y-beta/spec.md),
del diseño «Consola Customers» (2026-10-22).

- **La Bandeja solo enseña lo que el agente atiende o atendió.** Una
  conversación existe para la Bandeja si tiene un entrante que el agente pudo
  atender: uno que la puerta de números permitidos (spec 024) no silenció, en un
  número con agente. El despachador lo anota en `conversations.attended_at` (el
  primero) y `last_attended_inbound_at` (el último); la migración `0171` los
  rellenó desde los mensajes. Sin `attended_at`, la conversación no se lista, no
  se cuenta y toda ruta con su id responde 404 (`inbox_view._in_inbox`). El hilo
  empieza en `attended_at` y no enseña entrantes silenciados; el «sin leer» se
  mide contra `last_attended_inbound_at` (`last_inbound_at` sigue siendo la
  ventana de 24 h de WhatsApp, que Meta abre con cualquier mensaje). Un mensaje
  silenciado no avisa: el despachador encola «mensaje para ti» después de la
  puerta, y la fan-out descarta lo que la Bandeja no enseña. Barrido:
  `tests/isolation/test_lite_inbox_attended_only.py`.
- **El «esperan» del Panel es el de la Bandeja**: la misma función
  (`inbox_view.counts`), sin la ventana de 7 días del Inicio del partner, que no
  cambia.
- **Motivo y espera**: cada fila que espera trae `waiting {reason, since}` (el
  último escalado del agente); el detalle, `waiting_since`.
- **El saldo dice hasta cuándo alcanza**: `balance.month_days_left` (días del
  mes que quedan, hoy incluido, en la zona del negocio) y `runs_out_on` (la
  fecha local en que se acaba al ritmo de 7 días; `null` sin gasto o sin tope),
  en `/home` y `/usage/summary` (`lite_home.balance_horizon`). Sigue siendo de
  solo lectura: sin «Comprar saldo» ni alertas (decisión del owner).
- **El horario del negocio en `/me`**: `business {timezone, hours, hours_label}`,
  con `hours` en la forma canónica del bug `horario-del-negocio-en-tres-formas`
  y la frase compuesta en el idioma de la persona (el de su teléfono; en la web,
  el del navegador).
- **Silencio fuera de horario**, por teléfono: `quiet_outside_hours` en
  `/phones/current/notices`, encendido por defecto. Fuera del horario del
  negocio no sale el push de lo que no es urgente; «una conversación espera a
  una persona» sale siempre. La entrega queda `skipped` con `quiet_hours`. Sin
  horario no se silencia nada.
- **Pantallas**: Panel con la tarjeta destacada de conversaciones, «Cubre N de M
  días del mes» con el tono por días; Bandeja que nombra solo WhatsApp, con el
  motivo y la espera en la fila y la píldora «N agentes activos»; Consumo que
  empieza por «Te alcanza hasta…» y agrupa el detalle técnico en mensajes, uso
  del modelo y multimedia. Esqueletos con las medidas finales en `/` y `/usage`.
  «Gasto del mes» baja junto a la gráfica solo cuando se reparte por agente;
  con una sola cifra es una tarjeta más de la primera fila y la gráfica ocupa
  el ancho (una tarjeta de dos filas con una cifra era una caja vacía).
- **Accesibilidad que destapó el pase vivo** (`e2e/lite.spec.ts` contra datos
  sembrados): el hilo de la Bandeja toma el foco para poder desplazarlo con el
  teclado cuando no trae ningún enlace (axe `scrollable-region-focusable`).
- **Beta**: el lateral de una persona de cliente enseña la insignia «Beta» (la
  misma que la del partner, con su pista `shell.beta.client.hint`); «lite» ya no
  sale en pantalla.

## Lo que la spec 047 cambió aquí (ola 1: ningún mensaje se pierde)

Spec [`047-la-fabrica-de-agentes`](../specs/047-la-fabrica-de-agentes/spec.md),
requisitos 1 y 2.

- **Todo entrante se guarda antes de decidir nada** (`dispatcher.accept_inbound`).
  Ni la bolsa vacía, ni la pausa, ni el número con problemas lo impiden; hasta
  la 047, sin saldo, el mensaje se perdía sin rastro. El resolutor de números
  reconoce también los canales en pausa y degradados (migración `0176`); un
  número con la calidad en amarillo **sigue contestando**.
- **Si el agente no contesta, la conversación dice por qué**:
  `conversations.waiting_reason`, con la lista cerrada de `contracts/events.md`
  §2. Salvo fuera de la audiencia, pasa a «Espera a una persona» (`escalated`)
  con un evento cuyo motivo es ese código —el `waiting.reason` de la fila— y se
  marca atendida para que la Bandeja la enseñe. El agente **no** se calla en
  ella: lo calla la puerta, y en cuanto la puerta se abre y vuelve a contestar,
  la conversación vuelve al agente sola (`inbox_lifecycle.release_reason`). El
  escalado del agente es `escalated`; «la lleva una persona», `human_takeover`,
  sin convertirla en espera.
- **Avisos**, uno por espera, no por mensaje: con Bandeja, campana, correo y
  push de «una conversación espera a una persona» con su motivo (sin texto del
  mensaje); sin Bandeja, la fila `conversation.escalated` que el alertador
  convierte en la plantilla al dueño (hasta que la ola 4 traiga los
  destinatarios por canal) y, si el canal tiene `config.wait_message`, ese
  mensaje como mucho una vez cada 6 h por conversación. Sin saldo, además, los
  avisos de hoy al partner y al cliente (uno por cliente y día).
- **Un turno por ráfaga y uno a la vez**: cada entrante programa el turno de su
  conversación a +3 s (`NEXUS_RUNNER_COALESCE_WINDOW_MS`) en una cola diferida de
  Redis; el turno toma con el candado de la base todos los mensajes sin
  `turn_id` y contesta a todos de una vez (`runtime/turns.py`). Un reintento
  conserva el `turn_id`, y la reserva, el enlace de pago y la respuesta pasan
  por `turn_effects`: no se repiten (`runtime/turn_effects.py`).

## Reservas (spec 043)

Módulo `reservas`, entre la Bandeja y el Consumo. Pantalla `/reservas`
(`app/(console)/reservas/`, `components/reservas/`) en el modo del cliente:
**Servicios** (Agenda · Lista de espera · Ajustes, agenda por profesional) o
**Aforo** (Ocupación · Lista de espera · Ajustes, mapa de ocupación y lista por
hora con llegadas). Vista (Cuadrícula o Lista) y periodo (Día, Semana, Mes) son
dos controles separados; los botones de cada reserva salen de `allowed`. El
Panel enseña su bloque (de `/reservas/summary`) y la fila «N reservas de hoy sin
confirmar». Todo lo demás —dominio, API, agente, crons, plantillas, Google
Calendar— está en [reservas.md](reservas.md).
