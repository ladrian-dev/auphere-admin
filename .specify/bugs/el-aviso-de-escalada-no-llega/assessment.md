# Bug Assessment: el aviso de escalado por WhatsApp no llega

- **Slug**: el-aviso-de-escalada-no-llega
- **Created**: 2026-11-08
- **Source**: pasted text (encargo de Luis, comprobado en los logs de staging
  `/nexus/staging/scheduler` desde el 2026-10-25 y en prod en octubre)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

En staging no se ha entregado **ni un solo** aviso de escalado por WhatsApp desde
el 2026-10-25.

- **Jemma's Hair** (destinatarios de escalado configurados, canal de WhatsApp):
  5× `operator_alerter.channel_recipient_failed` con
  `whatsapp: RuntimeError: no_auphere_notification_number`. Su WABA no tiene
  `alert_escalation_v1`, así que `channel_config.notify_from` eligió el número de
  Auphere, y staging no tiene número de avisos de Auphere por defecto
  (`auphere_owner_channels`, `AuphereChannelRepository.get_default`).
- **Los demás clientes**: `operator_alerter.send_failed` con
  `alert_escalation_v1` / `alert_needs_reauth_v1` y Meta
  `(#132001) Template name does not exist in the translation`.
- **Prod** (código viejo de `main`): 4 enviados y 2 fallidos por 132001 en
  octubre.

## Symptom

Cuando el agente pasa una conversación a una persona, quien debía enterarse por
WhatsApp no recibe nada. La conversación queda en la Bandeja («Espera a una
persona») y el correo sale, pero el aviso por WhatsApp, que es el que se lee
enseguida, no. Nadie lo ve: la página del canal decía «Los avisos por WhatsApp
saldrán del número de avisos de Auphere» aunque ese número no existiera.

Lo esperado (spec 047, requisito 33.3): el aviso sale del número del canal si
tiene la plantilla aprobada; si no, del número de avisos de Auphere; y la
configuración dice cuál se usará.

## Reproduction

1. Un canal de WhatsApp con un destinatario de escalado por WhatsApp; su WABA
   sin `alert_escalation_v1` y `auphere_owner_channels` vacío.
2. El agente escala (`conversation.escalated`) y corre un tic del alerter.
3. Resultado: `channel_recipient_failed … no_auphere_notification_number`; la
   página del canal no avisa de nada.

Y por la vía de siempre (un canal sin destinatarios propios):

1. Un cliente con `owner_phone` y su WABA con `alert_escalation_v1` aprobada en
   `es` (el idioma por defecto de la consola, `schemas_channels.py:256`), o sin
   ella.
2. Escala y corre un tic.
3. Resultado: el alerter manda la plantilla desde el número del cliente y en
   `es_CL` fijo; Meta responde 132001.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/streams/operator_alerts.py:425` y `:602` —
  `language="es_CL"` fijo, en el envío desde Auphere y desde el cliente.
- `apps/api/src/nexus_api/services/channel_config.py:191-206` — `notify_from`
  acepta la plantilla aprobada en **cualquier** idioma y no dice cuál.
- `apps/worker/src/nexus_worker/streams/operator_alerts.py:192-256` — la vía de
  siempre manda desde el número del cliente sin mirar si su WABA tiene la
  plantilla.
- `apps/worker/src/nexus_worker/streams/operator_alerts.py:401-416` — sin número
  de Auphere, `RuntimeError` genérico: no hay motivo que la consola pueda
  enseñar, y cada aviso deja su propio warning.
- `apps/api/src/nexus_api/services/channel_config.py:353-390` — las
  comprobaciones de la página no miran si el aviso por WhatsApp tiene salida.

## Root Cause Hypothesis

Tres causas que se suman. **Confianza: alta** (las tres se ven en los logs).

1. **Idioma**: el alerter manda siempre `es_CL`, pero decide «del canal» con la
   plantilla aprobada en cualquier idioma, y la consola las crea en `es`. Meta
   busca la traducción `es_CL`, no la encuentra: 132001.
2. **La vía de siempre no comprueba la plantilla**: manda desde el número del
   cliente aunque su WABA no la tenga. La plantilla `alert_*` vive, según el
   RUNBOOK, en la WABA de Auphere, no en la del cliente.
3. **Falta configuración**: staging no tiene número de avisos de Auphere por
   defecto. Sin él y sin la plantilla en el cliente no hay por dónde salir, y
   nada lo dice ni en la consola ni en un evento claro del log.

## Proposed Remediation

**Preferred**:

1. `notify_from(session, channel, template)` devuelve el número **y el idioma**
   (`NotifyRoute`): del canal en el idioma en que su WABA tiene la plantilla
   APPROVED (`whatsapp_template_status`, el español primero); si no, del de
   Auphere en un idioma configurado (`auphere_alert_template_language`,
   `es_CL` por defecto). El registro de Auphere no guarda su `waba_id`, así que
   su idioma no se puede leer del espejo: va por configuración.
2. La vía de siempre usa la misma decisión: del número del cliente solo con la
   plantilla aprobada en su WABA; si no, del de Auphere. Para todas las
   plantillas `alert_*` (también `alert_needs_reauth_v1`, que falla igual).
3. Sin ninguno de los dos, el aviso no sale y no se marca como enviado: motivo
   `escalation_whatsapp_unavailable` (o `alert_whatsapp_unavailable`) en
   `operator_notifications.last_error` y un evento
   `operator_alerter.whatsapp_unavailable` por cliente y día, no uno por tic.
4. La página del canal enseña la comprobación `escalation_template_missing`
   (aviso, sin bloquear, sin arreglo en la consola) cuando hay destinatarios por
   WhatsApp y el aviso no tiene salida.
5. Configuración (no código): registrar el número de avisos de Auphere en
   staging, verificar el de prod y aprobar `alert_escalation_v1` en su WABA en el
   idioma configurado. Pasos en `fix.md`.

**Alternatives**:

- *Mandar en `es` en vez de `es_CL`.* Arregla los WABA de la consola, rompe los
  que la tienen en `es_CL` (los 4 enviados de prod).
- *Probar idiomas hasta que Meta acepte.* Gasta llamadas fallidas en cada aviso
  y oculta la causa.
- *Guardar el `waba_id` de Auphere y leer su idioma del espejo.* Mejor a largo
  plazo, pero exige migración y que el webhook de plantillas de esa WABA llegue;
  hoy no hay nada que lo rellene.

**Files likely to change**:

- `apps/api/src/nexus_api/services/channel_config.py`
- `apps/api/src/nexus_api/config.py`, `apps/api/.env.example`
- `apps/worker/src/nexus_worker/streams/operator_alerts.py`
- `apps/console/src/components/builder/channel-model.ts`,
  `apps/console/src/i18n/lanes/builder-channels.ts`
- `docs/canales.md`, `apps/api/RUNBOOK.md`,
  `specs/047-la-fabrica-de-agentes/contracts/console-api.md`

**Tests to add or update**:

- Idioma: aprobada en `es` → `es`; en `es_CL` → `es_CL`; en `en_US` y `es_ES` →
  `es_ES`; en ninguno → Auphere con el idioma configurado.
- Sin plantilla ni número de Auphere: no sale, `FAILED`, motivo claro y un solo
  evento por cliente aunque haya dos escalados y tres tics; el correo sigue.
- La vía de siempre: con la plantilla, del número del cliente y en su idioma;
  sin ella (o rechazada), de Auphere, también `alert_needs_reauth_v1`.
- La comprobación `escalation_template_missing` aparece y desaparece al
  registrar Auphere o aprobar la plantilla.
- Las pruebas de siempre del alerter dan a sus clientes la plantilla aprobada:
  fijaban el error (mandar sin comprobar).

## Risks & Considerations

- **Cambia de qué número salen los avisos al dueño** de los clientes sin la
  plantilla: del de Auphere y no del suyo. No cambia a quién se avisa. Es lo que
  dice el RUNBOOK (las `alert_*` van en la WABA de Auphere) y hoy esos avisos no
  llegaban.
- **Las plantillas `alert_*` del número de Auphere** tienen que estar aprobadas
  en su WABA en `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE`; si no, Meta devolverá
  132001 desde Auphere. El código no lo puede comprobar (no hay espejo de esa
  WABA). El canal del dueño (`owner_outbox`) manda las suyas en `es`: si la WABA
  de Auphere las tiene todas en `es`, se configura `es` y no `es_CL`.
- Un cliente sin canal de WhatsApp sigue sin aviso al dueño por WhatsApp
  (`no_whatsapp_channel_for_tenant`), como antes: fuera de alcance.
- Garantías de aislamiento: ninguna tocada. El registro de Auphere es global y se
  lee con sesión propia, como ya hacía el worker; la decisión del idioma lee
  `whatsapp_template_status` por el `waba_id` del canal del cliente.

## Open Questions

Ninguna que bloquee. Se decide sin Luis y queda escrito: `es_CL` por defecto
para Auphere (el encargo), el español primero cuando hay varios idiomas, y el
evento una vez al día por cliente y réplica.
