# Registro de incidencias

Fecha: 2026-10-30. Código revisado: `develop` en `9e7c71b5`. Staging: ver README §2.

## Origen de la evidencia

| Código | Significado |
|---|---|
| **QA-código** | Leído y comprobado por QA en el código, con línea citada |
| **Delegada** | Revisión estática hecha por un subagente con línea citada; QA no la ha vuelto a comprobar |
| **Doc oficial** | Contrastado hoy con `developers.facebook.com` |
| **Staging** | Observado en staging (navegador o HTTP) |
| **Doc interna** | Lo dicen las notas del propio equipo (spec, evidencia) |

- **Estado de la causa:** `CONFIRMADA` solo si el código o el entorno lo demuestran sin ambigüedad. Si depende de cómo responda Meta o de datos que no he visto, es `PROBABLE`.
- **No se ha corregido nada.** Todas las propuestas esperan autorización.

---

## Bloqueantes para grabar

### INC-01 · Catálogo: «Desconectar» y «Cambiar» llaman a un DELETE que Meta no tiene

| Campo | Valor |
|---|---|
| Canal | Catálogo (número de WhatsApp) |
| Severidad / prioridad | Alta / P1 |
| Precondiciones | Número por Cloud API con un catálogo enlazado |
| Pasos | 1. Página del número → Catálogo → «Desconectar» (o «Cambiar» y elegir otro) |
| Esperado | El enlace se quita en Meta y la tarjeta queda en «Ninguno» (o con el catálogo nuevo) |
| Real (inferido, no ejecutado) | `unlink_catalog` hace `DELETE /{waba}/product_catalogs?catalog_id=` (`apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py:544-555`). Según la referencia de Graph, ese edge no admite DELETE. Si Meta rechaza, el catálogo sigue y se guarda `catalog_error`. «Cambiar» desenlaza primero, así que tampoco funcionaría |
| Evidencia | QA-código; Doc oficial ([referencia](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/product_catalogs/)); Doc interna: `specs/050-whatsapp-al-dia/research.md` D11 («desenlazar: no hay `DELETE` del enlace») |
| Impacto | El paso 1f de las instrucciones del revisor y el paso 14 del montaje («Disconnect» para dejar el catálogo sin enlazar) fallarían delante de Meta |
| Causa | Código: CONFIRMADA. Respuesta real de Meta: PROBABLE (no se ha llamado) |
| Propuesta | No llamar a Meta al desconectar (solo quitar `config.catalog_id`, como en coexistencia). «Cambiar» = enlazar el nuevo directamente. Si hace falta quitar el enlace de verdad, documentar que se hace desde el WhatsApp Manager |
| Regresión | Test unitario: desconectar no llama a `_delete`. E2E: cambiar de catálogo A a B con un número Cloud API |
| ¿Bloquea grabar? | Sí: V-CAT-1 y las instrucciones del revisor |

### INC-02 · Catálogo: el cliente de demo está en coexistencia y no enseña la lista de catálogos

| Campo | Valor |
|---|---|
| Canal | Catálogo |
| Severidad / prioridad | Alta / P1 (preparación de la revisión) |
| Evidencia | Doc interna: `specs/049…/app-review-reviewer-setup.md` §«Estado real». El número del cliente de demo está en coexistencia, en el portfolio personal del owner; la consola entra directamente en modo manual |
| Impacto | Sin la lista, `business_management` y la lectura de `owned_product_catalogs` no se ven en uso. Además, las instrucciones del revisor piden lo contrario (número Cloud API) |
| Causa | CONFIRMADA (por diseño: Meta devuelve `(#10) SMB business type` en coexistencia, ver `specs/022…/evidence/iteracion-4-coexistencia.md`) |
| Propuesta | Conectar el número de demo por Cloud API, en un portfolio de prueba, como piden las instrucciones (requisito 2) |
| ¿Bloquea grabar? | Sí: V-CAT-1 |

### INC-03 · Instagram y Messenger: staging no puede recibir eventos reales

| Campo | Valor |
|---|---|
| Canal | Instagram, Messenger |
| Severidad / prioridad | Alta / P1 |
| Precondiciones | Una cuenta conectada en staging |
| Real | Los objetos `instagram` y `page` de la app comparten una sola URL de callback, la de producción. No existe override por activo (auditoría §3.2). El diseño de la 049 hace que producción reenvíe a staging lo que no es suyo. Pero **producción (`main` = `daf0ca15`) no tiene la spec 049**: no existe `api/webhooks/meta_social.py` en `origin/main` (`git ls-tree`), así que los descarta |
| Evidencia | QA-código (git); memoria del proyecto (T042: «webhook apuntado a staging con permiso del owner», pendiente) |
| Impacto | Ningún DM, comentario ni mensaje de Messenger llega a staging. Ninguna prueba IG-05…IG-08 ni MS-04…MS-06 es ejecutable |
| Causa | CONFIRMADA (estado de los despliegues) |
| Propuesta | Una de dos: a) promover la 049 a producción para que reenvíe; b) con permiso del owner, apuntar los webhooks `instagram` y `page` a staging durante las pruebas (corta producción, que hoy no usa esos objetos). La auditoría recomendaba una app de prueba de Meta |
| ¿Bloquea grabar? | Sí: todos los vídeos de Instagram y Messenger |

### INC-04 · Catálogo: el registro integrado no concede el catálogo a la integración

| Campo | Valor |
|---|---|
| Canal | Catálogo |
| Severidad / prioridad | Alta / P1 |
| Evidencia | Doc interna: `app-review-reviewer-setup.md` §«Avance y bloqueo» (2026-10-29, en producción). El agente responde «I couldn't access the catalog»; en «Apps conectadas → Auphere» el negocio solo concede cuentas de WhatsApp |
| Impacto | Cualquier cliente cuyo catálogo no esté en los activos de la integración no puede usar las tarjetas de producto |
| Causa | PROBABLE: la configuración del Embedded Signup no pide el activo «Catálogos». No lo he comprobado en el Dashboard |
| Propuesta | Añadir el activo de catálogo a la configuración del registro integrado (lo hace el owner en el Dashboard) o un paso para concederlo. Ver también INC-30 (mensaje engañoso) |
| ¿Bloquea grabar? | Sí: V-CAT-1 paso 3 |

### INC-05 · Despliegue: consola y API de staging en commits distintos

| Campo | Valor |
|---|---|
| Componente | Despliegue a staging |
| Severidad / prioridad | Media / P2 |
| Real | Los despliegues de la API de `e1e0b8f5`, `912ca8e1` y `177e4bb6` (spec 050) **abortaron porque CI falló** (un test de `wallet` y `test-console`). La API de staging sigue en `1fd9e254`: su `/openapi.json` no tiene `meta_graph_version` en `InstanceOut` ni las rutas `/admin/tenants/{t}/opt-outs` y `/two-step-pin`. Vercel, en cambio, publicó consola y panel de `9e7c71b5`, que llevan la 050 |
| Evidencia | Staging (OpenAPI); GitHub (runs 40979652006, 40979651999; deployments de Vercel) |
| Impacto | Mientras dure: pantallas del panel de la 050 (bajas, PIN) contra rutas que no existen (404). Las pruebas de la 050 en staging no son válidas hasta que la API llegue |
| Causa | CONFIRMADA: Vercel no espera a CI y AWS sí |
| Propuesta | Hacer que Vercel espere a CI (Ignored Build Step o despliegue desde GitHub Actions), o al menos comprobar los dos commits antes de probar |
| Estado | **El desfase se resolvió** a las 12:27 UTC, cuando la API de `9e7c71b5` llegó a staging. El riesgo de proceso sigue: la próxima CI roja volverá a dejar consola y API en commits distintos |

### INC-07 · Instagram: la respuesta pública a un comentario nunca sale

| Campo | Valor |
|---|---|
| Canal | Instagram |
| Severidad / prioridad | Alta / P1 |
| Real | `reply_comment` solo se llama si `channel.config.comment_public_reply` tiene valor (`apps/worker/src/nexus_worker/bootstrap.py:325-327`). Ningún endpoint ni código de producción lo escribe: solo hay lecturas (`api/console/channels.py:175-178`, `schemas_channels.py:112-113`, `api/webhooks/meta_social.py:183`) |
| Evidencia | QA-código (grep sin escritores fuera de los tests) |
| Impacto | El vídeo de `instagram_manage_comments` (kit §3.3, paso 3 «la respuesta aparece bajo el comentario») no se puede grabar. Incumple el Req. 4.2 de la spec 049 |
| Causa | CONFIRMADA |
| Propuesta | Exponer el ajuste en la página del canal o hacer que el agente genere la respuesta pública |
| ¿Bloquea grabar? | Sí: V-IG-3 |

---

## Otras incidencias P1

| ID | Canal | Título | Evidencia (origen) | Causa | Propuesta |
|---|---|---|---|---|---|
| INC-06 | WhatsApp | **El cron de salud quita la pausa del partner.** Con calidad YELLOW/RED, un canal en PAUSED pasa a DEGRADED, y con GREEN a ACTIVE. El cron recorre todos los canales que no están en DISCONNECTED | `apps/worker/src/nexus_worker/streams/whatsapp_health_cron.py:121-130` y `:181` (QA-código). Lo mismo con los eventos de cuenta: `services/whatsapp_account_events.py:370-388` (Delegada) | Código: CONFIRMADA. Que el agente vuelva a responder: PROBABLE | No tocar `status` si está PAUSED; guardar el problema aparte. Test: canal en pausa + calidad RED → sigue en pausa |
| INC-08 | IG, Messenger | La página del canal ofrece «A quién responde» (audiencia), pero fuera de WhatsApp no se aplica. El agente responde según `admin_access` y la consola muestra un estado que no es real | `services/channel_config.py:244`, `agent_lifecycle.py:151`, `core/admin_gate.py:91` (Delegada) | CONFIRMADA según la revisión delegada | Aplicar la audiencia por IGSID/PSID o no mostrarla en estos canales |
| INC-09 | IG, Messenger | Si el negocio quita la app o el token caduca, el canal se queda en `degraded` para siempre: no se desconecta ni arranca el borrado a 30 días. Tampoco hay callback de desautorización ni de borrado | `meta_social_cron.py:129-133`, `retention.py:113-121` (Delegada) | CONFIRMADA según la revisión delegada | Desconectar ante `token_revoked` persistente; añadir el callback con `signed_request` |
| INC-24 | IG, Messenger | Con la 049 en producción, cualquier evento de una cuenta desconocida (suscripciones viejas, desuscripciones fallidas) se reenvía a staging con contenido real de clientes finales | `config.py:679-688`, `api/webhooks/meta_social.py:94` (Delegada) | PROBABLE | Reenviar solo los ids que staging tenga registrados |

## Incidencias P2

| ID | Canal | Título | Evidencia (origen) | Causa | Propuesta |
|---|---|---|---|---|---|
| INC-10 | Messenger | `pages_read_engagement` se usa (nombre y foto de la Página, `graph.py:112`) pero no está en la configuración «Auphere Messenger» | Delegada + auditoría 2026-10-29 | CONFIRMADA (T050 abierta) | Añadirlo en el Dashboard (owner) |
| INC-11 | IG, Messenger | La app es la misma para staging y producción: **desconectar en staging hace `DELETE subscribed_apps` y corta también producción** si la cuenta está viva allí. La unicidad no cruza entornos | `meta_social/connect.py:344`, `:259-263` (Delegada) | CONFIRMADA (por diseño) | Usar activos exclusivos de staging. **Afecta a la autorización de las pruebas de desconexión** |
| INC-13 | Revisión | Las instrucciones del revisor dicen «Clients > Meta Review Demo > Channels», pero en la consola v2 la ficha del cliente solo tiene las pestañas Panel, Negocio y Agentes. Los canales se conectan desde agente → Canales. `/clients/{ref}/channels` existe pero solo se llega por URL, y solo ofrece WhatsApp | Staging (navegador, cliente «Prueba WhatsApp 016») | CONFIRMADA | Reescribir las instrucciones con la ruta del agente, o enlazar la pantalla en la ficha |
| INC-14 | WhatsApp | Desvincular borra `config_encrypted` y con él el PIN de dos pasos. Al reconectar se genera otro PIN y Meta puede rechazar el `register` | `api/console/channels.py:933`; `signup.py:173-179, 428-443` (Delegada) | PROBABLE (depende de Meta) | Conservar o rotar el PIN |
| INC-15 | WhatsApp | Cualquier fallo de `register` (5xx, timeout) se presenta como 409 «el dueño anterior lo retiene» | `signup.py:186-189`; `meta_signup_service.py:108-124` (Delegada) | CONFIRMADA | Mapear solo los códigos concretos de Meta |
| INC-16 | WhatsApp | `register` y `subscribed_apps` (con `override_callback_uri`) se llaman antes de comprobar que el número no está en otro cliente: puede repuntar el callback de otro cliente o entorno | `signup.py:176-220`; `console/whatsapp.py:110-121` (Delegada) | CONFIRMADA | Comprobar la unicidad antes de llamar a Meta |
| INC-17 | WA, IG, MS | La clave de duplicados en Redis se pone antes de procesar o encolar. Si algo falla se responde 200 y el reintento de Meta se descarta: el evento se pierde | WA: `api/webhooks/meta.py:455-458`; IG/MS: `api/webhooks/meta_social.py:160-161` frente a `:217` (Delegada) | CONFIRMADA | Poner la clave después de encolar o borrarla si falla |
| INC-18 | WhatsApp | Los cron de cobranza y reservas se bloquean con cualquier baja, también las de marketing (contradice la Historia 4.4 de la 050) | `cobranza_reminder_cron.py:602-607`; `reservation_outbox_cron.py:179-188` (Delegada) | CONFIRMADA | `blocks(marketing=False)` |
| INC-19 | WhatsApp | «cancelar», «cancela» y «salir» son palabras de baja: el mensaje no llega al agente y da de baja de marketing. En reservas son intenciones normales | `webhook_adapter.py:252-263`; `consumer.py:551-553` (Delegada) | CONFIRMADA (anterior a la 050) | Quitar las palabras ambiguas o pedir confirmación |
| INC-20 | WhatsApp | El número de Auphere se detecta por el primer `phone_number_id` del POST: un lote con varias `entry` puede perder eventos | `api/webhooks/meta.py:268-279, 398` (Delegada) | CONFIRMADA | Partir el lote antes de enrutar |
| INC-21 | Instagram | En un turno de comentario, los envíos interactivos y de medios ignoran el contexto `comment:` y mandan un DM que Meta rechaza | `meta_social/adapter.py:135-159, 283-301` (Delegada) | CONFIRMADA | Degradar a respuesta privada de texto |
| INC-22 | IG, Messenger | Los errores de Graph al enviar no se clasifican (ventana cerrada, mensajes apagados). Los helpers existen pero no se usan | `exceptions.py:61-79`; `outbound.py:1151-1172` (Delegada) | CONFIRMADA | Clasificarlos y marcar el canal |
| INC-23 | IG, Messenger | Se ignoran `standby` y el traspaso de conversación, y no hay `pass_thread_control` al tomar la conversación. El kit §3.4 pide mostrar que el hilo pasa a la bandeja | `webhook_adapter.py:103`; `graph.py:36-55` (Delegada) | PROBABLE | Suscribir `standby` y `messaging_handovers` y traspasar el hilo |
| INC-25 | IG, Messenger | El borrado de una persona deja los objetos en S3 y no limpia `username` ni `kg_node_id`. Falta el aviso al negocio (Req. 5.6) | `retention.py:51-90` (Delegada) | CONFIRMADA | Completar el borrado |
| INC-26 | Catálogo | Si el canal de la conversación no tiene catálogo, el agente usa el del primer número activo **del mismo cliente** que lo tenga (no cruza clientes) | `apps/mcp/src/nexus_mcp/servers/meta_catalog/tools.py:75-85` (QA-código) | CONFIRMADA | Respaldo solo para el Playground |
| INC-27 | Catálogo | En coexistencia, el `catalog_id` manual solo se valida por longitud (1-64) en el servidor y se interpola en la ruta Graph `/{catalog_id}/products` | `schemas_channels.py:66` (QA-código); `tools.py:151` (Delegada). La consola sí lo valida | CONFIRMADA (explotación poco probable: el token es del propio cliente) | `pattern=r"^\d{5,32}$"` en el servidor |
| INC-28 | Catálogo | Solo se listan `owned_product_catalogs`, 50 como mucho y sin paginar. Un catálogo compartido o el número 51 da `catalog_not_owned` | `meta_client.py:501-513` (Delegada) | CONFIRMADA | Paginar y añadir los catálogos de cliente |
| INC-29 | Catálogo | `catalog_message` no exige `catalog_id`; sin catálogo, Meta lo rechaza y no hay vuelta a texto. En coexistencia, con una lista vacía no aparece el formulario manual | `outbound.py:849, 1335-1346`; `catalog-picker.tsx:69-71, 163` (Delegada) | CONFIRMADA | Extender la vuelta a texto y ofrecer el modo manual con la lista vacía |
| INC-30 | Catálogo | Un rechazo de permiso de Meta (#10/#200) llega al agente como «Meta no respondió, inténtalo de nuevo», lo que le invita a reintentar | `meta_catalog/tools.py:154-158, 184-188` (Delegada) | CONFIRMADA | Código propio `catalog_permission_missing` |

## Incidencias P3 (agrupadas)

| ID | Canal | Resumen | Origen |
|---|---|---|---|
| INC-12 | Documentación | `kb/…/meta-app-ids.md` (2026-05-21) da por aprobado `business_management` y por pendiente la configuración de Instagram; el Dashboard del 2026-10-29 dice otra cosa | QA (KB frente a memoria) |
| INC-31 | IG, Messenger | El selector enseña Instagram y Messenger «Próximamente» a partners sin acceso, contra el principio de no mostrar botones apagados | Staging (navegador) + `channel-picker.tsx:29-30` (Delegada) |
| INC-32 | IG, Messenger | Al cerrar la ventana de Meta, la consola dice «sin código» en vez de «cancelado»; no hay «Reconectar» en un canal degradado; la cabecera muestra el tipo en minúscula | Delegada |
| INC-33 | API | Staging publica `/docs` y `/openapi.json` sin autenticación (565 rutas, incluidas las de `/admin`) | Staging (HTTP 200) |
| INC-34 | WhatsApp | Sin `state`: el alta se ata a la sesión de consola y al `ref` (riesgo bajo). `debug_token` existe pero no se usa para validar `waba_id`/`phone_number_id`. El `client_secret` va en la query del canje. `resolve_waba_tenants` (SECURITY DEFINER) sin `SET search_path`. La migración 0206 se editó después de crearla. Límites del `code` distintos (512 / 2048). Errores crudos en español o inglés. `tasks.md` cita tests que no existen | Delegada |
| INC-35 | IG, Messenger | Un código 200 cualquiera se lee como «mensajes apagados». Dos `complete` simultáneos dan 500 en vez de 409. La ventana de 7 días de la respuesta privada cuenta desde el webhook. Una reacción siempre manda `love`. HUMAN_AGENT se acepta de un operador sin persona nombrada. Verify token comparado con `!=`. Si se quita la beta, los canales siguen activos pero el partner deja de verlos | Delegada |
| INC-36 | Catálogo | Etiqueta de `catalog.get_product` engañosa («Enviar»). Descripción de esquema contradictoria. `catalog_thumbnail_retailer_id` nunca se escribe. Caché por WABA y no por cliente. `meta.unverified` no se enseña en la tarjeta. Los endpoints de catálogo con un canal IG/MS darían 500 (`KeyError`) | Delegada |

## Añadida al corregir (2026-10-30, tarde)

| ID | Canal | Título | Evidencia (origen) | Causa | Propuesta |
|---|---|---|---|---|---|
| INC-37 | IG, Messenger | Un DM que llega a un canal en pausa o degradado se descarta, en vez de guardarse para una persona como en WhatsApp | `apps/api/src/nexus_api/api/webhooks/meta_social.py`, `_enqueue_once`: `channel_status != ACTIVE` → `return False` (QA-código) | CONFIRMADA | Guardar el mensaje y dejar que la puerta del turno decida, como en WhatsApp |

## Añadidas al preparar la cuenta de revisión (2026-10-31)

| ID | Canal | Título | Evidencia (origen) | Causa | Propuesta |
|---|---|---|---|---|---|
| INC-38 | Todos | Un partner de staging sin clave del proxy LiteLLM no puede usar la IA: el constructor, el chat de prueba y las pruebas fallan con `missing partner virtual key`. Además, `nexus/staging/litellm-admin` estaba vacío desde el 2026-09-01 | Logs de `/nexus/staging/api` y `/runner` (Staging) | CONFIRMADA | Dar clave al partner de revisión (hecho: `scripts/ops/staging-litellm-partner-key.sh`) y rellenar el secreto de administración (hecho: `staging-litellm-admin-secret.sh`). Falta un paso en el alta de partners de staging |
| INC-39 | Todos | El agente dice «te paso con el equipo» y no pasa la conversación. `escalate.escalate_to_human` exige `conversation_id`, un UUID interno que el modelo no conoce, y el sistema solo lo rellenaba si el modelo lo escribía; si no, el modelo se negaba («the conversation ID isn't available») | Prueba «Pide hablar con una persona» de Ava (Staging); `apps/worker/src/nexus_worker/runtime/pipeline.py`, `_dispatch_tool` (QA-código) | CONFIRMADA | El modelo ya no ve un `conversation_id` obligatorio y el sistema lo rellena siempre (corregido en develop) |
| INC-40 | Todos | Un agente del constructor sin la herramienta de escalar en su lista no tiene forma de recibirla desde la consola (el copiloto no toca `/tools` y no hay editor). La ficha «Cuándo pasa a una persona» solo escribe texto en el prompt | `copilot_model.py:41, 92`; `compiler.py:138-147` (Delegada) | PROBABLE | Añadir `escalate.escalate_to_human` al borrador cuando hay disparadores de escalado |

El estado de cada incidencia corregida está en `06-correcciones.md`.
