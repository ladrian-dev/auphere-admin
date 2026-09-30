# Tasks: el catálogo en el número

**Input**: documentos de diseño de `/specs/022-catalogo-en-el-numero/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/catalog.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia. H1 = el partner enlaza el catálogo desde la
tarjeta · H2 = el alta lo ofrece · H3 = el agente lo usa, y solo cuando lo
tiene. **Orden de entrega** (plan): Meta y la API → la tarjeta (H1) → el
agente (H3) → el alta (H2). H2 va última porque monta sobre la tarjeta ya
hecha, aunque en la spec tenga la misma prioridad que H3.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO);
  **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada
  nuevo gasta (T-MET).
- **Una dependencia fuera del repo** (research D5): el permiso
  `catalog_management` en el panel de Meta. La iteración 1 se cierra en
  local con Meta simulado; CE-002 y CE-004 esperan a ese permiso en staging.
- **Cierre**: tests rojos → código → suites en verde → paridad → evidencia →
  log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

API en `apps/api/src/nexus_api/` con tests en `apps/api/tests/{unit,integration,isolation}/`;
cliente de Meta en `apps/channels/src/nexus_channels/whatsapp_meta/`;
servidores internos en `apps/mcp/src/nexus_mcp/servers/`; consola en
`apps/console/src/` con tests junto al código; KB en
`/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

- [ ] T001 [P] Crear `specs/022-catalogo-en-el-numero/evidence/README.md` (una entrada por iteración) y `parity.md`: qué hace hoy la tarjeta del número (spec 021) y qué de eso cambia — **nada se retira**; se añade «Catálogo». _Requisitos: ninguno — ritual de cierre_
- [ ] T002 [P] T-LIC · hashes de `pnpm-lock.yaml`, `apps/api/uv.lock` y `apps/mcp/uv.lock` en `evidence/locks-at-open.sha256`; se comparan al cerrar. _Requisitos: ninguno — puerta §VIII_
- [ ] T003 [P] T-MET · Test en `apps/api/tests/unit/test_endpoint_console_catalog.py` de que listar, enlazar y desconectar el catálogo **no** escriben ningún evento de consumo; y test en `apps/mcp/tests/` de que `catalog.search_products` tampoco (una llamada a Meta no es modelo, reloj ni herramienta de pago). _Requisitos: ninguno — puerta del medidor_

---

## Phase 2: Foundational — Meta y la API

- [ ] T004 T-ISO · `apps/api/tests/isolation/test_channel_catalog_scope.py`: con dos tenants, (a) `GET …/catalogs` del canal de A bajo el scope de B es 404 y no llama a Meta; (b) `PUT …/catalog` de B sobre el canal de A es 404 y el canal de A no cambia; (c) la lista de catálogos que recibe A sale **solo** del token del canal de A (el simulador registra con qué token se le llamó); (d) barrido por OpenAPI de las rutas nuevas: ninguna acepta `tenant_id`, `partner_id` ni `access_token`. _Requisitos: 1.1, 1.8 · puerta §I_
- [ ] T005 [P] Tests en `apps/channels/tests/test_meta_client.py` (respx) para `list_catalogs(business_id, access_token)`, `get_linked_catalog(waba_id, access_token)`, `link_catalog(waba_id, catalog_id, access_token)`, `unlink_catalog(waba_id, catalog_id, access_token)` y `search_products(catalog_id, query, limit, access_token)`: cuerpos exactos, y un rechazo por permiso (`code 10`/`200`) sube como `MetaAPIError` con su `code`. _Requisitos: 1.1, 1.2, 1.4, 3.3_
- [ ] T006 [P] Implementar los cinco métodos en `apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py` sobre `_get`/`_post`/`_delete`. _Requisitos: 1.1, 1.2, 1.4, 3.3_
- [ ] T007 [P] Migración `apps/api/alembic/versions/0134_audit_vocab_catalog.py` (id ≤ 32 caracteres): fila `console.channel.catalog` · `channels` · `info` · «{actor} cambió el catálogo de {client}.» / «{actor} changed {client}'s catalogue.» Test: `test_every_console_action_written_has_vocabulary` sigue verde. _Requisitos: 1.7_
- [ ] T008 [P] `apps/api/src/nexus_api/api/console/schemas_channels.py`: `CatalogOut {id, name, checked_at}`, `CatalogListOut {items, linked_id}`, y en `ChannelDetailOut`: `catalog`, `catalog_state` (`none | linked | permission_missing | unchecked`), `catalog_error`. Contrato en `contracts/catalog.md`. _Requisitos: 1.2, 1.5, 1.6, 1.9_
- [ ] T009 `apps/api/src/nexus_api/api/console/channels.py`: `catalog_permission_missing(exc)` (pura: `MetaAPIError.code in {10, 200, 190}`), y la **conciliación** al listar canales (research D3): por WABA, caché Redis `nexus:catalog:waba:{waba_id}` 300 s, adopta lo que Meta tiene, borra lo que Meta ya no tiene, `unchecked` si Meta no responde, nunca pregunta sin credencial. Test primero en `tests/unit/test_endpoint_console_catalog.py`: los cuatro casos de la tabla de D3 + «sin credencial no se llama a Meta» + «una WABA con dos números = una llamada». _Requisitos: 1.9, 4.3_

**Checkpoint**: el cliente sabe hablar de catálogos, la lista de canales dice la verdad de Meta, y ningún tenant ve lo de otro.

---

## Phase 3: Historia 1 — El partner enlaza el catálogo desde la tarjeta (P1) 🎯 MVP

**Goal**: en Canales, conectar, cambiar (con confirmación) y desconectar el catálogo, con los estados honestos.

**Independent Test**: CE-001, CE-003 y CE-005 del quickstart, en local con Meta simulado.

### Tests (OBLIGATORIO — §VII) ⚠️

- [ ] T010 [P] [US1] `apps/api/tests/unit/test_endpoint_console_catalog.py` (Meta simulado por `build_meta_client`, como en la 021): `GET …/catalogs` devuelve los del negocio con `linked_id`; sin credencial → 409 `channel_has_no_credentials`; permiso → 409 `catalog_permission_missing`; Meta caído → 503 `meta_unavailable`. _Requisitos: 1.1, 1.5, 1.6_
- [ ] T011 [P] [US1] Mismo fichero: `PUT …/catalog` enlaza y guarda `id`+`name`; con otro ya enlazado desenlaza y enlaza en ese orden y `after.meta == {unlinked, linked}`; si el segundo paso falla, `catalog == null` y `catalog_error` con el motivo; catálogo ajeno → 409 `catalog_not_owned`; audita `console.channel.catalog` con `before/after` y el actor. _Requisitos: 1.2, 1.3, 1.5, 1.7_
- [ ] T012 [P] [US1] Mismo fichero: `DELETE …/catalog` desenlaza y borra; sin catálogo no llama a Meta; si Meta rechaza, el catálogo sigue y `catalog_error` lo dice; invalida la caché de la WABA. _Requisitos: 1.4, 1.5_
- [ ] T013 [P] [US1] Mismo fichero: `channels:read` puede `GET …/catalogs`; `PUT`/`DELETE` piden `channels:write` (403 con el rol `analyst`). _Requisitos: 1.8_
- [ ] T014 [P] [US1] `apps/console/src/components/channels/__tests__/channel-card.test.tsx`: los cinco estados de la tarjeta (`none`, `linked`, `permission_missing`, `unchecked`, solo lectura) enseñan su frase y sus controles, y ningún otro; el texto de `permission_missing` dice «vuelve a conectar el número»; con `unchecked` se ve el nombre guardado y «no se pudo comprobar». _Requisitos: 1.6, 1.8, 1.9_
- [ ] T015 [P] [US1] `apps/console/src/components/channels/__tests__/catalog-picker.test.tsx`: la lista con nombres; lista vacía → «tu negocio no tiene catálogos» con dónde se crea, sin lista vacía; con uno ya enlazado, elegir otro muestra el diálogo «vas a sustituir A por B» y solo al confirmar llama a la acción; `catalog_not_owned` y `meta_unavailable` tienen frase. _Requisitos: 1.3, 1.5_

### Implementación

- [ ] T016 [US1] Endpoints en `apps/api/src/nexus_api/api/console/channels.py`: `GET /{channel_id}/catalogs`, `PUT /{channel_id}/catalog`, `DELETE /{channel_id}/catalog`, con las credenciales por canal y respaldo por tenant (mismo par que desvincular), la auditoría y la invalidación de caché. _Requisitos: 1.1–1.8_
- [ ] T017 [P] [US1] `apps/console/src/lib/backend/channels.ts`: tipos `Catalog`, `CatalogState`, `CatalogError`; `listCatalogs`, `setCatalog`, `clearCatalog`. `apps/console/src/app/(console)/clients/[ref]/channels/actions.ts`: `listCatalogsAction` (`channels:read`), `setCatalogAction` y `clearCatalogAction` (`channels:write`), con `revalidatePath(…, "layout")`. _Requisitos: 1.1, 1.2, 1.4, 1.8_
- [ ] T018 [US1] `apps/console/src/components/channels/catalog-picker.tsx`: diálogo con la lista, el vacío diseñado, la confirmación de cambio y las frases de error; y en `channel-card.tsx` la fila «Catálogo» con los cinco estados y los controles (solo con `manage`). Copia en `apps/console/src/i18n/lanes/channels.ts` (ES/EN; sin «;», sin «cupo», un solo idioma por frase). _Requisitos: 1.2, 1.3, 1.5, 1.6, 1.8, 1.9_

**Checkpoint**: CE-001, CE-003 y CE-005 pasan en local. **Se puede soltar sola.**

---

## Phase 4: Historia 3 — El agente lo usa, y solo cuando lo tiene (P2)

**Goal**: dos capacidades que aparecen solo con catálogo; el agente busca en el catálogo y envía la tarjeta.

**Independent Test**: con catálogo enlazado, pedir un producto en el Playground y recibir una tarjeta; sin catálogo, la capacidad no está.

### Tests (OBLIGATORIO — §VII) ⚠️

- [ ] T019 [P] [US3] `apps/mcp/tests/test_meta_catalog.py`: `catalog.search_products` resuelve el `catalog_id` y el token del canal por el que llegó la conversación (no del tenant «en general»), devuelve `{retailer_id, name, price, currency, availability, image_url}`, nunca el token; sin catálogo → `catalog_not_linked`; `limit` ≤ 10. `catalog.get_product` idem con `description`. _Requisitos: 3.3, 4.3_
- [ ] T020 [P] [US3] `apps/api/tests/unit/test_capabilities_catalog.py`: con `catalog_id` en el canal, Capacidades lista «Buscar en el catálogo» y «Enviar productos del catálogo» encendidas por defecto en `woocommerce_sales_v1`, `inventario_v1` y `restaurante_v1`, apagadas en las demás, y apagables; sin `catalog_id`, **no aparecen**. _Requisitos: 3.1, 3.2_
- [ ] T021 [P] [US3] `apps/worker/tests/unit/test_outbound_products.py` (extiende el existente si lo hay): tras desconectar el catálogo, un `send_interactive` con `products` no sale como tarjeta — se degrada a texto con los nombres, y se anota. _Requisitos: 3.4_

### Implementación

- [ ] T022 [US3] Servidor interno `apps/mcp/src/nexus_mcp/servers/meta_catalog/` (`tools.py`, `schemas.py`, `README.md`) con las dos herramientas, resolviendo credenciales como hace `servers/woocommerce/tools.py` pero por canal de la conversación; registro en `apps/mcp/src/nexus_mcp/registry.py`. _Requisitos: 3.3, 4.3_
- [ ] T023 [P] [US3] Migración `apps/api/alembic/versions/0135_catalog_tools.py`: filas de `tool_catalog` para `catalog.search_products` y `catalog.get_product` (nativas, sin `side_effects`, `default_mode = enabled`). _Requisitos: 3.1_
- [ ] T024 [US3] `apps/api/src/nexus_api/api/console/capability_names.py`: nombres de negocio de las dos herramientas y de «Enviar productos del catálogo» (modo de `response.send_interactive` con `products`), con `requires: channel_catalog`; `capabilities_client.py`: resolver `channel_catalog` mirando si algún canal activo del cliente tiene `catalog_id`; plantillas de venta las traen encendidas. _Requisitos: 3.1, 3.2_
- [ ] T025 [US3] `apps/worker/src/nexus_worker/streams/outbound.py`: sin `catalog_id`, `products` se degrada a texto y se registra `outbound.products_without_catalog`. _Requisitos: 3.4_

**Checkpoint**: en local, con catálogo simulado, el Playground devuelve una tarjeta; sin catálogo, la capacidad no existe.

---

## Phase 5: Historia 2 — El alta lo ofrece (P2)

**Goal**: al terminar el alta de WhatsApp, si hay catálogos, la consola los ofrece; se puede saltar.

**Independent Test**: CE-004 del quickstart (staging con número real); en local, con el simulador, el mismo recorrido con Meta simulado.

### Tests (OBLIGATORIO — §VII) ⚠️

- [ ] T026 [P] [US2] `apps/console/src/components/channels/__tests__/whatsapp-connect.test.tsx`: tras un alta con éxito, si `listCatalogs` trae ≥ 1, se abre el mismo `catalog-picker` con «puedes hacerlo luego»; saltarlo cierra sin llamar a `setCatalog`; con 0 no se abre nada. `permission_missing` tras el alta no abre el selector y no rompe el toast de «conectado». _Requisitos: 2.1, 2.2, 2.3_
- [ ] T027 [P] [US2] `apps/api/tests/unit/test_endpoint_console_whatsapp.py`: el alta guarda `business_id` en `config` (o lo hereda de la credencial del tenant), porque `GET …/catalogs` lo necesita. _Requisitos: 2.1_

### Implementación

- [ ] T028 [US2] `apps/console/src/components/channels/whatsapp-connect.tsx`: al `ok` del alta, pedir `listCatalogsAction` y, si hay, abrir `CatalogPicker` en modo «oferta» (salta con un clic). _Requisitos: 2.1, 2.2, 2.3_
- [ ] T029 [US2] Comprobar y documentar en `quickstart.md` el permiso `catalog_management` en las dos configuraciones del Embedded Signup (panel de Meta; lo hace el owner); el alta de la consola no cambia de código porque el permiso viene del `config_id`. _Requisitos: 2.4_

---

## Phase 6: Cierre

- [ ] T030 Recorrer `quickstart.md`: CE-001, 003 y 005 en local; CE-002 y 004 en staging **tras** T029 con el `+34653321693`. Anotar en `evidence/`. _Requisitos: todos · CE-001–005_
- [ ] T031 Paridad al 100 %, log de sesión en la KB, comparar `locks-at-open.sha256`, merge a `develop`, staging. Suites: API (canales, catálogo, capacidades, aislamiento; la completa en CI), channels, mcp, worker, consola. _Requisitos: ninguno — ritual de cierre_

---

## Dependencies & Execution Order

- **T004–T009 antes que todo lo demás**: cliente, conciliación y aislamiento.
- **T009 antes de T014**: la tarjeta lee `catalog_state`.
- **T016 antes de T017/T018**; **T018 antes de T028** (H2 reutiliza el selector).
- **T022 antes de T024**: la capacidad nombra herramientas que tienen que existir.
- **T029 antes de CE-002 y CE-004** en staging; no bloquea nada en local.

### Parallel Opportunities

- T001, T002, T003 a la vez.
- T005/T006 (cliente) y T007/T008 (vocabulario y esquemas) a la vez.
- T010–T015 a la vez (ficheros distintos).
- T019, T020, T021 a la vez.

---

## Implementation Strategy

**Iteración 1 = Phase 1 + 2 + 3** (H1): se cierra en local con Meta simulado y
se sube a staging; CE-003 se ve allí sin permiso, y el día que el owner añada
el permiso, CE-001 con catálogo real. **Iteración 2 = Phase 4** (H3): el
agente. **Iteración 3 = Phase 5** (H2): el alta lo ofrece. Cada una se puede
soltar sola.
