# Guía de validación: 050 — WhatsApp al día

Cómo probar que cada iteración funciona de punta a punta. Contratos: [contracts/](contracts/). Datos: [data-model.md](data-model.md).

## Requisitos previos

- **Local:** Docker con Postgres y Redis de pruebas. Ejecutar una sola suite pytest a la vez contra `nexus_test`.
- **Staging:**
  - un número de prueba por Cloud API y otro en coexistencia;
  - una cuenta de WhatsApp de prueba **con nombre de usuario** y sin conversación previa con el número;
  - un portafolio de negocio sin catálogo;
  - un partner con la consola nueva.
- **Cargas firmadas:** `tests/fixtures/meta_webhooks/*.json`, una por campo de [webhook-events.md](contracts/webhook-events.md). Se firman con `sign_meta_request(app_secret, body)`.

## Iteración 1

| # | Escenario | Cómo | Resultado esperado |
|---|---|---|---|
| 1 | Lote de 5 mensajes y 5 estados | `POST /webhook/meta` con la carga de lote | 5 entradas en el stream y 5 estados aplicados; ningún `unhandled_field` |
| 2 | Mensaje solo con BSUID | Carga con `from_user_id` y sin `from` | El cliente se crea con `identifier = bsuid` y el agente responde; la respuesta sale con `recipient` |
| 3 | La misma persona con teléfono y luego con BSUID y teléfono | Dos cargas | Un solo cliente, con `phone` y `bsuid`, en la misma conversación |
| 4 | `user_changed_number` | Carga de sistema | `phone` actualizado, sin turno del agente |
| 5 | Registro integrado v4 | Conectar por Cloud API, coexistencia, enlace del dueño y beta de inicio de sesión con WhatsApp, en staging | Cada número queda activo, suscrito y respondiendo; los `extras` no llevan `sessionInfoVersion` |
| 6 | Reconexión | Volver a conectar un número con catálogo y audiencia | Conserva `catalog_id`, audiencia y escalado |
| 7 | PIN | Alta por Cloud API, luego rotar desde el panel | PIN guardado cifrado; rotación auditada; nunca sale en una respuesta |
| 8 | Versión de Graph | `grep` de versiones en el código y en las llamadas de staging | Solo `v26.0`, tomada de la configuración |
| 9 | Plantilla pausada | Carga `message_template_status_update` `PAUSED` | Aviso al partner, la plantilla no se ofrece y la caché se invalida |
| 10 | Evento de socio sin número | `account_update` `PARTNER_REMOVED` con `waba_info` | Los números de esa WABA del negocio quedan en problema; otro negocio con otra WABA no cambia |
| 11 | Cron frente a problema de cuenta | Problema de cuenta y luego calidad `GREEN` | El problema de cuenta sigue |
| 12 | Baja de Meta | `user_preferences` `stop` y luego una difusión de marketing | La difusión no le llega; una plantilla de utilidad sí |
| 13 | Reactivación | `user_preferences` `resume` | La baja se levanta y queda constancia |
| 14 | «STOP» escrito | Mensaje «baja» | Llega a la bandeja marcado; no hay turno; la baja es de marketing |

Aislamiento: `tests/isolation/` (ver [plan.md](plan.md), «Las tres puertas»).

## Iteración 2

| # | Escenario | Resultado esperado |
|---|---|---|
| 15 | Crear plantillas con cabecera de imagen, de autenticación con copiar código y en carrusel | Meta las aprueba en staging; la consola muestra su estado y su calidad |
| 16 | Pulsar un botón de plantilla | El agente recibe el botón y la plantilla de origen, y responde |
| 17 | Mensaje desde un anuncio de clic a WhatsApp (carga con `referral`) | `ad_referral` guardado; el agente lo tiene como contexto |
| 18 | Turno del agente | Primero el acuse con indicador de escritura, después la respuesta |
| 19 | El agente envía una ubicación y la pide | Ubicación nativa; la respuesta de la persona llega como ubicación |
| 20 | Precio | En Consumo, «Mensajes de Meta» por categoría y cuántos se cobraron; nada se suma a lo que cobra Auphere |

## Iteración 3: catálogo

| # | Escenario | Resultado esperado |
|---|---|---|
| 21 | Número sin catálogo → «Crear catálogo» | Catálogo creado en el portafolio, enlazado y visible |
| 22 | Añadir 3 productos con foto y precio | Aparecen con su estado en Meta; el agente envía la tarjeta |
| 23 | Cambiar precio y marcar uno como agotado | La siguiente respuesta usa el precio nuevo; el agotado no se ofrece |
| 24 | Borrar un producto | Confirmación con su nombre, auditoría, el agente no lo ofrece |
| 25 | Catálogo con feed (Barber Supply en staging) | Solo lectura, con «Se gestiona desde la tienda o el archivo del negocio» |
| 26 | Número en coexistencia | Modo manual de hoy, con la explicación |
| 27 | Agente sin herramientas de catálogo en su plantilla y número con catálogo | El agente busca productos y envía tarjetas |
| 28 | Revisión de Meta | Vídeo de `catalog_management` (crear, editar y borrar) y de `business_management` (crear en el portafolio) según el kit |

## Iteración 4: perfil

| # | Escenario | Resultado esperado |
|---|---|---|
| 29 | Editar la descripción y la foto (Cloud API) | WhatsApp las muestra; queda auditado |
| 30 | Abrir el perfil de un número en coexistencia | Explicación, sin formulario |

## Comprobación de cada iteración

```bash
NODE_OPTIONS=--experimental-require-module ./scripts/verify.sh lint
```

Después, las suites de la iteración por fichero (no la suite completa entera) y CI en `develop` antes de mirar staging.
