# Progreso de la implementación — spec 047

Lo que sobrevive a una compactación. Se actualiza al cerrar cada bloque.

## Dónde se trabaja

- **Worktree**: `/Users/lmatos/Workspace/nexus/.claude/worktrees/047-impl`, rama
  `047-la-fabrica-de-agentes-impl`, cortada de `047-la-fabrica-de-agentes`
  (`89b8c81f`). Nunca en el checkout principal.
- **Bases de prueba** (una por track; nunca dos suites contra la misma): coordinador
  `nexus_047_coord` (Redis 10); tracks `nexus_047_<track>` (Redis 11–14). URL:
  `postgresql+asyncpg://nexus:nexus@localhost:5433/<base>`. El `conftest` borra y
  vuelve a migrar la base al empezar cada sesión de pytest. La API y el worker se
  corren en llamadas separadas (los dos paquetes de tests se llaman `tests`).
- **Cadena de migraciones**: `0174` → `0175_fabrica_base` → `0176` … `0182_router_profiles_v1`.
  La siguiente es la **0183** (la del bloque C, ya redactada).
- **Modo de trabajo** (Luis, 2026-10-27): avanzar hasta el final sin pedir
  aprobaciones; Luis lo revisa todo al terminar.

## Cómo quedan los commits (Luis los hace al final)

Nada está commiteado: los hace Luis con `bash .claude/commits/commit-all.sh` (en el
worktree; `.claude/` lo ignora git). El guion comprueba que `HEAD` es la base y
commitea en orden, un commit por fase:
- **A1** ya está en el índice; **A2** es `A-fase2.patch` más los dos `uv.lock` (una
  regla impide a la sesión tocar `uv.lock` con git);
- **B0, F3, F4, F5 y F16** son `B-*.patch`, construidos uno sobre otro en un índice
  temporal (`scratchpad/commits/build_patches.sh`), y ensayados en cadena.

Cada bloque congela así su trabajo: lo que hace el bloque siguiente no entra en los
commits del anterior. Nadie de los tracks hace `git add`.

Los bloques A a C entraron en `fa716e82`. Lo de después (fases 8 a 26) se commiteó
el 2026-10-28 en esta rama, sin push, un commit por grupo de fases y en el orden de
la cadena de migraciones: 8–9 (0187, 0188), 10–11 (0189), 12–13 (0190–0192),
14–15 (0193, 0194), 16–17, 18 (0195, 0196), 19–21 (0197, 0198), 22–24 (0199,
0200), 25 (0201) y 26 (0202). El reparto es por archivo: un archivo que tocan
varias fases va en la última que lo toca, y los registros comunes (modelos,
routers, trabajos) en el de la 26. Solo la punta está probada entera. Los commits
intermedios no compilan solos: las fases se construyeron entrelazadas y 64
importaciones apuntan a un archivo de un commit posterior (por ejemplo,
`agent-builder.tsx` usa los tipos de siete fases). Sirven para leer la rama por
fases; la rama se fusiona entera y no se lleva una fase suelta con `cherry-pick`.

## Spec 046 (Andrés) — comprobado el 2026-10-26

- Nada de la 046 está en `develop`: su rama lleva la constitución 1.2.0 y la
  iteración 1a (catálogo y asistente de canales). Su 1b no está en ninguna rama, así
  que T025 y T032 se construyeron aquí, y T109 se construirá.
- **T001 (constitución 1.3.0) espera** a que la 1.2.0 esté en `develop`.
- T107, T109 y T115 reutilizan el asistente de la 1a: necesitan la 046 fusionada.

## Decisiones tomadas al implementar

- **D43**: sin Dramatiq; trabajos por `nexus:jobs` (`jobs-consumer`) y la agrupación
  por una cola diferida de Redis.
- **D44**: ningún despliegue de hoy tiene la retención cero comprobada; el router
  nuevo no elige ninguno y los agentes de hoy siguen fijados en su modelo.
- `job_tenant(job_id)` (SECURITY DEFINER) para `GET /console/jobs/{id}`.
- El verde profundo del primario es global (T005).
- Las certificaciones que paga Auphere van a la partida `platform`, fuera de las del
  partner (requisito 42.6).
- `events.md` §5: `turn.coalesced` lleva `message_count` (no `messages`), y
  `llm.route_decision` lleva `decision_id`, `agent_version` y `conversation_id`.
- Las migraciones posteriores de `tasks.md` llevan `NNNN` hasta escribirse.

## Bloque A — Base (fases 1 y 2) · cerrado el 2026-10-26

T002–T022 hechas (T001 en espera). Coordinador: la 0175 y su prueba, `pgvector`
(T022) y el contrato (`console_version`, `JobOut`, `SearchOut`). Tracks: A1 `@nexus/ui`
y el marco v2 · A2 trabajos, `console_v2`, ⌘K, estado visible y atención · A3 los
barridos `test_43`–`test_52` · A4 la semilla `dev_seed_fabrica.py`.
`verify.sh`: verde salvo los locks (a propósito, T022) y `expo-doctor` (parches de
Expo publicados en internet; la app no cambia dependencias).

## Bloque B — Olas 1, 2 (alta) y 6 (núcleo del router) · cerrado el 2026-10-27

T023–T050 y T135–T141, T143, T144 hechas. Coordinador: las migraciones 0176–0180 con
sus modelos y `test_migration_047_block_b.py`; el contrato del colector (sin él, una
lectura de web se habría cobrado al cliente); `0182_router_profiles_v1`; el cron
`meta-reconciliation-cron` en el planificador; el modo estricto del medidor
(`NEXUS_USAGE_REQUIRE_TASK=1` en los `conftest`), que destapó dobles de prueba sin
tarea (corregidos); la API carga el catálogo de modelos al arrancar.
- **B1** (T023–T037): guardar todo entrante antes de las puertas, el turno agrupado
  de 3 s de uno en uno (candado de transacción + arriendo en `turn_effects`, por
  PgBouncer en modo transaction), efectos idempotentes, la Bandeja con motivo, la
  tarea y la partida en el medidor, y la conciliación diaria con Meta.
- **B2** (T038–T041): un borrador por agente con `If-Match` (412 con los cambios),
  «v{n}», descartar que archiva, la barra única en la consola. Coordinador: la frase
  de `agent_config.discard` y archivar los `staged` más viejos que la activa (0178).
- **B3** (T042–T050 y `0181_clients_active`): el alta en tres datos sin agente, la
  deducción de país y monedas, la detección de enlaces, la lectura de la web en
  segundo plano (`client_read`), el modal de la consola. La 0181 solo pasa a `active`
  los `provisioning` sin versión publicada.
- **B4** (T135–T141, T143, T144): el catálogo, `chain_for`, la afinidad, el
  transporte por capacidad, la certificación por clase y por agente, y
  `docs/modelos-y-router.md`.

`verify.sh`: la API 6760 en verde y 10 en rojo, todos por el modo estricto (dobles
sin tarea) más uno de carga (`test_lite_send_idempotency`, verde a solas); el worker,
6 por lo mismo. Corregidos y repetidos en verde, más `verify.sh lint` entero. Quedan
los locks y `expo-doctor`, como en el A.

**Quedó para bloques siguientes:**
- C1: aplicar lo leído que hoy queda en sugerencias (`/locations/-`, `/hours`,
  `/services/-`, `/faqs/-`), y la recompilación por revisión (T059).
- C3: el router en el grafo (clasificador tipado, escalado, afinidad,
  `conversation_id` en `llm.route_decision`), y la tarea de `wk/multimodal/processor.py`.
- G: `wallet_currency` y la moneda de la cuenta (hoy USD por defecto); `partners.country`
  para la segunda fuente de la deducción.
- D: el trabajo de `certify_in_background` (necesita la suite).
- B2: `GET draft` aún sin AgentSpec, vista previa ni pruebas (ola 3).
- `test_model_catalog_matches_db` compara solo `active`.
- Observación de B1: `nexus_api/core/leader.py` usa un candado de sesión a través de
  PgBouncer en modo transaction; puede fallar en la elección de líder. Sin tocar.
- Las pruebas de consola de B2 y B3 se escribieron junto a los componentes, no en
  rojo primero (la API sí fue rojo primero).

## Pendientes de Luis (no bloquean)

- Fusionar la 046 en `develop` (para T001, T107, T109 y T115).
- Confirmar la retención cero con OpenAI y Anthropic, o dar de alta Bedrock y Scaleway
  como subprocesadores (T142): sin eso, el router nuevo no elige ningún modelo (D44).
- El bug de la garantía 8 (sesión aparte, rama `laughing-poitras-e07cc2`): arreglado
  y pendiente de su commit.
- Alinear `spec.md` (Marta en Barbería Cultor) con `quickstart.md` (en Flor y Encanto).

## Defectos de aislamiento anteriores a la 047

1. **Garantía 8** (herramientas que buscan a un cliente final en un agente abierto):
   en su sesión aparte, arreglado.
2. **Garantía 1, baja**: `booking.create_appointment` y `queue.join_queue` aceptan un
   `barber_id` de otro cliente (FK de una columna a `kg_nodes`). En el inventario de
   `test_43`.
3. El teardown del `conftest` borra de `tool_catalog` filas que siembran las
   migraciones; las pruebas que dependen de ellas cambian con el orden.

## Bloque C — siguiente

Redactado: `0183_business_hours_services` (scratchpad `blockC/`) y, en el árbol, el
contrato de escritura de la ficha (`services/business/writes.py`, `compilation.py`
y `T/integration/business/test_section_writes.py`).

## Retoma (Claude, por encargo de Andrés) · 2026-10-27

La sesión de Luis se quedó sin tokens tras commitear todo en `fa716e82`
(«feat: improve agent creation and create constructor agente»). Se retoma en el
worktree `/Users/matos/workspace/Auphere/auphere-047` (rama
`047-la-fabrica-de-agentes-impl`), con base de pruebas propia `nexus_047`
(Redis 11): `NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_047`.

**Estado real encontrado** (más de lo que decía este documento):
- Bloque C hecho en código y en verde aunque `tasks.md` no lo marcaba: fases 6 y 7
  (T051–T072), más T142 en borrador (0185), T145 (D45), T148–T150 (ciclo de vida de
  modelos y pantallas del admin). Batería: 281 pruebas de la API en verde
  (`tests/integration/{business,clients,models}`, migraciones 0183/0185/0186 y los
  unitarios de horario, ClientSpec, deducción y enlaces).
- Consola: `tsc` tenía un error en `hours-model.test.ts` (corregido). Vitest de la
  consola (1162), admin (238) y `@nexus/ui` (252) en verde; los rojos que salen con
  la máquina cargada son tiempos agotados de 5 s, en verde a solas.
- Cadena de migraciones: … `0185_bedrock_scaleway_drafts` → `0186_migrate_hours_to_ficha`
  → **`0187_agent_spec_and_testing`** (nueva, fase 8). No hay 0184.

**Bloque D (fase 8 en adelante), en curso:**
- Hecho: `services/agent_spec/{schema,compiler,validator,legacy}.py`, la migración
  0187 y `db/models/agent_spec.py`; pruebas `test_agent_spec_{contract,validator,compiler}.py`
  (50 en verde). `test_44` gana `proposals`, `agent_test_suites` y `agent_test_runs`.
- Decisión: el borrador de un agente **nuevo** lo escribe el trabajo `agent_draft`
  directamente (lo pidió una persona al pulsar «Generar borrador» y no atiende a
  nadie hasta pasar la puerta); sobre un agente que ya tiene versión, el
  constructor y el copiloto solo proponen (`proposals`).
- Decisión: en local, con `llm_use_inmemory`, el constructor usa un generador
  determinista (sin modelo) para poder recorrer el flujo entero sin claves.
- **Fase 8 (backend) y fase 9 (backend) hechas el 2026-10-27**: constructor
  (`services/builder/`, trabajo `agent_draft`), propuestas (`services/proposal_state.py`),
  playground sobre el borrador (`wk/simulation/`), suite con 3 pasadas y juez
  (`services/testing/`, trabajo `tests`), revisión (`agent_spec/review.py`),
  catálogo del sector v1 (migración 0188) y calibración del juez. Pruebas:
  `T/integration/builder/` (36) y unitarias `test_agent_spec_*`, `test_agent_review`.
- La consola de la fase 8 (T081) la está haciendo un subagente en `apps/console`
  (pestaña Agentes v2, «Nuevo agente», pantalla del agente).
- **Fase 10 y fase 11 (backend) hechas el 2026-10-27**: la puerta única
  (`services/publishing.py`, trabajo `publish`, rutas `agent_publish.py`) en la
  consola nueva, la de hoy, el admin y la API de partners; deshacer, historial y
  restaurar; migración `0189_agent_spec_from_prompts`; constructor del cliente
  (`client_builder`) y copiloto (`agent_copilot.py`); evaluación del constructor
  (`/admin/builder/eval`). Decisión: la puerta es **estricta** con agentes
  «structured» o de partners con la consola nueva; con agentes de antes de
  partners sin activar, integración sin conectar y bloqueantes de la revisión se
  avisan sin bloquear (historia 13). El admin y la API de partners toman la
  decisión de aviso de IA de hoy (CP-31) al publicar.
- Pendiente de consola (subagente en curso): T089 y T094 (playground, pruebas,
  revisión, barra de guardar). Luego: revisión por secciones (T098), panel del
  copiloto (T099), y en el admin las pantallas de T087, T090, T100.
- Cadena de migraciones: … `0187` → `0188_sector_tests_v1` → `0189_agent_spec_from_prompts`.
- Bases de pruebas: `nexus_047` (Redis 11) y `nexus_047b` (Redis 12) para correr dos
  suites a la vez.
- **Fase 13 (backend) hecha el 2026-10-27** (bloque E): migración `0190_agent_lifecycle`
  (vida, pausa con motivo, `before_pause`, `is_default` único, `is_reception`,
  `monthly_cap_micros`), `services/agent_states.py`, rutas
  `agent_lifecycle_routes.py`, el despachador respeta la pausa del agente. Consola
  T124 + T098/T099 (consola) encargadas al subagente.

## Bloques F y G — dinero, Panel, lite, app, mejora y Recepción · 2026-10-28

Retomado por Claude por encargo de Andrés. Commiteado el 2026-10-28 (ver «Cómo
quedan los commits»).
Bases de pruebas: `nexus_047` a `nexus_047e` (Redis 11 a 15), una suite por base:
los fixtures truncan tablas y dos procesos en la misma base se pisan.

**Cadena de migraciones**: … → `0195_client_wallets` → `0196_usage_lines_reporting`
→ `0197_audit_vocabulary_047` → `0198_lite_and_corrections` → `0199_agent_suggestions`
→ `0200_reception` → `0201_console_v2_reports`. `alembic_version` es `varchar(32)`:
los nombres largos no caben (por eso `0198_lite_and_corrections`).

**Decisiones**:
- **Las bolsas son tablas del cliente** (`client_wallets`, `client_wallet_entries`,
  `balance_requests`, `agent_monthly_spend`): RLS canónica por `tenant_id` (garantía
  1, `test_21`, `test_22` y `test_43`). El partner las toca cliente a cliente con
  `bags.as_client(session, tenant_id)` (vacía lo pendiente y pone el GUC del
  cliente). Los traspasos y lo del partner (`wallet_transfers`,
  `partner_build_budget`, `build_budget_requests`, `wallet_migration_proposals`,
  `migration_reports`) siguen con RLS por partner. La política de lectura de
  `daily_cost_snapshots` para `nexus_reporting` se quitó: el gasto de Meta se lee
  por cliente.
- **Unidades**: el dinero va en cien milésimas (`amount_micros`, 1e-5) con su
  moneda; precio = coste × 2,2; el cambio es el del BCE del día (`fx_rates`).
  Las partidas de Consumo y el asiento de cada bolsa llevan `seq` para el orden.
- **Bolsas activas**: con bolsas, `seed_default_allocation` no reparte nada (las
  bolsas mandan). La puerta del turno lee todo en una consulta (`gate_facts`).
- **Audiencia y activación estrictas** solo para partners con la consola nueva;
  los demás siguen con lo de hoy (`admin_access`, historia 13).
- **`gate.decision`** lleva `outcome` (no `result`), y el bloqueo su `blocking`.
- **Recepción**: a la tercera ida y vuelta (quinto salto) la conversación espera
  a una persona con `reception_loop`. `agents.is_reception` dice lo publicado y
  sale en la tarjeta y la cabecera del agente.
- **Correcciones**: el tipo (dato o comportamiento) es una regla determinista; los
  datos personales bloquean en todos los alcances; un dato se puede deshacer.
- **Escrituras de la lite**: `Idempotency-Key` se honra en Negocio (Redis, un día
  por cliente, ruta y clave, guardado tras el commit); el horario de una sede se
  lee con `GET /console/lite/business/hours?location_id=` y su revisión es la de
  Sedes.
- **Avisos**: `agent.tests.failing` sale del trabajo de pruebas cuando una pasada
  por un cambio de la ficha deja rojos (requisito 13.7). Los avisos del cliente
  enlazan a la lite (`LITE_LINKS`); la consola tiene palabras para los 21 tipos
  nuevos (`i18n/lanes/notices.ts`).

**Huecos de la API anotados, sin rodear**: las pausas de agentes y números no
declaran `If-Match` ni `Idempotency-Key`; `GET /business` de la lite no lista lo
archivado; el 412 de Negocio nombra a la persona por su id; `PriceOut` y `HoursIn`
van poco tipados en el OpenAPI; los conectores no tienen estado «Pendiente» ni
«Próximamente»; los asientos de la cuenta siguen en USD si Auphere cambia la
moneda de la cuenta (`billing/credit` es solo USD); `admin_only` de Recepción no
se comprueba contra el agente destino; la prueba de rendimiento de la búsqueda de
conocimiento falla con la máquina cargada.

**Regresión completa de la API (2026-10-28)**, en cuatro bases a la vez
(`tests/unit`, `tests/release` y las carpetas de `tests/integration`;
`tests/isolation`; y los archivos de `tests/integration` en dos mitades):
8.110 en verde y 17 en rojo. Qué era cada rojo:
- **Pruebas que esperaban lo de antes** (se actualizan): el teléfono nace con
  `agents.state` encendido; `reception.handoff` es la herramienta 42 del
  catálogo; `channel.problem` va al partner y al cliente (dos avisos); la
  Auditoría agrupa lo mismo de la misma persona y día (`group=false` para
  paginar); la capa y la papelera del conocimiento salen en el listado del admin
  (sin texto); los borradores de Bedrock y Scaleway (0185) no tienen precio a
  propósito.
- **Defectos de verdad, corregidos**:
  - `GET /console/clients/{ref}/channels/diagnostics` respondía 422: la página
    del canal (`/channels/{channel_id}`) se registraba antes y lo capturaba.
    Ahora `diagnostics` va primero (un barrido de rutas confirma que no queda
    otra sombra nueva; la de `/admin/tenants/{id}/conversations/stream` ya estaba
    en `develop`).
  - Pausar o reanudar un número tiraba la caché del número **antes** del commit:
    un turno a la vez podía volver a guardarla con el estado viejo. La lite la
    tira tras el commit; la consola del partner, ya y otra vez tras el commit.
  - El simulador (playground, pruebas y calidad) llamaba al modelo sin
    `llm_proxy_partner_scope`: con el proxy cerrado por defecto de staging, cada
    turno simulado moría. `simulation/runner.run_turn` abre el ámbito del
    partner en la misma tarea.
  - Nueve acciones de auditoría sin frase (catálogo de modelos, fuentes de la
    ficha y la beta de «Iniciar sesión con WhatsApp»): migración
    `0202_audit_vocabulary_more`; la beta escribe constantes, no un nombre
    armado.
  - `services/knowledge/embeddings.py` llama al proveedor sin estar declarado
    en la garantía 7 (no pide `store`): declarado.
  - `reception.handoff` es a la vez evento y herramienta: `test_49` lista los
    tres sitios donde el literal nombra la herramienta.
  - La tabla `whatsapp_login_beta_countries` no se vaciaba entre pruebas: un
    país abierto en una prueba seguía abierto en la siguiente.
- **Ruido de la máquina cargada**: `test_local_dispatch` (espera 0,2 s) pasa a
  solas. `test_retrieval::test_search_takes_under_30_ms_p95_with_5000_chunks`
  da 40–50 ms en este portátil también a solas (24 muestras): es el criterio de
  éxito de la búsqueda exacta y se mide en staging (T188), no aquí.

**Conectores y Calidad (T129, T147), huecos de la API anotados sin rodear**:
quitar un conector de un agente no tiene ensayo (`DELETE …/activations/{x}` dice
lo afectado después de quitarlo); `POST /connections/{id}/reconnect` responde
`authorize_with_form` sin el formulario (la página lo lee de `GET /connectors`);
`browser_credentials`, `webhook_manual` y el enlace público de AgendaPro no
traen formulario; la página de la conexión no trae `allowed` ni detalle de su
salud; las filas del catálogo del agente no traen `allowed`, descripción ni
`vendor`, y `list_catalog` no filtra por partner (35.2 pide el catálogo
permitido al partner); los precios de Calidad van siempre en USD (39.4 pide la
moneda de la bolsa); la API de Calidad manda frases en español; el resultado de
la comprobación no dice qué política probó y empaqueta cifras en texto
(`"regression:0.05"`).

**Estado al cerrar el día**: quedan 11 tareas abiertas. T186 espera el paso
`js` de `verify.sh`; las demás no dependen de esta rama: la 046 fusionada
(T001, T101, T107, T109, T115), los proveedores de Luis (T142), staging (T181,
T184 a mano, T188) y retirar lo viejo cuando nadie use la consola de hoy (T182).
