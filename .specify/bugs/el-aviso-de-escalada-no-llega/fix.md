# Bug Fix: el aviso de escalado por WhatsApp no llega

- **Slug**: el-aviso-de-escalada-no-llega
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied (código); la configuración de abajo la hace un operador

## Summary

Un aviso por WhatsApp (`alert_*`) sale del número del cliente **solo** si su WABA
tiene la plantilla APPROVED, y en el idioma en que está aprobada; si no, del
número de avisos de Auphere, en `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE`
(`es_CL` por defecto). Vale para los destinatarios del canal (requisito 33) y
para la vía de siempre (dueño y revisores). Sin ninguno de los dos el aviso no
sale ni se da por enviado, deja un motivo claro y la página del canal lo dice.
No cambia a quién se avisa, ni la campana, ni el correo.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/channel_config.py` | modified | `NotifyRoute(source, language)`; `approved_language` (lee `whatsapp_template_status`, el español primero); `notify_from(session, channel, template)` devuelve la ruta; `auphere_can_notify` (sesión propia, registro global); `whatsapp_notice_can_leave`; comprobación `escalation_template_missing`; `read_config` sigue dando `channel \| auphere` |
| `apps/api/src/nexus_api/config.py` | modified | `auphere_alert_template_language = "es_CL"` |
| `apps/api/.env.example` | modified | documenta `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE` |
| `apps/worker/src/nexus_worker/streams/operator_alerts.py` | modified | `_send_routed` para las dos vías; idioma de la ruta en vez de `es_CL` fijo; la vía de siempre decide con `notify_from`; `WhatsAppAlertUnavailable`; motivo `escalation_whatsapp_unavailable` / `alert_whatsapp_unavailable`; `operator_alerter.whatsapp_unavailable` una vez al día por cliente y motivo; `send_from_auphere(phone, template, params, language)` |
| `apps/console/src/components/builder/channel-model.ts` | modified | `checkText` conoce `escalation_template_missing` |
| `apps/console/src/i18n/lanes/builder-channels.ts` | modified | su frase en `es` y `en`, sin punto y coma |
| `apps/api/tests/integration/channels/test_operator_alert_sender.py` | new test | la vía de siempre: idioma, Auphere, sin salida (6) |
| `apps/api/tests/integration/channels/test_escalation_recipients.py` | modified test | idioma `es` / `es_CL` y sin salida con correo (3 nuevas); el falso de Auphere recibe el idioma |
| `apps/api/tests/integration/channels/test_channel_config.py` | modified test | `test_the_page_warns_when_the_whatsapp_notice_cannot_leave` |
| `apps/api/tests/integration/channels/conftest.py` | modified test | `give_alert_templates` y `alert_templates_approved` |
| `test_operator_alerter.py`, `test_operator_alerter_extended.py`, `test_operator_alerter_provider.py` | modified test | sus clientes tienen las plantillas aprobadas: fijaban el error de mandar sin comprobar |
| `apps/console/src/components/builder/__tests__/channel-model.test.ts`, `channel-page.test.tsx` | modified test | la frase, y que se enseña sin enlace |
| `docs/canales.md`, `apps/api/RUNBOOK.md`, `specs/047-la-fabrica-de-agentes/contracts/console-api.md` | docs | la regla del número y el idioma, el motivo y la comprobación |

## Diff Highlights

```python
# channel_config.notify_from
language = await approved_language(session, (channel.config or {}).get("waba_id"), template)
if language is not None:
    return NotifyRoute(source="channel", language=language)
return NotifyRoute(source="auphere", language=get_settings().auphere_alert_template_language)
```

```python
# operator_alerts, la vía de siempre
route = await notify_from(session, channel, template)
...
except WhatsAppAlertUnavailable:
    reason = _unavailable_reason(template)        # escalation_whatsapp_unavailable
    errors.append(reason)
    _log_unavailable(tenant_id, reason, template=template, channel_id=channel.id)
    break
...
if sent == 0:
    notif.status = OperatorNotificationStatus.FAILED
```

## Configuración que tiene que hacer un operador (no es código)

Sin esto, el código nuevo ya no manda a ciegas, pero en staging los avisos
seguirán sin salir: lo dirán la página del canal y el log.

### 1. Registrar el número de avisos de Auphere en staging

Panel de administración de staging → **Plataforma → Números de Auphere**
(`/auphere/channels`, `apps/admin/src/app/(dashboard)/auphere/channels`). En
«Crear canal»:

- **Teléfono E.164**: el número de avisos de Auphere (de su WABA, no la de un
  cliente).
- **Nombre visible**: p. ej. «Auphere avisos».
- **País**: opcional.
- **Provider**: `meta`.
- **Provider phone_id**: el `phone_number_id` de Meta de ese número.
- **Access token Meta**: el token de usuario de sistema (BISUAT) con permiso
  para enviar desde ese número. Se guarda cifrado.
- Marcar **default** del provider (★). Solo hay uno por provider: si ya hay
  otro, quitarle la marca antes.

Equivale a `POST /admin/auphere/channels` con el token de admin
(`apps/api/src/nexus_api/api/admin/auphere_channels.py`):

```json
{
  "phone_e164": "+34…",
  "display_name": "Auphere avisos",
  "provider": "meta",
  "provider_phone_id": "<phone_number_id>",
  "access_token": "<BISUAT>",
  "is_default": true
}
```

El alerter lo usa solo si está activo, es el default de `meta` y tiene
`provider_phone_id` y token (`ResolvedAuphereChannel.can_send`).

### 2. Verificar el de producción (solo lectura)

Panel de prod → **Números de Auphere**: tiene que haber una fila activa con ★,
provider `meta`, `phone_id` y token. O `GET /admin/auphere/channels` y mirar
`is_default: true`, `active: true`, `provider_phone_id` no nulo y
`has_access_token: true`. Nada se cambia en prod hasta fusionar `develop`.

### 3. Aprobar `alert_escalation_v1` en la WABA de Auphere

En el idioma que diga `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE` (`es_CL` si no se
toca). **Ojo**: el canal del dueño manda `auphere_owner_consult` desde esa
misma WABA en `es` (`owner_outbox.py`); si las plantillas de Auphere están en
`es`, lo coherente es configurar `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE=es` en
los servicios del worker (scheduler) y de la API, no crear otra traducción.

- **Nombre**: `alert_escalation_v1` · **Categoría**: UTILITY · solo cuerpo, sin
  cabecera ni botones.
- **Variables** (de `_render_params`, en este orden):
  - `{{1}}`: quién. El nombre del cliente final, o su identificador, o
    `cliente` si no se sabe. Sin resumen (el canal lo apagó): `un cliente`.
  - `{{2}}`: por qué. El motivo que dio el agente, o `sin motivo informado`.
    Sin resumen: `Abre la Bandeja para verla`.
- **Cuerpo de referencia** (el que tenía la plantilla de Cultor, adaptado):
  «Auphere: la conversación con {{1}} pasó a una persona. Motivo: {{2}}. Entra
  en la consola para atenderla.» Ejemplos para Meta: `Lucía`, `Quiere hablar
  con el dueño`.

Para que los otros avisos al dueño también salgan desde Auphere, las demás
`alert_*` en el mismo idioma: `alert_needs_reauth_v1` (sin variables),
`alert_cost_threshold_v1` (1: `USD 42.50 / umbral USD 40.00`),
`alert_isolation_v1` (2: la métrica y la cuenta), `alert_whatsapp_burst_v1`
(1: el número de errores).

### 4. Alternativa por cliente

Un cliente que quiera que el aviso salga de su propio número aprueba
`alert_escalation_v1` en su WABA desde la consola («Plantillas de mensaje» del canal), en el
idioma que sea: el alerter usa el aprobado.

## Deviations from Assessment

Ninguna.

## Follow-ups

- Guardar el `waba_id` del número de Auphere y leer su idioma del espejo
  `whatsapp_template_status`, como en los clientes, en vez de configurarlo.
- `operator_notifications` no se ve en ningún panel: el motivo queda en la base
  y en el log; la consola lo enseña por la comprobación del canal.
