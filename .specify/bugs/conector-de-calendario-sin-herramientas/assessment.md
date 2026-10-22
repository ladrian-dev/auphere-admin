# Bug Assessment: Google Calendar y Calendly se conectan pero el agente no recibe herramientas, y reintentar da 502

- **Slug**: conector-de-calendario-sin-herramientas
- **Created**: 2026-10-22
- **Source**: logs de producción del alta de `demo-lorenzo` (tenant `a2bfc92d`)
- **Verdict**: valid
- **Severity**: high — un cliente de reservas no puede reservar aunque todo diga
  «conectado»

## Report (summarized)

Al configurar `demo-lorenzo`, conectar Google Calendar dio 502 dos veces.

## Symptom

Cronología (UTC, 22-oct):

| Hora | Qué |
|---|---|
| 11:47:28 | `POST …/googlecalendar/consent` → 201 |
| 11:47:46 | `GET /connectors/oauth-callback?status=success` — Google autorizado |
| 11:48:40, 11:48:53 | `POST …/googlecalendar/consent` → **502**, sin una línea de log |
| 12:16:15 | WhatsApp conectado; el tenant pasa a `active` |
| 12:25:37 | el cron reconcilia: Google Calendar y Calendly `connected`… y `connector.sync.dropped_blank_tools` **20 de 20** en los dos |

Lo esperado: tras autorizar, la tarjeta pasa a «conectado» en segundos, un
segundo clic no rompe nada, y el agente recibe las herramientas del calendario.

## Root cause

Son cuatro fallos encadenados:

1. **El webhook de Composio no llega a producción.** Cero peticiones a
   `/connectors/composio-webhook` en 30 días, ni siquiera rechazadas. La URL sí
   estaba registrada (proyecto `auphere`, desde el 12-may, payload V3), pero
   suscrita solo a `trigger.message`, `trigger.disabled` y
   `connected_account.expired`: faltaba `composio.connected_account.activated`,
   el evento de «el dueño ha autorizado». Es configuración, no código.
2. **El cron de reconciliación solo recorre tenants `active`.** Un cliente en
   alta (`provisioning`) conecta el calendario antes que WhatsApp, y su conector
   se queda `pending` hasta que conecta el canal: 38 minutos aquí.
3. **Reintentar el consentimiento da 502.** Con la tarjeta aún en «pendiente», el
   dueño pulsa Conectar otra vez. El SDK de Composio rechaza una segunda cuenta
   para el mismo usuario y auth config mientras haya una `ACTIVE`
   (`ComposioMultipleConnectedAccountsError`, `allow_multiple=False` por
   defecto). Eso sale como `ComposioError` → 502.
4. **Las herramientas llegan sin nombre.** `LiveComposioClient.list_tools` llama a
   `tools.get()`, que devuelve las herramientas envueltas para el proveedor por
   defecto (OpenAI): diccionarios `{"type": "function", "function": {…}}`. El
   código las lee con `getattr(t, "name", getattr(t, "slug", ""))`, que en un
   diccionario da `""`. `_drop_blank_tools` las descarta todas: el conector
   queda `connected` con cero herramientas.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/connectors/composio_client.py` — `LiveComposioClient.list_tools`.
- `apps/api/src/nexus_api/services/connectors/service.py` — `initiate_consent`.
- `apps/api/src/nexus_api/api/console/tools.py` — `start_consent` (`ComposioError` → 502).
- `apps/worker/src/nexus_worker/streams/connector_reconcile_cron.py` — `_list_active_tenants`.

## Possible Remediation

- Leer el esquema crudo (`tools.get_raw_composio_tools`), que trae `slug`, en las
  dos versiones del SDK (0.13 del lock y 0.28 de la imagen).
- En un reconsentimiento con la instalación `pending`, reconciliar primero; si
  ya está `ACTIVE` arriba, dejarla `connected` y decirlo (409), confirmando la
  transacción.
- El cron reconcilia todo tenant que no esté archivado.
- Suscribir el webhook a `composio.connected_account.activated` — **acción
  manual** en el panel de Composio, fuera del código.
