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
