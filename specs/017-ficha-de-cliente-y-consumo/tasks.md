# Tasks: la ficha de cliente y el consumo, por flujo

**Input**: Design documents from `/specs/017-ficha-de-cliente-y-consumo/`

**Prerequisites**: plan.md, spec.md (Clarificada), research.md, data-model.md, contracts/, parity.md, quickstart.md

**Tests**: NO son opcionales en este repo (constitución §VII): cada bloque de tests se escribe primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por **iteración** (una pantalla por iteración, en el orden del plan), y dentro de cada iteración por historia. US1 = Historia 1 (ficha) · US2 = Historia 2 (publicar desde cualquier sitio) · US3 = Historia 3 (Integraciones + Capacidades) · US4 = Historia 4 (Consumo) · US5 = Historia 5 (alta) · US6 = Historia 6 (portada y lista) · US7 = Historia 7 (Ajustes del agente) · US8 = Historia 8 (lenguaje y ayuda). R12 (nada desaparece, prototipo aprobado) es el ritual de cierre de **cada** iteración y aparece en cada una.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: commit/PR, fusionado YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con una tarea por garantía (T-ISO); **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada nuevo, la equivalencia es lectura (T-MET).
- **Cada iteración cierra igual** (R12): prototipo aprobado → tests rojos → código → suites en verde → paridad completa → evidencia → log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Monorepo: API en `apps/api/src/nexus_api/`, migraciones en `apps/api/alembic/versions/`, tests en `apps/api/tests/{unit,integration,isolation}/`; DS en `packages/ui/src/{components,stories}/` con tests en `packages/ui/src/components/__tests__/`; consola en `apps/console/src/` con tests junto al código (`__tests__/`) y e2e en `apps/console/e2e/`; KB en `/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: lo que todas las iteraciones comparten y no cambia comportamiento.

- [X] T001 Crear la migración de datos `apps/api/alembic/versions/0129_console_audit_vocab_017.py` (siguiendo `0128_console_audit_vocab_016.py`) con las acciones `console.capability.update`, `console.billing.email_update` y sus plantillas ES/EN, y con la etiqueta ES/EN de cada categoría existente del vocabulario. Test primero: `apps/api/tests/unit/test_console_audit_vocab_017.py` (toda acción `console.*` escrita en `api/console/**` está sembrada; cada categoría tiene etiqueta en los dos idiomas). _Requisitos: 5.4, 11.5, 12.1_ Entregado: rama 017, 2026-09-24 (0129 + test; etiquetas de categoría en `audit.CATEGORY_LABELS`, no en la tabla).
- [ ] T002 [P] Añadir a `apps/console/src/i18n/lanes/{clients,capabilities,usage,glossary}.ts` (crear `capabilities.ts` y `glossary.ts`) las claves con ES y EN, **cada una en la iteración que la usa** (una clave sin consumidor es huérfana): `clients.setup.*` (agente, canal, cupo, activo, next.*), `clients.quota.*`, `clients.nav.group.{configure,connect,observe}`, `clients.more.*`, `draft.bar.*`, `draft.diff.*`, `capabilities.*` (función, sector, recomendadas, verTodas, sinSector, necesita, técnico), `usage.balance.*`, `usage.split.*`, `usage.equivalence.*`, `wizard.sector.*`, `home.start.*`, `agentSettings.summary.*`, `glossary.*`, `audit.category.*`. Los tests `apps/console/src/i18n/__tests__/messages.test.ts` (paridad ES/EN) y el de claves huérfanas fijan que ninguna sobre. _Requisitos: 1.1, 2.1, 3.1, 5.1, 6.2, 7.2, 8.1, 10.1, 11.1_
- [X] T003 [P] Crear `specs/017-ficha-de-cliente-y-consumo/evidence/README.md` (una entrada por iteración: prototipo, aprobación del owner con fecha, capturas, suites, paridad) y la carpeta `packages/ui/src/stories/prototypes/` con un `README.md` que explique que cada prototipo es una story con los bloques del DS y copy real en español, revisada con el addon a11y. _Requisitos: 12.4_ Entregado: rama 017, 2026-09-24.
- [X] T004 [P] T-LIC · Añadir a `scripts/verify.sh` (o a un test de CI existente) la comprobación de que `pnpm-lock.yaml` y `uv.lock` no cambian en la rama 017 respecto a `develop`; documentar en `plan.md` §Puertas. _Requisitos: 12.2_ Entregado: rama 017, 2026-09-24 (`scripts/verify.sh locks`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: las lecturas derivadas que usan la ficha, la lista y la portada, y la barrida de aislamiento que cubre todo endpoint nuevo.

- [X] T005 Test primero en `apps/api/tests/integration/test_console_client_setup.py`: `GET /console/clients/{ref}` devuelve `sector` (de `seed_template_ref` de la activa, o del borrador si no hay activa; `null` sin plantilla), `setup` con los cuatro booleanos y `next` en el orden agente → canal → cupo → activación (`null` cuando todo está), y `quota` `{cap, remaining}` o `null` sin tope; el canal cuenta solo con `customer_facing_channel()` (un canal `web/qa_playground` no cuenta). _Requisitos: 1.1, 1.2, 1.3, 5.2_ Entregado: rama 017, 2026-09-24.
- [X] T006 Implementar `sector_of(cfg)` y `client_setup(session, tenant, quota_state)` en `apps/api/src/nexus_api/api/console/deps.py` (reutilizando `client_health`), y exponer `sector`, `setup`, `quota` en `ClientOut` (`schemas.py`) desde `tenants.py::_detail`. _Requisitos: 1.1, 1.2, 1.3_ Entregado: rama 017, 2026-09-24 (`client_sector`, `client_setup_detail`, `active_customer_channel`; `ClientSetupDetailOut`, `ClientQuotaOut`).
- [X] T007 Test primero en `apps/api/tests/integration/test_console_client_setup.py` (lista): `GET /console/clients` devuelve por fila `setup` (sin `next`), `quota` y `conversations_7d`, calculados con **tres consultas agrupadas por página** (contador de consultas con `sqlalchemy` events en el test) y nunca por fila. _Requisitos: 9.1_ Entregado: rama 017, 2026-09-24 (una lectura por página: ledger en una consulta + `tenant_snapshots` a 7 días; no hay política de reporting para canales ni conversaciones, así que es un statement acotado por tenant, nunca una llamada HTTP por fila).
- [X] T008 Implementar en `tenants.py::list_clients` las tres lecturas en bloque (`quota_state` ya en lote; canales activos de cliente final por tenant; versiones activas por tenant; `conversations.started_at >= now() - 7d` agrupado) y los campos en `ClientSummaryOut`. _Requisitos: 9.1_ Entregado: rama 017, 2026-09-24 (`allocations_for`, `active_channels` en el snapshot).
- [ ] T009 T-ISO (el caso de la lista está en `test_console_client_setup.py`; los endpoints entran en la barrida a medida que existen) · Añadir a `apps/api/tests/isolation/test_console_scope.py` los endpoints nuevos de esta spec (`GET/PUT …/capabilities`, `GET …/agent/draft-diff`, `PUT /console/billing/email`, `GET /console/audit?category=`) a la barrida de 404 opaco con cliente de otro partner, y un caso nuevo: la lista de clientes de un partner nunca contiene `setup`/`quota`/`conversations_7d` de un tenant de otro partner. _Requisitos: 12.2_
- [X] T010 [P] Tipos en `apps/console/src/lib/backend/clients.ts` (o `index.ts`): `ClientSetup`, `ClientQuota`, `sector`, `conversations_7d`; test de tipos en `apps/console/src/lib/__tests__/backend-types.test.ts` si existe el patrón, o `pnpm typecheck` como criterio. _Requisitos: 1.1, 9.1_ Entregado: rama 017, 2026-09-24 (`ClientSetup`, `ClientSetupDetail`, `ClientQuota`, `sector` en `lib/backend.ts`).

---

## Iteración 1 · Ficha del cliente (US1 + US2) 🎯 MVP

**Goal**: la cabecera dice qué falta y lo resuelve; tres grupos por rol; el borrador se ve y se publica desde cualquier pestaña.

**Independent Test**: quickstart §Iteración 1 con cuatro roles; e2e `record.spec.ts`; paridad it. 1 al 100 %.

### Prototipo (R12.4)

- [X] T011 [US1] Story `packages/ui/src/stories/prototypes/client-record.stories.tsx` con la cabecera (nombre, estado, teléfono, cuatro puntos de puesta en marcha con botón del primer pendiente, `Meter` del cupo, menú «Más»), `NavTabs` con los tres grupos, `DraftBar` y la hoja «Ver diferencias», en los estados: falta canal · atendiendo · sin tope · analyst (solo lectura) · archivado · móvil 375 px. Addon a11y en verde. **Aprobación del owner** anotada en `evidence/iteracion-1.md`. _Requisitos: 12.4_ Entregado: rama 017, aprobado por el owner 2026-09-25 (doce estados, ocho pasadas, crítica medida en dos agentes aislados).

### Bloques del DS (test primero)

- [X] T012 [P] [US1] Tests `packages/ui/src/components/__tests__/nav-tabs.test.tsx`: grupos con nombre, `aria-current="page"` en uno solo, `renderLink` para el router, modo compacto (`NativeSelect` con `optgroup`) por debajo del breakpoint, grupo vacío no se pinta. _Requisitos: 2.1, 2.2, 2.3, 2.4_ Entregado: rama 017, 2026-09-25 (6 casos; la marca por pestaña se anuncia con `aria-label`, no con texto).
- [X] T013 [US1] Implementar `packages/ui/src/components/nav-tabs.tsx` (`NavTabs {groups, current, renderLink?, compact?, ariaLabel}`) sobre `Section`/tokens, exportarlo en `src/index.ts`, story en `src/stories/building-blocks.stories.tsx`. _Requisitos: 2.1, 2.3, 2.4_ Entregado: rama 017, 2026-09-25 (`marks`/`markSuffix` para el punto de borrador o incidencia; el `ul` envuelve).
- [X] T014 [P] [US2] Tests `packages/ui/src/components/__tests__/draft-bar.test.tsx`: nombra las pantallas con cambios, «Ver diferencias» y «Publicar» como acciones, variante sin permiso (frase + quién puede, sin botón), pegada abajo en móvil (`data-placement`), `role="status"`. _Requisitos: 3.1, 3.4_ Entregado: rama 017, 2026-09-25 (7 casos; dos regiones vivas fijas —`status` y `alert`— en vez de intercambiar el rol, que es lo que midió la crítica del prototipo).
- [X] T015 [US2] Implementar `packages/ui/src/components/draft-bar.tsx` (`DraftBar {screens, canPublish, whoCanPublish, onDiff, onPublish, labels}`), exportar, story. _Requisitos: 3.1, 3.4_ Entregado: rama 017, 2026-09-25 (`whoCanPublish` va dentro de `labels`; además `state` pending/publishing/failed y `failure`).

### API (test primero)

- [X] T016 [P] [US2] Test primero `apps/api/tests/integration/test_console_draft_diff.py`: `GET …/agent` devuelve `draft_screens` (`[]` sin borrador; `["settings"]` tras cambiar el horario; `["settings","capabilities"]` tras activar una herramienta); `GET …/agent/draft-diff` devuelve `settings` con `{field, before, after}`, `capabilities`, `knowledge`, `prompt`; 404 `no_draft` sin borrador; `agents:read` basta para leer. _Requisitos: 3.1, 3.2_ Entregado: rama 017, 2026-09-25 (6 casos; `knowledge` es `[]`: los documentos no se versionan con el agente, la clave existe para que la consola no ramifique).
- [X] T017 [US2] Implementar `draft_screens` y `draft_diff()` en `apps/api/src/nexus_api/api/console/agent_drafts.py` (comparar `policies` campo a campo con claves estables, `tools`/`runtime_skills`/`tool_modes`, documentos de conocimiento, `system_prompt_rendered`), endpoint en `agents.py`, `DraftDiffOut` en `schemas.py`. _Requisitos: 3.1, 3.2_ Entregado: rama 017, 2026-09-25 (`draft_screens`/`draft_diff` en `agent_drafts.py`; herramientas y habilidades comparten la pregunta «¿qué sabe hacer?»; `tool_modes` no existe todavía, entra en la iteración 2).
- [X] T018 [P] [US2] Test primero en `apps/api/tests/integration/test_endpoint_console_agents.py`: publicar con `{"from": "draft_bar"}` deja `after_json.from = "draft_bar"` en `console.agent.publish`; sin el campo, `"agent_tab"`. _Requisitos: 3.3_ Entregado: rama 017, 2026-09-25 (3 casos, incluido un origen desconocido → 422).
- [X] T019 [US2] Aceptar `from` opcional en `POST …/versions/{version}/publish` (`agents.py`) y escribirlo en la auditoría. _Requisitos: 3.3_ Entregado: rama 017, 2026-09-25 (`AgentPublishIn` con alias `from`; el origen viaja a `promote(origin=…)` y acaba en `after_json`; la acción es `agent_config.promote`, que es la que el servicio ya escribía, no una nueva).

### Consola (test primero)

- [X] T020 [P] [US1] Tests `apps/console/src/components/clients/__tests__/client-header.test.tsx`: cuatro puntos con nombre; botón del primer pendiente con `href` correcto («Preparar el agente» → `/agent`, «Conectar un canal» → `/channels`, «Asignar cupo» abre diálogo, «Activar» abre confirmación); sin botón cuando el rol no puede; «Atendiendo desde …» sin botón; cupo como `Meter` o «Sin tope…»; «Más» solo con `clients:write`; Eliminar solo archivado. _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_ Entregado: rama 017, 2026-09-25 (8 casos sobre `client-header-model`, puro; «Asignar crédito» lleva a `/usage`, que es la pantalla que lo asigna hoy — asignarlo sin salir de la ficha es de la iteración 3).
- [X] T021 [US1] Implementar `apps/console/src/components/clients/client-header.tsx` (+ `setup-steps.tsx`, `quota-meter.tsx`, `more-menu.tsx` sobre `DropdownMenu` y `ClientLifecycleActions` existente) y usarlo en `apps/console/src/app/(console)/clients/[ref]/layout.tsx`; la referencia y la zona horaria salen de la cabecera. _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_ Entregado: rama 017, 2026-09-26. Los pasos con su estado, el botón único del pendiente con su porqué, la frase de quién puede cuando el rol no, el crédito como `Meter` o «Sin crédito asignado», y el menú «Más» en la cabecera — un solo control en el mismo sitio para todos los roles, con `moreMenuItems()` decidiendo qué hay dentro (4 casos) y las dos confirmaciones compartidas con la fila de botones de siempre, que no desaparece. Verificado en el stack local.
- [X] T022 [P] [US1] Tests `apps/console/src/components/clients/__tests__/client-nav.test.tsx`: grupos y pestañas por rol (owner: todo; builder: sin nada oculto de escritura salvo lo que `can()` diga; analyst: sin Playground; billing: no llega); `aria-current` en la actual; raíz = Resumen sin redirección visible. _Requisitos: 2.1, 2.2, 2.4, 2.5_ Entregado: rama 017, 2026-09-25 (8 casos sobre `client-nav-model`, puro: qué ve cada rol es una decisión y se prueba sin montar React).
- [X] T023 [US1] Reescribir `apps/console/src/components/clients/client-tabs.tsx` como `client-nav.tsx` sobre `NavTabs` con el mapa `PERMISSIONS`; quitar el `redirect` de `clients/[ref]/page.tsx` si lo hay; en la iteración 1 la pestaña «Capacidades» del grupo Configurar enlaza a `/tools` (la pantalla actual) e «Integraciones» a `/tools#integraciones`; las rutas `/capabilities` e `/integrations` y las redirecciones desde `/tools` y `/skills` se crean en la iteración 2 (T037). _Requisitos: 2.1, 2.2, 2.5, 12.5_ Entregado: rama 017, 2026-09-25 (`client-nav.tsx` sobre `NavTabs`; `client-tabs.tsx` queda sustituido y se retira; «Capacidades» → `/tools` e «Integraciones» → `/tools#integraciones` hasta T037).
- [X] T024 [P] [US2] Tests `apps/console/src/components/clients/__tests__/draft-bar-client.test.tsx` y `draft-diff-sheet.test.tsx`: la barra aparece con `draft_screens` no vacío en cualquier pestaña; «Ver diferencias» pide el diff al abrirse y muestra «Horario: Atiende siempre → L–V 9–18» con claves traducidas; el prompt plegado al final; «Publicar» confirma y llama a la acción con `from: "draft_bar"`; tras publicar, la barra desaparece; sin permiso, frase y roles. _Requisitos: 3.1, 3.2, 3.3, 3.4_ Entregado: rama 017, 2026-09-25 (4 casos de las dos acciones nuevas: el analista lee el diff y no publica; publicar desde la barra llama al backend con `draft_bar`; el rol de facturación ni lee).
- [X] T025 [US2] Implementar `draft-bar-client.tsx` y `draft-diff-sheet.tsx` en `apps/console/src/components/clients/`, la acción `draftDiffAction` y `publishFromBarAction` en `apps/console/src/app/(console)/clients/[ref]/agent/actions.ts` (con `can()` y test en el arnés `__tests__/actions.test.ts`), y montarla en el layout de la ficha; los toasts de Ajustes/Herramientas/Habilidades/Conocimiento pasan a solo confirmar. _Requisitos: 3.1, 3.3, 3.4, 3.5_ Entregado: rama 017, 2026-09-26. `draft-bar-client.tsx` y `draft-diff-sheet.tsx` en el layout, con `draftDiffAction` y `publishFromBarAction` (ambas con `can()` y test); el diff se pide al abrir la hoja, no al montar; y la ventana de deshacer de diez minutos con su contador vivo, que al expirar cierra el aviso solo. El componente se monta siempre que haya agente para que el aviso sobreviva al refresco. Verificado en el stack local: publicar → «Versión 2 publicada, deshacer vuelve a la versión 1, quedan 10 min» → Deshacer → versión 1 activa. **Pendiente** (menor): que los toasts de Ajustes/Herramientas/Habilidades/Conocimiento pasen a solo confirmar, ahora que la barra es quien lleva a publicar.
- [X] T026 [US2] Agente como historial: en `apps/console/src/components/clients/agent-versions.tsx` cada versión con fecha, quién, `draft_screens`-like resumen de qué cambió (del diff cuando es la activa vs anterior no aplica: solo borrador vs activa; el resto muestra fecha y autor) y las acciones actuales intactas; test en `__tests__/agent-versions.test.tsx`. _Requisitos: 3.6_ Entregado: rama 017, 2026-09-26 (`agent-history.ts` puro con 5 casos: el resumen sale solo en el borrador actual, no en una versión preparada y luego superada ni en la activa; las acciones de siempre intactas). Verificado en el stack local: «v3 · Borrador · Cambia: Ajustes».

### E2E, paridad y evidencia

- [ ] T027 [US1] `apps/console/e2e/record.spec.ts`: recorrido de la ficha con owner, builder y analyst (pasos, botón, grupos, «Más», barra de borrador); añadir `/clients/{ref}/capabilities` (aunque redirija) a `a11y.spec.ts`; 360 y 1 920 px, ES/EN. _Requisitos: 2.3, 12.3_
- [ ] T028 [US1] Cerrar `parity.md` §Iteración 1 (las 23 filas revisadas contra el código) y `evidence/iteracion-1.md` (capturas por rol, resultados de suites); log de sesión `kb/…/sessions/2026-MM-DD-spec-017-iteracion-1.md`; merge a `develop`, despliegue y recorrido en staging. _Requisitos: 12.1, 12.2, 12.5_

---

## Iteración 2 · Capacidades e Integraciones (US3)

**Goal**: una pantalla de Capacidades por función y sector, con Integraciones delante y un clic que guarda.

**Independent Test**: quickstart §Iteración 2; paridad de Herramientas y Habilidades al 100 %.

- [ ] T029 [US3] Prototipo `packages/ui/src/stories/prototypes/capabilities.stories.tsx`: Integraciones arriba, grupos por función, tarjeta con conmutador/estado/modo/«Necesita X», «Ver todas», sin sector, buscador, lote; aprobación en `evidence/iteracion-2.md`. _Requisitos: 12.4_
- [ ] T030 [P] [US3] Test primero `apps/api/tests/unit/test_capability_names.py`: el mapa `capability_names.py` cubre **todas** las herramientas del catálogo sembrado y todas las habilidades del bundle (nombre de negocio ES/EN, función, sectores); una entrada sin traducción falla el test; `function` ∈ {appointments, orders, messages, escalation, knowledge, other}. _Requisitos: 5.1, 5.6_
- [ ] T031 [US3] Crear `apps/api/src/nexus_api/api/console/capability_names.py` con el mapa y las funciones `business_name(key, kind, lang)`, `function_of`, `sectors_of` (a partir de `capability_tags` que nombren un vertical). _Requisitos: 5.1, 5.2_
- [ ] T032 [P] [US3] Test primero `apps/api/tests/integration/test_console_capabilities.py`: `GET …/capabilities` agrupa por función; con sector filtra y devuelve `hidden_by_sector`; `all=true` incluye el resto marcado; `q=` busca en nombre y descripción del idioma; `recommended` = herramientas de la plantilla del sector; `usable=false` con conector no conectado; `mode.options` sin `needs_approval`; `PUT` con un cambio crea borrador (`draft_created`), escribe la lista blanca **solo** de ese tenant, audita `console.capability.update`; `PUT` `needs_approval` → 422; activar con conector ausente → 409 `connector_required`; `PUT …/tools` con `needs_approval` → 422. _Requisitos: 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8, 5.9_
- [ ] T033 [US3] Implementar `apps/api/src/nexus_api/api/console/capabilities_client.py` (router bajo `/clients/{ref}/capabilities`, `client_scope("agents:read"/"agents:write")`, `ensure_draft`, reutilizando `tools.py`/`skills.py`), `schemas_capabilities_client.py`, registro del router, y el 422 en `tools.py`. _Requisitos: 5.1–5.9_
- [ ] T034 [P] [US3] T-ISO · `apps/api/tests/isolation/test_42_capabilities_whitelist_scoped.py`: un `PUT …/capabilities` sobre el ref de otro partner → 404 opaco y la lista blanca de ese tenant intacta; la lista escrita es subconjunto del catálogo (`test_2_tool_whitelist_contract.py` extendido a `capabilities`). _Requisitos: 12.2_
- [ ] T035 [P] [US3] Companion: `console.get_capabilities` en `apps/api/src/nexus_api/companion/tools/catalog.py` sobre el mismo endpoint; test en `apps/api/tests/unit/test_companion_catalog.py` (o el existente) de que la herramienta aparece y cita el endpoint. _Requisitos: 5.1_
- [ ] T036 [P] [US3] Tests `apps/console/src/components/capabilities/__tests__/catalog.test.tsx`: grupos y filtro por sector; contador «n de otros sectores · Ver todas»; sin sector; buscador; conmutador guarda con un clic (acción llamada una vez por clic, sin «Guardar»); tarjeta «Necesita WooCommerce · Conectar» sin conmutador; sin «Requiere aprobación»; detalle técnico plegado; lote «Marcar todas las visibles» llama N veces con progreso; solo lectura sin `agents:write`. _Requisitos: 5.1–5.9_
- [ ] T037 [US3] Implementar `apps/console/src/components/capabilities/{catalog.tsx, capability-card.tsx, integrations-list.tsx}`, `lib/backend/capabilities.ts`, acciones `setCapabilityAction` en `apps/console/src/app/(console)/clients/[ref]/capabilities/actions.ts` (con `can()` y test en el arnés), páginas `capabilities/page.tsx` e `integrations/page.tsx`; `tools/page.tsx` y `skills/page.tsx` pasan a `redirect()` definitivos. Integraciones reutiliza los diálogos de conectores y AgendaPro de la 016. _Requisitos: 4.1, 4.2, 4.3, 5.1–5.9_
- [ ] T038 [US3] Tras conectar una integración, refrescar Capacidades sin recarga manual (`router.refresh()` + revalidación de la lista); test en `catalog.test.tsx`. _Requisitos: 4.3_
- [ ] T039 [US3] E2E: `a11y.spec.ts` con `/capabilities` e `/integrations`; recorrido «activar Reservas → barra → publicar» en `record.spec.ts`; paridad §Iteración 2 (desde `tools-catalog.tsx` y `skills-grid.tsx`, incluidas las acciones de lote, el modo, «en la versión activa», conectar/desconectar/sincronizar); `evidence/iteracion-2.md`; log de sesión; merge y staging. _Requisitos: 5.9, 12.1, 12.2, 12.3, 12.5_

---

## Iteración 3 · Consumo (US4)

**Goal**: créditos, tres bloques, todo lo de hoy en su sitio.

- [ ] T040 [US4] Prototipo `packages/ui/src/stories/prototypes/usage.stories.tsx` (Saldo con equivalencia y alertas plegadas, Reparto con barras y diálogo Ajustar, Consumo con etiquetas humanas; estado saldo ilegible); aprobación en `evidence/iteracion-3.md`. _Requisitos: 12.4_
- [ ] T041 [P] [US4] Test primero `apps/api/tests/integration/test_console_wallet_equivalence.py`: `GET /console/wallet` devuelve `equivalence` con `usd_per_credit` del precio vigente de la 005, `credits_per_message` = media de 30 días del partner (`basis: partner_30d`) o valor de referencia (`platform_default`) sin historial; ausente cuando el saldo no se puede leer; `GET /wallet/allocations` trae `client_name` y `consumed = cap - remaining`. _Requisitos: 6.2, 6.3, 6.5_
- [ ] T042 [US4] Implementar `equivalence` en `apps/api/src/nexus_api/api/console/wallet.py` + `schemas_wallet.py` (media desde `usage_records` con sesión de partner; constante de referencia en `config.py` como `platform_credits_per_message`), y los campos de asignación. T-MET: la equivalencia es lectura; nada nuevo entra en el medidor (anotar en `plan.md`). _Requisitos: 6.2, 6.3_
- [ ] T043 [P] [US4] Tests `packages/ui/src/components/__tests__/row-actions.test.tsx` e implementación de `packages/ui/src/components/row-actions.tsx` (`RowActions {items, label}` sobre `DropdownMenu`, con teclado), exportar, story. _Requisitos: 6.3_
- [ ] T044 [P] [US4] Tests `apps/console/src/components/usage/__tests__/{balance,allocation-rows,adjust-dialog}.test.tsx`: cifras en créditos con «≈ USD · ≈ mensajes» y el sufijo según `basis`; alertas plegadas y editables dentro de Saldo; barra por cliente con «Sin cupo»; «Ajustar» abre diálogo con Editar tope / Mover (una operación, mismos errores de la 016); «Asignar cupo» para clientes sin asignación; tabla sin `llm.*`; saldo ilegible → Saldo lo dice, resto sigue, «≈ —». _Requisitos: 6.1–6.6_
- [ ] T045 [US4] Reescribir `apps/console/src/app/(console)/usage/page.tsx` en tres bloques con `components/usage/{balance.tsx, allocation-rows.tsx, adjust-dialog.tsx, consumption.tsx}`; `usage/alerts/page.tsx` → `redirect("/usage#alerts")`; `buy-credit-form.tsx` dentro de Saldo; filtros y exportación CSV conservados. _Requisitos: 6.1, 6.4, 6.6, 12.5_
- [ ] T046 [US4] E2E (`/usage` en `a11y.spec.ts` ya está; añadir el diálogo Ajustar al recorrido), paridad §Iteración 3 (desde `usage/page.tsx`, `usage/alerts/*`, `buy-credit-form.tsx`, `charts.tsx`), `evidence/iteracion-3.md`, log de sesión, merge y staging. _Requisitos: 12.1, 12.2, 12.3_

---

## Iteración 4 · Alta (US5)

**Goal**: 4 clics + 1 campo + 2 de plantilla; termina en la ficha.

- [ ] T047 [US5] Prototipo `packages/ui/src/stories/prototypes/wizard.stories.tsx` (tres pasos, tarjetas por sector, Avanzado plegado, obligatorios primero); aprobación en `evidence/iteracion-4.md`. _Requisitos: 12.4_
- [ ] T048 [P] [US5] Tests `apps/console/src/app/(console)/clients/new/__tests__/wizard.test.tsx` (nuevo render test): paso 1 con Nombre y Zona horaria y la referencia solo en «Avanzado» con la validación actual; paso 2 sin preselección, tarjetas con sector y frase, sin ids ni recuentos; placeholders solo tras elegir, obligatorios primero, opcionales plegados; sin paso «Canal»; revisión con «Publicar y activar» y etapas de la 016; al terminar, navegación a la ficha; guardia de salida y cierre por cuota intactos. _Requisitos: 7.1–7.6_
- [ ] T049 [US5] Implementar en `apps/console/src/app/(console)/clients/new/{wizard.tsx, wizard-state.ts}`: `STEPS = ["details","sector","review"]`, tarjetas de sector (`sector.frase` en i18n por `vertical`), `Field` + `NativeSelect` con nombres de zona (R8 del research: `Intl.supportedValuesOf` con fallback), `router.push(clientHref)` al terminar; `wizard-state.test.ts` actualizado. _Requisitos: 7.1–7.6_
- [ ] T050 [US5] E2E: contar clics y campos en `record.spec.ts` (CE-003) y `/clients/new` en `a11y.spec.ts`; paridad §Iteración 4; `evidence/iteracion-4.md`; log; merge y staging. _Requisitos: 12.1, 12.2, 12.3_

---

## Iteración 5 · Inicio y lista (US6)

**Goal**: una lista de tareas y una tabla que dice quién está listo.

- [ ] T051 [US6] Prototipo `packages/ui/src/stories/prototypes/home-and-list.stories.tsx`; aprobación en `evidence/iteracion-5.md`. _Requisitos: 12.4_
- [ ] T052 [P] [US6] Test primero en `apps/api/tests/unit/test_endpoint_console_onboarding.py` (o el existente): `channel_connected` solo con canal de cliente final, `conversations` solo de canal (un hilo del Playground no cuenta); `GET /console/onboarding` devuelve `teammates_plan: bool` (nivel con `max_teammates > 0`). _Requisitos: 8.2, 8.3_
- [ ] T053 [US6] Implementar en `apps/api/src/nexus_api/api/console/onboarding.py` y `schemas_onboarding.py`. _Requisitos: 8.2, 8.3_
- [ ] T054 [P] [US6] Tests `apps/console/src/components/home/__tests__/start-card.test.tsx` y `apps/console/src/components/clients/__tests__/clients-table.test.tsx`: una sola tarjeta con pasos pendientes y acción («Conectar un canal» → Canales del primer cliente sin canal); «Tu puesto de trabajo» solo con `teammates_plan`; métricas con etiqueta en sans y sin «calculado en»; tabla con las cinco columnas, tres puntos con nombre, `Meter` de cupo, fila clicable con el nombre como enlace, filtros con contador, sin referencia ni zona horaria, búsqueda por referencia sigue. _Requisitos: 8.1, 8.2, 8.4, 8.5, 9.1–9.4_
- [ ] T055 [US6] Implementar `apps/console/src/components/home/start-card.tsx` (sustituye a `onboarding-card-client.tsx` + `workstation-setup-card.tsx` en la portada; el puesto de trabajo mantiene su tarjeta en `/workstation`), `apps/console/src/app/(console)/page.tsx`, `apps/console/src/components/clients/clients-table.tsx` y `clients/page.tsx`. _Requisitos: 8.1–8.5, 9.1–9.4_
- [ ] T056 [US6] E2E (`/` y `/clients` en `a11y.spec.ts`; recorrido lista → ficha), paridad §Iteración 5, `evidence/iteracion-5.md`, log, merge y staging. _Requisitos: 12.1, 12.2, 12.3_

---

## Iteración 6 · Ajustes del agente (US7)

- [ ] T057 [US7] Prototipo `packages/ui/src/stories/prototypes/agent-settings.stories.tsx` (secciones plegables con resumen, índice lateral, pie fijo, selectores con nombres, contador, «Atiende siempre»); aprobación en `evidence/iteracion-6.md`. _Requisitos: 12.4_
- [ ] T058 [P] [US7] Tests y bloque `packages/ui/src/components/kbd.tsx` (`Kbd` que resuelve ⌘/Ctrl por plataforma, para los atajos del índice) en `__tests__/kbd.test.tsx`; exportar; story. _Requisitos: 10.1_
- [ ] T059 [P] [US7] Tests `apps/console/src/components/agent-tools/__tests__/agent-settings-form.test.tsx`: resumen por sección («Horario: Atiende siempre», «Idiomas: español»); sin franjas → «Atiende siempre» marcado y guardado como tal; selector de zonas con ciudades y búsqueda (fallback a la lista corta); idiomas con nombres (`Intl.DisplayNames`); contador de caracteres; Guardar visible al desplazarse (pie `sticky`); todos los campos y validaciones actuales presentes (paridad por `settings-schema.ts`). _Requisitos: 10.1–10.6_
- [ ] T060 [US7] Implementar en `apps/console/src/components/agent-tools/agent-settings-form.tsx` (+ `settings-sections.ts` con resúmenes, `timezone-select.tsx`, `language-select.tsx`), sobre `Section`, `Field`, `NativeSelect`. _Requisitos: 10.1–10.6_
- [ ] T061 [US7] E2E (`/agent/settings` en `a11y.spec.ts`), paridad §Iteración 6, `evidence/iteracion-6.md`, log, merge y staging. _Requisitos: 12.1, 12.2, 12.3_

---

## Iteración 7 · Transversal (US8)

- [ ] T062 [US8] Prototipo `packages/ui/src/stories/prototypes/help-and-minor.stories.tsx` (HelpHint en contexto, glosario, Ajustes del cliente con Zona de peligro, Playground con hilo por fecha); aprobación en `evidence/iteracion-7.md`. _Requisitos: 12.4_
- [ ] T063 [P] [US8] Test primero `apps/api/tests/integration/test_console_audit_category.py`: `GET /console/audit?category=clients` filtra; desconocida → 422; `vocabulary.categories` con etiqueta en el idioma. Implementar en `audit.py`. _Requisitos: 11.5_
- [ ] T064 [P] [US8] Test primero `apps/api/tests/integration/test_console_billing_email.py`: `PUT /console/billing/email` con `billing:manage`; 422 `invalid_email`; auditoría `console.billing.email_update` sin exponer nada más. Implementar en `billing.py` + `schemas.py`. _Requisitos: 11.5_
- [ ] T065 [P] [US8] Test primero en `apps/api/tests/integration/test_endpoint_console_playground.py`: crear un hilo sin título → «Conversación del {fecha}» en el idioma del principal; nunca «Untitled». Implementar en `playground.py` / `schemas_playground.py`. _Requisitos: 11.3_
- [ ] T066 [P] [US8] Tests de consola: `apps/console/src/app/(console)/ayuda/__tests__/page.test.tsx` (glosario con los términos de R11.1 en ES/EN y anclas), `components/clients/__tests__/client-settings.test.tsx` (Datos con referencia copiable, Zona de peligro con las reglas de hoy), `components/billing/__tests__/billing-email.test.tsx`, `components/playground/__tests__/{turn-inspector,budget-bar}.test.tsx` (error con causa y reintento; presupuesto en una línea), `components/notifications/__tests__/notifications-list.test.tsx` (títulos del vocabulario), `app/(console)/audit/__tests__/controls.test.tsx` (filtro por categoría). _Requisitos: 11.1–11.5_
- [ ] T067 [US8] Implementar `apps/console/src/app/(console)/ayuda/page.tsx`, `i18n/lanes/glossary.ts`, `HelpHint` con enlace a `/ayuda#term` en cada término (ficha, Capacidades, Consumo, alta, Ajustes), `clients/[ref]/settings/page.tsx` (Datos + Zona de peligro), `components/billing/billing-email.tsx` + acción con `can()`, cambios de Playground, Notificaciones y Auditoría. _Requisitos: 11.1–11.5_
- [ ] T068 [US8] Barrido tipográfico: ningún rótulo de sección, métrica, menú o tarjeta en `font-mono` (`grep` como test en `apps/console/src/__tests__/typography.test.ts` que solo permite mono en identificadores, código y `Kbd` por lista blanca de ficheros/clases). _Requisitos: 11.6_
- [ ] T069 [US8] E2E (`/ayuda`, `/clients/{ref}/settings`, `/billing`, `/audit`, `/notifications` en `a11y.spec.ts`; test de que ningún `title=` queda como única ayuda), paridad §Iteración 7, `evidence/iteracion-7.md`, log, merge y staging. _Requisitos: 12.1, 12.2, 12.3_

---

## Phase Final: cierre de la spec

- [ ] T070 Recorrido completo en staging (crear cliente → cupo → agente → integraciones → operativo) con evidencia en `evidence/staging-final.md`; CE-001…CE-009 medidos y anotados en `spec.md` §Criterios de éxito. _Requisitos: 12.2_
- [ ] T071 [P] `docs/console.md` (spec viva) actualizado con la ficha, Capacidades, Consumo, alta, portada, Ajustes y glosario; `nexus/architecture/console-map.md` y `console-design-system.md` (bloques `NavTabs`, `DraftBar`, `RowActions`, `Kbd`) en la KB; `PLAN-ACCION-CONSOLA-2026-09-22.md` con el Bloque D cerrado. _Requisitos: 12.1_
- [ ] T072 [P] T-LIC final: `pnpm-lock.yaml` y `uv.lock` sin cambios respecto a `develop` al abrir el PR de cierre; T-ISO final: `tests/isolation` completo en verde. _Requisitos: 12.2_

---

## Dependencies & Execution Order

- **Setup (T001–T004) → Foundational (T005–T010) → Iteración 1**. La iteración 1 es el MVP y bloquea a las demás solo por el `layout.tsx` de la ficha (navegación y barra).
- **Iteración 2** depende de la 1 (barra de borrador y redirecciones). **3, 4, 5, 6 y 7** dependen de la 1 y son independientes entre sí; el orden del plan es por valor, no por dependencia técnica.
- Dentro de cada iteración: prototipo → tests (API ∥ DS ∥ consola) → implementación → e2e → paridad/evidencia/log → merge.

## Parallel opportunities

- Setup: T002 ∥ T003 ∥ T004 (tras T001).
- Foundational: T005/T007 (tests) ∥ T009 ∥ T010; luego T006 → T008.
- Iteración 1: T012 ∥ T014 ∥ T016 ∥ T018 ∥ T020 ∥ T022 ∥ T024 (tests) tras la aprobación del prototipo T011; implementación T013 ∥ T015 ∥ T017 ∥ T019, después T021 → T023 → T025 → T026.
- Iteración 2: T030 ∥ T032 ∥ T034 ∥ T035 ∥ T036 tras T029.

## Implementation Strategy

- **MVP** = Setup + Foundational + Iteración 1: con eso el partner ya ve qué le falta a cada cliente, cuánto cupo le queda y publica desde donde está. Sale a staging solo.
- Cada iteración siguiente se fusiona en `develop` al cerrar, con la consola usable de punta a punta entre iteraciones (R12.5).
- Nada a `main` hasta que el owner lo decida.
