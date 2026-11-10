# Bug Assessment: desconectar un número en un entorno deja sin webhook al otro

- **Slug**: desconectar-respeta-el-otro-entorno
- **Created**: 2026-10-22
- **Source**: pasted text (Luis, sesión coordinadora) + logs de CloudWatch de staging y producción
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> Escribí un mensaje y el agente no me respondió.

El mensaje iba al `+34672138367`, canal vivo de **Demo Farmacia Amacrux** en
staging, recién activado con Reservas. En los logs (2026-10-22, UTC):

| Hora | Entorno | Qué |
|---|---|---|
| 11:31 | staging | último mensaje entrante de la farmacia (`webhook.meta.inbound_enqueued`) |
| 12:06 | staging | último webhook de Meta que recibe staging |
| 12:16:13 | prod | `webhook.meta.handshake.ok`: Meta verifica la URL de producción |
| 12:16:15 | prod | `meta.signup.complete` en `demo-lorenzo`: `display_phone = +34672138367`, `waba_id = 725663313243186` |
| 12:24:44 | prod | `POST /console/clients/demo-lorenzo/channels/a84dbaf1…/disconnect` → 200 |
| desde entonces | los dos | ni staging ni producción reciben nada de ese número: ni `channel.unresolved_event` ni firmas rechazadas en prod |

## Symptom

Desconectar un número en un entorno (producción) da de baja la suscripción de la
app de Meta en su cuenta de WhatsApp Business **aunque esa suscripción emita al
webhook de otro entorno** (staging), y el número deja de recibir mensajes en
todos. Lo esperado: desconectar solo deshace en Meta lo que **este** entorno
hizo; si la suscripción apunta a otro entorno, no se toca.

## Reproduction

1. Entorno A (staging) tiene el número N conectado: su WABA está suscrita a la
   app de Meta con `override_callback_uri = https://api.staging.auphere.com/webhook/meta`.
2. En el entorno B (producción) se conecta el mismo número N en otro cliente.
   El alta (`EmbeddedSignupOrchestrator`) hace `POST /{waba}/subscribed_apps`
   con `override_callback_uri = https://webhooks.auphere.com/webhook/meta`: la
   suscripción de la app (una por WABA y app) pasa a apuntar a B.
3. En B se desconecta ese canal. En B era el último canal vivo de la WABA
   (`count_live_channels_for_waba` = 0, solo ve la base de B), así que
   `disconnect_channel` ejecuta `unsubscribe` → `DELETE /{waba}/subscribed_apps`.
4. Resultado: la WABA queda sin la app suscrita; Meta no entrega los webhooks de
   N ni a A ni a B. El canal de A sigue «activo» y su agente no recibe nada.

La variante peligrosa es la inversa: un número real de un cliente de producción
probado en staging y desconectado allí dejaría **a producción** sin mensajes.

El paso 2 también rompe A por sí solo (mientras B tiene el canal, los mensajes de
N van a B). Eso es inherente a compartir una app de Meta entre entornos y se
deshace volviendo a conectar en A; lo que este bug corrige es que la
desconexión de B no deje **a nadie** suscrito.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/channels.py:disconnect_channel` — decide `["unsubscribe"] if hermanos == 0` con `count_live_channels_for_waba`, que solo cuenta canales de esta base; nunca mira a qué URL emite la suscripción antes de borrarla.
- `apps/api/src/nexus_api/api/console/channels.py:UNLINK_STEPS` — documenta que «la suscripción es por cuenta, no por número», pero no que es también **por app y compartida entre entornos**.
- `apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py:unsubscribe_app` / `list_subscribed_apps` — existe la lectura (`GET /{waba}/subscribed_apps`, ya usada por el diagnóstico) pero la desconexión no la usa.
- `apps/channels/src/nexus_channels/whatsapp_meta/signup.py:190,314` — el alta suscribe siempre con `override_callback_uri = settings.meta_webhook_callback_url`, que es distinto por entorno (`config.py:149`; staging lo fija con `NEXUS_META_WEBHOOK_CALLBACK_URL`).
- `apps/api/src/nexus_api/api/console/diagnostics.py:webhook_subscribed` — lector puro de la respuesta de `subscribed_apps` que se puede reutilizar.

## Root Cause Hypothesis

La desconexión trata «último canal vivo de la WABA **en esta base**» como «nadie
más usa esta suscripción», pero la suscripción es de la **app**, y la app de Meta
es la misma en staging y producción. Cada entorno marca su suscripción con su
propio `override_callback_uri`, así que el dato para saber de quién es la
suscripción está en Meta y no se lee. Confianza: **alta** (secuencia de logs
completa: alta en prod con la WABA 725663313243186 y el número de staging,
desconexión 8 minutos después, y silencio total desde entonces en los dos
entornos).

## Proposed Remediation

**Preferred**: antes de `unsubscribe`, leer `GET /{waba}/subscribed_apps` con el
mismo token y localizar la entrada de **nuestra** app
(`whatsapp_business_api_data.id == settings.meta_app_id`):

- si emite a **nuestro** webhook (`override_callback_uri` igual a
  `settings.meta_webhook_callback_url`, normalizado) → desuscribir, como hoy;
- si nuestra app **no** está suscrita → no hay nada que deshacer: el paso se da
  por hecho sin llamar a `DELETE`;
- si emite a **otra** URL, o no lleva override (va al webhook general de la app,
  que no es de ningún entorno en concreto) → **no tocarla**: el paso se anota en
  `skipped` con el motivo (`subscription_elsewhere`) y el host al que emite, en
  el log y en la auditoría. Se sigue borrando la credencial local, como al
  desuscribir: este cliente ya no usa esa cuenta;
- si la lectura falla → el paso queda pendiente con su error, igual que un fallo
  de `DELETE` (el mismo endpoint lo reintenta).

La regla es «solo se borra lo que se sabe propio»: ante la duda, se deja la
suscripción. Una suscripción de más no rompe nada (sus mensajes llegan, el canal
está desconectado y se registran como no resueltos); una de menos deja a otro
entorno sordo sin aviso.

**Alternatives**:
- Una app de Meta por entorno. Lo resuelve de raíz, pero es configuración en Meta
  (app nueva, revisión, plantillas por app) y no protege de una desconexión
  manual. Complementario, no sustituto.
- Contar canales vivos en todos los entornos. Imposible sin cruzar bases
  (rompe el aislamiento por entorno).

**Files likely to change**:
- `apps/api/src/nexus_api/api/console/channels.py`
- `apps/api/src/nexus_api/api/console/diagnostics.py` (lector puro compartido, si se mueve ahí)
- `apps/api/tests/unit/test_endpoint_console_channels.py`
- `docs/` del canal de WhatsApp (lo que hace desconectar)

**Tests to add or update**:
- Desconectar el último canal de una WABA cuya suscripción emite a **otro**
  webhook → no se llama a `unsubscribe_app`; el canal queda desconectado, sin
  pendientes, y la auditoría dice `skipped: ["unsubscribe"]` con el motivo.
- Igual, con la suscripción **sin override** → no se llama a `unsubscribe_app`.
- Nuestra app **no** suscrita → sin `DELETE`, sin pendientes.
- Suscripción a **nuestro** webhook → se desuscribe como hoy (los tests
  existentes, con el simulador devolviendo nuestra URL).
- La lectura de `subscribed_apps` falla → `unsubscribe` queda pendiente con su error.

## Risks & Considerations

- **Una llamada más a Meta** al desconectar el último número de una cuenta
  (`GET` antes del `DELETE`). Sin coste y con el mismo token.
- **Forma de la respuesta.** `override_callback_uri` aparece en cada entrada de
  `GET /{waba}/subscribed_apps` cuando hay override (documentado por Meta para
  los overrides por WABA). Si Meta no lo devolviera, la regla conservadora deja
  la suscripción: el peor caso es una suscripción de más, no un entorno sordo.
- **Comparación de URL**: normalizar esquema/host en minúsculas y la barra final.
- **No arregla lo ya roto**: el `+34672138367` necesita volver a conectarse en
  staging para recuperar la suscripción.
- Aislamiento: no toca ninguna garantía; la lectura usa el token de la propia
  cuenta y no cruza tenants.

## Open Questions

- Ninguna que bloquee el arreglo. Aparte (no es este bug): conviene no reutilizar
  el número de pruebas de staging en clientes de producción, o pasar a una app de
  Meta por entorno.
