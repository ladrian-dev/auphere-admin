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
  si tiene la plantilla `alert_escalation_v1` aprobada, o del número de Auphere.
- Cada cambio lleva `If-Match` (`412` con lo que cambió), queda en el historial
  y se puede **deshacer**. **Mover** el número a otro agente, **pausar** y
  **reanudar** avisan al partner y quedan en la auditoría.
- Los checks de la página dicen qué falta para «A todos» y qué bloquea.

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
