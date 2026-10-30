# QA de canales Meta en staging (2026-10-30)

Validación de lo que `develop` lleva a staging para conectar y configurar **WhatsApp, Catálogo, Messenger e Instagram**, y preparación de los vídeos para la revisión de Meta.

| Documento | Contenido |
|---|---|
| [01-matriz-de-pruebas.md](01-matriz-de-pruebas.md) | Casos, resultados y nivel de verificación |
| [02-incidencias.md](02-incidencias.md) | Registro de incidencias con evidencia |
| [03-permisos-meta.md](03-permisos-meta.md) | Permiso → uso real → requisito → caso → escena |
| [04-guiones-de-grabacion.md](04-guiones-de-grabacion.md) | Guiones por vídeo (provisionales) |
| [05-checklist-antes-de-grabar.md](05-checklist-antes-de-grabar.md) | Checklist común y por vídeo |
| [06-correcciones.md](06-correcciones.md) | Lo corregido después del QA (INC-01, 06, 07, 08, 09, 13, 17, 22, 27, 30) y lo que queda |

> **Actualización 2026-10-30, tarde:** ocho commits en `develop` corrigen los bloqueantes de código. El detalle está en `06-correcciones.md`. Las tablas de abajo reflejan el QA **antes** de esas correcciones; los casos FAIL [C] corregidos hay que repetirlos en staging.

## 1. Alcance

| Canal | Qué es en este producto | Cambio que lo trae |
|---|---|---|
| WhatsApp | Número del cliente por Cloud API o coexistencia, conectado con Embedded Signup desde la consola de partners (agente → Canales) o con el enlace del dueño | Specs 016, 021, 047 (página del canal) y **050 it. 1** (lotes y BSUID, registro v4/v5, Graph v26, salud de cuenta y plantillas, bajas de marketing; migraciones 0206 y 0207) |
| Catálogo | Catálogo de **Meta Commerce enlazado a la WABA del número de WhatsApp**: se lista, se enlaza y el agente lo lee (`catalog.search_products`, `catalog.get_product`) para mandar tarjetas `product`/`product_list`. No hay catálogo en Instagram ni en Messenger. El código no crea ni edita productos | Spec 022 (it. 1-4). La 050 solo lo planifica |
| Messenger | Página de Facebook con Facebook Login for Business (configuración `2188508105420190`), token de usuario del sistema por canal, webhook `object=page` | **Spec 049** (0205) |
| Instagram | Cuenta profesional con **login unificado** (configuración `1157578836735566`), permisos `instagram_*` (no `instagram_business_*`), webhook `object=instagram`, DM, comentarios y respuesta privada | **Spec 049** |

Fuera de alcance: `instagram_content_publish` (decisión del owner), Threads, TikTok, Telegram y producción.

## 2. Versión de staging

**Estado final (2026-10-30, 12:27 UTC): API, consola y panel de staging en `9e7c71b5`.**

| Pieza | Commit | Cómo se sabe |
|---|---|---|
| API (AWS) | **`9e7c71b5`** | `deploy-staging` run 41046402283 con éxito a las 12:27 UTC. Huella: el `/openapi.json` de staging tiene **exactamente** las mismas rutas que la API local de `9e7c71b5` (0 de diferencia en cualquier sentido) e `InstanceOut` ya trae `meta_graph_version`. `/admin/instance` daría el commit exacto, pero pide un token de admin que no tengo |
| Consola y panel (Vercel) | `9e7c71b5` | Despliegues de GitHub «Preview – auphere-console-staging» y «auphere-admin» con éxito |
| API antes de las 12:27 | `1fd9e254` (049 sin la 050) | Las rutas de la 050 faltaban (INC-05). Las pruebas de UI de staging de este informe se hicieron **antes** de las 12:27, con la consola en `9e7c71b5` y la API en `1fd9e254`. Las de webhook se repitieron después, con el mismo resultado |

- **Por qué la 050 no está en la API:** sus tres despliegues abortaron porque CI falló (`test_agent_cap_and_alerts` y `test-console`). Esos fallos se arreglaron en `9fd0001b` y `644d0d73`; CI de `644d0d73` salió verde.
- **Punto de comparación:**
  - para la 049: `d480dc43`, el despliegue anterior con éxito;
  - para la 050: `1fd9e254`, lo desplegado hoy;
  - en conjunto: `1fd9e254..9e7c71b5`, que trae 050 y 047.
- **Copia local:** `develop` estaba 9 commits por detrás; lo avancé por fast-forward a `9e7c71b5`, sin tocar los ficheros sin versionar.

## 3. Resumen ejecutivo por canal

| Canal | Conexión | Configuración | E2E verificado | PASS / FAIL / BLOQ. / NO EJEC. | Bloqueantes | Listo para grabar | Requisitos Meta pendientes |
|---|---|---|---|---|---|---|---|
| WhatsApp | UI hasta la ventana de Meta: PASS. Alta real: BLOQUEADA | BLOQUEADA (no hay canal en staging) | Solo webhook (firma y verify) y UI previa | 1 + 1 [M] / 3 [C] / 8 / 0 | INC-06 (INC-05 resuelta al desplegar) | **Bloqueado por accesos** (número dedicado y autorización) | Meta revisa de nuevo el acceso existente; instrucciones del revisor desactualizadas (INC-13) |
| Catálogo | BLOQUEADA | PASS [M] | Ninguno | 1 [M] + 1 [M] con salvedad / 3 [C] / 4 / 0 · 1 NO APLICA | **INC-01, INC-02, INC-04** | **Bloqueado por incidencias** | `catalog_management` y `business_management` en borrador sin enviar |
| Messenger | BLOQUEADA (beta apagada en el partner) | — | Ninguno | 3 [M] / 1 [C] / 6 / 0 | **INC-03**, INC-10, INC-11 | **Bloqueado por incidencias y accesos** | Sin aprobar ni enviar; T050 (`pages_read_engagement`, `messaging_policy_enforcement`) |
| Instagram | BLOQUEADA (beta apagada, 0 evaluadores) | — | Ninguno | 2 [M] / 3 [C] / 5 / 0 | **INC-03, INC-07**, INC-08 | **Bloqueado por incidencias y accesos** | Sin aprobar ni enviar; Human Agent con login unificado sin confirmar; decisión sobre Business Asset User Profile Access |

En la tabla:
- «[M]» = PASS con mocks.
- «[C]» = FAIL por inspección de código (falta reproducirlo E2E).

Nada está **«Listo técnicamente para grabar»**:
- **Pendiente de validación de requisitos de revisión:** las reglas de grabación se contrastaron hoy con la guía oficial; la regla de «llamadas en 30 días» y la lista de Messenger, no.
- **Bloqueado por incidencias o accesos:** los cuatro canales.

## 4. Lo que falta para seguir (en un solo bloque)

**Accesos y datos:**
1. Activos de prueba con rol en la app:
   - un número dedicado para Cloud API;
   - una cuenta profesional de Instagram en un portfolio y una cuenta personal;
   - una Página de Facebook publicada.
2. ~~Que termine el despliegue de `9e7c71b5`~~: hecho a las 12:27 UTC.
3. Opcional: el commit exacto de la API vía `/admin/instance`. Lo puedes mirar tú en el panel → Estado; no compartas el token.

**Decisiones del owner:**
4. Dónde se graba: staging, o producción como dicen las instrucciones del revisor (C-01).
5. Cómo recibe staging los eventos de Instagram y Messenger (INC-03).

**Autorizaciones con efecto fuera de Auphere o en datos persistentes** (no hago ninguna sin tu sí, por acción y por activo):

| Acción | Efecto |
|---|---|
| Activar `instagram` y `messenger` en `beta_channels` del partner «Demo (staging)» | Cambio de datos en staging |
| Conectar un número por Embedded Signup | Registra el número en Meta, cambia el callback de la WABA y lo saca de la app si es Cloud API |
| Enviar mensajes de prueba | Escribe a destinatarios de prueba |
| Enlazar o desenlazar un catálogo | Cambia el activo en Meta; desenlazar probablemente falle (INC-01) |
| Desconectar Página o Instagram | Desuscribe la app de la Página **también para producción** (INC-11) |
| Repuntar webhooks en el Dashboard | Lo hace el owner |

## 5. Cómo se ejecutó

**Revisión estática:**
- tres revisiones delegadas en paralelo (WhatsApp, Instagram/Messenger, Catálogo);
- QA comprobó en el código las P1 que cita como «QA-código».

**Tests locales**, uno detrás de otro contra `nexus_test`, con el entorno de la API:
- **API:**
  - `unit/test_endpoint_console_meta_social.py`, `test_endpoint_webhook_meta_social.py`, `test_meta_window.py`;
  - `test_endpoint_console_whatsapp.py`, `test_endpoint_console_channels.py`, `test_endpoint_meta_signup.py`;
  - `test_endpoint_webhook_meta_{batches,coexistence,inbound}.py`, `test_webhook_meta_status_publishes.py`;
  - `test_whatsapp_template_cache.py`, `test_endpoint_console_catalog.py`, `test_admin_whatsapp_pin.py`;
  - `isolation/test_meta_social_channel_isolation.py`, `test_whatsapp_identity_bsuid.py`, `test_channel_catalog_scope.py`;
  - `isolation/test_channel_number_scope.py`, `test_9_channel_credentials_scoped.py`, `test_signup_scope.py`;
  - `integration/channels/*`, `test_channel_credentials.py`, `test_channel_routing.py`;
  - `test_channel_signup_links.py`, `test_admin_channels_and_connectors.py`.
- **Paquetes:** `apps/channels/tests`, `apps/worker/tests/unit` y `apps/mcp/tests/test_meta_catalog_tools_unit.py`.
- **Consola (vitest):** los 17 ficheros de canales y catálogo.

**Staging:**
- HTTP sin efectos: salud, verify token y firma del webhook con payloads vacíos de tipo `qa_test`, cabeceras.
- Navegador integrado con la sesión del owner, **solo lectura**. Abrí el diálogo «Conectar WhatsApp» y lo cerré sin abrir Meta.

**Documentación oficial consultada hoy:**
- referencia de `/{waba}/product_catalogs`;
- guía de grabaciones de App Review.

## 6. Conclusión

- **La base de seguridad que se puede probar desde fuera se sostiene:**
  - firma del webhook, verify token y cabecera de reenvío sin bypass;
  - CSP y COOP correctos para la ventana de Meta;
  - tokens solo en el servidor;
  - aislamiento cubierto por tests.
- **Pero no se puede grabar ningún vídeo todavía.**
  - **WhatsApp:** la API de staging ya tiene la 050; falta un activo real y autorización para conectarlo.
  - **Catálogo:** tres bloqueantes de producto o configuración. El más claro es INC-01: «Desconectar» o «Cambiar» delante del revisor fallaría.
  - **Instagram y Messenger:** staging no recibe sus eventos (INC-03), y la respuesta pública a comentarios no existe en la práctica (INC-07).
- **Orden recomendado:**
  1. Arreglar INC-01, INC-06 e INC-07.
  2. Decidir INC-03.
  3. Montar los activos con rol.
  4. Repetir los casos BLOQUEADOS en E2E.
  5. Ensayar los guiones.
- Esto mide la preparación técnica; la decisión es de Meta.
