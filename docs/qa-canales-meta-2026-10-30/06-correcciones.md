# Correcciones aplicadas tras el QA (2026-10-30)

Autorizadas por el owner el 2026-10-30. Todas van en `develop` y llegan **solo a staging** al subirlas. `main` (producción) no se toca. Cada una lleva su prueba de regresión.

## Resueltas en código

| Incidencia | Commit | Qué cambia | Prueba de regresión |
|---|---|---|---|
| INC-01 · Catálogo: DELETE inexistente | `3910f73f` | «Cambiar» enlaza el nuevo sin desenlazar. «Desconectar» no llama a Meta: quita el catálogo del número y lo marca como `catalog_detached`, y la conciliación no lo vuelve a adoptar mientras Meta lo siga teniendo. `MetaClient.unlink_catalog` eliminado. El texto de confirmación dice que el enlace en Meta se quita desde el Administrador de WhatsApp | `test_endpoint_console_catalog.py`: cambiar sin desenlazar; si falla, el viejo sigue; desconectar sin llamar a Meta; no se readopta; volver a enlazar limpia la marca. `test_meta_client.py`: no existe `unlink_catalog` |
| INC-06 · La salud quitaba la pausa | `ac48c753` | `set_health` / `health_degraded`: con el canal en pausa se cambia `before_pause` y el estado sigue en `paused`. Se aplica en el cron de salud de WhatsApp, los eventos de cuenta, el cron de meta_social y el despachador | `test_channel_health_keeps_the_pause.py`; `test_whatsapp_health_cron.py::test_a_paused_number_stays_paused_whatever_the_quality` |
| INC-07 · Respuesta pública a comentarios | `05f2060f` | Sección «Comentarios» en la página del canal de Instagram: atender o no y la línea pública (hasta 300 caracteres). Endpoint `PUT /console/clients/{ref}/channels/{id}/comments` con auditoría. La cabecera dice «Instagram» o «Messenger» | `test_endpoint_console_meta_social.py` (2 casos); `channel-comments.test.tsx` |
| INC-27 · `catalog_id` sin validar | `f759dfea` | El servidor exige cifras (1-32) | `test_a_catalog_id_that_is_not_digits_is_refused_before_meta` |
| INC-30 · Permiso presentado como «reinténtalo» | `f759dfea` | Las herramientas de catálogo devuelven `catalog_permission_missing` (no reintentar, ofrecer una persona), `catalog_unavailable` o `catalog_rejected` | `test_a_permission_refusal_is_not_presented_as_try_again` |
| INC-17 · Eventos perdidos (Instagram y Messenger) | `d4bab938` | Si encolar falla, se libera la marca de duplicado y el 5xx deja pasar el reintento de Meta | `test_a_failed_enqueue_lets_metas_retry_through` |
| INC-22 · Errores de Graph sin clasificar | `d4bab938` | `window_closed`, `recipient_gone`; `messages_disabled` y `permission_lost` además marcan el canal. De paso salió que `failure_code` admite 20 caracteres | `test_graph_refusals_say_what_they_mean` |
| INC-08 · Audiencia falsa en Instagram y Messenger | `99491d02` | La audiencia del canal rige también Instagram y Messenger: sin configurar = nadie, «A todos» = todos. «Solo mi equipo» y «Excepciones» (teléfonos) no se ofrecen allí, y la API rechaza `team_only` con `team_only_needs_whatsapp` | `test_channel_audience_meta_social.py`; `channel-comments.test.tsx` |
| INC-09 · Token revocado para siempre | `b67704bd` | Con el acceso perdido 7 días seguidos (`token_revoked`, `permission_lost`, `no_credentials`), el cron desconecta el canal: borra el token, pone `disconnected_at` (arranca el plazo de 30 días) y lo audita | `test_access_lost_for_a_week_disconnects_and_starts_the_clock` |
| INC-13 · El revisor no encuentra el catálogo | `c66994a1` + borradores | Sección «Catálogo» en la página del número de WhatsApp (la misma fila, selector y desconectar). Rutas de `app-review-reviewer-instructions.md` y `app-review-reviewer-setup.md` reescritas para la consola v2. **Esos dos ficheros son borradores tuyos sin versionar: los dejé modificados y sin commit** | `test_the_channel_page_shows_the_numbers_catalogue`; `channel-comments.test.tsx` |

## Segunda tanda (2026-10-30, tarde), tras verificar `c99aed95` en staging

`c99aed95` está desplegado en staging: el OpenAPI de staging coincide al 100 % con el código (rutas y esquemas) y T-WH-01…04 siguen en PASS. La tabla de Consumo, sin el botón en la columna Bolsa, está comprobada en el navegador.

| Incidencia | Commit | Qué cambia | Prueba de regresión |
|---|---|---|---|
| CI roja de `073967bb` | `c99aed95` | Migración `0211_audit_words_meta_fixes`: frases de Auditoría para `channel.meta_social.access_lost` y `console.channel.comments` | `test_console_audit_words.py` |
| INC-37 · DM a un canal en pausa descartado | `b7fa55d1` | Instagram y Messenger encolan aunque el canal esté en pausa o degradado, como WhatsApp; el turno del worker lo guarda para una persona. Solo se descarta si está desconectado | `test_a_paused_channel_keeps_the_message_and_a_disconnected_one_does_not` |
| INC-21 · Botones o medios en un turno de comentario | `d2bc4333` | En un turno de comentario, las opciones van como líneas de la respuesta privada y el pie de un adjunto va como esa respuesta. Un adjunto sin pie da error de capacidad, no de Meta | `test_in_a_comment_turn_buttons_and_media_become_the_one_private_reply` |
| INC-19 · «Cancelar» era una baja | `2c76e6a1` | Fuera «cancelar», «cancela» y «salir» de las palabras de baja; llegan al agente | `test_only_unambiguous_words_are_an_opt_out` |
| INC-15 · 409 engañoso al registrar | `72fbb2d0` | Solo un rechazo de Meta (4xx) es `number_held_by_previous_owner`. Un timeout o un 5xx sale como 502 | `test_meta_not_answering_the_register_is_not_blamed_on_a_previous_owner` |
| INC-20 · Lote mixto con el número de Auphere | `91600ea0` | El canal del dueño se detecta por elemento, no por el primer número del POST | `TestMixedBatch` |

Regresión local de la segunda tanda (sobre `91600ea0`):
- mypy `--strict`: limpio en los cuatro paquetes.
- API: **392 passed**.
- channels: **102 passed**.
- worker unit: **654 passed**.
- mcp: **130 passed**.

### Decisión pendiente

- **INC-18 (no tocada):** los cron de cobranza y reservas bloquean con cualquier baja, también las de marketing. El código lo justifica en cobranza («una baja significa dejar de perseguirme», por cumplimiento). Desde la 050, «STOP» es una baja de marketing; relajarlo haría que un deudor que escribió STOP siguiera recibiendo recordatorios. Es una decisión de cumplimiento del owner, no un bug.

### Hallazgo nuevo

- **INC-38 (P3, consola):** React #418 (desajuste de hidratación de texto) al cargar la ficha del agente, y probablemente Clientes, en staging. La página funciona porque React la vuelve a pintar en el cliente. El origen no está determinado: no se ha comprobado si existía antes de estos cambios, que no tocan esas pantallas. Habría que reproducirlo en local con el build de desarrollo, que dice qué texto difiere.

## Verificación local (sobre `c66994a1`)

- mypy `--strict`: limpio en api, worker, channels y mcp.
- ruff check y ruff format: limpios.
- tsc y eslint de la consola: limpios.
- Contrato OpenAPI de la app móvil: sin cambios. `gen-i18n` del móvil: sin diferencias.
- Consola: 52 ficheros de vitest de builder, canales y catálogo, **534 tests en verde**.
- Regresión de Python (los mismos ficheros del QA más los nuevos), una suite detrás de otra contra `nexus_test`:
  - API: **368 passed**.
  - channels: **100 passed**.
  - worker unit: **654 passed**.
  - mcp: **130 passed**.
- Todas usan mocks de Meta. El E2E real en staging sigue pendiente de los activos de prueba (README §4).

## No corregidas (y por qué)

| Incidencia | Motivo |
|---|---|
| INC-02, INC-04, INC-10 | Se hacen en el panel de Meta. La app es **la misma para staging y producción**, así que cualquier cambio allí afecta a producción. Las hace el owner |
| INC-03 (staging no recibe eventos de Instagram y Messenger) | Repuntar los webhooks de `instagram` y `page` a staging cortaría producción. La alternativa es una app de prueba de Meta, que también se crea en el panel. Decisión del owner |
| INC-17 en WhatsApp | El webhook de WhatsApp responde 200 aunque falle un elemento, por diseño de la 050. Arreglarlo exige responder 5xx, y entonces Meta reintenta el lote entero durante 36 h si un elemento falla siempre. Es una decisión de producto |
| INC-11 | Por diseño (app compartida). Mitigación operativa: en staging usar solo activos que no estén en producción |
| INC-14…16, 18…21, 23…26, 28, 29, 31…36 | P2/P3 que no bloquean la grabación. Siguen abiertas en `02-incidencias.md` |

## Hallazgo nuevo al corregir

- **INC-37 (P2, Instagram y Messenger):** un DM que llega a un canal en pausa o degradado se descarta (`webhook.meta_social.channel_not_active`), en lugar de guardarse para una persona como en WhatsApp. Ver `apps/api/src/nexus_api/api/webhooks/meta_social.py`, en `_enqueue_once`. Pendiente.

## Tercera tanda (2026-10-30, noche): decisiones del owner y diseño de los flujos

### Decisiones del owner (2026-10-30)

| Decisión | Qué se hizo |
|---|---|
| Se graba en **staging** | `app-review-reviewer-instructions.md` y `app-review-reviewer-setup.md` apuntan a `console.staging.auphere.com` y siguen la ruta de la consola v2 (agente → Canales → el número). Son borradores del owner sin versionar: quedan modificados y sin commit |
| Apuntar temporalmente los webhooks de Instagram y Page a staging | Pasos en `07-webhooks-a-staging.md`. Los hace el owner en el panel de Meta (app compartida). WhatsApp no se toca |
| La baja del cliente **no** bloquea recordatorios: decide la tienda | `9ec70d14` (+ `9ccab143`): la publicidad la bloquea cualquier baja; todo lo demás (respuestas, recordatorios de cita y de pago, plantillas de utilidad), solo una baja que puso el negocio (`source=operator`). Mismo criterio en los cron de cobranza y reservas |
| Mostrar nombre y foto de quien escribe | `5d8a359b` (ver abajo). Hace falta pedir a Meta la función **Business Asset User Profile Access** y grabar su vídeo (V-PROF-1) |

### Foto de quien escribe por Instagram o Messenger (`5d8a359b`)

- El adaptador pide `profile_pic` junto con el nombre y descarga la imagen solo de dominios de Meta (como mucho 2 MB, solo imágenes).
- El worker la guarda en nuestro almacenamiento, porque el enlace de Meta caduca, y apunta la clave en `customers.avatar_s3_key` (migración `0212`). Pregunta una sola vez por persona.
- La API de la bandeja dice `has_avatar` y sirve la foto en `/inbox/conversations/{id}/avatar`:
  - con RLS: la conversación de otro cliente da 404;
  - **ningún enlace de almacenamiento llega al navegador**, porque la consola la pide por su BFF, como los adjuntos.
- La consola la enseña en la lista, la cabecera y la ficha del contacto; si no hay foto o falla, salen las iniciales.
- El borrado de una persona la quita.
- La app móvil solo tiene el contrato regenerado; sigue enseñando iniciales.

### Diseño de los flujos (auditoría del 2026-10-30)

| # | Arreglo | Commit |
|---|---|---|
| 1 | **Plantillas de WhatsApp en la página del número.** Solo vivían en una pantalla a la que no lleva ninguna pestaña; ahora se listan, crean y borran desde el número, con su entrada en el índice | `fcf9618a` |
| 2 | El asistente de 4 pasos marca el paso real (antes decía «¡Listo!» mientras se elegía), y la página del canal dice «Paso 3 de 4 · Configurar el canal» hasta que se configura | `41c77542` |
| 3 | Compositor: fuera «Autenticación», que Meta solo acepta con formato fijo de código. Enviar incompleto marca y enfoca el primer campo en vez de apagar el botón. Categorías con radios nativos. El contador ya no anuncia cada tecla. Textos de «acción sugerida» sin códigos | `5c0dd0a2` |
| 4 | Instagram/Messenger terminan como WhatsApp: el fallo se queda en pantalla con «Intentar de nuevo», el selector de cuentas tiene «Cancelar», y al conectar se abre la página del canal | `1b1439b1` |
| 5 | Una plantilla se abre entera (estado, motivo completo de Meta, qué hacer, vista previa) y una rechazada se puede **«Duplicar y corregir»**. El idioma se ve en palabras | `f92290f7` |
| 6 | El diálogo de conexión de WhatsApp solo enseña lo que se puede usar: sin modos apagados, y sin Meta configurado solo el aviso y el enlace del dueño. Nota de la tarjeta corregida (Cloud API no conserva la app) | `8af7a685` |
| 7 | Página del canal en orden de lectura: Comprobaciones, A quién responde, lo propio del canal (Comentarios, Catálogo, Plantillas), Escalado y Cuenta. Índice igual, títulos h3, sin teléfonos de prueba en Instagram/Messenger. «Conectar canal» del siguiente paso y de salud lleva a Agentes | `c6baecd6` |

Detectado al hacerlo y ya corregido:
- `9ccab143`: el lint de CI pasa mypy con la configuración de cada paquete, y el worker veía `Any`.
- `587763f1`: la prueba de conexión no simulaba la acción nueva de plantillas.

### Pendiente de esta parte

- **Verlo en el navegador.** La máquina local estaba saturada (carga media ~200) y la consola local no llegaba a pintar. Las comprobaciones son con vitest, axe, typecheck y lint. Falta mirarlo en staging cuando llegue el despliegue.
- La pantalla antigua `/clients/{ref}/channels` sigue existiendo, con el diagnóstico y los enlaces pendientes del dueño. Llevar esas dos piezas a la v2 y retirarla es trabajo aparte.
- Mostrar la foto en la app móvil.
