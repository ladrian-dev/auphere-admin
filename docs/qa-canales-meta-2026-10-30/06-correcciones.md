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
