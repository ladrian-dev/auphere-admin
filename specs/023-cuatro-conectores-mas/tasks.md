# Tasks: tres conectores más

**Input**: documentos de diseño de `/specs/023-cuatro-conectores-mas/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/connectors.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia. H1 = el partner conecta uno de los tres y el
agente lo usa (lista cerrada, nombres, categoría, frase) · H2 = las
plantillas recomiendan. **Orden de entrega** (plan): la lista y el filtro →
nombre, categoría y frase (H1) → recomendación (H2).

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO);
  **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada
  nuevo gasta (T-MET).
- **Una comprobación fuera del repo** (research D1): confirmar en el panel
  del proveedor que cada slug de Stripe y HubSpot existe. Se hace en staging
  (T014) antes de dar la H1 por cerrada; el registro `allowlist_missing`
  delata cualquier error el primer día.
- **Cierre**: tests rojos → código → suites en verde → paridad → evidencia →
  log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

API en `apps/api/src/nexus_api/` con tests en `apps/api/tests/{unit,integration}/`;
consola en `apps/console/src/` con tests junto al código; KB en
`/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

- [X] T001 [P] T-LIC · hashes de `pnpm-lock.yaml` y `apps/api/uv.lock` en `specs/023-cuatro-conectores-mas/evidence/locks-at-open.sha256`; se comparan al cerrar. Crear `parity.md`: qué hace hoy Conectores y Capacidades con un conector dinámico y qué de eso cambia — **nada se retira**; Google Calendar, Notion, Gmail, Sheets y Outlook siguen igual. _Requisitos: 5.1, 5.2, 5.3 · puerta §VIII_ Entregado: rama 023, 2026-09-30 — `evidence/locks-at-open.sha256` (pnpm, api) y `parity.md`: nada se retira; la única baja es una pista de Calendly que nunca casó con nada.
- [X] T002 [P] T-MET · Dentro de `apps/api/tests/integration/connectors/test_sync_allowlist.py` (T007), un caso que afirma que sincronizar con lista **no** escribe ningún evento de consumo (misma comprobación que `test_the_catalog_costs_nothing_the_meter_sees` de la 022). _Requisitos: ninguno — puerta del medidor_ Entregado: rama 023, 2026-09-30 — caso `T-MET` dentro de `test_sync_allowlist.py` (cuenta `usage_events` antes y después).

---

## Phase 2: Foundational — la lista y el filtro

- [X] T003 [P] Test `apps/api/tests/unit/connectors/test_toolkit_allowlists.py`: para cada toolkit de `TOOLKIT_ALLOWLISTS`, (a) todo slug empieza por `<TOOLKIT>_`; (b) `read_only` y `destructive` no son los dos `True`; (c) `read_only=False` implica `destructive=True`; (d) **todo slug tiene entrada en `CAPABILITY_NAMES` con nombre y descripción en `es` y `en`**, y el nombre no es el slug; (e) los tamaños son 12 · 10 · 11. _Requisitos: 2.3, 2.5, 3.2_ Entregado: rama 023, 2026-09-30 — `test_toolkit_allowlists.py`: prefijo, pistas coherentes, nombre en es/en para cada slug, tamaños 12·10·11, lecturas 8·7·6.
- [X] T004 [P] `apps/api/src/nexus_api/services/connectors/toolkits.py`: `ToolHint` y `TOOLKIT_ALLOWLISTS` con las tres listas de research D1, con un comentario por lista que diga de dónde salió (panel / catálogo público, fecha). _Requisitos: 2.3, 2.5_ Entregado: rama 023, 2026-09-30 — `services/connectors/toolkits.py` con `TOOLKIT_ALLOWLISTS`, `allowlist_for` y `hint_for_slug`; origen de cada lista en el docstring.
- [X] T005 Tests en `apps/api/tests/unit/connectors/test_annotation_derivation.py`: un slug de la lista toma sus anotaciones de la lista aunque la heurística de prefijo dijera otra cosa (`CALENDLY_POST_INVITEE` → escribe; `CALENDLY_WHO_AM_I` → lee); `CALENDLY_CANCEL_EVENT` ya no está en `_TOOL_SLUG_ANNOTATIONS`; un slug de toolkit sin lista sigue como hoy. _Requisitos: 2.1, 2.2, 2.5_ Entregado: rama 023, 2026-09-30 — cuatro tests más en `test_annotation_derivation.py` (la lista manda, gana a las etiquetas, Calendly fuera de la tabla, sin lista todo igual).
- [X] T006 `apps/api/src/nexus_api/services/connectors/service.py`: `_derive_annotations` consulta `TOOLKIT_ALLOWLISTS` (por prefijo del slug) antes que `_TOOL_SLUG_ANNOTATIONS`; retirar las cuatro entradas `CALENDLY_*` de la tabla. _Requisitos: 2.1, 2.2, 2.5_ Entregado: rama 023, 2026-09-30 — `_derive_annotations` consulta la lista antes que nada; las cuatro filas `CALENDLY_*` salen de `_TOOL_SLUG_ANNOTATIONS`.
- [X] T007 T-ISO · `apps/api/tests/integration/connectors/test_sync_allowlist.py` con `fake_composio`: (a) el fake devuelve 3 slugs de la lista de Stripe + 2 fuera → quedan 3 filas, `SyncToolsResult` y la auditoría `connector.tools.synced.after` llevan `dropped_count=2` y `missing=[…9 restantes]`; (b) un slug de la lista que tenía fila y el fake ya no devuelve pasa a `deprecated`; (c) un toolkit sin lista (`notion`) sincroniza todo como hoy y su auditoría **no** lleva `missing` ni `dropped_count`; (d) sincronizar Stripe no toca las filas de Notion ni de WooCommerce; (e) T-MET (T002). _Requisitos: 2.3, 2.4 · puerta §I_ Entregado: rama 023, 2026-09-30 — `test_sync_allowlist.py`: 3 + 2 → 3 filas y `dropped_count=2`; retirada → `deprecated` y en `missing`; Notion igual que hoy y sin claves nuevas en la auditoría; Stripe no toca a Notion.
- [X] T008 `sync_tools_for` en `service.py`: si `toolkit in TOOLKIT_ALLOWLISTS`, filtrar `tools` a la lista antes de `upstream_slugs`; registrar `connector.sync.allowlist_dropped` (cuenta) y `connector.sync.allowlist_missing` (slugs); añadir `missing` y `dropped_count` a `after` y a `SyncToolsResult`. Contrato en `contracts/connectors.md` §3. _Requisitos: 2.3, 2.4_ Entregado: rama 023, 2026-09-30 — `sync_tools_for` filtra por lista, registra `allowlist_dropped` / `allowlist_missing`, y `SyncToolsResult` y la auditoría llevan `missing` y `dropped_count`.

**Checkpoint**: Calendly, que ya existía con 53 filas, pasa a 10 en la primera sincronización; ningún toolkit sin lista cambia.

---

## Phase 3: Historia 1 — nombre, categoría y frase (P1)

**Goal**: en Conectores, cada uno en su categoría con su frase; en Capacidades, las de lectura encendidas y las de escritura bloqueadas, todas con nombre de negocio.

**Independent test**: con las tres cuentas en el proveedor, conectar cada una en un cliente de prueba y leer Capacidades (quickstart, pasos 2–5).

- [X] T009 [P] [US1] Tests en `apps/api/tests/unit/test_capability_names.py`: las 33 entradas nuevas se leen en `es` y `en`, ninguna repite la clave técnica, ninguna descripción contiene «PaymentIntent», «invitee», «deal» ni «CRM»; Stripe cae en `orders`, Calendly en `appointments`, HubSpot en `other`. _Requisitos: 3.1, 3.2_ Entregado: rama 023, 2026-09-30 — `test_the_closed_lists_are_named_and_grouped_where_the_partner_expects` en `test_capability_names.py` (función por toolkit, sin sector, sin jerga por idioma).
- [X] T010 [P] [US1] `apps/api/src/nexus_api/api/console/capability_names.py`: las 33 entradas de research D1, en su bloque `# ── Stripe / Calendly / HubSpot (spec 023) ──`. _Requisitos: 3.1, 3.2_ Entregado: rama 023, 2026-09-30 — 33 entradas en `capability_names.py` (bloque «Stripe, Calendly y HubSpot (spec 023)»).
- [X] T011 [P] [US1] Test `apps/api/tests/unit/test_connector_category.py`: `_project_dynamic` da `billing` a `stripe`, `booking` a `calendly` y `crm` a `hubspot` aunque la metadata del proveedor diga «other» o venga vacía; `_resolve_category("payments")` → `billing`, `("e-commerce")` → `ecommerce`, `("developer-tools")` → `otros`. _Requisitos: 1.1_ Entregado: rama 023, 2026-09-30 — `test_connector_category.py`: los tres fijos aunque el proveedor diga «other»; `payments`/`e-commerce` ya no caen en «otros».
- [X] T012 [P] [US1] `apps/api/src/nexus_api/services/connectors/catalog.py`: `_CATEGORY_BY_TOOLKIT`, consultado en `_project_dynamic` antes que la metadata; `payment`/`billing`/`financ`/`invoic` → `billing` y `commerce`/`shop`/`store` → `ecommerce` en `_CATEGORY_MAP` y `_CATEGORY_KEYWORDS`. _Requisitos: 1.1_ Entregado: rama 023, 2026-09-30 — `_CATEGORY_BY_TOOLKIT` antes que la metadata; `payment…`/`commerce…` en mapa y palabras clave.
- [X] T013 [P] [US1] Consola: `connectors.desc.stripe`, `connectors.desc.calendly`, `connectors.desc.hubspot` en `apps/console/src/i18n/lanes/capabilities.ts` (research D5) y test en `components/integrations/__tests__/connector-card.test.tsx` de que la tarjeta de `stripe` enseña su frase y no la de reserva. _Requisitos: 1.2_ Entregado: rama 023, 2026-09-30 — tres claves `connectors.desc.*` y test de que la tarjeta de Stripe enseña su frase; `no-orphan-keys` verde.
- [ ] T014 [US1] Staging con cuentas reales (quickstart, pasos 1–5): confirmar los 23 slugs de Stripe y HubSpot en el panel (anotar en `evidence/iteracion-1.md` los que no existan y corregir la lista antes de seguir); conectar Stripe, Calendly y HubSpot en un cliente de prueba; capturas de Conectores en es/en (CE-004) y de Capacidades (CE-002, CE-003); auditoría con `missing=[]`; CE-001 en el Playground. _Requisitos: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3 · CE-001..004_

**Checkpoint**: Historia 1 cerrada con evidencia real.

---

## Phase 4: Historia 2 — las plantillas recomiendan (P2)

**Goal**: un cliente de citas ve Calendly y AgendaPro como recomendados; uno de cobranza, Stripe y Amigable Cobro.

**Independent test**: crear un cliente con cada plantilla y leer Conectores (quickstart, paso 6).

- [X] T015 [P] [US2] Test `apps/api/tests/unit/test_seed_templates_connectors.py`: `barbershop_v1` → `[agendapro, calendly]`, `cobranza_v1` → `[amigable_cobro, stripe]`, `woocommerce_sales_v1` → `[woocommerce]`, `generic_v1` → `[]`; un YAML sin bloque carga; un bloque que no sea lista de cadenas falla con el error de esquema de siempre. _Requisitos: 4.1_ Entregado: rama 023, 2026-09-30 — `test_seed_templates_connectors.py`: ocho de citas, cobranza, dos de tienda, dos sin bloque, bloque mal formado falla, bloque vacío carga.
- [X] T016 [P] [US2] `apps/api/src/nexus_api/services/templating/seed_templates.py`: `SeedTemplate.connectors_recommended` leído de `connectors.recommended` (vacío si falta; validado); bloque en `seeds/{barbershop,beauty_salon,clinica,dental,medspa,nail_studio,spa,aesthetic_clinic}_v1.yaml` (`[agendapro, calendly]`), `cobranza_v1.yaml` (`[amigable_cobro, stripe]`), `woocommerce_sales_v1.yaml` e `inventario_v1.yaml` (`[woocommerce]`). _Requisitos: 4.1_ Entregado: rama 023, 2026-09-30 — `SeedTemplate.connectors_recommended` con validación; bloque `connectors.recommended` en once plantillas.
- [X] T017 [US2] Test `apps/api/tests/integration/connectors/test_connectors_recommended.py`: `GET /console/clients/{ref}/connectors` marca `recommended=true` solo a los slugs de la plantilla del sector; un cliente sin sector, todos `false`; recomendar no quita ninguna tarjeta ni cambia `category`. _Requisitos: 4.1, 4.2_ Entregado: rama 023, 2026-09-30 — `test_connectors_recommended.py`: la plantilla decide (AgendaPro y Calendly con barbería), sin sector nadie, recomendar no esconde ni mueve.
- [X] T018 [US2] `apps/api/src/nexus_api/api/console/schemas_agent_tools.py`: `ConnectorOut.recommended: bool = False`; `tools.py::_connectors` lo rellena con `client_sector` + `load_seed_template` con la misma tolerancia que `_recommended`. Contrato en `contracts/connectors.md` §1. _Requisitos: 4.1, 4.2_ Entregado: rama 023, 2026-09-30 — `ConnectorOut.recommended` y `_recommended_connectors(sector)` en `tools.py`, misma tolerancia que en Capacidades.
- [X] T019 [US2] Consola: `recommended` en `apps/console/src/lib/backend/agent-tools-types.ts`; insignia «Recomendado para tu sector» (`connectors.badge.recommended`, es/en) en `components/integrations/connector-card.tsx` solo con `recommended: true`; test en `connector-card.test.tsx`; `no-orphan-keys` verde. _Requisitos: 4.1, 4.2_ Entregado: rama 023, 2026-09-30 — `recommended` en el tipo, insignia en `connector-card.tsx`, clave `connectors.badge.recommended`, dos tests en `connector-card.test.tsx`.
- [ ] T020 [US2] Staging: cliente nuevo con `barbershop_v1` y otro con `cobranza_v1`; captura de Conectores con las insignias (CE-005) en `evidence/iteracion-2.md`. _Requisitos: 4.1 · CE-005_

**Checkpoint**: Historia 2 cerrada con evidencia real.

---

## Phase 5: Polish & cierre

- [ ] T021 Comparar `evidence/locks-at-open.sha256` con los locks actuales (T-LIC); `parity.md` cerrado; log de sesión en `kb/Auphere/nexus/sessions/2026-09-30-spec-023-tres-conectores-mas.md` con enlace a esta carpeta; actualizar la memoria del proyecto; merge a `develop` y CI verde. _Requisitos: ninguno — ritual de cierre · puerta §IX_

---

## Dependencies

- Phase 2 antes que todo: sin lista no hay nada que nombrar.
- Phase 3 depende de la Phase 2 (T010 lo exige T003-d: el test de la lista falla hasta que existan los nombres, así que **T003/T004 y T009/T010 se cierran juntos**).
- Phase 4 depende de la Phase 3 solo para la evidencia (T020 necesita las tres tarjetas en su categoría); el código de la H2 es independiente.
- T014 y T020 exigen staging con las tres cuentas; todo lo demás se cierra en local.

## Parallel execution

- Phase 2: T003 ∥ T004 (unit) mientras T007 (integration) se escribe; T005/T006 y T008 después.
- Phase 3: T009/T010 ∥ T011/T012 ∥ T013.
- Phase 4: T015/T016 ∥ T019 (consola) mientras T017/T018 se hacen en la API.

## Implementation strategy

MVP = Phase 2 + Phase 3 (Historia 1): con eso los tres conectores sirven. La
Historia 2 es un día más y no bloquea. Cada fase se fusiona a `develop` en
verde y se comprueba en staging antes de la siguiente.
