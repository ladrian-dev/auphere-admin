---

description: "Tareas de la spec 085: el enlace para que el cliente conecte Instagram y Messenger"
---

# Tareas: el enlace para que el cliente conecte Instagram y Messenger

**Entrada**: `specs/085-enlace-instagram-messenger/` (spec, plan, research, data-model, contracts, quickstart).

**Pruebas**: obligatorias (constitución §VII). Cada bloque de pruebas se escribe y se ve en rojo antes de implementar.

**Organización**: por historia de la spec. H1 es Instagram, H2 Messenger y H3 elegir cuenta o Página.

## Reglas de este repo *(constitución)*

- Cada tarea cita sus requisitos (`_Requisitos: N.m_`).
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero:** se escribe, se ve en rojo, y solo entonces se implementa. Un test que hace `skip` no cubre nada.
- **Aislamiento:** la garantía 1 tiene su tarea en `tests/isolation/` (T008). Bloquea el merge.
- **Base propia para pytest:** `NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_<x>` con su propio Redis. Nunca dos suites a la vez sobre la misma base.

**Rutas:**
- API: `apps/api/src/nexus_api/` y `apps/api/tests/`;
- paquete de canales: `apps/channels/src/nexus_channels/`;
- consola: `apps/console/src/`.

---

## Fase 1: Preparación

- [x] T001 Dejar el entorno listo en el worktree:
  - `cd apps/api && uv sync --extra dev`;
  - una base de pruebas propia, migrada hasta `0243`;
  - `pnpm install --frozen-lockfile` en la raíz.

  Comprobar que `tests/integration/test_channel_signup_links.py` y `tests/unit/test_endpoint_console_meta_social.py` pasan antes de tocar nada.
  _Requisitos: —_
  - **Hecho (2026-11-27):** dependencias de la API (`uv sync --extra dev`) y de la raíz (`pnpm install --frozen-lockfile`); base propia `nexus_test_085` creada desde la plantilla `nexus_test_fixrev` (en `0243`), Redis 13. Línea base en verde: `test_channel_signup_links.py`, `test_endpoint_console_meta_social.py` y `channels/test_owner_link.py`, 32 pasan.

---

## Fase 2: Base (bloquea todas las historias)

### Pruebas de la base (en rojo antes de T004–T005)

- [x] T002 [P] Pruebas del enlace por canal en `apps/api/tests/integration/test_085_owner_link_meta_social.py`:
  - crear un enlace de Instagram **no** anula uno de WhatsApp vivo del mismo cliente, y crear otro de Instagram sí anula el anterior de Instagram;
  - un agente puede tener a la vez pendientes uno de WhatsApp y uno de Instagram;
  - un enlace de agente caducado sin anular no impide crear el siguiente del mismo agente y canal (hoy da 500);
  - la migración rechaza `channel='instagram'` con `mode='coexistence'`.

  _Requisitos: 1.2, 1.5_
  - **Hecho (2026-11-27):** 4 pruebas en `tests/integration/test_085_owner_link_meta_social.py` (nivel de servicio, `mint_link`). Rojo: 3 con `TypeError: mint_link() got an unexpected keyword argument 'channel'` y 1 con `CheckViolationError ck_channel_signup_links_channel`. Verde tras T004–T005: 4 pasan.
- [x] T003 [P] Prueba de `origin` en las pruebas de `apps/channels` para `meta_social/connect.py`:
  - una elección iniciada con `origin="link:A"` no se completa con `origin="console"` ni con `origin="link:B"`, y da `pending_expired`;
  - con el mismo origen, sí se completa;
  - un valor guardado sin `origin` se lee como `"console"`.

  _Requisitos: 7.3_
  - **Hecho (2026-11-27):** 3 pruebas en `apps/channels/tests/test_085_meta_social_pending_origin.py`, sin base: Redis falso, un cliente de Meta mínimo que concede dos cuentas, y `_connect` sustituido (lo que se prueba es la comprobación del origen). Rojo: 3 con `TypeError: begin()/complete() got an unexpected keyword argument 'origin'`. Verde tras T006: 3 pasan.

### Implementación de la base

- [x] T004 La migración `apps/api/alembic/versions/0244_owner_links_meta_social.py` (down_revision `0243_template_edit_vocabulary`):
  - amplía `ck_channel_signup_links_channel` a `('whatsapp','instagram','messenger')` y `ck_channel_signup_links_mode` añadiendo `'meta_login'`;
  - crea `ck_channel_signup_links_mode_per_channel`: `(channel = 'whatsapp' AND mode IN ('coexistence','cloud_api','whatsapp_login')) OR (channel IN ('instagram','messenger') AND mode = 'meta_login')`;
  - cambia `uq_channel_signup_links_one_pending` a `(tenant_id, agent_id, channel)` con la misma condición `WHERE consumed_at IS NULL AND revoked_at IS NULL AND agent_id IS NOT NULL`;
  - la vuelta atrás borra los enlaces que no son de WhatsApp y restaura las restricciones de 0191.

  Ajustar `apps/api/src/nexus_api/db/models/channel_signup_link.py` si declara los valores.
  _Requisitos: 1.2_
  - **Hecho (2026-11-27):** `0244_owner_links_meta_social`: amplía los dos CHECK, crea `ck_channel_signup_links_mode_per_channel` y rehace `uq_channel_signup_links_one_pending` sobre `(tenant_id, agent_id, channel)`. Probada subida, bajada y subida sobre `nexus_test_085`. El modelo solo cambia sus comentarios (no declara los valores).
- [x] T005 En `apps/api/src/nexus_api/services/channel_signup_links.py`:
  - `mint_link(..., channel="whatsapp")`. Sin agente, anula solo los vivos del cliente **de ese canal**. Con agente, anula antes los caducados sin usar ni anular del mismo agente y canal, y `link_pending_exists` pasa a ser por agente y canal.
  - Instagram y Messenger guardan `mode="meta_login"`.
  - `link_url(token, channel)` da `/connect/{channel}/{token}`.
  - `live_links` y `recent_links` exponen `channel`.

  _Requisitos: 1.2, 1.5_
  - **Hecho (2026-11-27):** `mint_link(..., channel="whatsapp")` con `mode` opcional (Instagram y Messenger guardan `meta_login`; otro modo da 422 `unknown_mode`, otro canal 422 `unknown_channel`); `live_links(..., channel=)`; con agente revoca antes los caducados del mismo agente y canal (motivo `expired`, con su auditoría); `link_url(token, channel)`; la auditoría de creación lleva `channel`. `recent_links` ya devuelve la fila con `channel`. Además, la lista del panel de operador (`api/admin/channel_signup_links.py`) filtra `channel = 'whatsapp'` para seguir solo con WhatsApp (R12).
- [x] T006 [P] `origin` en `apps/channels/src/nexus_channels/meta_social/connect.py`:
  - `begin(*, kind, code, origin="console")` lo guarda dentro del JSON cifrado;
  - `complete(*, kind, nonce, account_id, origin="console")` responde `pending_expired` si no coincide;
  - un valor sin `origin` cuenta como `"console"`.

  La consola no cambia de comportamiento (sigue usando el valor por defecto). T003 pasa a verde.
  _Requisitos: 7.3_
  - **Hecho (2026-11-27):** `begin` y `complete` reciben `origin` (por defecto `CONSOLE_ORIGIN = "console"`), va dentro del JSON cifrado; si no coincide, `pending_expired` y la clave se queda para quien la inició. La consola no cambia: sigue sin pasar `origin`.
- [x] T007 [P] Acciones inyectadas en `apps/console/src/components/channels/meta-social-connect.tsx`:
  - `useMetaSocialConnect({ offer, actions: { connect(kind, code), complete(kind, nonce, accountId) }, onConnected?, onDone? })`;
  - el `router.refresh()` y el toast van solo en el lado de la consola;
  - las llamadas de hoy pasan sus acciones ligadas al `ref`.

  Las pruebas de `components/channels/__tests__/meta-social-connect.test.tsx` y `components/builder/__tests__/channel-connect.test.tsx` siguen en verde sin cambiar lo que comprueban.
  _Requisitos: 2.2, 2.3, 4.1_
  - **Hecho (2026-11-27):** `useMetaSocialConnect` acepta `actions?: MetaSocialConnectActions` (`connect`, `complete`) y `onDone?`; sin `actions` usa `consoleMetaSocialActions(refId)`, las de hoy, y conserva el toast y `router.refresh()`. Con `actions` propias, el toast y el refresco no se hacen (los decide la página). Desviación menor: `refId` sigue siendo opcional en la firma para que las llamadas de hoy (`MetaSocialConnect`, `agent-channels.tsx` y el arnés de la prueba) no cambien. `meta-social-connect.test.tsx` y `channel-connect.test.tsx`: 41 pasan, sin tocarlas.

---

## Fase 2b: Las puertas de la constitución

- [x] T008 Prueba de aislamiento de la garantía 1 en `apps/api/tests/isolation/test_085_owner_link_meta_social_scope.py`. Va en rojo antes de US1 y US3, y comprueba:
  - un enlace del cliente A conecta la cuenta en A, nunca en B (`channel.tenant_id == A`);
  - una elección iniciada por el enlace L1 no se completa con el enlace L2 del mismo cliente;
  - una elección iniciada en la consola no se completa desde un enlace, ni al revés;
  - ninguna ruta pública nueva acepta `tenant_id` ni lo devuelve.

  Barre las rutas `/console/channel-signup/*` desde el router, no por una lista escrita a mano.
  _Requisitos: 7.1, 7.2, 7.3, 7.4_
  - **Hecho (2026-11-27):** 4 pruebas. Rojo: 3 con 404 en `/meta-social` y `/meta-social/complete` (no existían) y 1 porque el barrido de `/console/channel-signup*` no alcanzaba ninguna ruta `meta-social`. Tras H1 (T013–T016): 2 en verde (el enlace conecta solo en su cliente, y un cuerpo con `tenant_id` da 422; el barrido de rutas). Las 2 de la elección esperan a T026. El barrido lee `app.routes` y el OpenAPI (parámetros, cuerpo y respuestas 2xx, recorriendo `$ref`), no una lista. `test_console_scope.py` cubre solas las rutas nuevas: 1685 pasan junto a esta.
  - **Hecho (2026-11-27), tras T026:** las 4 en verde.

---

## Fase 3: H1, el cliente conecta su Instagram desde un enlace (P1) 🎯 MVP

**Objetivo:** el partner crea el enlace en la tarjeta de Instagram y el dueño lo conecta desde la página pública.

**Prueba independiente:** un cliente sin Instagram, un enlace y la conexión de una cuenta sin sesión de la consola.

### Pruebas de H1 (en rojo antes de T013–T020)

- [x] T009 [P] [US1] Pruebas de la API en `apps/api/tests/integration/test_085_owner_link_meta_social.py`, con el `FakeGraph` de `tests/unit/test_endpoint_console_meta_social.py`:
  - `POST /console/clients/{ref}/channels/instagram/signup-link` da 201 con `{url, channel:"instagram", expires_at}` y la dirección `/connect/instagram/`; da 404 si el canal no está disponible;
  - `GET /console/channel-signup/{token}` da `channel`, `mode:"meta_login"`, `meta_config_id` y `meta_page_config_id`, y `state:"unknown"` si el canal no está disponible para el partner;
  - `POST /console/channel-signup/{token}/meta-social` con una sola cuenta da `connected`, deja el enlace usado y el canal en el cliente, sin aplicar la cuota de números;
  - el enlace de agente deja el canal en ese agente y avisa con `channel.connected` y `via: "owner_link"`;
  - un fallo de Meta o un 409 de motivo no consume el enlace;
  - usado, caducado o anulado dan los 410 de siempre;
  - `POST /console/channel-signup/{token}` (WhatsApp) con un enlace de Instagram da 409 `link_channel_mismatch` y no lo consume;
  - volver a conectar por enlace una cuenta que ya está en ese cliente actualiza su canal y su token, sin crear otro (spec, casos límite).

  _Requisitos: 1.1, 1.2, 1.6, 2.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1_
  - **Hecho (2026-11-27):** 8 pruebas de H1 en `test_085_owner_link_meta_social.py` (con un `FakeGraph` propio de la prueba, la misma clase de la 049). Rojo: 8 fallan (404 en las rutas nuevas, 422 `extra_forbidden` por `channel` en `owner-links`, y `detail` sin `code` en un 404 de ruta inexistente). Verde tras T013–T017: 7 de 8; la de los enlaces muertos también llama a `/meta-social/complete` y pasa con T026. Cubren además la lista con `channel` y `pending_links` del agente (T017).
- [x] T010 [P] [US1] Prueba de la consola de la página pública en `apps/console/src/app/connect/[kind]/__tests__/owner-connect-social.test.tsx` (con `loginForCode` y las acciones simuladas):
  - Instagram con configuración de Página pregunta «¿Cómo entras a Meta?» y abre la ventana con la configuración de cada opción;
  - sin configuración de Página abre directamente;
  - «¡Listo! Tu Instagram está conectado» con la cuenta;
  - los estados muertos usan `connect.dead.*`;
  - reintentar repite la forma elegida;
  - un motivo de Meta se muestra con el texto de la consola.

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.4, 5.6_
  - **Hecho (2026-11-27):** `app/connect/[kind]/__tests__/owner-connect-social.test.tsx`, escrita junto a las de Messenger (T022) y elegir (T025) para verlas todas en rojo antes de la página compartida. Rojo: el fichero no carga (`Failed to resolve import ../owner-connect-social`). Verde tras T019–T020: el bloque de Instagram, 8 de 8 (preguntar y abrir con cada configuración, sin Página abre directo, motivo con el texto de la consola y el aviso de avisar a quien lo envió, reintento con la misma forma, y los 4 estados muertos con `connect.dead.*`), con axe sin violaciones.
- [x] T011 [P] [US1] Prueba de la consola del panel para compartir en `apps/console/src/components/channels/__tests__/share-link.test.tsx`:
  - en Instagram no hay selector de modo;
  - copiar, enviar por WhatsApp y enviar por correo usan el asunto de Instagram;
  - muestra la caducidad;
  - sin Instagram disponible para el partner, la tarjeta no ofrece el enlace: ni botón apagado ni explicación.

  También `pending-signup-links.test.tsx`: cada enlace muestra su canal y se anula igual.
  _Requisitos: 1.3, 1.4, 1.5_
  - **Hecho (2026-11-27):** `components/channels/__tests__/share-link.test.tsx` (4) y 2 nuevas en `pending-signup-links.test.tsx`. Rojo: 6 fallan (`ShareLink` no existe; `TypeError ... reading 'es'` al pintar un enlace `meta_login`). Verde tras T020: 5 de 6; la de Messenger espera a sus textos (T023). Los botones de compartir son anclas pintadas por `Button` con `nativeButton={false}`: la prueba las busca por su texto. Desviación: en Instagram y Messenger el botón dice «Enviar enlace de Instagram al cliente» / «… de Messenger …» y no «Enviar enlace al cliente», porque en Canales del cliente conviven los tres y tres botones iguales no se distinguen (ni a la vista ni por lector de pantalla).
- [x] T012 [P] [US1] En `apps/console/src/__tests__/proxy-public-routes.test.ts`, `/connect/instagram/un-token` y `/connect/messenger/un-token` son públicas.
  _Requisitos: 2.1, 3.1_
  - **Hecho (2026-11-27):** 3 rutas nuevas en `proxy-public-routes.test.ts` (`/connect/instagram/un-token`, `/connect/messenger/un-token`, `/connect/instagram`). Sin rojo posible: el proxy ya abre todo `/connect/` (spec 040), no había nada que implementar; pasan a la primera y quedan como guarda.

### Implementación de H1

- [x] T013 [US1] En `apps/api/src/nexus_api/api/console/meta_social.py`, `POST /console/clients/{ref}/channels/{kind}/signup-link` con `kind: Literal["instagram","messenger"]`, `client_scope("channels:write")`, `_require_enabled` y `mint_link(channel=kind)`. Devuelve `{url, channel, expires_at}`. La ruta de WhatsApp (`/channels/whatsapp/signup-link`) sigue registrada antes y no cambia.
  _Requisitos: 1.1, 1.2, 1.6_
  - **Hecho (2026-11-27):** En `meta_social.py`, `link_router` aparte con `POST /clients/{ref}/channels/{kind}/signup-link` (`kind: Literal[instagram, messenger]`, otro valor 422), `channels:write`, `_require_enabled` (404) y `mint_link(channel=kind)`. Se monta en `api/console/__init__.py` **después** de `whatsapp.router`: `meta_social.router` va antes, y `/{kind}/signup-link` habría capturado `/whatsapp/signup-link` con un 422.
- [x] T014 [US1] En `apps/api/src/nexus_api/api/console/channel_signup.py`:
  - `LinkInfoOut` gana `channel` y `meta_page_config_id`;
  - para Instagram y Messenger, `meta_config_id` sale de `meta_social_service.offer(partner)` del partner del cliente (`tenant.partner_id`), y si `enabled_kinds(partner)` no incluye el canal responde `state:"unknown"`;
  - la ruta POST de WhatsApp responde 409 `link_channel_mismatch` con enlaces de otro canal.

  _Requisitos: 2.1, 2.3, 3.2, 5.6_
  - **Hecho (2026-11-27):** `LinkInfoOut` gana `channel` y `meta_page_config_id`. Para Instagram y Messenger los valores salen de `meta_social_service.offer(partner)` del partner del cliente (`tenant.partner_id`): `app_id`, `config_id`, `page_config_id` y `graph_version` (la de la conexión social, no la de Embedded Signup); sin el canal en la oferta, `state: unknown`. La ruta POST de WhatsApp responde 409 `link_channel_mismatch` antes de bloquear el enlace, que sigue vigente.
- [x] T015 [US1] En `apps/api/src/nexus_api/services/channel_signup_links.py`, `connect_meta_social_with_link(session, redis, *, link, code)`, bajo el ámbito del cliente del enlace y con el enlace releído `FOR UPDATE`, como la ruta de WhatsApp:
  - usa `meta_social_service.connector(...)` y `begin(kind=link.channel, code=code, origin=f"link:{link.id}")`;
  - si conecta: coloca el canal en `link.agent_id` con la **misma** función de servicio que usa la consola al mover un canal (extrae su parte de sesión si depende del `ClientScope`, sin cambiar su comportamiento); audita `channel.{kind}.connect` con el actor `link:{id}`; y marca `consumed_at` y `channel_id`;
  - si hay que elegir, devuelve `nonce` y `accounts` sin consumir el enlace;
  - no aplica la cuota de números.

  _Requisitos: 5.2, 5.5, 6.1, 7.1, 7.2_
  - **Hecho (2026-11-27):** `connect_meta_social_with_link` (y `complete_meta_social_with_link`, que usa T026) en `channel_signup_links.py`: comprueban canal y disponibilidad (409 `link_channel_mismatch` / 404 `link_unknown`), llaman a `begin`/`complete` con `origin=link:{id}`, auditan `channel.{kind}.connect` con el actor `link:{id}` (la auditoría de la consola, extraída a `meta_social_service.audit_connect`), colocan el canal en `link.agent_id` con `channel_config.move_channel` y marcan `consumed_at` y `channel_id`. Sin cuota. R6: la lógica de `POST …/channels/{id}/move` se extrajo a `services/channel_config.move_channel(session, channel, *, to_agent_id, actor)`; la ruta de la consola la llama y traduce el error con `_error`, mismas respuestas (422 `unknown_target_agent`, 409 `audience_admin_only_template` con `fix`).
- [x] T016 [US1] En `apps/api/src/nexus_api/api/console/channel_signup.py`, `POST /console/channel-signup/{token}/meta-social` con `{code}`:
  - `require_console_service()`, `_limit`, y `require_valid` antes y después de `FOR UPDATE`;
  - respuestas según el contrato: `connected` con `display_name` y `business_name`, o `choose` con `nonce` y `accounts`;
  - los 409 `{code, help}` de `REASON_HELP` y el 502 de Meta;
  - `announce_connected` después del commit;
  - ningún campo `reason`, `message`, `text` ni `tenant_id`.

  _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.4_
  - **Hecho (2026-11-27):** `POST /console/channel-signup/{token}/meta-social` con `ConnectIn` de la consola (`extra=forbid`): `require_console_service`, `_limit`, `require_valid` antes y después de `FOR UPDATE`; `LinkSocialOut` (`status`, `display_name`, `business_name`, `nonce`, `accounts`); 409 `{code, help}` y 502 con todo deshecho; `announce_connected` tras el commit con el agente donde quedó el canal.
- [x] T017 [US1] En `apps/api/src/nexus_api/api/console/whatsapp.py`, la lista de enlaces del cliente devuelve `channel`. En `apps/api/src/nexus_api/api/console/channel_config.py`:
  - `OwnerLinkIn` gana `channel` (por defecto `whatsapp`; `mode` es obligatorio solo en WhatsApp);
  - `OwnerLinkOut` gana `channel`;
  - `AgentChannelsOut` gana `pending_links` (uno por canal) y conserva `pending_link` (el de WhatsApp).

  _Requisitos: 1.1, 1.2, 1.5_
  - **Hecho (2026-11-27):** `_SignupLinkRow` gana `channel`. `OwnerLinkIn` gana `channel` (por defecto `whatsapp`) y `mode` pasa a opcional: en WhatsApp, sin él, `coexistence` como hasta hoy (la prueba de la 047 crea con `{}`); en Instagram y Messenger, cualquier modo da 422, y sin el canal para el partner, 404. `OwnerLinkOut` gana `channel`. `AgentChannelsOut` gana `pending_links` y conserva `pending_link` (el de WhatsApp). Desviación: `pending_links` es `list[PendingOwnerLinkOut]` (`id`, `channel`, `mode`, `expires_at`), no `list[OwnerLinkOut]`: `OwnerLinkOut` lleva la URL, que no se guarda y no se puede volver a enseñar (31.7).
- [x] T018 [US1] En la consola, las llamadas al backend en `apps/console/src/lib/backend.ts`:
  - `channelSignupInfo` con los campos nuevos;
  - `channelSignupMetaSocial(token, code)` y `channelSignupMetaSocialComplete(token, nonce, accountId)` con `mintServiceToken`;
  - el mint del cliente por canal;
  - `ownerLink` con `channel`.

  Y las acciones `apps/console/src/app/(console)/clients/[ref]/channels/actions.ts` (`signupLinkAction({ref, channel, mode?})`) y `agents/channel-actions.ts`, con `requirePrincipal` y `can("channels:write")`.
  _Requisitos: 1.1, 1.6_
  - **Hecho (2026-11-27):** `backend.ts`: `ChannelSignupLinkInfo` con `channel`, `meta_login` y `meta_page_config_id`; `consoleService.channelSignupMetaSocial` y `channelSignupMetaSocialComplete` con `mintServiceToken`. `backend/channels.ts`: `metaSocialSignupLink(ref, kind)`, `SignupLinkRow.channel` y `MetaSocialConnectResult.display_name`. `backend/channel-config*`: `OwnerLinkChannel`, `pending_links`, `createOwnerLink` con `channel`. Acciones: `signupLinkAction({ref, channel, mode?})` sustituye a `whatsappSignupLinkAction` (unión discriminada por canal; solo WhatsApp lleva modo), y `createOwnerLinkAction` acepta `channel` (WhatsApp sigue mandando solo `mode`).
- [x] T019 [US1] La página pública en `apps/console/src/app/connect/[kind]/`:
  - `page.tsx`: solo `instagram|messenger`, otro valor da `notFound`; lee la cookie del canal y `channelSignupInfo`; si el canal no coincide o el estado no es `valid`, muestra el estado muerto;
  - `[token]/route.ts`: cookie `nx_owner_link_{kind}` (`httpOnly`, ruta `/connect`, 1 h) y redirección 303 a `/connect/{kind}`;
  - `actions.ts`: el token sale de la cookie, nunca del cliente;
  - un componente que usa `useMetaSocialConnect` con las acciones del enlace.

  Generalizar `apps/console/src/app/connect/whatsapp/link-cookie.ts` a un nombre de cookie por canal, con el de WhatsApp sin cambios.
  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 5.1, 5.6, 7.4_
  - **Hecho (2026-11-27):** `app/connect/[kind]/`: `page.tsx` (solo `instagram|messenger`, `notFound` si no; cookie del canal; muerto si el estado no es `valid` o el canal no coincide), `[token]/route.ts` (cookie `nx_owner_link_{kind}`, httpOnly, `/connect`, 1 h, 303 a `/connect/{kind}`; 404 con otro canal), `actions.ts` (`ownerSocialConnectAction` y `ownerSocialCompleteAction`, el token sale de la cookie y se borra al conectar) y `owner-connect-social.tsx` con `useMetaSocialConnect` y las acciones del enlace. Un enlace que muere con la página abierta (404/410) cambia la página al estado muerto. `link-cookie.ts` gana `ownerLinkCookie(channel)` (WhatsApp conserva `nx_owner_link`). El hook gana `failureHint` (5.4). `connect/whatsapp/page.tsx` trata como inexistente un enlace de otro canal.
- [x] T020 [US1] El panel para compartir:
  - `apps/console/src/components/channels/whatsapp-share-link.tsx` pasa a ser un panel por canal (el modo solo en WhatsApp);
  - se ofrece «Enviar enlace al cliente» en la tarjeta de Instagram de Canales del cliente (`app/(console)/clients/[ref]/channels/*`) donde está «Conectar Instagram», y también en la vista de escritorio, que hoy oculta conectar;
  - `apps/console/src/components/builder/owner-link-panel.tsx` recibe `channel`, y el agente lo ofrece donde WhatsApp lo ofrece;
  - `pending-signup-links.tsx` muestra el canal.

  Textos nuevos en `apps/console/src/i18n/lanes/channels.ts`: `connect.social.*` (título y «¡Listo!» por canal) y `ch.link.subject` y `ch.link.message` por canal, en es y en. No se añaden textos bajo `builder.channel.state.*` ni `builder.channel.problem.*` (obligaría a regenerar la app móvil).
  _Requisitos: 1.1, 1.3, 1.4, 1.5, 2.1, 5.1_
  - **Hecho (2026-11-27):** `whatsapp-share-link.tsx` exporta `ShareLink({channel, modes?, offer?})`: el modo solo en WhatsApp; sin el canal en la oferta, no pinta nada. En Canales del cliente sale junto a «Conectar Instagram»/«Conectar Messenger», también en la app de escritorio (donde el botón de conectar no existe). `pending-signup-links.tsx` dice el canal de cada enlace y su confirmación de anular. `OwnerLinkPanel` recibe `channel` (sin modo, textos y logo del canal). En el agente: la tarjeta del pendiente de cada canal arriba, como la de WhatsApp, y bajo el asistente «¿Prefieres que lo conecte el cliente?» con un botón por canal que abre el mismo panel en un diálogo. Decisión tomada sin Luis: en el agente, WhatsApp ofrece el enlace dentro de su modal de conectar; Instagram y Messenger abren Meta directamente desde su tarjeta, así que el enlace va en una línea bajo el asistente en vez de añadir un paso a la conexión de la consola. Textos de Instagram en `channels.ts` y `channels-proto.ts`, es y en; ninguno bajo `builder.channel.state.*` ni `builder.channel.problem.*`.

---

## Fase 4: H2, el cliente conecta su Messenger desde un enlace (P1)

**Objetivo:** el mismo flujo desde la tarjeta de Messenger, entrando con Facebook sin pregunta.

### Pruebas de H2 (en rojo antes de T023)

- [x] T021 [P] [US2] En `test_085_owner_link_meta_social.py`, el enlace de Messenger:
  - `info` sin `meta_page_config_id`, con el `meta_config_id` de Messenger de la oferta;
  - conecta una Página, y el canal queda en el cliente.

  _Requisitos: 3.1, 3.2, 5.2_
  - **Hecho (2026-11-27):** `test_the_owner_connects_a_page_to_messenger`, escrita antes de la implementación de H1. Rojo: 404 al crear el enlace de Messenger. Verde con la implementación compartida de H1 (T013–T016), sin código propio de Messenger en la API: `info` sin `meta_page_config_id` y con la configuración de Messenger de la oferta; conecta la Página con su token de Página y la deja en el cliente; 1 pasa.
- [x] T022 [P] [US2] En `owner-connect-social.test.tsx`, Messenger:
  - «Conecta el Messenger de {negocio}» sin pregunta;
  - la ventana con la configuración de Messenger;
  - «¡Listo! Tu Messenger está conectado» con la Página.

  _Requisitos: 3.1, 3.2, 5.1_
  - **Hecho (2026-11-27):** En `owner-connect-social.test.tsx` (2: la página de Messenger y su diálogo de elegir Página). Rojo: primero el fichero no cargaba; con la página de H1 ya hecha, seguían en rojo porque faltaban los textos de Messenger (el título salía como su clave). Verde tras T023: 2 pasan.

### Implementación de H2

- [x] T023 [US2] «Enviar enlace al cliente» en la tarjeta de Messenger y en el agente. Textos de Messenger. La página `[kind]` ya lo sirve: solo cambian los textos y la configuración.
  _Requisitos: 1.1, 3.1, 3.2_
  - **Hecho (2026-11-27):** Textos de Messenger (`ch.link.open/body/message/subject.messenger`, `connect.social.title/body/start/done.messenger`), es y en. La página `[kind]`, el panel de compartir, la tarjeta de Canales del cliente y la línea del agente ya servían Messenger: salen solos con la oferta del partner. `share-link.test.tsx` (Messenger) también pasa: 17 de 17 entre las dos pruebas.

---

## Fase 5: H3, elegir entre varias cuentas o Páginas (P2)

**Objetivo:** si Meta devuelve más de una cuenta o Página, el dueño elige con el diálogo de la consola.

### Pruebas de H3 (en rojo antes de T026–T027)

- [x] T024 [P] [US3] En `test_085_owner_link_meta_social.py`:
  - con dos cuentas, el primer paso da `choose` sin consumir el enlace;
  - `.../meta-social/complete` con la segunda conecta esa y consume el enlace;
  - un `nonce` caducado da 409 `pending_expired` y el enlace sigue vigente;
  - con una sola cuenta no hay elección.

  _Requisitos: 4.1, 4.2, 4.3, 4.4_
  - **Hecho (2026-11-27):** `test_the_owner_picks_one_of_several_accounts_with_the_same_link` (y la llamada a `/complete` de `test_dead_links_answer_like_whatsapps`). Rojo: 404 al crear el enlace al escribirla; tras H1, 404 `Not Found` en `/meta-social/complete`. Verde tras T026: elegir no consume el enlace, un `nonce` que no es da 409 `pending_expired` y lo deja vigente, y la elegida es la que queda conectada; con una sola cuenta no hay elección (pruebas de H1).
- [x] T025 [P] [US3] En `owner-connect-social.test.tsx`:
  - el diálogo «¿Qué cuenta de Instagram conectas?» o «¿Qué Página de Facebook conectas?»;
  - elegir llama a `complete`;
  - cancelar no conecta nada y deja el enlace válido;
  - «La elección caducó» con reintento.

  _Requisitos: 4.1, 4.4, 4.5_
  - **Hecho (2026-11-27):** En `owner-connect-social.test.tsx` (4: el diálogo de Instagram y el de Messenger, cancelar sin conectar y con el enlace válido, y «La elección caducó» con reintento). Rojo: el fichero no cargaba (escritas con T010). Verde con T019, porque la página ya pasa al hook las dos acciones del enlace; ver T027.

### Implementación de H3

- [x] T026 [US3] `complete` en `connect_meta_social_with_link` (`channel_signup_links.py`), con `origin=f"link:{link.id}"`, y la ruta `POST /console/channel-signup/{token}/meta-social/complete` con `{nonce: 8..64, account_id: 1..64}` en `channel_signup.py`. Mismo bloqueo, auditoría, colocación en el agente y aviso que T015 y T016.
  _Requisitos: 4.2, 4.3, 4.4, 5.2, 5.3, 7.3_
  - **Hecho (2026-11-27):** `POST /console/channel-signup/{token}/meta-social/complete` con `CompleteIn` de la consola (`nonce` 8..64, `account_id` 1..64), por el mismo `_social` que T016: bloqueo, auditoría, colocación en el agente, consumo y aviso. El servicio (`complete_meta_social_with_link`, con `origin=link:{id}`) ya venía de T015. Las 18 pruebas de API de la 085 en verde (14 de integración y 4 de aislamiento).
- [x] T027 [US3] Conectar el diálogo de elegir de `useMetaSocialConnect` a las acciones del enlace en la página `[kind]`. Cancelar cierra sin llamar a la API.
  _Requisitos: 4.1, 4.5_
  - **Hecho (2026-11-27):** Sin código nuevo: desde T019 la página `[kind]` pasa a `useMetaSocialConnect` las dos acciones del enlace (`connect` y `complete`), así que el diálogo de elegir de la consola completa con `ownerSocialCompleteAction`, y cancelar lo cierra sin llamar a la API (lo comprueba T025).

---

## Fase 6: Cierre

- [x] T028 [P] Actualizar en `docs/` el documento del enlace del dueño (el que describe la spec 040) y el de canales de Meta: el enlace sirve también Instagram y Messenger, un enlace vivo por cliente y canal, y `origin` en la elección pendiente.
  _Requisitos: —_
  - **Hecho (2026-11-27):** `docs/canales.md` §4 gana «Un enlace por canal: también Instagram y Messenger (spec 085)»: modos, uno vivo por cliente y canal, uno pendiente por agente y canal (y los caducados), dónde se crea, la página `[kind]` y su cookie, las dos llamadas públicas, la colocación en el agente con `move_channel` y `origin` en la elección pendiente. `docs/admin.md`: uno vivo por cliente y canal, y el panel sigue solo con WhatsApp.
- [x] T029 Correr y dejar en verde:
  - las pruebas tocadas y las del enlace y la conexión (ver `quickstart.md`), incluida `tests/isolation/test_console_scope.py`;
  - las del paquete de canales;
  - `./scripts/verify.sh lint` y `./scripts/verify.sh js`.

  Confirmar con `pnpm --dir apps/mobile gen:check`, o el paso equivalente de `verify.sh mobile`, que la app móvil no necesita regenerar nada.
  _Requisitos: —_
  - **Hecho (2026-11-27):** En verde sobre `nexus_test_085`: las 18 pruebas de API de la 085; las del enlace y la conexión (`test_channel_signup_links.py`, `channels/test_owner_link.py`, `test_endpoint_console_meta_social.py`, `test_meta_social_channel_isolation.py` y `test_console_scope.py`, 1740 juntas); las de mover canales, auditoría y vocabulario (175); **la suite de aislamiento entera, 4112 pasan** (1 `skip` previo y ajeno, `test_37_customer_axis_contract`); el paquete de canales, 126. Hubo que poner al día una prueba de la 040: la forma de un enlace muerto gana `channel` y `meta_page_config_id` (contrato). `verify.sh lint` en verde. `verify.sh js` en verde a la segunda: la primera falló solo en `panel · typecheck` y `panel · vitest` por `@nexus/ucm-*` sin construir (entorno, el panel no se toca); tras `pnpm --dir apps/admin build:packages`, todo verde (consola 2741 pruebas, panel 872, `@nexus/ui` 332, y los dos `next build`, con `/connect/[kind]` y `/connect/[kind]/[token]`). App móvil: `export_openapi.py` no cambia nada y `pnpm --dir apps/mobile gen:check` sale con 0.
- [x] T030 Dejar el guion de commits en `.claude/commits/2026-11-27-085-impl.sh`:
  - empieza con `cd` al worktree, comprueba la rama `085-enlace-instagram-messenger` y que el índice esté vacío;
  - un commit por bloque coherente, Conventional Commits en inglés y sin atribuciones;
  - cubre todos los ficheros tocados.

  Actualizar `HANDOFF.md`.
  _Requisitos: —_
  - **Hecho (2026-11-27):** `.claude/commits/2026-11-27-085-impl.sh` (ejecutable): `cd` al worktree, comprueba la rama y el índice vacío, usa `GIT_LITERAL_PATHSPECS=1` (rutas con `[kind]` y `(console)`), y antes de nada aborta si algún fichero cambiado no está en un bloque (salvo `HANDOFF.md`, `tsconfig.tsbuildinfo` y `next-env.d.ts`). Seis commits: specs, base de datos, paquete de canales, API, consola y docs. `HANDOFF.md` al día.

---

## Dependencias y orden

- **Fase 1 → Fase 2:**
  - T002 y T003 en rojo;
  - T004 y T005 en orden;
  - T006 y T007 en paralelo con T004 y T005.
- **Fase 2b (T008):** se escribe en rojo después de la Fase 2 y se pone en verde con H1 (T015 y T016) y H3 (T026).
- **H1 (Fase 3):**
  - depende de la Fase 2;
  - T009–T012 se escriben en paralelo;
  - T013–T017 son la API, T018–T020 la consola, y T018 va antes que T019 y T020.
- **H2 (Fase 4):** depende de H1, porque reutiliza la página y el panel.
- **H3 (Fase 5):** depende de H1 (T015, T016 y T019).
- **Cierre:** al final.

## Paralelismo

- T002, T003, T006 y T007 tocan ficheros distintos: van en paralelo.
- T009, T010, T011 y T012 van en paralelo.
- T021 con T022, y T024 con T025.

## Estrategia

- **MVP (H1, Instagram):** cubre la mayor parte del trabajo, porque deja la página, el panel y las llamadas para los dos canales. H2 y H3 son pequeñas encima.
- **El paso a producción del PR 77 espera a las tres historias** y a la prueba manual en staging (`quickstart.md`).

## Notas de implementación

Implementada el 2026-11-27, en el worktree `085-enlace-instagram-messenger` y sin commit. El guion es `.claude/commits/2026-11-27-085-impl.sh`.

### Decisiones tomadas sin Luis

- **El canal en el agente (R6).** La lógica de «Mover» de la consola se extrajo a `services/channel_config.move_channel` sin cambiar sus respuestas, y el enlace la usa.
  - Si «Mover» lo rechazaría (un agente en borrador o archivado, o una audiencia «A todos» hacia un agente de solo administradores), el canal se queda en el cliente. Así pasa en la consola: «un agente sin guardar no puede recibirlo».
  - La página del dueño no dice nada de eso: es cosa del partner.
- **Sin modo prueba en Instagram y Messenger.** El enlace de WhatsApp de un agente deja el número en «Solo mi equipo» (32.9). Conectar Instagram o Messenger desde la consola no lo hace, y el enlace hace lo mismo que la consola.
- **Dónde ofrece el enlace el agente.** WhatsApp lo ofrece dentro de su modal «Conectar WhatsApp». Instagram y Messenger abren Meta directamente desde su tarjeta del asistente. Para no añadir un paso a la conexión de la consola, el enlace va en una línea bajo el asistente: «¿Prefieres que lo conecte el cliente?», con un botón por canal. El pendiente de cada canal tiene su tarjeta arriba, como el de WhatsApp.
- **El texto del botón.** En Instagram y Messenger dice «Enviar enlace de Instagram al cliente» y «Enviar enlace de Messenger al cliente». WhatsApp conserva «Enviar enlace al cliente». En Canales del cliente salen los tres, y tres botones iguales no se distinguen.
- **El panel de operador sigue solo con WhatsApp (R12).** Su lista de enlaces filtra `channel = 'whatsapp'`. Si no, enseñaría los de Instagram con un modo que no conoce.
- **`pending_links` no es `list[OwnerLinkOut]`.** Es `list[PendingOwnerLinkOut]`, con `id`, `channel`, `mode` y `expires_at`. `OwnerLinkOut` lleva la URL, que no se guarda y no se puede volver a enseñar (31.7).
- **`OwnerLinkIn.mode` sigue siendo opcional en WhatsApp.** Sin él, `coexistence`, como hasta hoy: la prueba de la 047 crea con `{}`. En Instagram y Messenger, cualquier modo da 422.
- **Los caducados de un agente se anulan con el motivo `expired`.** Desde entonces, su página dice «Este enlace ya no es válido» y no «Este enlace caducó». Los dos mandan pedir otro.
- **Un enlace que muere con la página abierta.** Un 404 o un 410 de las llamadas cambia la página al mismo estado muerto que al abrirla, sin el diálogo de «Intentar de nuevo».
- **El aviso de avisar a quien lo envió (5.4)** es una frase fija bajo cualquier motivo en la página del dueño: «Si no puedes arreglarlo tú, avisa a quien te envió el enlace». No hay una lista de qué motivos dependen del dueño.
- **Una elección que no es suya** da `pending_expired` y se queda en Redis para quien la inició. No se borra: si no, otro enlace podría estropear la elección de la consola.
- **La versión del Graph** de la página de Instagram y Messenger es la de la conexión social (`meta_social_graph_api_version`), la misma de la oferta de la consola, no la de Embedded Signup.

### Lo que queda

- La prueba en staging con Meta real (`quickstart.md`, «En staging»).
- Las auditorías de UI del workspace (estados, a11y, responsive y tokens) no se pasaron como skills ni en navegador. Las pruebas de componente pasan axe en la página del dueño.
