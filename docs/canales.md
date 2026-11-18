# Canales: alta, coexistencia, página del canal y enlace del dueño

Spec 047 (requisitos 28 a 34). Un **canal** es un número (WhatsApp hoy) que
atiende **un agente** (`channels.agent_id`). Este documento cuenta cómo se
conecta, cómo se configura y qué pasa cuando el negocio sigue usando su app.

## 1. Conectar un número

- **Desde la consola** (Embedded Signup v5 de Meta,
  `api/console/channel_signup.py`) o **con el enlace del dueño** (sección 4).
- **Modos** (`services/channel_signup_links.MODES`): `coexistence` (el negocio
  sigue con su app WhatsApp Business y Auphere responde a la vez), `cloud_api` (el
  número pasa entero a la API) y `whatsapp_login` (beta por país, nunca en la UE
  ni en el EEE; la activa Auphere en el admin, `whatsapp_login_beta_countries`).
  El `config_id` de Meta del modo beta es `NEXUS_META_CONFIG_ID_WA_LOGIN` (si no
  está, el de `cloud_api`).
- Un número nuevo empieza **en prueba**: «Solo mi equipo» con el teléfono del
  dueño, para que nadie de fuera hable con un agente a medio hacer.

### Llegar a la configuración del número (spec 063, requisito 2)

- **Quién atiende un número sin agente:** el **principal** del cliente, es decir,
  el marcado por defecto o, si ninguno lo está, el activo más antiguo
  (`services/agents.principal_agent_id`, la regla del turno). Lo usan la página
  del número (`_agent_of`), la pestaña Canales de cada agente (`agent_channels`) y
  las tarjetas de Agentes. El canal interno del probador no sale en ninguna.
- **Desde Canales del cliente:** cada tarjeta lleva a la configuración del número
  («Configurar», `/clients/{ref}/channels/{id}`, que redirige dentro de su agente).
  - **«Sin configurar»:** dice «No responde a nadie» en vez de «Activo», y su
    acción principal es «Decidir a quién responde».
  - **Sin agentes en el cliente:** la tarjeta lleva a crear uno.
  - **Al conectar un número aquí:** al terminar, la consola abre su configuración,
    después de la oferta del catálogo si la hay (047, 30.6).
- **Desde un agente:** todo enlace a «los canales» lleva a su pestaña Canales
  (`?tab=channels`), nunca a Canales del cliente. Eso incluye su tarjeta cuando
  espera un número, «Guardar y conectar un canal» y el arreglo «canal» de la
  revisión.
  - **Por qué importa:** antes, un agente «Listo · sin canal» llevaba a la página
    del cliente. El número se conectaba allí sin agente, se quedaba «Sin
    configurar» y el partner no volvía a ver su configuración (prod, 2026-11-18).
- **«Listo · número sin configurar»:** así sale un agente publicado cuyo único
  número no responde a nadie (`visible_state` con `reason="unconfigured"`).

## 2. La página del canal

`api/console/channel_config.py`, `services/channel_config.py`,
`/console/clients/{ref}/channels/{channel_id}`:

- **Audiencia**: `unset` (sin configurar: no responde a nadie), `team_only` («Solo
  mi equipo», con sus números de prueba) o `everyone` («A todos», con sus
  excepciones). La regla de audiencia se aplica de forma **estricta** en WhatsApp
  para los partners con la consola nueva; los demás siguen con las políticas de
  `admin_access` de la versión (`core/admin_gate.audience_suppresses`).
  «A todos» exige saldo en la bolsa del cliente (`bag_empty`).
- **Escalada**: cuándo se pasa a una persona (pide hablar con alguien, intentos
  fallidos, una queja o un motivo propio), a quién se avisa (campana, correo o
  WhatsApp) y el mensaje de espera. El aviso por WhatsApp sale del propio número
  si su WABA tiene la plantilla `alert_escalation_v1` aprobada, en el idioma en
  que está aprobada (el español primero si hay varios); si no, del número de
  avisos de Auphere (el predeterminado de `auphere_owner_channels`, en el admin
  «Números de Auphere») en el idioma `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE`
  (`es_CL` por defecto). Si no hay ninguno de los dos, el aviso por WhatsApp no
  sale ni se da por enviado (`escalation_whatsapp_unavailable` en
  `operator_notifications.last_error` y un evento
  `operator_alerter.whatsapp_unavailable` al día por cliente), el correo y la
  Bandeja siguen igual y la página lo enseña con la comprobación
  `escalation_template_missing`. Lo mismo vale para los avisos de siempre al
  dueño (canal sin destinatarios propios): del número del cliente solo con la
  plantilla aprobada en su WABA, si no del de Auphere.
- Cada cambio lleva `If-Match` (`412` con lo que cambió), queda en el historial
  y se puede **deshacer**. **Mover** el número a otro agente, **pausar** y
  **reanudar** avisan al partner y quedan en la auditoría.
- Los checks de la página dicen qué falta para «A todos» y qué bloquea, y
  avisan (sin bloquear) si las pruebas no están al día, si nadie recibe el
  escalado o si el aviso por WhatsApp no puede salir.

## 3. Coexistencia

El webhook de Meta deja tres streams en Redis y responde enseguida; tres
consumidores del worker los procesan con la RLS del cliente
(`wk/streams/meta_*_consumer.py`):

- **Ecos** (`smb_message_echoes`): lo que el negocio escribe desde su app se
  guarda como mensaje de una persona (`origin = business_app_echo`) y la
  conversación pasa a «La lleva una persona» **2 horas**: el agente calla. Pasado
  el plazo, el siguiente mensaje del contacto lo atiende el agente.
- **Historial**: solo si el canal lo pidió (`config.history_import`); entra como
  `origin = history_import`.
- **Contactos** (`state_sync`): pasan a clientes del negocio.

Los avisos de cuenta de Meta (`account_update`) marcan el canal `degraded` con su
motivo: `PARTNER_REMOVED` → `auth_expired`; `ACCOUNT_OFFBOARDED` y
`PARTNER_APP_UNINSTALLED` → `coexistence_inactive`; `ACCOUNT_DELETED`,
`ACCOUNT_RESTRICTION` y `DISABLED_UPDATE` → `meta_error`. Cada uno deja la
auditoría `channel.problem` y el aviso `channel.problem` al partner. Los tics azules
no se mandan a quien queda fuera de la audiencia.

## 4. El enlace del dueño

`services/channel_signup_links.py`, `api/console/channel_signup.py`: el partner
genera un enlace para un agente (uno pendiente a la vez, `409
link_pending_exists`), el dueño conecta su número desde el móvil, el número queda
asignado a ese agente y empieza en prueba con el teléfono del dueño. Al conectar
se avisa al partner (`channel.connected`). Revocar el enlace lo invalida al
momento.

## 5. Dónde mirar si algo falla

- El estado visible del canal sale de `services/agent_lifecycle.channel_visible_state`
  (`pending_link`, `disconnected`, `problem`, `paused`, `unconfigured`,
  `team_only`, `everyone`).
- La conciliación diaria de mensajes con Meta queda en `meta_reconciliation_runs`
  y sus diferencias se ven en el admin (`GET /admin/reconciliations`).
- Los consumidores de coexistencia mandan lo que falla a su buzón de descarte con
  el error.
