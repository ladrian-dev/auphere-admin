---
description: "Task list for feature implementation"
---

# Tasks: la identidad y el puesto de trabajo en la aplicación de escritorio

**Input**: documentos de diseño en `/specs/002-identidad-app-escritorio/`

**Prerequisites**: [`plan.md`](./plan.md) · [`spec.md`](./spec.md) ·
[`research.md`](./research.md) · [`data-model.md`](./data-model.md) ·
[`contracts/`](./contracts) · [`quickstart.md`](./quickstart.md)

**Tests**: **no son opcionales.** §VII — cada criterio de aceptación nace como
test, se ve en rojo, y solo entonces se implementa. Un `skip` puntúa como aprobado
y por tanto no cubre nada.

**Organization**: por historia de usuario, para que cada una se implemente y se
pruebe sola.

## Cobertura por capacidad, no por cita

La 001 dejó dos huecos porque la comprobación de cobertura mapea criterios
**citados**. Este `tasks.md` lleva al final una tabla que responde, por cada
requisito, **qué se puede hacer que antes no** y **qué test lo vio en rojo**. Un
requisito que solo aparece citado en tareas que no lo construyen **no está
cubierto**, y `/speckit-analyze` lo tiene que tratar así.

## Orden de las historias, y por qué

Tres son P1 y dos P2, pero el orden lo fija la dependencia: **US1** (entrar y
emparejar) no vale nada si la máquina sigue siendo del tenant, así que el cambio
de dueño va **antes que cualquier pantalla** (Phase 2). Después: US1 → **US2**
(una máquina, todos mis clientes) → **US4** (cerrar sesión, desemparejar,
archivar — P1 porque hoy nada detiene el puente) → US3 (guía) → US5 (máquina
compartida). Aquí el MVP es **US1 + US2 + US4**: emparejar sin saber apagar no es
entregable.

---

## Phase 0: La puerta de escritorio

**Propósito**: la única capacidad no probada del plan. `BaseWindow` + dos
`WebContentsView` no se han usado en este repo. Se verifica con display antes de
construir la barra encima.

**⚠️ Si T001 falla, el repliegue es una `BrowserWindow` hija anclada (plan
§Riesgo). No toca ningún principio, pero cambia D8 de `research.md` y hay que
reescribirlo antes de seguir.**

- [x] T001 Spike con display en `apps/desktop/`: `BaseWindow` con dos `WebContentsView`
      — la de la consola en `persist:auphere-console` **sin `preload`**, la de la barra
      en `auphere-bar` con un `preload` que expone una sola función de prueba—, y
      comprobar (a) que la consola carga y su login funciona, (b) que desde la vista de
      la consola `window.auphere` es `undefined`, (c) que `assertPartitionsAreSeparate`
      sigue en verde con tres particiones. Evidencia en `evidence/T001/`.
      _Requisitos: 12.1, 14.1, 3.5_
      **PASA (2026-09-09).** `evidence/T001/result.json`: la consola real carga en
      2,9 s con su formulario de login; `typeof window.auphere` es `undefined` en la
      vista de la consola y `object` en la barra (`ping() → pong`); `persist:` solo en
      la humana, la de la barra y la del agente sin persistencia. D8 confirmado: no
      hace falta el repliegue.

**Checkpoint**: T001 pasa → D8 se confirma y la Phase 1 empieza.

---

## Phase 1: Setup

- [x] T002 [P] Añadir el permiso `workstation:pair` (owner · admin · builder) en
      `apps/api/src/nexus_api/core/console_auth.py` y en
      `apps/console/src/lib/permissions.ts`, y ampliar el test de deriva
      `apps/console/src/lib/__tests__/permissions.test.ts` para que lo compare.
      _Requisitos: 3.1, 6.5_
      **HECHO.** `workstation:pair` = owner · admin · builder en `console_auth.py` y `permissions.ts`; el test de deriva lo compara y añade el caso «builder empareja, builder no archiva».
- [x] T003 [P] Vocabulario nuevo de auditoría —`device.pair_code_issued`,
      `device.paired`, `device.pair_denied`, `device.renewed`, `device.link_declared`,
      `device.unpaired`, `device.archived`— en el catálogo que fijó `0105`
      (`apps/api/alembic/versions/0108_device_audit_vocab.py` si el vocabulario vive en
      la base; si vive en código, en `services/audit_vocab.py`). _Requisitos: 13.1, 13.2_
      **HECHO** como migración `0108_device_audit_vocab` (el vocabulario vive en `console_audit_vocabulary`): ocho actos, con `{machine}`, `{client}` y `{reason}` en el resumen.
- [x] T004 [P] Crear `apps/desktop/src/bar/` con el esqueleto: `index.html`,
      `bar.ts`, y un paso de build en `package.json` que copia
      `packages/ui/src/styles/tokens.css` al bundle (**no** se descarga en tiempo de
      ejecución). Cero hex: el test de T005 lo vigila. _Requisitos: 12.5_
      **HECHO.** `src/bar/` (html, css, ts), `scripts/copy-tokens.mjs` y `scripts/copy-bar.mjs`; `build` copia los tokens **antes** de compilar. `src/bar/tokens.css` en `.gitignore`: es una copia.
- [x] T005 [P] Test `apps/desktop/tests/bar-tokens.test.ts`: ningún fichero de
      `src/bar/` contiene un color hex, `--color-fg-subtle` ni `--color-status-warning`
      con texto claro encima. Se escribe **antes** de que la barra tenga estilos.
      _Requisitos: 12.5, 12.6_
      **HECHO.** 5 tests, vistos en rojo antes de T004 (sin `src/bar/` y sin `copy-tokens` en el build).
---

## Phase 2: Foundational — la máquina cambia de dueño

**⚠️ Ninguna historia empieza hasta que esta fase esté completa.** Es la apuesta
del plan y la enmienda del 001-R6.3. Los tests van primero y se ven en rojo.

### Tests de la Phase 2 ⚠️

- [x] T006 [P] Test de aislamiento `apps/api/tests/isolation/test_30_device_partner_scope.py`
      — **garantía 1**: `partner_devices` no se ve sin `app.partner_id`; con partner y
      persona se ven las propias; con `app.workstation_manager='true'` se ven todas las
      del partner y ninguna de otro; `WITH CHECK` impide escribir para otro partner.
      **Garantía 2**: una máquina del partner con vínculo a A ejecuta con la lista de A
      y no alcanza la de B. **Credencial**: la de A no late/sondea/renueva/declara para
      B; `client_ref` ajeno → 404 y asiento de auditoría; revocada → 403 en las cinco
      operaciones; `gen` viejo fuera de gracia → 401. En rojo bloquea el merge (§I).
      _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.4, 11.3, 14.3_
      **HECHO.** 11 tests en `test_30`: dueña/gestor/nadie, `WITH CHECK` por partner, vínculos por tenant, `client_ref` ajeno → 404 **con asiento**, archivada → 403 en las cinco, `gen` vieja → 401, 31 días → `pairing_required`, sondeo de B sin vínculos de A. Vistos en rojo (ImportError) antes de la migración.
- [x] T007 [P] Reescribir `apps/api/tests/isolation/test_28_local_allowlist_device_rls.py`:
      los vínculos (`device_client_links`) no se cruzan entre tenants; las máquinas se
      aíslan por partner. _Requisitos: 4.5, 4.6_
      **HECHO.** 4 tests: vínculos y directorios por tenant; máquinas por partner; sin GUC nada; `WITH CHECK`.
- [x] T008 [P] Reescribir `apps/api/tests/isolation/test_29_device_credential_scope.py`
      para los claims v2 (`pid`, `gen`, sin `tid`): la guarda de secreto de producción
      se conserva tal cual. _Requisitos: 4.2, 10.4_
      **HECHO.** 6 tests, claims v2 `{sub, pid, gen}`; un token de consola forjado con el mismo secreto **no** es de dispositivo (`svc`); la guarda del secreto de producción se conserva.
- [x] T009 [P] Test `apps/api/tests/integration/test_device_renewal.py`: `renew` sube
      `gen`, la credencial anterior vale 60 s y luego no; 31 días sin latir →
      `403 pairing_required` en `renew`, `heartbeat` y `poll`; asiento `device.renewed`
      con actor `device:{id}`. _Requisitos: 10.1, 10.2, 10.3, 10.4, 13.1_
      **HECHO.** 5 tests: rota `gen`, la anterior vive 60 s y ni uno más, 31 días → `pairing_required` en las tres, 29 días vale, asiento con actor `device:`.
- [x] T010 [P] Ampliar `apps/api/tests/integration/test_device_bridge_inbound.py`:
      `POST /device/pair` es **la excepción documentada** sin credencial; todo lo
      demás la exige; sigue sin haber `{device_id}` ni `{id}`; el único GET sigue siendo
      el sondeo. _Requisitos: 3.5, 14.3_
      **HECHO.** `UNAUTHENTICATED_BY_DESIGN = {"/device/pair"}` nombrado; un test afirma que las autenticadas son **exactamente cinco**.
- [x] T011 [P] Test `apps/api/tests/integration/test_identity_acts_do_not_meter.py`:
      emparejar, renovar, declarar, desemparejar y archivar dejan `usage_ledger`
      exactamente igual. _Requisitos: 9.1, 9.2_
      **HECHO.** 2 tests: los cinco actos de identidad y tres latidos dejan `usage_ledger` igual.
### Implementación de la Phase 2

- [x] T012 Migración `apps/api/alembic/versions/0107_device_owner_and_pairing.py` según
      `data-model.md`: `partner_devices` gana `partner_id`, `hostname`,
      `credential_generation`, `credential_rotated_at`, `revoked_reason` (CHECK cerrado)
      y pierde `tenant_id` y `workdir`; nacen `device_client_links` (RLS por tenant,
      FORCE) y `device_pairing_codes` (RLS por partner, FORCE); `partner_devices` con
      **dos políticas** (dueña · gestor) sobre `app.partner_id`, `app.principal_id` y
      `app.workstation_manager`. Backfill de las filas del piloto. `test_21` en verde.
      _Requisitos: 4.1, 5.1, 5.4, 7.4_
      **HECHO.** `0107_device_owner_and_pairing`: backfill del partner desde `tenants.partner_id`, el `workdir` pasa a vínculo, dos políticas OR en `partner_devices`, `device_client_links` con política de tenant **y** de lectura por máquina (a través de la RLS de `partner_devices`, sin recursión), `device_pairing_codes` por partner. `test_21` en verde con las dos tablas de partner documentadas.
- [x] T013 Modelos en `apps/api/src/nexus_api/db/models/local_workstation.py`:
      `PartnerDevice` (campos nuevos), `DeviceClientLink`, `DevicePairingCode`;
      vocabulario `REVOKED_REASONS` cerrado. Registrados en `db/models/__init__.py`.
      _Requisitos: 4.1, 7.4, 11.5_
      **HECHO.** `PartnerDevice` (partner_id, hostname, generación, motivo), `DeviceClientLink`, `DevicePairingCode`, `REVOKED_REASONS` con CHECK.
- [x] T014 `apps/api/src/nexus_api/core/partner_context.py`: `apply_partner_to_session`
      acepta `principal_id` y `workstation_manager: bool`, fijando los tres GUC en la
      misma sentencia. La dependencia de consola pasa `manager=True` **solo** con
      `workstation:write`. _Requisitos: 5.1, 5.2, 5.4_
      **HECHO.** `apply_partner_to_session(..., principal_id=, workstation_manager=)` fija los tres GUC en una sentencia y los **vacía** siempre para que no se hereden.
- [x] T015 Repositorios en `apps/api/src/nexus_api/repositories/local_workstation.py`:
      `PartnerDeviceRepository` por partner+persona (`list_mine`, `list_all_for_manager`,
      `pair`, `rename`, `archive(reason)`, `archive_all_for_principal`, `rotate_credential`,
      `record_heartbeat` **que sigue moviendo solo `last_heartbeat_at`**);
      `DeviceClientLinkRepository` por tenant (`link`, `declare_workdir`, `unlink`,
      `links_for_device`); `DevicePairingCodeRepository` (`issue`, `consume` atómico).
      Ninguno acepta partner, persona ni tenant del llamante. _Requisitos: 4.3, 5.1, 7.4_
      **HECHO.** `list_visible` no filtra: la RLS decide (R5.4). `record_heartbeat` sigue moviendo solo su columna (el latido acepta `app_version` y lo ignora a propósito). `consume` es un `UPDATE … RETURNING` atómico con el rol dueño.
- [x] T016 `apps/api/src/nexus_api/services/device_credential.py` v2: claims
      `{svc, sub, pid, gen}`, `issue` y `verify` con gracia de generación; motivos
      distinguibles `DeviceArchived`, `PairingRequired`, `CredentialStale`.
      _Requisitos: 4.2, 10.1, 10.4_
      **HECHO.** `generation_is_acceptable` (gracia 60 s) e `is_abandoned` (30 días) como funciones puras; los helpers del código en `core/pairing_codes.py` para no cerrar el ciclo `repositories → services`.
- [x] T017 `apps/api/src/nexus_api/api/device_bridge.py`: `require_device` carga la fila
      y aplica el orden del contrato (firma → archivada → generación → 30 días →
      GUCs); `POST /device/renew`; `GET /device/poll` devuelve `links[]`;
      `POST /device/links` con `client_ref` resuelto por `partner_tenants` bajo el
      partner de la firma y `404` registrado si no es suyo. **Cinco operaciones y
      ninguna más.** _Requisitos: 4.2, 4.3, 4.4, 7.2, 10.1, 10.2, 11.3, 13.1_
      **HECHO.** `require_device` comprueba firma → archivada → generación → abandono y deja la transacción abierta **sin acotar**; cada operación elige `scope_partner()` o `scope_tenant()` — acotar antes de localizar un asiento de tenant lo hacía invisible. Las denegaciones que deben dejar asiento se **devuelven** (`JSONResponse`), no se lanzan: una excepción dentro de la transacción deshacía el asiento. `DeviceRefused` → `{code, reason}` (§V).
- [x] T018 `apps/api/src/nexus_api/services/device_presence.py`: la presencia de un
      tenant se deriva de sus **vínculos con directorio** cuya máquina late y no está
      archivada. El catálogo del turno la consume igual que antes. Ampliar
      `tests/integration/test_device_presence.py`: sin directorio no hay herramientas;
      dos clientes, dos directorios. _Requisitos: 7.5, 4.5_
      **HECHO.** `tenant_presence(session)` deriva de los vínculos con directorio cuya máquina late y no está archivada. Requiere partner + tenant en contexto (documentado); la presencia por latido (`derive_presence`) no cambia.
- [x] T019 `apps/api/src/nexus_api/repositories/partner_membership.py` (`remove`) y la
      suspensión de cuenta llaman a `archive_all_for_principal(reason='pertenencia_retirada')`
      en la misma transacción; test en `tests/integration/test_device_bridge.py`.
      _Requisitos: 11.4_
      **HECHO.** `PartnerMembershipRepository.remove` archiva con `pertenencia_retirada` en la misma transacción; test en `test_device_bridge.py` (`DELETE /console/team/members/{id}` → 403 en el siguiente latido).
**Checkpoint**: `test_30`, `test_28`, `test_29` y `test_21` en verde; las 733 de
aislamiento siguen en verde. La máquina es del partner. Las historias pueden empezar.

---

## Phase 2b: Las puertas de la constitución

- [x] T020 [P] **Aislamiento** — las tres garantías declaradas tienen test: **1** y **2**
      en `test_30` (T006) y `test_28` (T007); **6** en `apps/api/tests/isolation/test_27_local_execution_audit_tenant_tagged.py`
      **ampliado** con los siete actos de identidad etiquetados por partner y persona.
      Esta tarea es la ampliación de `test_27`. _Requisitos: 13.1, 13.2, 13.3_
      **HECHO.** `test_27` ampliado: los cuatro actos de una máquina emparejada por HTTP dejan asientos con `target = partner:<id>` y actor persona o `device:<id>`; la auditoría de B no ve ninguno.
- [x] T021 [P] **Licencias** — no entra ninguna dependencia. Tarea de verificación:
      `pnpm ls --depth 0` en `apps/desktop` y `apps/console`, y `uv lock --check` en
      `apps/api`, sin diferencias respecto a `develop`; si alguna tarea de este plan
      quiere añadir una, se detiene y declara el párrafo (§VIII). _Requisitos: —, §VIII_
      **HECHO.** `git diff develop --stat` sobre `package.json`, `pnpm-lock.yaml`, `pyproject.toml` y `uv.lock`: sin cambios. Electron 44 trae `BaseWindow`, `WebContentsView` y `safeStorage`.
- [x] T022 [P] **Medidor** — nada gasta. La puerta es la no-regresión de T011 (cero
      asientos) más una afirmación en `apps/desktop/tests/bar-state.test.ts`: ningún
      estado de la barra contiene una cifra de consumo, y `/usage` dentro de la ventana
      es la misma página que en el navegador (T066 lo recorre). _Requisitos: 8.2, 8.3, 9.1, 9.2_
      **HECHO.** `bar-state.test.ts` afirma que ninguna clave de estado contiene `usage|consumo|tokens|saldo`; T011 cubre el libro.
**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: User Story 1 — Entrar y reclamar mi máquina sin que nadie de Auphere intervenga (P1) 🎯

**Goal**: de «acabo de abrir la app» a `conectada` sin ningún paso fuera de la
ventana.

**Independent Test**: `quickstart.md` §1–§3 en una máquina limpia.

### Tests de la US1 ⚠️

- [x] T023 [P] [US1] `apps/api/tests/integration/test_device_pairing.py`: emitir código;
      canjear una vez → credencial, máquina a nombre de la persona y el partner del
      código; segunda vez → 404; caducado → 404; otro partner → 404; **mismo cuerpo** en
      los tres; 6.º fallo → 429 con `Retry-After`; cada denegación con su motivo real en
      auditoría; emitir otro código invalida el anterior. _Requisitos: 3.1, 3.2, 3.3, 3.4, 13.2_
      **HECHO.** 9 tests. Sorpresa útil: la cuenta atrás de intentos y la auditoría de denegaciones obligaron a que el canje abra **tres** transacciones cortas en vez de una — un `rollback` dentro de `session.begin()` no se puede.
- [x] T024 [P] [US1] `apps/desktop/tests/bar-state.test.ts`: los siete estados, sus
      transiciones según `contracts/desktop-bar.md`, ningún estado con tono `error`,
      herramientas locales **solo** en `conectada`, y el latido solo corre en
      `conectada`/`reconectando`. _Requisitos: 1.1, 1.3, 12.2, 12.3_
      **HECHO.** 13 tests: los siete estados, sus transiciones, tono `estado` en todos, herramientas solo en `conectada`, latido solo en `conectada`/`reconectando`, y sin cifrado no se ofrece emparejar.
- [x] T025 [P] [US1] `apps/desktop/tests/credential-store.test.ts` (con `safeStorage`
      doblado): nunca texto plano en disco (`eyJ` no aparece), mapa por `user_id`, sin
      cifrado disponible **no se escribe** y el estado lo dice, desemparejar borra la
      entrada. _Requisitos: 1.2, 14.2_
      **HECHO.** 6 tests con un cifrado doble que sí transforma los bytes: `eyJ` no aparece en disco, mapa por persona, sin cifrado no se escribe, corrupto = vacío.
- [x] T026 [P] [US1] `apps/desktop/tests/session-isolation.test.ts` **ampliado**: tres
      particiones distintas, la de la barra no persiste, la vista de la consola **no
      tiene `preload`**, y `assertPartitionsAreSeparate` falla si alguna se iguala.
      _Requisitos: 3.5, 14.1_
      **HECHO.** `BAR_PARTITION`, `consoleWebPreferences()` sin `preload`, `barWebPreferences(preload)`, `assertPartitionsAreSeparate` con tres particiones.
- [x] T027 [P] [US1] `apps/console/src/components/workstation/__tests__/pairing-dialog.test.tsx`:
      los cinco estados (cargando · vacío · error · parcial · ideal), el código en
      `XXXX-XXXX`, la cuenta atrás, y que **nunca** se vuelve a mostrar tras cerrar.
      _Requisitos: 3.1, 3.2_
      **HECHO.** 5 tests: generando, mostrado con cuenta atrás, caducado como estado, error con «pedir otro», y al cerrar no vuelve.
### Implementación de la US1

- [x] T028 [US1] `apps/api/src/nexus_api/services/device_pairing.py`: generación con
      `secrets.choice` sobre el alfabeto de 30 símbolos, normalización, hash, canje
      atómico, límite de intentos en Redis (5 → espera 60 s que se duplica hasta 15 min).
      _Requisitos: 3.1, 3.3, 3.4_
      **HECHO.** `core/pairing_codes.py` + `services/device_pairing.py` (`PairingRateLimiter` en Redis: 5 fallos → 60 s que se duplican hasta 15 min; un canje correcto limpia).
- [x] T029 [US1] `POST /device/pair` en `api/device_bridge.py` (sin credencial, con
      límite) y `POST /console/workstation/pairing-codes` en un router nuevo
      `api/console/workstation_partner.py` (`workstation:pair`). Esquemas en
      `schemas_workstation.py`. `test_console_scope` en verde. _Requisitos: 3.1, 3.2, 3.5, 3.6_
      **HECHO.** `POST /device/pair` y `POST /console/workstation/pairing-codes` en `api/console/workstation_partner.py` (`workstation_scope` fija los tres GUC). `test_console_scope` en verde (433) tras enseñarle `{device_id}`.
- [x] T030 [US1] `apps/desktop/src/electron/main.ts`: `BaseWindow` + dos vistas (D8), UA
      con sufijo `AuphereDesktop/<version>` en la partición humana, **sin
      `AUPHERE_DEVICE_TOKEN`** — la variable desaparece del código y de
      `infra/terraform` si estaba. `bar-preload.ts` con exactamente las seis funciones del
      contrato. _Requisitos: 1.1, 1.2, 12.1, 12.7_
      **HECHO.** `BaseWindow` + dos `WebContentsView`; UA `AuphereDesktop/<v>` en la partición humana; `setWindowOpenHandler` + `will-navigate` por `window-open-policy.ts`; `bar-preload.cjs` generado en el build (CommonJS, que es lo que un renderer con sandbox carga). `AUPHERE_DEVICE_TOKEN` desapareció del código.
- [x] T031 [US1] `apps/desktop/src/credential-store.ts` (`safeStorage`, por persona) y
      `apps/desktop/src/bar-state.ts` (la máquina de siete estados). _Requisitos: 1.2, 12.2, 14.2_
      **HECHO.** `credential-store.ts` (cifrado y fichero inyectados; `safeStorage` + `userData` en `electron/adapters.ts`) y `bar-state.ts`.
- [x] T032 [US1] `apps/desktop/src/http-transport.ts`: `pair(code, hostname, platform,
      version)`, `renew()`, `declareLink()`, `poll()` con `links`; mapa de rechazos →
      estado (`401`/`403 pairing_required` → `volver_a_emparejar`, `403 device_archived`
      → `archivada_desde_consola`). `AppRuntime` arranca el puente solo desde
      `conectada`. _Requisitos: 3.2, 10.1, 11.3, 12.3_
      **HECHO.** `pair`, `renew`, `declareLink`, `pollAll` con `links`, y `BridgeRejected` (401 · `device_archived` · `pairing_required`) distinto de `BridgeUnavailable`; 15 tests en `http-transport.test.ts`. `AppRuntime` arranca el puente solo desde la puerta de sesión o tras un canje.
- [x] T033 [US1] La barra (`apps/desktop/src/bar/`): 44 px, hoja expandible, estados
      del contrato con su copy, campo de código que acepta minúsculas y guion, propone el
      `hostname` como nombre; tokens de `@nexus/ui`; estética *terminal-bloomberg
      discreta* de D8; WCAG 2.2 AA (foco, objetivo ≥ 24 px, `prefers-reduced-motion`,
      `prefers-color-scheme`). _Requisitos: 1.1, 3.6, 12.1, 12.2, 12.4, 12.5, 12.6_
      **HECHO.** `src/bar/` sin dependencias (script clásico): siete estados con copy es/en, código en minúsculas y con guion, hoja de directorios, desemparejar con confirmación, foco visible, objetivos ≥ 24 px, `prefers-reduced-motion`, tokens copiados; `bar-tokens.test.ts` en verde.
- [x] T034 [US1] Consola: ruta `apps/console/src/app/(console)/workstation/page.tsx` a
      nivel de partner con la lista de máquinas (mías / todas con dueño para `write`),
      presencia y desde cuándo, y el diálogo de emparejar
      (`components/workstation/pairing-dialog.tsx`, `machines-list.tsx`); cliente
      `lib/backend/workstation.ts` con la API nueva; `nav.ts` con `/workstation`
      (`Laptop`, `workstation:read`); carril i18n `workstation.ts` con las cadenas
      nuevas en `es` y `en`. Cinco estados en cada componente. _Requisitos: 3.1, 3.2, 3.6, 5.2, 8.1_
      **HECHO.** `/workstation` (`page.tsx` + `actions.ts`), `machines-list.tsx`, `pairing-dialog.tsx`, `workstationPartnerApi` en `lib/backend/workstation.ts`, `/workstation` en `nav.ts` con `Laptop`, carril i18n `ws.*` es/en. `machines-list.test.tsx` cubre vacío (con y sin permiso), error parcial, ideal y archivadas plegadas.
- [x] T035 [US1] Borrar `apps/api/scripts/enrol_device_dev.py` y el endpoint
      `POST /console/clients/{ref}/workstation/devices` (el emparejamiento lo sustituye);
      `DELETE …/devices/{id}` y `GET …/devices` se mueven al router de partner. Actualizar
      `quickstart.md` de la 001 donde los nombraba. _Requisitos: 3.5, CE-002_
      **HECHO.** Script borrado; `POST /console/clients/{ref}/workstation/devices` retirado; el `GET` de cliente lista solo las máquinas **vinculadas a ese cliente** que la persona puede ver.
- [x] T046 [US1] `apps/console/src/app/api/session/whoami/route.ts` (mismo origen, cookie,
      sin cuerpo): 200 `{user_id, partner_slug}` · 401 anónimo · 403 `no_membership`.
      _Requisitos: 2.4, 11.1_
      Va en la US1 y no en la US4 porque la barra necesita distinguir «sin sesión» de
      «sin pertenencia» desde el primer día (2.4); la US4 lo reutiliza.
      **HECHO.** `app/api/session/whoami/route.ts`.
- [x] T066 [US1] **Entrar es entrar en la consola, y se prueba, no se hereda.**
      `apps/desktop/tests/session-gate.test.ts` (parte 1): `whoami` distingue
      `anonymous` (401) de `no-membership` (403) y la barra **no ofrece emparejar** en
      ninguno de los dos —solo `sin_sesion`—; la caducidad de la cookie se trata como
      cerrar sesión. `apps/desktop/tests/no-own-auth.test.ts`: ni `src/bar/` ni el
      `preload` contienen campo de contraseña, ruta de login ni registro — la
      aplicación **no tiene** flujo de autenticación propio. `quickstart.md` §2 recorre
      la invitación aceptada en el navegador y el login posterior en la app, con
      evidencia en `evidence/T066/`. `whoami` (T046) devuelve 403 `no_membership` para
      que la barra pueda distinguirlo. _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 1.1_
      **HECHO.** `no-own-auth.test.ts` (ni contraseña, ni login, ni registro en la barra ni en el preload; el preload expone las seis funciones), `session-gate.test.ts` (anónimo y sin pertenencia paran sin ofrecer emparejar), `whoami` 403 `no_membership`. Queda el §2 del quickstart con evidencia (T065).
**Checkpoint**: Historia 1 completa. Una persona entra, empareja y ve `conectada`
sin que nadie toque una base de datos.

---

## Phase 4: User Story 2 — Una máquina, todos mis clientes (P1)

**Goal**: un emparejamiento sirve a N clientes, cada uno con su directorio y su
lista, sin alcanzar los de otro.

**Independent Test**: `quickstart.md` §4.

### Tests de la US2 ⚠️

- [x] T036 [P] [US2] `apps/desktop/tests/directory-declare.test.ts`: las cuatro
      validaciones (existe · es directorio · resuelve dentro de sí · legible con el
      permiso del sistema) cada una con su mensaje; si falla una, **no se envía nada**; el
      selector nativo se dobla. _Requisitos: 7.1, 7.2, 7.3_
      **HECHO.** 9 tests: cada comprobación con su nombre, nada se envía si falla, cancelar no envía, y la firma de `declareDirectory` no admite una ruta.
- [x] T037 [P] [US2] `apps/api/tests/integration/test_device_links.py`: vincular desde la
      consola crea el vínculo sin directorio; declarar desde la máquina lo rellena con
      `checks`; un `client_ref` ajeno → 404 registrado; dos clientes en una máquina no
      comparten directorio; desvincular archiva. _Requisitos: 4.1, 7.2, 7.4, 8.1_
      **HECHO** dentro de `test_device_bridge.py` (vincular desde consola sin directorio, declarar desde la máquina con `checks`, sin vínculo previo 404) y `test_30` (ref ajeno 404 con asiento; dos clientes no comparten directorio por RLS).
- [x] T038 [P] [US2] `apps/console/src/components/workstation/__tests__/machine-clients.test.tsx`:
      elegir clientes, estado «falta el directorio», y la ausencia diseñada cuando no hay
      clientes que vincular. _Requisitos: 7.5, 8.1, 8.4_
      **HECHO.** `machine-clients.test.tsx`: 6 tests — vincular envía solo el ref (nunca una ruta), sin clientes no hay selector apagado, todos vinculados se dice, pendiente de declarar es estado, solo lectura sin controles.
### Implementación de la US2

- [x] T039 [US2] `POST/DELETE /console/workstation/devices/{id}/clients[/{ref}]` en
      `workstation_partner.py`: el tenant sale de `partner_tenants` bajo el partner de
      la sesión. _Requisitos: 4.1, 7.4_
      **HECHO.** `POST /devices/{id}/clients` y `DELETE /devices/{id}/clients/{ref}`: el ref se resuelve **antes** que la máquina para que el 404 sea el opaco de CP-04.
- [x] T040 [US2] `apps/desktop/src/directory-declare.ts`: `dialog.showOpenDialog`
      (`openDirectory`), las cuatro validaciones reutilizando `containment.ts`, y el
      envío por `declareLink`. La barra lista «falta el directorio de N clientes» desde
      `links[]` del sondeo y abre el selector por cliente. _Requisitos: 7.1, 7.2, 7.3, 7.5_
      **HECHO.** `directory-declare.ts` (puro) + `nativeDirectoryPicker`/`nodeDirectoryFs` en `electron/adapters.ts`; la barra lista «falta el directorio de N clientes» desde `links[]` y abre el selector por cliente.
- [x] T041 [US2] Consola: `components/workstation/machine-clients.tsx` (clientes por
      máquina, estado del directorio, «pendiente de declarar desde la máquina» como
      estado y no como campo). _Requisitos: 7.1, 8.1, 8.4_
      **HECHO.** `machine-clients.tsx`: clientes por máquina, «pendiente de declarar desde la máquina» como estado, selector solo con clientes disponibles.
- [x] T042 [US2] La página de cliente `clients/[ref]/workstation` conserva los
      ejecutables (de Auphere) y muestra las máquinas del partner **vinculadas a ese
      cliente**; el resto de la lista de máquinas se va de ahí. _Requisitos: 4.5, 8.1_
      **HECHO.** El `GET` de cliente lista las máquinas vinculadas a ese cliente con el directorio del vínculo (`workdir` nulo tolerado); el panel enlaza a `/workstation` («Gestionar máquinas») y el vacío explica que se empareja y se vincula desde ahí.
**Checkpoint**: Historia 2 completa. Una fila, una credencial, N vínculos.

---

## Phase 5: User Story 4 — Cerrar sesión, desemparejar, archivar (P1)

**Goal**: tres actos, tres consecuencias dichas, y el puente **para** en los
tres.

**Independent Test**: `quickstart.md` §5–§6.

### Tests de la US4 ⚠️

- [x] T043 [P] [US4] `apps/desktop/tests/session-gate.test.ts`: `whoami` sin sesión →
      `sin_sesion` y latido parado; misma persona → arranca sin código; otra persona →
      `pairedByOther` y oferta; el cambio de cookie dispara la relectura; la caducidad
      de 7 días se comporta como cerrar sesión. _Requisitos: 2.2, 11.1_
      **HECHO.** 8 tests en `session-gate.test.ts`, más `app-runtime-identity.test.ts` (parar conserva la credencial; misma persona arranca sin código).
- [x] T044 [P] [US4] `apps/console/src/app/api/session/__tests__/whoami.test.ts`: con
      cookie válida devuelve `{user_id, partner_slug}`; sin cookie 401; **no** devuelve
      nada más. _Requisitos: 11.1, 14.1_
      **HECHO.** `whoami.test.ts`: 200 con `user_id` y `partner_slug` **y nada más**, 401 anónimo, 403 `no_membership` para sin pertenencia/suspendida/deshabilitada; `cache-control: no-store`.
- [x] T045 [P] [US4] `apps/api/tests/integration/test_device_bridge.py` **ampliado**:
      desemparejar archiva con `desemparejada`; archivar desde la consola →
      `archivada_consola` y el siguiente latido recibe `403 device_archived`; una
      máquina archivada no se vuelve a emparejar (se empareja otra). _Requisitos: 11.2, 11.3, 11.5_
      **HECHO** en `test_device_bridge.py`: archivar desde la consola → `403 device_archived` con motivo; archivada no se renombra; pertenencia retirada archiva; dos personas, un hostname.
### Implementación de la US4

- [x] T047 [US4] `apps/desktop/src/session-gate.ts`: `session.fromPartition(HUMAN).fetch`
      a `whoami` al arrancar y en `cookies.on('changed')` filtrado a
      `nexus-console.session`; decide arrancar / parar / `pairedByOther`.
      `AppRuntime.stop()` detiene el latido sin olvidar la credencial. _Requisitos: 2.2, 11.1_
      **HECHO.** `session-gate.ts` + `consoleWhoami`/`sessionCookieWatcher` en `electron/adapters.ts` (`session.fromPartition(HUMAN).fetch` y `cookies.on('changed')` filtrado a `nexus-console.session`). `AppRuntime.applyGate` arranca/para/ofrece emparejar; `stop()` no olvida la credencial.
- [x] T048 [US4] Desemparejar desde la barra: `unpair()` **olvida la credencial de
      forma irrecuperable** (borra la entrada del almacén y sobrescribe el fichero),
      detiene el latido, y la barra pasa a `sin_emparejar` diciendo que la máquina queda
      pendiente de archivar desde la consola. **No** hay sexta operación de la
      credencial: archivar es un acto de persona (R13.1) y se hace en `/workstation`.
      Ver la nota al final de este fichero y la enmienda de R11.2. _Requisitos: 11.2, 11.5_
      **HECHO.** `AppRuntime.unpair()` olvida la credencial, para el latido y la barra dice «archívala desde la consola si no vas a volver».
- [x] T049 [US4] Consola: «Archivar» en `machines-list.tsx` con confirmación y motivo;
      la máquina archivada se muestra con persona y fecha; `DELETE
      /console/workstation/devices/{id}` con `revoked_reason='archivada_consola'`.
      _Requisitos: 11.3, 11.5, 13.1_
      **HECHO.** «Archivar» con confirmación que dice que archiva, no borra; `DELETE /console/workstation/devices/{id}` con `archivada_consola`; las archivadas se pliegan con su motivo y fecha.
**Checkpoint**: MVP completo (US1 + US2 + US4). Se puede entregar.

---

## Phase 6: User Story 3 — La consola me lleva de la mano (P2)

**Goal**: cuatro pasos, calculados en cada visita, que desaparecen al completarse.

**Independent Test**: `quickstart.md` §3 con una persona ajena; CE-007.

### Tests de la US3 ⚠️

- [x] T050 [P] [US3] `apps/api/tests/integration/test_workstation_setup.py`: los cuatro
      pasos por persona; cada uno pasa a verde con el hecho correspondiente; sin
      `workstation:pair` → 403; nada se persiste. _Requisitos: 6.1, 6.2, 6.5, 6.6_
      **HECHO.** 4 tests: cuatro pendientes sin nada, cada hecho pone su paso en verde, los pasos son por persona (la máquina de la owner no cuenta para la builder), sin `workstation:pair` 403.
- [x] T051 [P] [US3] `apps/console/src/components/home/__tests__/workstation-setup-card.test.tsx`:
      se cierra y no bloquea; con pasos pendientes reaparece al montar de nuevo; con
      los cuatro en verde **no se renderiza** y no hay control para verla; el paso de
      ejecutables muestra «Pedirla» y ningún control de añadir. _Requisitos: 6.1, 6.3, 6.4, 6.6_
      **HECHO.** `setup-card.test.tsx`: progreso, pendientes contados, cerrar no persiste nada, completa no se renderiza, ejecutables se piden.
### Implementación de la US3

- [x] T052 [US3] `GET /console/workstation/setup` en `workstation_partner.py`, derivado
      (D10). _Requisitos: 6.1, 6.2, 6.5_
      **HECHO.** `GET /console/workstation/setup` derivado por persona (T050, su test, sigue pendiente).
- [x] T053 [US3] `components/home/workstation-setup-card.tsx` montada en
      `app/(console)/page.tsx` y en `/workstation`; el paso 4 enlaza a los ejecutables del
      cliente con «Pedirla». Copy que **continúa** el paso 3 del onboarding del diseño.
      _Requisitos: 6.1, 6.3, 6.4, 6.6_
      **HECHO.** `workstation-setup-card.tsx` (cliente) + `workstation-setup.tsx` (servidor, solo con `workstation:pair`), montada en la home y en `/workstation`.
**Checkpoint**: Historia 3 completa.

---

## Phase 7: User Story 5 — La misma máquina, dos personas (P2)

**Goal**: un emparejamiento por persona; nadie ve lo de nadie.

**Independent Test**: `quickstart.md` §6, segundo bloque.

### Tests de la US5 ⚠️

- [x] T054 [P] [US5] En `test_30` (T006) ya está la RLS dueña/gestor. Aquí,
      `apps/api/tests/integration/test_device_bridge.py`: dos máquinas con el mismo
      `hostname` y dueños distintos conviven; el listado de la builder no ve la del
      owner; el del owner (gestor) ve las dos con dueño. _Requisitos: 5.1, 5.2_
      **HECHO** en `test_device_bridge.py::test_two_people_can_pair_the_same_hostname`: la builder ve la suya, la owner las dos con dueña.
- [x] T055 [P] [US5] `apps/desktop/tests/session-gate.test.ts` **ampliado**: con dos
      entradas en el almacén, cada persona arranca la suya; `pairedByOther` no revela el
      nombre de la otra. _Requisitos: 5.1, 5.3_
      **HECHO** en `session-gate.test.ts` («otra persona… sin revelar a Luis») y `app-runtime-identity.test.ts`.
- [x] T056 [P] [US5] `apps/desktop/tests/approvals-client.test.ts` **ampliado**: las
      aprobaciones pendientes se piden **con la identidad de la persona con sesión**,
      nunca con la del dueño de otra credencial. _Requisitos: 5.3_
      **HECHO.** `pendingApprovals`/`answerApproval` se rechazan con `ApprovalsNotForThisPerson` cuando el puente no corre para la persona con sesión — no se devuelve `[]`, que diría «nada que aprobar» (§V). 3 tests.
### Implementación de la US5

- [x] T057 [US5] `credential-store.ts` multi-persona y `session-gate.ts` eligiendo la
      entrada por `user_id`; la barra con el estado «emparejada por otra persona».
      _Requisitos: 5.1, 5.3_
      **HECHO.** Almacén por `user_id`; `applyGate` elige la entrada de quien tiene la sesión; `pairedByOther` sin nombre.
- [x] T058 [US5] `GatewayApprovals` acotado por persona: la cola que contesta la app es la
      de los hilos de quien tiene la sesión. Si el gateway no puede acotar, la app
      **no contesta** y lo dice (§V), en vez de contestar por otro. _Requisitos: 5.3_
      **HECHO** en el runtime (T056): si no hay persona dueña con sesión, la app no contesta y lo dice.
**Checkpoint**: las cinco historias completas.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T059 [P] `apps/console/src/lib/shell.ts` (`isDesktopShell()` por UA) usado
      **solo** en el componente de conectar canales de Meta, que en la cáscara pinta
      «Continúa en el navegador» con el enlace; test `shell-detect.test.ts` que afirma
      una única importación. _Requisitos: 12.7_
      **HECHO.** `lib/shell-ua.ts` (puro) + `lib/shell.ts` (`headers()`); la página de canales bifurca a `WhatsAppContinueInBrowser`; `shell-detect.test.ts` afirma **una** importación.
- [x] T060 [P] Los `target="_blank"` y `window.open` de la consola dentro de la cáscara:
      `setWindowOpenHandler` en la vista de la consola que abre en el navegador del
      sistema **solo** URLs del origen de la consola o `https:`; nunca una ventana de la
      aplicación sin barra de direcciones. Test en `apps/desktop/tests/window-open.test.ts`.
      _Requisitos: 12.7, 14.1_
      **HECHO.** `window-open-policy.ts` (https y el origen de la consola → navegador del sistema; el resto se deniega) + `will-navigate` acotado al origen; 5 tests.
- [x] T061 [P] Auditorías del workspace sobre la barra y `/workstation`:
      `ui-states-checklist` → `a11y-audit` → `responsive-audit` → `design-tokens`.
      Cero 🔴. Evidencia en `evidence/T061/`. _Requisitos: 12.4, 12.5, 12.6_
      **HECHO (estático; el pase vivo queda con T065).** `a11y-audit`: sin 🔴 — se corrigieron la región viva (solo el texto de estado, no la barra entera), `lang` por idioma detectado, `title` en los truncados y nombres accesibles con contexto en «Renombrar/Archivar/Quitar»; **8/10**, sube a 9 con un pase de VoiceOver sobre el diálogo de emparejar. `design-tokens`: cero hex/rgb/inline/paleta por defecto; `13px→14px`, `10px→12px`, `tracking-[0.2em]→tracking-widest`; los diez `var()` de la barra existen en `tokens.css`; **9/10**. `ui-states-checklist`: los siete estados de la barra y los cinco de Hurff en las cuatro vistas; se añadió `loading.tsx` de `/workstation` y el diálogo de renombrar conserva lo escrito en error; **8/10**. `responsive-audit`: `min-w-0` + `truncate` con `title`, `break-all` en hostname y URL, `flex-wrap` en la barra y las tarjetas; **8/10** (pase vivo a 360/768/1440 pendiente con T065).
- [x] T062 [P] Spec viva: `specs/001-puesto-trabajo-partner/contracts/device-bridge.md`
      ya lleva la nota de sustitución; añadir en `docs/` un `docs/desktop-workstation.md`
      que describa lo que existe (barra, emparejamiento, cinco operaciones, estados) —
      es el primer documento vivo del escritorio, y el que cambia en el mismo commit que
      lo que describe. _Requisitos: §Spec viva_
      **HECHO.** `docs/desktop-workstation.md`: la cáscara y sus tres particiones, cómo entra una persona, el emparejamiento, las cinco operaciones, quién ve qué, los tres actos, los siete estados, la única bifurcación y el desarrollo local. Cambia en el mismo commit que lo que describe.
- [x] T063 [P] Enlace de vuelta desde la KB: `[[14-mvp-y-fases]]` §3 apunta a
      `specs/002-identidad-app-escritorio/`; `[[10-decisiones]]` §2.3 ya apunta.
      _Requisitos: §IX_
      **HECHO.** `[[14-mvp-y-fases]]` §3 abre con el enlace a `specs/002-identidad-app-escritorio/`, a la evaluación y a la spec viva; `[[10-decisiones]]` §2.3 ya apuntaba.
- [x] T064 Cerrar el expediente de bug `task_e4dabc39` por referencia: la revocación
      la cubre `test_30` y `require_device` de T017. Si el bug aterrizó antes, rebasar y
      quedarse con **una** implementación. _Requisitos: 11.3, 11.6_
      **HECHO por referencia.** `require_device` (T017) carga la fila y una máquina archivada recibe `403 device_archived` en las cinco operaciones — `test_30` y `test_device_bridge` lo cubren. El expediente `task_e4dabc39` se retiró con ese motivo; no hay dos implementaciones.
- [x] T065 Ejecutar la validación completa de `quickstart.md` en una máquina limpia,
      con una persona ajena al equipo para §3 (CE-007), y dejar la evidencia en
      `evidence/T065/`. _Requisitos: CE-001 … CE-011_
      **EN CURSO — lo automatizable está en verde; el recorrido con persona queda
      con Luis.** Entorno local preparado: partner `demo` con dos clientes
      (`cultor`, `retail-sur`), invitación de owner emitida para
      `contacto@ladrian.dev`, API y consola locales sirviendo las rutas nuevas, y la
      aplicación de escritorio abierta contra `http://localhost:3110`. Lo que falta es
      lo que **no me corresponde hacer**: aceptar la invitación y entrar (contraseña),
      y conducir la ventana de la app —el acceso de control se denegó—. Los pasos y la
      evidencia esperada están en `quickstart.md` §1–§8.
      **HECHO (2026-09-10).** Luis recorrió el flujo de punta a punta en su máquina:
      invitación aceptada en el navegador, login dentro de la app, código pedido en
      `/workstation`, tecleado en la barra → `Adrians-MacBook-Pro.local · connected`
      (captura aportada). Dos fallos reales salieron del recorrido y quedaron
      corregidos con test: `bar.js` compilaba con un `export {}` que rompía el script
      clásico, y los tokens semánticos de `@nexus/ui` viven en `@theme { … }` —solo
      Tailwind lo entiende—, así que la copia los pasa a `:root` y la barra consume el
      puente de tema. Las dos asperezas que salieron —la barra hablaba el idioma del sistema
      y no el de la cuenta, y `/workstation` no refrescaba sola la presencia— quedaron
      cerradas el mismo día: `whoami` devuelve `locale` y la barra lo adopta;
      `PresenceRefresh` refresca con la cadencia del latido mientras la pestaña está
      visible. Tests en `session-gate`, `app-runtime-identity` y `presence-refresh`.
---

## Nota sobre T048 — una enmienda que el plan devolvió a la spec

Al bajar al detalle, «desemparejar desde la barra» (R11.2) tenía dos formas:
una sexta operación de la credencial (`/device/unpair`) o que la barra olvide la
credencial y la persona archive desde la consola. **Se elige la segunda**: la
credencial autoriza cinco operaciones y ninguna más (R4.2), y un archivado es un
acto de persona que debe quedar con su nombre (R13.1). R11.2 se enmienda para
decir: *«la aplicación DEBE olvidar su credencial de forma irrecuperable y decir
que la máquina queda pendiente de archivar desde la consola; la plataforma la
muestra `ausente` hasta que una persona la archive o la pertenencia se retire»*.
`contracts/desktop-bar.md` cambia en el mismo sentido. Se anota aquí porque
`/speckit-analyze` tiene que verlo.

---

## Dependencies & Execution Order

### Orden de fases

- **Phase 0** (T001) → **Phase 1** (T002–T005, en paralelo) → **Phase 2** (tests
  T006–T011 en paralelo → T012 → T013 → T014 → T015 → T016 → T017 → T018, T019) →
  **Phase 2b** (T020–T022) → US1 → US2 → US4 → US3 → US5 → Polish.
- **US1** necesita toda la Phase 2 (la máquina ya es del partner).
- **US2** necesita US1 (una máquina emparejada) y T018 (presencia por vínculos).
- **US4** necesita US1 (algo que parar, y `whoami` de T046) y T019 (pertenencia retirada).
- **US3** necesita US1, US2 (los pasos existen) — puede ir en paralelo con US4.
- **US5** necesita US1 y US4 (`session-gate`).

### Paralelismo

- Phase 1 entera en paralelo. Los seis tests de la Phase 2 en paralelo, **antes**
  de T012. Dentro de cada historia, todos sus tests en paralelo; consola y
  escritorio en paralelo una vez la API de esa historia está (T029 + T046 / T039 / T047 /
  T052).

---

## Implementation Strategy

### MVP — US1 + US2 + US4

Emparejar sin poder apagar no es entregable, y emparejar por cliente tampoco. El
MVP son las tres P1 juntas; US3 y US5 se añaden sin romper nada.

### Entrega incremental

1. Phase 0–2b → la máquina es del partner, el puente v2 funciona con el script
   sustituido por el canje (aún sin pantalla).
2. + US1 → se puede emparejar desde la ventana. Demo.
3. + US2 → una máquina, N clientes, directorios nativos. Demo.
4. + US4 → se puede apagar desde tres sitios. **Entregable.**
5. + US3, US5 → guía y máquina compartida.

---

## Cobertura por capacidad

| Requisito | Qué se puede hacer que antes no | Test que lo vio en rojo | Tarea que lo construye |
|---|---|---|---|
| 1.1–1.3 | Abrir sin emparejar y saberlo; nada en disco | T024, T025 | T030, T031, T033 |
| 2.1–2.5 | Entrar por la consola; caducidad como estado; invitación en navegador; sin acceso sin barra; sin registro | T066 (`whoami` anonymous/no-membership, sin flujo propio, §2 del quickstart), T043 (2.2) | T030, T046, T047 |
| 3.1–3.6 | Emitir y canjear un código; nombre propuesto | T023, T027 | T028, T029, T033, T034 |
| 4.1–4.6 | Máquina del partner, N clientes, una credencial, cinco operaciones, tests de aislamiento | T006, T007, T008, T037 | T012–T017, T039 |
| 5.1–5.4 | Dueño leído por RLS; gestor ve todas; aprobaciones por persona | T006, T054, T055, T056 | T012, T014, T015, T057, T058 |
| 6.1–6.6 | Cuatro pasos derivados, cerrables, que desaparecen; «Pedirla» | T050, T051 | T052, T053 |
| 7.1–7.5 | Directorio con selector nativo, cuatro validaciones, por cliente y máquina; sin directorio no hay herramientas | T036, T037, T018 | T040, T041, T018 |
| 8.1–8.4 | Ver máquinas, clientes, directorios, ejecutables; barra sin cifras; `/usage` igual que en el navegador; ausencia diseñada | T038, T022 (8.2, 8.3), T066 | T034, T041, T042 |
| 9.1–9.2 | (no-regresión) un solo contador | T011, T022 | — |
| 10.1–10.4 | Renovación sola, 30 días, gracia, asiento de máquina | T009 | T016, T017, T032 |
| 11.1–11.6 | Cerrar sesión para; olvidar credencial; archivar desde consola para en < 1 min; pertenencia retirada; terminal; dependencia del bug cerrada | T043, T044, T045, T006 (revocada → 403) | T046, T047, T048, T049, T019, T064 |
| 12.1–12.7 | Una sola superficie, siete estados, AA, tokens, sin fg-subtle, Meta en navegador | T024, T005, T061, T059 | T033, T059, T060 |
| 13.1–13.3 | Siete actos auditados con persona o máquina; denegaciones con motivo real | T020, T023, T009 | T003, T017, T028 |
| 14.1–14.3 | Nada se relaja: particiones, cifrado, saliente | T026, T025, T010 | T030, T031, T017 |

Ningún requisito aparece **solo citado**. Si `/speckit-analyze` encuentra uno,
la tabla está mal y se corrige antes de implementar.
