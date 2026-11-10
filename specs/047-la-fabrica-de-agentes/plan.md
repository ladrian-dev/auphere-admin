# Plan de implementación: 047 — La fábrica de agentes

**Rama**: `047-la-fabrica-de-agentes` | **Fecha**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Entrada**:
- [spec.md](spec.md): 33 historias y 56 requisitos;
- [research.md](research.md): decisiones D1–D42;
- [data-model.md](data-model.md);
- [contracts/](contracts/);
- KB `[[research/2026-10-26-fabrica-de-agentes-v2/_index]]` y `[[decisions/ADR-049-la-fabrica-de-agentes]]`.

Las rutas de código se midieron en `ef358cdd` (sobre `develop`, Alembic en
`0174_reservation_calendars`).

## Resumen

Un programa en diez olas, detrás de una activación de la consola nueva partner a
partner. Los cimientos del turno (ningún mensaje se pierde, un turno a la vez) y
el clasificador barato llegan a todos sin esperar a la consola nueva.

Las piezas:
- **La ficha** en tablas por cliente, con el **ClientSpec** como vista tipada, y
  un solo servicio de horario.
- **El AgentSpec**, compilado a prompt por versión y por revisión de la ficha y del
  conocimiento.
- **El constructor**, como trabajos del worker que siempre proponen, sobre las
  propuestas con `state_hash` del Companion.
- **La puerta de publicación**, con una suite de 20 pruebas por 3 pasadas, la misma
  en la consola, el admin y la API de partners.
- **Canales con su configuración** dentro, y WhatsApp por coexistencia con ES v5,
  con el asistente de la spec 046 abierto desde el agente.
- **Conexiones por cliente y activaciones por agente.**
- **Conocimiento en dos capas**, con búsqueda exacta por cliente.
- **Un router por política** sobre un catálogo certificado, con Bedrock y Scaleway.
- **Bolsas de dinero apartado**, con un libro de doble entrada y el cambio del BCE.
- **El marco común de la consola** en `@nexus/ui`, y las secciones nuevas de la
  consola lite y de la app.
- **Mejora agregada, correcciones desde la Bandeja y Recepción que deriva.**
- **Migraciones que no cambian nada**, comprobadas por partner antes de activar.

**Coordinación con la spec 046** (Andrés, «un alta que termina en un agente que
responde», sin fusionar):
- **Se reutiliza** su iteración 1a: `GET /console/channel-catalog`, el asistente
  `clients/[ref]/channels/new/*` y `components/channels/wizard/*`.
- **Su iteración 1b** (ningún cliente mudo) toca los mismos archivos que la ola 1.
  Lo que entre por la 046 se marca entregado en `tasks.md`. Su T011 (activar un
  cliente) no se construye: la puerta va por canal (T104, T112).
- **Sus iteraciones 2 y 3** las sustituye esta spec, y «activar» pasa a ser por
  canal (decisión del owner del 2026-10-26, escrita en las dos specs y en ADR-049).
- **La constitución** de esta spec es la 1.3.0, sobre la 1.2.0 de la 046.

## Contexto técnico

**Lenguaje/versión**:
- Python ≥ 3.11: FastAPI, SQLAlchemy 2 async, Alembic, Redis Streams (sin Dramatiq: research D43), LangGraph ≥ 1.0
  y LiteLLM `<1.106`.
- TypeScript 5.9, con Next.js 16.2 y React 19.2.
- Expo SDK 58 y React Native 0.88 (Auphere Customers 1.1.0).

**Dependencias nuevas**:
- **`pgvector`** (Python, MIT), para el tipo `vector` en SQLAlchemy. Es la única.
  Instalada la 0.5.1 en `apps/api` y `apps/worker`, sin dependencias propias, y
  leída entera (`docs/licenses/pgvector.md`). El párrafo que la permite: «Permission
  is hereby granted, free of charge, to any person obtaining a copy of this software
  and associated documentation files (the "Software"), to deal in the Software
  without restriction, including without limitation the rights to use, copy, modify,
  merge, publish, distribute, sublicense, and/or sell copies of the Software».
- **Bedrock** entra por LiteLLM, con `boto3`, que ya está en `apps/api` y `apps/worker`.
- **Scaleway** entra por su API compatible con OpenAI, a través de LiteLLM.
- **El BCE** se lee con `httpx`, que ya está.
- **La paleta ⌘K y la gráfica de bloques** salen de `@nexus/ui`: la paleta ya
  existe (`command-palette.tsx`), y la gráfica es SVG y CSS propios.

**Almacenamiento**:
- PostgreSQL 16 (Aurora en producción), con la extensión `vector` y búsqueda de
  texto `spanish`.
- S3 para los documentos subidos, como hoy.
- Redis para los streams de hoy, más los consumidores que faltan de coexistencia.

**Pruebas**:
- **pytest**: `apps/api/tests/{unit,integration,isolation}`. Las pruebas del
  worker con base de datos viven en la suite de la API
  (`tests/integration/channels/`, `test_dispatcher_*`, `test_budget_*`); las
  unitarias, en `apps/worker/tests/unit/`. Las suites se corren de una en una
  (memoria del repo).
- **Aislamiento**: la numeración sigue en `test_43_*`.
- **Consola**: vitest, y Playwright en `apps/console/e2e/` con el ayudante de axe
  `e2e/audit.ts` (WCAG 2.2 AA).
- **Admin**: vitest.
- **App**: Jest y RNTL 14 en `apps/mobile/__tests__/` (`fireEvent` asíncrono), y
  Maestro en `apps/mobile/e2e/`.

**Plataforma**:
- AWS `eu-south-2` (ECS), con Bedrock en la misma cuenta y región.
- Scaleway en París.

**Restricciones**:
- Aurora no tiene `btree_gist`: candados de transacción y revalidación, como en Reservas.
- LiteLLM se queda fijado en `<1.106` (ADR-036).
- La consola de partners no guarda credenciales del backend (`check:no-admin-token`).
- `mypy --strict` en los cuatro paquetes de Python.
- **Cada cron nuevo lleva tres ediciones** (`apps/worker/src/nexus_worker/bootstrap.py`
  y `apps/worker/tests/unit/test_bootstrap_split.py`):
  - su conjunto de nombres;
  - su `_spawn`;
  - `ALL_EXPECTED`.
- **La app comprueba que su contrato está al día**: `verify.sh mobile` corre
  `export_openapi.py --check` y `gen:check`, así que las rutas nuevas de
  `/console/lite/*` regeneran `apps/mobile/src/api/openapi.json` y `schema.gen.ts`.
- **Locks**: una dependencia nueva cambia los locks de `apps/api` y del worker
  (memoria del repo: lockfile único).
- Los teammates no se tocan.

**Objetivos de rendimiento**:

| Qué | Objetivo |
|---|---|
| Lo que la puerta del turno (saldo, tope, pausa, audiencia) añade al turno | < 15 ms p95 |
| Borrador del constructor | < 30 s p90 |
| Suite completa (20 × 3) | < 4 min p90, en paralelo dentro del lote del cliente |
| Búsqueda de conocimiento con ≤ 5.000 fragmentos | < 30 ms p95 |
| Pantallas de la consola | LCP < 2,5 s en 4G, sin CLS |

**Escala**: dos partners en producción (Facelad y Amacrux), con decenas de
clientes cada uno, varios agentes por cliente y miles de mensajes al día.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | **Tablas**: RLS FORCE y FK compuestas. Como `test_21` no exige FORCE en las tablas de cliente normales y no hay barrido de FK compuestas, `test_43_force_and_composite_fk_sweep.py` barre todas las tablas de cliente, con un inventario escrito de excepciones solo para las de antes. **Garantía 9**: `test_44_agent_within_client.py` barre toda tabla con `agent_id` y toda herramienta del registro. **Rutas nuevas**: `/console/*` entra sola en `test_console_scope.py`; `/console/lite/*`, en `test_lite_route_scope.py` y `test_phone_route_scope.py`. Requiere la enmienda 1.3.0 de la constitución (tarea T001) |
| II | Superficie | ☑ | `0`. La lectura de webs ya existía (`services/knowledge_indexer.py`, hoy síncrona en la petición) y pasa a segundo plano con las mismas guardas, más `robots.txt` y 25 páginas. Bedrock y Scaleway son subprocesadores, no superficies |
| III | Lo leído es dato | ☑ | La información, la descripción y lo leído van vallados (`core/guardrails/untrusted.py`). El validador del constructor rechaza claves de plataforma, herramientas fuera de catálogo y clientes finales como argumento. Una prueba adversarial con una web que da órdenes (T045) |
| IV | Acción `mutates` | ☑ | El constructor solo propone, con el `Proposal`/`canonical_hash` del Companion y caducidad de 15 min. Publicar pasa la puerta, y saltarla pide owner o admin con motivo. Pausar, asignar y corregir auditan a la persona y su origen. El borrado RGPD de un cliente queda como excepción escrita (enmienda de §IV y ADR-049) |
| V | Estados honestos | ☑ | Un solo cálculo del estado visible y motivos de la Bandeja de una lista cerrada. «Próximamente» solo en el catálogo de canales de la consola de partners, sin poder iniciarse (constitución 1.2.0, spec 046), y nunca en la lite. Cinco estados por vista y `allowed` en cada recurso |
| VI | Por API | ☑ | El constructor, el copiloto, la consola lite y la app trabajan por la API. Nadie navega la consola |
| VII | Test primero | ☑ | Cada criterio, con su test en rojo antes, en `tasks.md`. Una tarea de aislamiento por garantía |
| VIII | Licencias | ☑ | `pgvector`, MIT (T022, con el párrafo citado). Los modelos abiertos se aceptan por despliegue y con la licencia leída (requisito 41.2): Llama 4 y Qwen3.8-Flash-Next quedan excluidos |
| IX | KB | ☑ | `[[research/2026-10-26-fabrica-de-agentes-v2/_index]]` · `[[decisions/ADR-049-la-fabrica-de-agentes]]` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías 1 a 8, más la 9 (el agente dentro del cliente) y el eje C8 (el partner nunca ve cuerpos de mensaje) | T012–T021 |
| **Licencias** | `pgvector` (MIT). Las licencias de los modelos abiertos se controlan en el catálogo (requisito 41.2) | T022 |
| **Medidor** | **Modelo**: turnos con paso directo, con tarea y decisión en `usage_records`. El constructor, las lecturas, las pruebas, la indexación, las sugerencias y las certificaciones del partner van a la partida «Construcción y pruebas», que paga Auphere hasta el tope. **Herramienta de pago**: Meta, enseñada aparte. El partner lo ve en Consumo › partidas | T023, T024 |

## Olas

| Ola | Historias | Requisitos | Depende de | A quién llega |
|---|---|---|---|---|
| 0 · Base | — | 47 (núcleo del marco), 56 (andamiaje), enmiendas | — | — |
| 1 · Mensajes y borrador | H1 (P1), H2 (P1) | 1–3 | 0 | **A todos**: son arreglos del runtime y del borrador, sin consola nueva |
| 2 · Clientes y ficha | H3–H6 (P1), H14–H17 (P2) | 4–14 | 0 | Partners con la consola nueva |
| 3 · Constructor y publicación | H7–H9 (P1), H18 (P2) | 15–24 | 2 | Ídem; la puerta única, a todos |
| 4 · Agentes y canales | H10, H11 (P1), H19, H20 (P2) | 25–34 | 3 | Ídem. La pausa, la reconexión que combina y la coexistencia, a todos |
| 5 · Integraciones y conocimiento | H21, H22 (P2) | 35–38 | 3 | Ídem |
| 6 · Modelos y router | H12 (P1), H23, H24 (P2) | 39–42 | 1; la calidad por versión, 3 | El catálogo, el router y `classify` barato, **a todos** (D24); la pantalla Calidad, con la consola nueva |
| 7 · Dinero | H25, H26 (P2) | 43–46 | 2 | Con la consola nueva y tras el reparto |
| 8 · Consola, lite, app y operador | H27–H30 (P2) | 47–50, 54 | 2–7 | Ídem |
| 9 · Mejora y Recepción | H31–H33 (P3) | 51–53 | 4, 5 | Ídem |
| 10 · Migración y activación | H13 (P1) | 55, 56 | Todas | Partner a partner |

**Cómo se reparte el trabajo.** La ola 6 es del runtime y del admin, y puede ir
en paralelo con las olas 2 a 5, que son de la API y la consola. La migración de
cada subsistema se escribe en su ola. La ola 10 solo ensaya, compara y activa.
H13 es P1, pero su valor se cobra al activar.

## Diseño

Rutas abreviadas:
- `api/` = `apps/api/src/nexus_api/`;
- `wk/` = `apps/worker/src/nexus_worker/`;
- `ch/` = `apps/channels/src/nexus_channels/`;
- `mcp/` = `apps/mcp/src/nexus_mcp/`;
- `con/` = `apps/console/src/`;
- `adm/` = `apps/admin/src/app/(dashboard)/`;
- `mob/` = `apps/mobile/`;
- `ui/` = `packages/ui/`.

### Ola 0 · Base

- **Enmiendas.**
  - La constitución pasa a 1.3.0, sobre la 1.2.0 de la 046: la garantía 9 en §I y
    el borrado RGPD de un cliente en §IV.
  - La KB añade la garantía 9 a `architecture/agent-isolation.md`.
  - `apps/api/tests/isolation/README.md` la documenta.
- **Activación por partner.**
  - Las columnas `partners.console_v2_enabled_at` y `_by`, y el servicio
    `api/services/console_v2.py`.
  - `/console/me` devuelve `console_version`, y `con/app/(console)/layout.tsx`
    elige el marco.
  - Las rutas viejas siguen para los partners sin activar.
- **Trabajos.**
  - La tabla `jobs`, el servicio `api/services/jobs.py` y `GET /console/jobs/{id}`
    en `api/api/console/jobs.py`.
  - En el worker, el consumidor `jobs-consumer` (familia runner, stream
    `nexus:jobs`) despacha por tipo de trabajo; un trabajo vivo sin latido caduca
    al leerlo (research D43).
- **`@nexus/ui`.**
  - Cambian `ui/src/components/{tabs,dialog,sonner,status-badge,command-palette}.tsx`:
    - píldora;
    - trampa de foco y devolución;
    - avisos que no se van con el foco o el ratón encima;
    - los tonos de `events.md`;
    - navegación con flechas.
  - Componentes nuevos: `block-chart.tsx` (y `money.tsx`, el formato `es-ES`).
  - En `ui/src/styles/tokens.css`, el primario verde profundo (≥ 4,5:1) y el
    vidrio con `prefers-reduced-transparency`. Regenera `mob/src/theme/tokens.gen.ts`.
  - Las reglas `nexus-ui/*` siguen.
- **El marco de la consola** (`con/components/shell/`):
  - `app-sidebar.tsx` y `nav.ts`: plegable a 64 px y sin etiquetas de grupo;
  - las migas, con el `breadcrumb` de la UI;
  - `console-command-palette.tsx`: busca agentes y acciones permitidas, con
    `GET /console/search`;
  - `notifications-bell.tsx`: un desplegable con los 5 últimos;
  - el menú de perfil, con el tema, que se queda en móvil.
  - Va en `con/app/(console)/layout.tsx`, con la URL en el historial.
  - Tiene que estar antes de las pantallas P1.
- **Estado visible y atención.** `api/services/agent_lifecycle.py::visible_state`
  y `api/services/attention.py` son funciones puras, con la tabla de
  `contracts/events.md` §1.3 y los motivos del requisito 7.
- **Semilla de desarrollo**: `apps/api/scripts/dev_seed_fabrica.py` (`quickstart.md` §1).

### Ola 1 · Mensajes y borrador

- **Guardar primero.**
  - En `wk/runtime/dispatcher.py`, la puerta de saldo (líneas 215–232) pasa a ir
    después de `persist_inbound_message` (línea 374).
  - El consumidor (`wk/streams/consumer.py:495`) ya no hace `ack` sin guardar.
  - Todas las puertas (`tenant_inactive`, `no_agent`, `agent_unpublished`,
    `human_takeover`, `not_admin`, presupuesto duro) escriben
    `conversations.waiting_reason` y `conversation_events`, y pasan a la Bandeja
    con `api/services/inbox_lifecycle.py`.
  - El mensaje de espera, como mucho una vez cada 6 h.
  - **Se solapa con la iteración 1b de la 046** (T010/T012): lo que entre por allí
    se marca entregado.
- **El resolutor reconoce los canales en pausa y degradados.**
  - La función SQL `resolve_channel_tenant` (SECURITY DEFINER, definida en
    `alembic/versions/0002_rls_policies.py:73-89`, con `status='active'`) se
    redefine en una migración nueva.
  - También cambian `api/core/tenant_resolver.py` y `_INBOUND_PRELUDE_SQL`
    (`api/api/webhooks/meta.py:116`).
  - Los envíos salientes (`api/services/channel_routing.py`) siguen solo con canales activos.
- **Agrupación y candado.**
  - Cada entrante programa el turno de su conversación a +3 s: una cola diferida
    de Redis, deduplicada por conversación (research D43).
  - El turno toma con un advisory lock todos los mensajes sin `turn_id`.
  - Los efectos pasan por `turn_effects`, con su clave `turno:acción`.
- **`wk/runtime/pipeline.py`.**
  - En `make_handler_node` (`MAX_TOOL_ITERATIONS=6`), la última iteración pide una
    respuesta final sin herramientas.
  - Un fallo sin recuperación pasa la conversación a la Bandeja y avisa a los
    destinatarios del canal (hasta la ola 4, por las vías de hoy).
- **Presupuesto de Auphere.** `wk/runtime/budget_gate.py::apply_hard_cutoff` guarda
  y marca la Bandeja.
- **Conciliación con Meta.** El cron `wk/streams/meta_reconciliation_cron.py`
  (diario, en el planificador).
- **Un solo borrador.**
  - Hoy el borrador es la versión `staged`: `api/api/console/agent_drafts.py`
    (`ensure_draft`, `draft_diff`), `api/services/agent_config_service.py`
    (`stage_new_version`, `promote`, `rollback`) y `api/repositories/agent_config.py`.
  - Se añade como mucho un `staged` por agente (índice único parcial),
    `agents.draft_revision` con `If-Match` (412 con los cambios) y el número de
    versión por agente («v{n}»), sin tocar el `version` de cada cliente.

### Ola 2 · Clientes y ficha

- **`api/services/business/`**:
  - `profile.py` y `sections.py` (revisión y estado de cada sección);
  - `locations.py`;
  - `hours.py`, el único servicio de horario. Detrás quedan las funciones de
    `api/services/business_hours.py` (`canonical_business_hours`,
    `business_hours_label`, `is_open_at`), que pasan a leer las tablas nuevas;
  - `special_dates.py`;
  - `services_catalog.py`, sobre `api/services/reservations/`;
  - `faqs.py` y `links.py` (la detección de enlaces, una función pura);
  - `provenance.py`, `history.py` (deshacer) y `suggestions.py`;
  - `client_spec.py`: el modelo Pydantic `extra="forbid"`, igual que
    `contracts/client-spec.schema.json`, más exportar, importar como propuesta y
    el validador sin modelo.
- **Lectores del horario que cambian**:
  - `mcp/servers/booking/availability.py`;
  - `api/services/reservations/core.py:125` (y `engine.py`, que intersecta con la agenda);
  - `api/services/push_fanout.py:185` (`_outside_hours`);
  - `api/api/console/lite/me.py:100`;
  - `wk/runtime/console_context.py::render_operating_policy_block` (`pipeline.py:707`),
    con `policies.console.schedule` de `api/services/agent_console_policy.py`;
  - la variable `tenant.business_hours_label` de `api/services/templating/seed_templates.py:16`.
  Las tres copias se escriben como proyección en la misma transacción hasta que el
  último lector cambie.
- **Escritores del horario que cambian**:
  - `api/api/admin/tenants.py:275`;
  - `api/api/console/lite/reservas.py:257`;
  - los validadores de la API de partners (`api/schemas/tenant.py:71,151`).
- **Lectura de webs y redes.**
  - `api/services/business/reader.py`, como trabajo `client_read` del worker.
  - Usa las guardas de `api/services/knowledge_indexer.py` (`assert_public_url`,
    `fetch_url`, `MAX_URL_BYTES`), más `robots.txt`, 25 páginas y los perfiles
    públicos de redes.
  - La extracción es la tarea `read_source` del router.
  - Lo que no choca se aplica con `review=pending`, y lo que choca queda en
    `business_suggestions`.
- **El alta.**
  - `api/api/console/tenants.py` (`/clients`) pide tres datos y no crea ningún
    agente, aunque el partner tenga plantilla por defecto.
  - `api/services/tenant_lifecycle.py` separa el ciclo de vida de la preparación:
    `provisioning` pasa a `active`.
  - Archivar pausa los agentes con su `before_pause`, y restaurar los devuelve.
  - El borrado RGPD queda como hoy.
  - La API de partners (`api/api/partners_clients.py`) conserva su contrato: si
    alguien pide una plantilla explícita, la aplica como hoy (`docs/partner-integration.md`).
- **Rutas**: `api/api/console/business.py` (`console-api.md` §3).
- **Agente**: la compilación por revisión (D4) entra en esta ola.
  - Un cambio de la ficha compila de nuevo la versión activa y reescribe su
    `system_prompt_rendered`, que sigue siendo la verdad del runtime.
  - Guarda la historia en `agent_version_compilations`.
  - `wk/runtime/agent_loader.py` solo invalida su caché.
  - La ficha va como bloque de datos vallado, no como instrucción (§III).
  Así el agente usa el horario nuevo desde el siguiente mensaje (requisito 8.4).
- **Consola** (`con/app/(console)/clients/`):
  - lista;
  - modal de alta y edición, que sustituye a `clients/new` para los partners activados;
  - `[ref]/` con pestañas en píldora: Panel, Negocio y Agentes;
  - Negocio, con su índice lateral y las seis secciones del prototipo (`01` §3.3).
  Los componentes van en `con/components/{clients,business}/`, y las cadenas, en
  `con/i18n/lanes/business.ts`.
- **Migración de la ola**: las tres copias del horario y `policies.console.schedule`
  pasan a la ficha, marcadas «Migrado · revísalo» si vienen del prompt.

### Ola 3 · Constructor y publicación

- **`api/services/agent_spec/`**:
  - `schema.py`: AgentSpec v1, igual que `contracts/agent-spec.schema.json`;
  - `compiler.py`: puro y determinista, con las variantes por familia;
  - `validator.py`: amplía `AgentConfigService._validate_tools` con lo del
    requisito 15.4;
  - `review.py`: los hallazgos del requisito 22;
  - `legacy.py`: el modo «instrucciones», byte a byte.
- **Constructor**:
  - `api/services/builder/` (`agent_draft.py`, `client_profile.py`, `tests_gen.py`,
    `fixes.py`, `copilot.py`, `prompts/` solo con patrones de Auphere);
  - corre en el worker (`wk/builder/`), en trabajos con progreso por bloques;
  - propone con `api/companion/tools/proposals.py` (`Proposal`, `canonical_hash`)
    y `actions.py` (`stage_action`, `apply_action`, `verify_action`);
  - los `kind` nuevos son `agent_spec_patch`, `client_spec_patch`, `test_add`,
    `fix` y `channel_config_patch`;
  - la comprobación del `state_hash` sale de `api/api/console/companion.py::_revalidate_state_hash`
    a un servicio común;
  - **no depende del módulo `companion`**.
- **Simulación y pruebas**:
  - `api/services/testing/` (`suites.py`, `sector_catalog.py`, `judge.py`) y
    `wk/simulation/`;
  - se apoya en `api/services/evals/pipeline_driver.py` (`EvalPipelineDriver.prime`),
    completando el paquete que hoy no lleva: asignaciones de modelo, banderas del
    runtime, `agent_id` y zona horaria;
  - registro de herramientas en seco, con dobles de estado (agenda y hora simuladas);
  - el cliente simulado y el juez son de otra familia;
  - 3 pasadas, en lotes del cliente.
- **Playground**: `api/api/console/playground.py` y `wk/runtime/qa_pipeline.py`
  ejecutan el borrador o una versión, no solo la activa. Su consumo pasa a la
  partida «Construcción y pruebas» (T024). El tope de tokens
  (`partners.qa_monthly_token_cap`) se queda hasta la ola 7.
- **Puerta**: `api/services/publishing.py`. Sigue la cadena compilar → validar →
  probar → revisar → decidir → publicar, con deshacer de 10 min, historial y
  restaurar. La usan los tres sitios que publican:
  - la consola (`api/api/console/agents.py`, que hoy solo exige el aviso de IA);
  - el admin (`api/api/admin/agent_configs.py:167`, que hoy exige las evals);
  - la API de partners.
- **Rutas**: `api/api/console/agent_builder.py` (`console-api.md` §4), con
  `agent_scope` de `api/api/console/deps.py`.
- **Consola** (`con/app/(console)/clients/[ref]/agents/[agentId]/`): la pantalla
  del constructor (`con/components/builder/`):
  - la descripción a la izquierda y el probador a la derecha;
  - los bloques editables, las preguntas, y las pruebas con «Por qué falló» y «Arreglar»;
  - la revisión, la barra de acción, las versiones y el copiloto lateral.
- **Admin** (`adm/tenants/[id]/agent/` ya tiene evals; lo nuevo va en `adm/builder/`):
  - la evaluación del constructor (100 descripciones);
  - el catálogo de pruebas del sector.
- **Migración de la ola**: cada versión activa con prompt propio pasa a un
  AgentSpec en modo «instrucciones». La compilación da los mismos bytes, y lo
  comprueba un test por agente en el ensayo.

### Ola 4 · Agentes y canales

- **Estados.**
  - `api/db/models/agent.py`: `AgentStatus` (`active`/`archived`) pasa a `lifecycle`.
  - `api/services/agent_lifecycle.py` lleva las transiciones de `data-model.md` §12.
  - `api/services/agents.py` (`archive`, `assign_channel`, `principal_agent_id`)
    usa el agente por defecto atómico.
- **WhatsApp ES v5**:
  - `ch/whatsapp_meta/signup.py` (`EmbeddedSignupOrchestrator.complete`,
    `connect_with_token`, `_upsert_channel`): combina el `config` en lugar de la
    línea 473, que hoy pierde `role`, `agent_enabled`, `catalog_*` y `unlink_*`;
  - `api/services/meta_signup_service.py` y sus tres llamadas: consola, API de
    partners y admin;
  - en `con/lib/meta-fb-sdk.ts`, `sessionInfoVersion` pasa a v5;
  - el asistente de la 046 (`clients/[ref]/channels/new/*`) se abre desde el agente,
    con su paso 3 ya resuelto.
- **Coexistencia.** Hoy `api/api/webhooks/meta.py` deja los ecos, el historial y
  la sincronización en tres streams de Redis (`nexus:meta:echoes`,
  `:history`, `:state_sync`) que **nadie lee**, y no maneja `account_update`. Se añaden:
  - los consumidores `wk/streams/meta_{echoes,history,state_sync}_consumer.py`, en
    la familia runner;
  - el manejo de `account_update`.
  Los ecos ponen `human_takeover` durante 2 h.
- **Enlace del dueño.**
  - `api/services/channel_signup_links.py` (`mint_link`, `revoke_link`,
    `connect_with_link`) gana el agente, el modo y uno pendiente como mucho.
  - Las rutas son `api/api/console/whatsapp.py` (signup-links) y
    `api/api/console/channel_signup.py`, con la página `con/app/connect/whatsapp/*`.
  - La beta aparece por país.
- **Página del canal.**
  - `api/services/channel_config.py` (nuevo).
  - La audiencia sale de `api/core/admin_gate.py` (`sender_is_admin`,
    `admin_only_suppresses`) y se lee del canal. Se aplica en `dispatcher.py:630`,
    `webhooks/meta.py:541` y `pipeline.py:967`.
  - Las rutas van en `api/api/console/channel_config.py`.
- **Escalado.** `mcp/servers/escalate/tools.py` avisa a los destinatarios del canal.
  El canal de respaldo con el dueño (`api/repositories/owner_backchannel.py`, ADR-018)
  pasa a ser una vía más.
- **Mover, pausar y desconectar**: en `api/api/console/channels.py` y
  `agents_list.py`, donde ya está `PATCH /clients/{ref}/channels/{id}/agent`.
  Desconectar no rompe la suscripción de otro entorno (`9fc02f96`).
- **Consola**:
  - la pestaña Canales del agente (`con/components/channels/`), con las tarjetas,
    el menú ⋯, el velo de Meta y «Pasar a otro agente»;
  - la página de configuración del canal, con su barra.
- **Migración de la ola**:
  - `policies.admin_access` (`admin_only` y `admin_phones`) pasa a la audiencia de
    cada canal;
  - `admins[]` pasa a `team_access` en el AgentSpec.

### Ola 5 · Integraciones y conocimiento

- **Activaciones.**
  - `api/services/activations.py` y la tabla `agent_connector_activations`. El
    permiso se traduce a `ConnectorToolMode` (`tenant_connector_tool_overrides`).
  - El catálogo (`api/services/connectors/catalog.py`) declara `settings_schema`.
  - `wk/runtime/agent_loader.py` construye las herramientas con la intersección de
    AgentSpec y activaciones; también `mcp/servers/composio_proxy/proxy.py`, que
    es dinámico.
  - La salud la sigue dando `TenantConnectorStatus` (`needs_reauth`, `error`), más
    la hora de la última comprobación de `wk/streams/connector_reconcile_cron.py`.
  - Los ajustes repartidos (AgendaPro, WooCommerce, Amigable, recordatorios) migran
    a la activación de cada agente que los usa.
- **Conocimiento.**
  - `api/services/knowledge/` (`layers.py`, `retrieval.py`, `teach.py`).
  - `knowledge_documents` gana `agent_id`, y se crea `knowledge_chunks`, con
    embeddings (`vector`) y `tsvector`.
  - El turno deja de leer el texto entero con `console_context.load_knowledge_block`
    (`pipeline._load_knowledge_text`): si cabe en el presupuesto del agente, va en
    la compilación; si no, se recupera.
  - Indexar pasa de la petición (`api/api/console/knowledge.py:167`) a un trabajo.
  - Las fuentes de cada respuesta van a `turn_sources`.
  - Releer las webs cada semana: el cron `wk/streams/source_reread_cron.py`.
- **Memoria.** `agent_memories` gana `agent_id`, y la «memoria propia» la filtra en
  `pipeline._load_recent_history`.

### Ola 6 · Modelos y router

- **Catálogo.**
  - `api/db/models/model_profile.py`: `model_profiles` gana las columnas de
    `data-model.md` §8, y entran `model_prices`, `router_taxonomy`,
    `router_profiles` y las tablas de certificación.
  - El servicio `api/services/router_catalog.py`.
  - `RESPOND_MODELS` y `HOP_MODEL_IDS` (`api/core/respond_catalog.py`, con su test
    `tests/unit/test_respond_catalog.py`) pasan a datos.
  - `cheapest_model` (`wk/metering/pricing.py:295`) filtra por estado,
    herramientas, lista permitida (`partner_model_allowlist`) y residencia.
- **Router** (`wk/runtime/model_resolver.py`):
  - `chain_for(task, profile, ctx)`, sobre `load_bindings`;
  - el clasificador (`make_classify_node`, `pipeline.py:563`) devuelve un objeto tipado;
  - el escalado es una subllamada aislada, por las señales del grafo;
  - la afinidad va en el estado del hilo (`pinned_model`), con el
    `TenantScopedPostgresSaver` de `wk/runtime/checkpointer.py`;
  - `tenant_model_bindings` sigue siendo el techo por cliente.
- **Transporte** (`wk/runtime/llm.py`):
  - `_with_prompt_caching` (línea 940) se aplica solo donde el despliegue lo admite;
  - `_wire_openai_tool_names` se aplica a todo proveedor sin puntos;
  - `store=false` y `data_retention_mode: none`;
  - el nivel de razonamiento, por tarea;
  - `LLMRouter` y `build_default_router` arman los grupos con sus alternativas.
- **Juez y multimedia.** `wk/guardrails/outcome_grader.py` y
  `wk/runtime/grading_policy.py` piden la tarea `judge`, de otra familia.
  `wk/multimodal/processor.py` pide `vision` y `transcribe`.
- **Medidor.**
  - `wk/metering/collector.py` (`USAGE_SOURCES`) y `consumer.py::persist_rows`
    escriben la tarea, la decisión y la partida.
  - Los pesos salen de `api/metering/pricing_policy.py::weights_for`.
- **Proveedores**: Bedrock, por el rol IAM de la tarea, y Scaleway, con la clave en
  Secrets Manager. Cada despliegue entra solo con sus comprobaciones (requisito 41.2).
- **Certificación**: `api/services/certification.py` y `wk/certification/`, con la
  batería común en español, la suite por agente, sus caducidades y la certificación
  en segundo plano.
- **Calidad del agente**: `api/api/console/agent_quality.py`.
- **Admin**: `adm/models/`, `adm/router/` y `adm/certifications/`. Hoy no hay
  pantallas para los perfiles ni para las asignaciones (solo la API
  `api/api/admin/model_bindings.py`). La lista de cada partner sigue en
  `adm/partners/[id]/models`.
- **Avisos**: el cron `wk/streams/model_lifecycle_cron.py`.
- **Migración de la ola**:
  - cada agente queda fijado en su modelo de hoy;
  - `classify` pasa al certificado más barato para todos, tras la batería (D24).

### Ola 7 · Dinero

- **Bolsas y libro**: `api/services/wallet/` (`bags.py`, `ledger.py`, `fx.py`,
  `alerts.py`, `build_budget.py`), sobre `api/db/models/partner_wallet.py`
  (`PartnerWallet` → `partner_wallets`, `UsageLedger` → `usage_ledger`,
  `PartnerAllocation`).
  - Los traspasos escriben su asiento en `usage_ledger`, que gana kinds, y su
    gemelo en `client_wallet_entries`.
  - `fx.py` amplía `api/services/exchange_rate.py` (hoy CLP→USD) con el BCE y la
    tabla `fx_rates`.
- **Débito**:
  - `api/metering/wallet.py` gana el débito de la bolsa;
  - `allow_channel_turn` lee la bolsa y el tope del agente;
  - `wk/metering/consumer.py::_debit_channel_wallet` debita la bolsa, con el
    cruce del cero de `record_absorbed`.
- **Presupuesto de Auphere**: `wk/metering/budget.py` y `budget_gate.py`
  (requisito 44.8).
- **Crons**: `fx_rates_cron.py`, `bag_refill_cron.py`, `bag_alerts_cron.py` y
  `ledger_reconciliation_cron.py`. Hasta la reactivación,
  `wk/streams/usage_alerts_cron.py` sigue con lo de hoy.
- **Rutas**: `api/api/console/wallet.py`, `usage.py`, `billing.py`,
  `api/api/console/lite/usage.py` y `api/services/lite_home.py`.
- **Consola**: `con/app/(console)/usage/**` y `billing/**`, `con/components/{billing,home}/`
  y el modal «Asignar saldo».
- **Migración de la ola**:
  - la cuenta de cada partner queda en USD;
  - «Repartir tu saldo en bolsas» propone lo que le queda a cada cliente este mes;
  - hasta que el partner confirme, sigue `partner_allocations`;
  - `partners.qa_monthly_token_cap` deja paso a `partner_build_budget`.

### Ola 8 · Consola, consola lite, app y operador

- **Consola**:
  - el Panel del partner (`con/app/(console)/page.tsx`,
    `api/services/console_home_blocks.py`, `api/api/console/home.py`);
  - la Auditoría agrupada, con CSV (`api/api/console/audit.py`, `audit_words.py`
    y filas de `console_audit_vocabulary`);
  - Equipo, API y Notificaciones;
  - el espejo de permisos en `con/lib/permissions.ts`.
- **Consola lite**: **no tiene grupo de rutas propio**. La persona del cliente usa
  las rutas de `(console)` (`LitePanel`), y la guarda es
  `app/__tests__/page-guards.test.ts`. Lo nuevo:
  - `ClientModule` gana `agents` y `business` (`api/db/models/client_access.py`,
    `con/lib/principal-access.ts::CLIENT_MODULES`, `con/components/shell/lite-nav.ts`);
  - las pantallas `con/app/(console)/agentes/` y `negocio/`;
  - la API `api/api/console/lite/{agents,business,corrections}.py`, con el `deps.py` de la lite.
- **App** (`mob/src/app/`):
  - las pestañas salen de los módulos (`src/lib/modules.ts`), y Ajustes es una
    hoja (`ajustes.tsx`), no una pestaña;
  - «Agentes» va en Inicio (`(app)/inicio/`) y en `agente/[id].tsx`;
  - «Negocio» es una pila nueva (`negocio/{index,horario,servicios,sedes}.tsx`), que
    se abre desde Inicio y desde Ajustes;
  - los avisos van en `src/push/routing.ts::routeFor`;
  - las llamadas, en `src/api/{endpoints,hooks}.ts`;
  - se regeneran `openapi.json`, `schema.gen.ts` y `src/i18n/lite.gen.ts`.
- **Admin**:
  - activar la consola nueva: `adm/partners/[id]/console-v2`;
  - el tope de construcción: `adm/partners/[id]/limits`;
  - la restricción soberana: `adm/tenants/[id]/`;
  - la beta por país: `adm/channels/`;
  - las anomalías y las conciliaciones: `adm/status/`.

### Ola 9 · Mejora y Recepción

- **Sugerencias.**
  - `wk/streams/weekly_suggestions_cron.py` y `api/services/improvement/suggestions.py`.
  - Lee en el contexto del cliente y agrupa al menos 5 conversaciones de al menos
    5 contactos.
  - Escribe una paráfrasis sin datos personales y una propuesta con su prueba.
  - Rendimiento solo devuelve metadatos y agregados, a través de
    `api/api/console/conversations.py`, que ya sirve metadatos, y de una ruta nueva
    por agente.
- **Correcciones.** `api/services/improvement/{corrections,paraphrase,pii}.py` y
  `api/api/console/lite/corrections.py`, sobre la Bandeja de hoy (`lite/inbox.py`):
  la web y la conversación de la app (`mob/src/app/conversacion/[id]/`).
- **Recepción.**
  - `mcp/servers/reception/` (`reception.handoff`), con el registro
    (`mcp/registry.py`) y la migración del catálogo con su JSON
    (`alembic/data/NNNN_reception_tool.json`), como hizo la 043.
  - El hilo separa el estado de cada agente.
  - A la tercera ida y vuelta, la conversación pasa a una persona.

### Ola 10 · Migración y activación

- **Ensayo**: `api/services/console_v2.py` corre cada migración de datos en una
  transacción que se deshace.
  - Compara la batería de cada agente (`services/evals/runner.py::run_eval`) y la
    audiencia efectiva de cada número, antes y después.
  - Escribe `migration_reports`.
- **Activación**: desde el admin, solo con el informe sin diferencias. Se puede
  desactivar hasta que el partner confirme el reparto.
- **Retirada de lo viejo**: cuando nadie use la consola de hoy, las rutas viejas
  (`/clients/{ref}/agent`, `clients/new` y la ficha de nueve pestañas) responden 410
  con la nueva, y se retiran las proyecciones del horario.

### Documentación (mismo commit que el cambio)

| Documento | Cambio |
|---|---|
| `docs/console.md` | Marco, clientes, agentes y canales |
| `docs/consola-lite.md` | Agentes, Negocio y correcciones |
| `docs/app-movil.md` | Pantallas, avisos y versión |
| `docs/admin.md` | Catálogo, router, certificación, activación y anomalías |
| `docs/billing.md` | Bolsas, libro, BCE y partidas |
| `docs/reservas.md` | Horario único |
| `docs/partner-integration.md` | La puerta en la API; el alta sin agente por defecto |
| `docs/agentes.md` (nuevo) | AgentSpec, constructor, pruebas, puerta, estados y versiones |
| `docs/canales.md` (nuevo) | ES v5, coexistencia, página del canal y enlace del dueño |
| `docs/modelos-y-router.md` (nuevo) | Catálogo, perfiles, router y certificación |
| `docs/ficha-del-negocio.md` (nuevo) | Ficha, ClientSpec, procedencia y lectura |
| `apps/api/tests/isolation/README.md` | La garantía 9 y los barridos `test_43`–`test_52` |

## Enmienda del 2026-10-29 · Ola 11 · Lista para staging

Requisitos 57 a 64 (`spec.md`, bloque R) y decisiones D46–D55 (`research.md`,
parte 6b). Nota de KB: `research/2026-10-29-auditoria-del-constructor/_index.md`.
Las tareas son la fase 27 de `tasks.md`. Va **después de la spec 048** (retirar
AgendaPro y `booking.*`), porque las guías del sector salen de las plantillas ya
pasadas a Reservas.

### Constitution Check de la enmienda

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Tablas nuevas por cliente (la guía generada y sus pruebas, las conversaciones de las pruebas): RLS FORCE y FK compuestas; entran solas en `test_43`. La guía generada es **del cliente**, nunca compartida (D47); un barrido nuevo comprueba que el prompt del constructor no lleva nada de otro cliente. Las herramientas pendientes no cambian la garantía 2: el runtime ve la intersección con las activaciones (D53), y `test_44` lo barre |
| II | Superficie | ☑ | `0`. El navegador de respaldo no es una superficie de entrada: es un servicio interno sin ruta pública que solo llama el worker, con token y las mismas guardas de direcciones públicas que el lector (D50) |
| III | Lo leído es dato | ☑ | El JSON-LD, la página renderizada, la etiqueta del sector y la salida del cliente simulado son datos no confiables: van vallados y se validan contra esquemas cerrados (la lista de claves de sector, la extracción solo de datos del negocio). Prueba adversarial: un JSON-LD y una página renderizada que dan órdenes |
| IV | Acción `mutates` | ☑ | El constructor del cliente solo propone; aceptar, editar o descartar lo hace una persona, con auditoría. Los agentes sugeridos no se crean solos |
| V | Estados honestos | ☑ | «Calidad» deja de ofrecer lo que no atiende (D55). Las redes que no dejan leer se dicen como tales. La guía y las pruebas generadas llevan «Generada». Cinco estados en cada vista nueva |
| VI | Por API | ☑ | Todo por `/console/*` y `/admin/*` |
| VII | Test primero | ☑ | Cada criterio, con su test en rojo antes (fase 27) |
| VIII | Licencias | ☑ | Playwright (Apache-2.0) y Chromium (BSD-3-Clause), solo en el servicio de renderizado; párrafo citado en la tarea que lo añade. Ninguna dependencia nueva en la API ni en el worker |
| IX | KB | ☑ | `[[research/2026-10-29-auditoria-del-constructor/_index]]` · ADR-049 §Enmiendas |

**Medidor.** Identificar el sector, generar la guía, el constructor del cliente,
la extracción con su reintento, el cliente simulado y el juez van a «Construcción
y pruebas», con su tarea en `usage_records`. El renderizado no llama a ningún
modelo; su coste es de máquina y no se repercute (como la lectura de hoy).

### Diseño

- **Sector (R57).** Columnas nuevas en la ficha del cliente (`business_profiles`
  o donde viva el nicho): `sector_key`, `sector_label`, `sector_confidence`,
  `sector_source`, `sector_decided_by`. Un trabajo `sector_identify` en el worker,
  encolado al alta, al terminar `client_read` y al cambiar nicho o información;
  una sola llamada con salida JSON validada contra la lista cerrada de claves.
  `sectors.py` queda como respaldo con palabras enteras. Todo lo que hoy llama a
  `sector_of_niche` lee el sector guardado.
- **Guías (R58).** `services/builder/guides/` con una guía por sector, en datos,
  derivada de las plantillas ya pasadas a Reservas por la 048. `build_messages`
  añade la guía y el patrón del papel. Tabla por cliente `generated_guides` (guía y
  12 pruebas, `status = generated`). Admin: listado de etiquetas sin guía y
  «Convertir en guía de Auphere». «Desde una plantilla» pasa por el mismo
  `write_new_agent`. El banco de evaluación gana sectores sin guía y nombres reales,
  y mide las pruebas del sector.
- **Lectura (R59).** `reader.py`: el parser guarda el JSON-LD y los microdatos; un
  extractor determinista los pasa a la extracción con procedencia `structured`;
  `sitemap.xml` para elegir páginas; lectura con `asyncio.Semaphore(4)`; redes
  permitidas también con web; reintento de la extracción. Sin relectura periódica:
  se retira `source_reread_cron` (y su nombre del contrato de crons), y las rutas
  que cambian la web o las redes encolan `client_read` si el valor cambió. El
  Panel monta la tarjeta de lectura.
- **Navegador de respaldo (R59.2).** `apps/renderer/` (Python 3.11, FastAPI,
  Playwright con Chromium): `POST /render` con token, una página por petición,
  20 s y 2 MB como mucho. Chromium sale por un proxy local que resuelve y conecta él
  mismo y rechaza direcciones no públicas en cada conexión (también tras
  redirecciones y en los recursos de la página), así que el rebinding de DNS no
  sirve. Imagen y servicio propios en Terraform, apagados por defecto
  (`renderer_enabled = false`); el worker lo usa solo si `NEXUS_RENDERER_URL` está
  puesta.
- **Constructor del cliente (R60).** Al terminar `client_read` (y al cambiar el
  sector) se encola `client_profile` con la huella de la ficha como clave de
  idempotencia; reintentos con espera creciente (3). Sus propuestas se guardan como
  sugerencias de sección (`business_suggestions`) para Políticas y Preguntas
  frecuentes, y los agentes sugeridos, aparte. Negocio gana las secciones
  «Políticas» y «Preguntas frecuentes»; Agentes, las tarjetas «Sugerido».
- **Pruebas de varios turnos (R61).** `agent_tests.py::_attempt` pasa a un bucle:
  turno del agente (`run_turn` con la agenda simulada) → turno del cliente simulado
  (modelo de simulación, con persona, plan y la conversación) → condición de
  parada. `world.final_state()` se amplía con las citas de Reservas, el escalado y
  los enlaces de pago. La conversación se guarda en el resultado de cada pasada.
  Modelos: `NEXUS_LLM_CUSTOMER_SIM_MODEL` y `NEXUS_LLM_JUDGE_MODEL` (configuración
  de plataforma, R64).
- **Herramientas pendientes (R62).** `sanitize` deja de quitar las herramientas no
  conectadas: las guarda en `spec.tools` con su petición en `connection_requests`.
  El validador acepta una herramienta del catálogo permitida al partner aunque no
  esté conectada. Al activar un conector para un agente, sus pruebas afectadas se
  marcan desactualizadas. En la consola, «Conectar {X}» abre `ConnectDialog` en el
  sitio.
- **Pantallas (R63).** Las de `evidence/prototipo/agente.md` §H5, §H9 y §H10.
- **Modelos (R64).** `agent-model-quality.tsx` se desmonta y Avanzado enseña una
  línea; la ruta de cambiar la política responde 409 `model_policy_managed`.

### Documentación de la enmienda (mismo commit que el cambio)

| Documento | Cambio |
|---|---|
| `docs/ficha-del-negocio.md` | Sector, lectura (JSON-LD, sitemap, redes, navegador), sin relectura periódica, constructor del cliente, Políticas y Preguntas frecuentes |
| `docs/agentes.md` | Guía × papel × ficha, guías generadas, herramientas pendientes, pruebas de varios turnos |
| `docs/console.md` | Canal dentro del agente, Rendimiento, Conectores, sin «Calidad» |
| `docs/modelos-y-router.md` | La restricción del requisito 64 |
| `docs/admin.md` | Sectores sin guía y «Convertir en guía» |
| `docs/renderer.md` (nuevo) | El servicio de renderizado, sus guardas y cómo encenderlo |

## Enmienda del 2026-10-30 · Solo lo que tenemos

**Qué cubre:** el requisito 65 y la precisión del 58.2 (`spec.md`). Las decisiones del owner están en Clarifications, sesión 2026-10-30. Las tareas son la fase 28 de `tasks.md`.

**Orden:** va después del paso 4 de la fase 27 (T201, T202 y T206), que ya cubre:
- 65.1 en las guías: patrones combinables, ninguno filtra herramientas;
- 65.2 para `reservas.*`;
- 65.7 para el constructor: lo que hace cada herramienta;
- 65.13.

Lo que T201 deje hecho se marca en la fase 28 con su referencia y no se repite.

### Constitution Check de la enmienda

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Sin tablas nuevas. 65.11 cierra un fallo abierto de la garantía 2, con su caso en `tests/isolation/` |
| II | Superficie | ☑ | `0`. `PUT /console/clients/{ref}/tools` se cierra para agentes estructurados |
| III | Lo leído es dato | ☑ | Sin cambios |
| IV | Acción `mutates` | ☑ | El constructor sigue proponiendo; nada se publica solo |
| V | Estados honestos | ☑ | Es el objeto de la enmienda: «No tenemos herramienta para: …» y promesas que bloquean |
| VI | Por API | ☑ | Todo por `/console/*` |
| VII | Test primero | ☑ | Fase 28: pruebas en rojo antes |
| VIII | Licencias | ☑ | Sin dependencias nuevas |
| IX | KB | ☑ | Nota de coordinación `evidence/enmienda-2026-10-29.md` |

### Diseño (dónde, según la auditoría del 2026-10-30)

Rutas relativas a `apps/api/src/nexus_api` salvo que se diga otra cosa.

- **65.2.** En `load_context` (`services/agent_spec/validator.py`) y `api/console/capability_names.py`, `reservas.*` con `ClientAccess.reservas_on` apagado cuentan como no conectadas y sin activación. La simulación (`apps/worker/src/nexus_worker/simulation/registry.py`) respeta el módulo.
- **65.3 y 65.4.**
  - `sanitize` (`services/builder/agent_draft.py`) quita las integraciones que no son conectores ofrecidos y las anota como `capability_missing`.
  - El validador da `integration_unknown`.
  - La consola pinta lo descartado (`apps/console/src/lib/backend/builder-types.ts`, `components/builder/block-view.tsx`).
- **65.5.**
  - `promises_without_tool` (`services/agent_spec/compiler.py`) compara con lo que hace cada herramienta según `capability_names`, no con su prefijo.
  - `services/agent_spec/review.py` le da gravedad «bloquea».
  - `services/publishing.py` la mete en la puerta.
- **65.6.** El compilador gana una sección fija «Lo que no haces», con las alternativas de las habilidades.
- **65.7.**
  - El copiloto (`services/builder/copilot_model.py`, y las reglas sin modelo de `copilot.py`) y las sugerencias (`services/builder/client_profile.py`) reciben las herramientas disponibles con lo que hace cada una.
  - El esquema de las sugerencias admite cualquier papel o ninguno.
- **65.8.**
  - Cada prueba del sector declara las familias de herramientas que necesita, en su catálogo (`services/testing/sector_catalog.py` y sus datos).
  - `add_sector_tests` marca «No aplica» sola.
  - Si hace falta una columna, va en una migración nueva sobre la cabeza de entonces.
- **65.9.** En `services/publishing.py`, «sin pruebas» deja de contar como aprobado para un agente estructurado.
- **65.10.** `api/console/tools.py` responde 409 `structured_agent` para un agente con AgentSpec.
- **65.11.** `_load_tool_policy` (`apps/worker/src/nexus_worker/runtime/pipeline.py`) falla cerrado: sin política, ninguna herramienta de conector.
- **65.12.** `services/builder/agent_draft.py`:
  - una ficha que no carga da `facts_unavailable`, en vez de seguir con `Facts(name="")`;
  - un modelo sin instrucciones cuenta como fallo del constructor.

**Fuera de la enmienda, como seguimiento:**
- los nombres de herramientas de Composio en el AgentSpec;
- el enrutado del turno por intenciones de vertical.

**Documentación**, en el mismo cambio:
- `docs/agentes.md`: el requisito 65;
- `docs/console.md`: «No tenemos herramienta para: …».

## Estructura

```text
apps/api/alembic/versions/0175_*.py …                # una o dos migraciones por ola, reversibles
apps/api/alembic/data/NNNN_reception_tool.json         # P3
apps/api/scripts/dev_seed_fabrica.py
apps/api/src/nexus_api/
  db/models/{business,agent_spec,testing,jobs,channel_config,activation,wallet_bags,router,improvement}.py
  services/business/{profile,sections,locations,hours,special_dates,services_catalog,faqs,links,
                     provenance,history,suggestions,client_spec,reader}.py
  services/agent_spec/{schema,compiler,validator,review,legacy}.py
  services/builder/{agent_draft,client_profile,tests_gen,fixes,copilot}.py + prompts/
  services/testing/{suites,sector_catalog,judge}.py
  services/{jobs,publishing,agent_lifecycle,channel_config,activations,attention,
            router_catalog,certification,console_v2,proposal_state}.py
  services/knowledge/{layers,retrieval,teach}.py
  services/wallet/{bags,ledger,fx,alerts,build_budget}.py
  services/improvement/{suggestions,corrections,paraphrase,pii}.py
  api/console/{business,agent_builder,agent_quality,channel_config,activations,
               usage_lines,search,jobs,improvements}.py
  api/console/lite/{agents,business,corrections}.py
  api/admin/{models_catalog,router,certifications,builder_eval,sector_tests,console_v2,whatsapp_beta}.py
apps/api/tests/isolation/test_43_*.py … test_52_*.py
apps/api/tests/{unit,integration}/…                  # ver tasks.md
apps/worker/src/nexus_worker/
  runtime/{dispatcher,pipeline,llm,model_resolver,agent_loader,budget_gate,checkpointer}.py   # cambios
  builder/ · simulation/ · certification/
  streams/{meta_reconciliation,fx_rates,bag_refill,bag_alerts,ledger_reconciliation,
           source_reread,model_lifecycle,weekly_suggestions}_cron.py
  streams/meta_{echoes,history,state_sync}_consumer.py
  bootstrap.py                                         # + apps/worker/tests/unit/test_bootstrap_split.py
apps/channels/src/nexus_channels/whatsapp_meta/signup.py
apps/mcp/src/nexus_mcp/servers/{reservas,booking,escalate,composio_proxy}/ · servers/reception/ (P3)
apps/console/src/
  components/shell/ · components/{clients,business,agents,builder,channels,integrations,
                                  knowledge,quality,money,home,audit,lite}/
  app/(console)/{page.tsx,clients/**,usage/**,audit/**,team/**,billing/**,notifications/**,agentes/**,negocio/**}
  lib/{meta-fb-sdk,permissions,principal-access}.ts · i18n/lanes/*.ts
apps/admin/src/app/(dashboard)/{models,router,certifications,builder,
                                partners/[id]/{console-v2,limits,models},channels,status,tenants/[id]}/**
apps/mobile/src/app/{(app)/inicio,agente,negocio,ajustes.tsx} · src/{api,push,lib}/
packages/ui/src/{styles/tokens.css,components/{tabs,dialog,sonner,status-badge,command-palette,block-chart,money}.tsx}
docs/{console,consola-lite,app-movil,admin,billing,reservas,partner-integration,agentes,canales,
      modelos-y-router,ficha-del-negocio}.md
```

## Complexity Tracking

| Añadido | Por qué |
|---|---|
| Tabla `jobs` genérica, en vez de una por tipo | Ocho tipos de trabajo largo con el mismo ciclo (cola, progreso, resultado, caducidad) y una sola ruta de consulta para la consola |
| `agent_version_compilations` (historia) | La ficha se aplica al momento (requisito 8.4) sin crear versiones (D4). El runtime sigue leyendo `system_prompt_rendered` (constitución); la tabla dice qué prompt respondió cada turno |
| `business_sections`, con revisión por sección | `If-Match` por sección: dos personas editando el horario y los servicios a la vez no chocan |
| Proyecciones del horario mientras haya lectores viejos | Seis lectores y tres escritores (Reservas, `booking.*`, avisos, lite, prompt) leen las copias de hoy. Cortarlos de golpe rompería la 043 |
| Búsqueda exacta en lugar de un índice ANN | Requisito 38.4: el índice no se comparte entre clientes. Al tamaño de hoy, los milisegundos no lo justifican (D14) |
| Dos consolas vivas durante la migración | La activación partner a partner (D38). La API sirve a las dos, y las rutas viejas se retiran al final |
| `fx_rates` persistida, frente al caché en memoria de `exchange_rate.py` | Cada traspaso guarda el cambio que usó, y el cuadre diario lo vuelve a leer |
| Las decisiones del router en el log, no en una tabla | Hay varias por turno. `usage_records.route_decision_id` las enlaza, y las anomalías sí van a tabla |
| `test_43` barre **todas** las tablas de cliente, con un inventario escrito de excepciones para las de antes | §I: «el test de una garantía nueva no enumera los sitios conocidos — barre». Hoy `test_21` no exige FORCE en las tablas normales y no hay barrido de FK compuestas. Las tablas de antes que no cumplan entran en el inventario con su razón; ninguna tabla nueva puede entrar en él |
| Consumidores de coexistencia nuevos | Los streams de ecos, historial y sincronización existen y nadie los lee. Sin consumidor, el requisito 30.11 no se cumple |
