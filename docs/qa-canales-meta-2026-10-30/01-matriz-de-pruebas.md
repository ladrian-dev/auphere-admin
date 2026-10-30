# Matriz de pruebas y resultados

Fecha de ejecución: 2026-10-30. Entorno: staging (`console.staging.auphere.com`, `api.staging.auphere.com`) y local (BD `nexus_test`).

## Cómo leer la matriz

**Prioridades:**
- **P0**: seguridad o aislamiento.
- **P1**: conexión y función principal.
- **P2**: configuración y recuperación.
- **P3**: detalles.

**Nivel de verificación:**
- **[C]**: inspección de código.
- **[M]**: tests automáticos con mocks.
- **[E2E]**: integración real.

**Estados:** PASS, FAIL, BLOQUEADA, NO EJECUTADA y NO APLICA.

**Datos de prueba usados en staging:**
- Partner «Demo (staging)», con la sesión del owner ya abierta en el navegador integrado.
- Cliente «Prueba WhatsApp 016» y su «Agente principal».
- No se ha enviado ningún mensaje, conectado ningún activo ni cambiado ningún dato.

## 1. Transversales

| ID | Funcionalidad | Tipo | Prio | Pasos | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|
| T-ENV-01 | Versión desplegada en staging | Despliegue | P1 | Historial de `deploy-staging.yml`, despliegues de Vercel y huella de `/openapi.json` | Commit conocido para la API y la consola Hasta las 12:27 UTC: API en `1fd9e254` y consola en `9e7c71b5` (INC-05). Desde las 12:27 UTC, las tres piezas en `9e7c71b5`: el OpenAPI de staging coincide al 100 % con el local | PASS | README §2 |
| T-WH-01 | Webhook: verify token incorrecto | Seguridad [E2E] | P0 | `GET /webhook/meta?hub.mode=subscribe&hub.verify_token=<incorrecto>` | 403 | 403 `bad verify_token`. T-WH-01…04 se repitieron con la API en `9e7c71b5`: mismo resultado | PASS | curl 2026-10-30 |
| T-WH-02 | Webhook: POST sin firma | Seguridad [E2E] | P0 | POST `{"object":"qa_test","entry":[]}` sin `X-Hub-Signature-256` | 401, sin procesar | 401 `invalid signature` | PASS | curl |
| T-WH-03 | Webhook: firma falsa | Seguridad [E2E] | P0 | Igual con `sha256=000…` | 401 | 401 | PASS | curl |
| T-WH-04 | Webhook: cabecera de reenvío falsificada | Seguridad [E2E] | P0 | Igual con `X-Auphere-Forwarded: prod` y sin firma | 401 (el reenvío no salta la firma) | 401 | PASS | curl |
| T-HDR-01 | CSP y COOP para la ventana de Meta | Configuración [E2E] | P1 | `curl -I /login` | `connect.facebook.net` en `script-src`; `www/web/staticxx.facebook.com` en `frame-src`; COOP `same-origin-allow-popups` | Coincide | PASS | Cabeceras |
| T-UI-01 | La consola carga sin errores propios | UI [E2E] | P2 | Inicio → Clientes → ficha → agente | Sin errores de la aplicación | Solo aparece el bloqueo CSP de `vercel.live` (barra de previsualización de Vercel; no es de la aplicación) | PASS | Consola del navegador |
| T-SEC-01 | Documentación de la API expuesta | Seguridad [E2E] | P3 | `GET /docs`, `/openapi.json` | Cerrado o aceptado a propósito | 200 públicos | FAIL (menor, INC-33) | curl |

## 2. WhatsApp

| ID | Funcionalidad | Tipo | Prio | Precondiciones | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|---|---|---|
| WA-01 | Acceso al flujo de conexión | UI [E2E] | P1 | Agente sin canal | Tarjeta WhatsApp «Conectar» → diálogo con Coexistencia (recomendado), Cloud API y «Compartir un enlace» | Coincide. Me detuve antes de «Conectar», que abre Meta | PASS (solo la parte de Auphere) | Captura del diálogo |
| WA-02 | Autorización con Embedded Signup | E2E | P1 | Número real dedicado y autorización | Ventana de Meta, permisos y vuelta con `code` | — | BLOQUEADA: hace falta autorizar la conexión de un activo real y un número dedicado | — |
| WA-03 | Elegir y asociar la WABA y el número | E2E | P1 | WA-02 | Número asociado al cliente correcto | — | BLOQUEADA | — |
| WA-04 | Persistencia (`waba_id`, `phone_number_id`, estado) | [M] + E2E | P1 | — | Datos guardados y fusionados al reconectar | [M] ver AUTO-API; E2E pendiente | BLOQUEADA (E2E) | — |
| WA-05 | Configuración de la página del canal (audiencia, escalada) | [M] + E2E | P2 | Canal conectado | Guardado con `If-Match` | No hay ningún canal conectado en el partner de staging | BLOQUEADA (E2E) | Inicio: «0 de 3 clientes sin problemas», todos sin canal |
| WA-06 | Salud de la cuenta y plantillas (050) | [M] + E2E | P2 | API con 050 | Calidad, límite y plantillas | La API ya tiene la 050 (desde las 12:27 UTC), pero no hay ningún número conectado en staging | BLOQUEADA | — |
| WA-07 | Recepción de mensajes | E2E | P1 | Canal + teléfono de prueba | Mensaje en la bandeja | — | BLOQUEADA | — |
| WA-08 | Envío a un destinatario de prueba | E2E | P1 | Autorización | Respuesta entregada | — | BLOQUEADA (necesita autorización) | — |
| WA-09 | Errores: permisos, número retenido, credencial inválida | [M] | P2 | — | Motivo claro | [M] pasan; en código se ven INC-15 e INC-16 | PASS [M] / FAIL [C] | AUTO-API; INC-15/16 |
| WA-10 | Desconectar y reconectar | E2E | P2 | Autorización | Deshace en Meta; reconectar funciona | En código: posible pérdida del PIN (INC-14) | BLOQUEADA | — |
| WA-11 | Regresión de conexiones previas | [M] | P1 | — | Sin cambios de comportamiento | [M] pasan. En código: el cron de salud quita la pausa (INC-06) | FAIL [C] | INC-06 |
| WA-12 | Bajas de marketing (050) | [M] [C] | P2 | — | Solo bloquean marketing | Los cron de cobranza y reservas bloquean con cualquier baja | FAIL [C] | INC-18, INC-19 |

## 3. Catálogo (catálogo de Meta Commerce enlazado al número de WhatsApp, spec 022)

| ID | Funcionalidad | Tipo | Prio | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|---|---|
| CAT-01 | Acceso al selector «Conectar catálogo» | E2E | P1 | En la tarjeta del número | Sin número conectado en staging | BLOQUEADA | — |
| CAT-02 | Lista de catálogos del negocio | E2E | P1 | `owned_product_catalogs` del portfolio del cliente | — | BLOQUEADA (INC-02: en coexistencia no hay lista) | — |
| CAT-03 | Enlazar un catálogo | E2E | P1 | `POST /{waba}/product_catalogs` y tarjeta actualizada | — | BLOQUEADA | — |
| CAT-04 | Persistencia y conciliación con Meta | [M] | P2 | `config.catalog_id`; `/overview` concilia | [M] pasan | PASS [M] | AUTO-API (`test_endpoint_console_catalog.py`) |
| CAT-05 | El agente lee productos y manda una tarjeta | E2E | P1 | Tarjeta nativa | En producción, el 2026-10-29, respondió «I couldn't access the catalog» | BLOQUEADA (INC-04) | Doc interna |
| CAT-06 | Catálogo vacío, sin permiso, inaccesible | [M] [C] | P2 | Motivo claro | El rechazo de permiso llega como error transitorio | FAIL [C] | INC-30 |
| CAT-07 | Paginación | [C] | P2 | Todos los catálogos | Como mucho 50, sin paginar | FAIL [C] | INC-28 |
| CAT-08 | Cambiar y desconectar | [C] + Doc oficial | P1 | Funciona en Meta | DELETE que Meta no tiene | FAIL [C] (pendiente de E2E) | INC-01 |
| CAT-09 | Aislamiento: un catálogo ajeno no se enlaza | [M] P0 | P0 | `catalog_not_owned` | [M] pasan (`test_channel_catalog_scope.py`). En coexistencia se puede declarar cualquier id | PASS [M] con salvedad (INC-27) | AUTO-API |
| CAT-10 | Crear o modificar productos | — | — | — | No existe en el código (planificado en la 050, T050) | NO APLICA | Revisión estática |

## 4. Messenger

| ID | Funcionalidad | Tipo | Prio | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|---|---|
| MS-01 | Inicio del flujo | E2E | P1 | Tarjeta «Conectar» | Tarjeta «Próximamente»: el partner no tiene `messenger` en `beta_channels` | BLOQUEADA (activar la beta = cambio de datos; necesita autorización) | Captura del selector |
| MS-02 | Elegir la Página | E2E | P1 | Lista de Páginas | — | BLOQUEADA | — |
| MS-03 | Suscripción (`subscribed_apps`) | [M] | P1 | Campos correctos | [M] pasan | PASS [M] | AUTO-CH/API |
| MS-04/05 | Recibir y enviar | E2E | P1 | Ida y vuelta | Staging no recibe eventos de Page | BLOQUEADA (INC-03) | — |
| MS-06 | Agente humano (7 días) | [M] | P1 | Etiqueta HUMAN_AGENT solo con una persona | [M] pasan (`test_meta_window.py`) | PASS [M] | AUTO-API |
| MS-07 | Perfil de quien escribe | [C] | P2 | Con la función aprobada | Función no pedida | BLOQUEADA (decisión del owner) | 03-permisos |
| MS-08 | Desconectar | E2E | P2 | Desuscribe | Afecta a producción si es el mismo activo | BLOQUEADA (INC-11) | — |
| MS-09 | Token revocado | [C] | P2 | Pasa a desconectado | Se queda en `degraded` | FAIL [C] | INC-09 |
| MS-10 | Aislamiento: una Página en un solo cliente | [M] P0 | P0 | Rechazo | [M] pasan | PASS [M] | `test_meta_social_channel_isolation.py` |

## 5. Instagram (login unificado: Facebook Login for Business con la configuración de Instagram y token de usuario del sistema)

| ID | Funcionalidad | Tipo | Prio | Esperado | Observado | Estado | Evidencia |
|---|---|---|---|---|---|---|---|
| IG-01 | Inicio del flujo | E2E | P1 | «Conectar» | «Próximamente» (sin beta) | BLOQUEADA | Captura |
| IG-02 | Compatibilidad de la cuenta de prueba | E2E | P1 | Profesional, en un portfolio, con mensajes permitidos | No hay cuentas con rol (0 evaluadores) | BLOQUEADA | Auditoría 2026-10-29 |
| IG-03 | Autorización y elección de la cuenta | [M] | P1 | `assigned_instagram_accounts`; el token nunca va al navegador | [M] pasan; [C] lista cifrada en Redis con nonce de 10 min | PASS [M] | Revisión delegada |
| IG-04 | Persistencia | [M] | P1 | Token en `config_encrypted` por canal | [M] pasan | PASS [M] | — |
| IG-05/06 | Recibir DM y responder | E2E | P1 | Ida y vuelta | Staging no recibe | BLOQUEADA (INC-03) | — |
| IG-07 | Comentarios: respuesta pública y privada | [C] | P1 | Las dos salen | La pública nunca se dispara | FAIL [C] | INC-07 |
| IG-08 | Agente humano con login unificado | — | P1 | Funciona | Sin confirmar con Meta | BLOQUEADA | Auditoría §3.5 |
| IG-09 | Errores: mensajes apagados, permiso | [C] | P2 | Motivo correcto | Cualquier código 200 se lee como «mensajes apagados»; los errores de envío no se clasifican | FAIL [C] | INC-22, INC-35 |
| IG-10 | Audiencia de la página del canal | [C] | P1 | Se aplica | No se aplica fuera de WhatsApp | FAIL [C] | INC-08 |

## 6. Tests automáticos ejecutados (local, `9e7c71b5`)

Todos usan **mocks** de Meta. No validan la integración real.

| ID | Suite | Resultado | Estado |
|---|---|---|---|
| AUTO-CON | Consola vitest: `meta-fb-sdk`, `components/channels/*` (incluidos `catalog-picker`, `whatsapp-connect`, `channel-card`), `builder/channel-*`, `agent-channels`, `catalog/*`, `channel-actions` | 17 ficheros, **179 PASS** | PASS [M] |
| AUTO-API | API: ficheros de canales, webhooks, alta, catálogo, meta_social y aislamiento (lista en README §5) | **332 PASS**, 0 FAIL, en 15 min 27 s | PASS [M] |
| AUTO-CH | `apps/channels/tests` (firma, cliente de Meta, adaptadores de WhatsApp y meta_social) | **100 PASS** | PASS [M] |
| AUTO-WK | `apps/worker/tests/unit` (incluye `test_whatsapp_health_cron.py`) | **653 PASS** | PASS [M] |
| AUTO-MCP | `apps/mcp/tests/test_meta_catalog_tools_unit.py` | **7 PASS** | PASS [M] |

**Qué significa que pasen.** Todas las suites pasan, y aun así hay FAIL [C] en la matriz. La razón es que los tests no cubren esos casos:
- el cron de salud con un canal pausado (INC-06);
- desconectar un catálogo contra el Meta real (INC-01: el mock acepta el DELETE);
- la respuesta pública a un comentario (INC-07);
- la clave de duplicados tras un fallo (INC-17);
- la clasificación de errores de Graph (INC-22).

Cada uno de estos huecos necesita su prueba de regresión, que se indica en la incidencia.
| AUTO-CI | CI de GitHub de `9e7c71b5` (run 41046402212: lint, api, console, admin, mobile, renderer, terraform) | Verde; despliegue a staging con éxito | PASS [M] |
