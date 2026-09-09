---
description: "Task list for feature implementation"
---

# Tasks: el puesto de trabajo del teammate en la máquina del partner

**Input**: documentos de diseño en `/specs/001-puesto-trabajo-partner/`

**Prerequisites**: [`plan.md`](./plan.md) · [`spec.md`](./spec.md) ·
[`research.md`](./research.md) · [`data-model.md`](./data-model.md) ·
[`contracts/`](./contracts) · [`quickstart.md`](./quickstart.md)

**Tests**: **no son opcionales.** §VII — cada criterio de aceptación nace como
test, se ve en rojo, y solo entonces se implementa. Un `skip` puntúa como aprobado
y por tanto no cubre nada.

**Organization**: por historia de usuario, para que cada una se implemente y se
pruebe sola.

## Orden de las historias, y por qué no es el del número

Las cuatro historias de la spec son **P1**, así que la prioridad no las ordena: las
ordena la dependencia de seguridad. **US4** (el catálogo es exhaustivo) y **US3**
(la lista blanca no se negocia) van antes que **US1** (el teammate ejecuta), porque
entregar US1 sin ellas sería ejecutar en la máquina de una persona sin lista blanca
acotada — exactamente lo que §I prohíbe. Aquí el MVP **no** es «la historia 1
sola».

---

## Phase 0: Las dos puertas

**Propósito**: las dos apuestas del plan. Ninguna tarea que dependa de los
Requisitos 5 u 11 arranca hasta que su puerta esté en verde.

**⚠️ Si T001 falla, el plan se detiene y la spec se replantea sobre el repliegue
escrito en la evaluación — antes de construir nada encima.**

- [x] T001 Verificar en máquina sucia que un envoltorio apuntado por `CLAUDE_CODE_EXECUTABLE`
      con `--strict-mcp-config` deja el catálogo **sin** los servidores ajenos de
      `~/.claude.json` **y con** las herramientas propias de Crew; contrastar contra el
      árbol de procesos del gateway, no solo contra lo que el agente enumera.
      Procedimiento en `quickstart.md` §Puerta 1. _Requisitos: 5.1, 5.2, 5.3_
      **PASA (2026-09-09).** Catálogo: 3 servidores ajenos → 0. Procesos ajenos bajo el
      gateway: 4 → 0. Crew conserva las suyas (74 de `core` + `cron`). Evidencia en
      [`evidence/T001/`](./evidence/T001/). Cierra la decisión D4 de `research.md`.
- [x] T002 **Establecer el contrato de la superficie de aprobación de subagentes**:
      qué predicado decide que existe, y por qué vía se contesta. _Requisitos: 11.1_
      **CONTRATO ESTABLECIDO (2026-09-09), no verificado de punta a punta.** El
      predicado es `has_dashboard_surface()`: una clave de sesión con prefijo
      `dashboard:` lo satisface **sin depender de que el dashboard corra**. Existe una
      cola global de aprobaciones —`GET /api/approvals`, `POST /api/approvals/{id}/{action}`—
      independiente de que haya pestaña de chat. En la evaluación falló porque
      `parent=cli_chat` no lleva ese prefijo. Evidencia en [`evidence/T002/`](./evidence/T002/).
      **T002 estaba mal planteada**: exigía verificar `apps/desktop/`, que no existe hasta
      T005. La verificación de punta a punta se movió a la Phase 7.

**Checkpoint**: T001 pasa, así que la fase 1 puede empezar. T002 dejó el Requisito 11
con el contrato conocido pero sin probar de punta a punta; la Phase 7 sigue siendo
condicional, y su condición ahora se resuelve **dentro** de ella (T052) en vez de
antes de existir el cliente que hay que probar.

---

## Phase 1: Setup (Shared Infrastructure)

- [x] T003 Crear `apps/edition/` (Python ≥3.12) con el entry point `kirocrew.plugins`
      → `build_enterprise_context`, componiendo con `dataclasses.replace` sobre
      `build_default_context(cfg, profile="enterprise")`. **El núcleo del sustrato queda
      a 0 archivos modificados**: si alguna tarea obliga a tocarlo, se detiene.
      _Requisitos: 5.1_
      **HECHO.** Composición verificada con `scripts/verify-composition.py`: perfil `enterprise`, `mcp_tooling` y `agent_catalog` propios, floor `PolicyAuthority` intacto, `contract_version` 1, y el clon en `37933a5` con **0 modificados**.
- [x] T004 [P] Automatizar la construcción y publicación de la rueda del sustrato desde
      el commit fijado `37933a5` en el índice interno — no hay rueda pública, así que
      esto es cadena de suministro del paquete firmado, no una línea de dependencias.
      _Requisitos: 9.1, 9.2_
      **HECHO.** `apps/edition/scripts/build-substrate-wheel.sh` exporta el commit con `git archive` —nunca `pip install -e` sobre el clon— y **falla si el clon queda con un solo fichero modificado**.
- [x] T005 [P] Crear `apps/desktop/` con el esqueleto del puente **saliente**: la
      aplicación abre la conexión y sondea; ningún puerto a la escucha, ningún túnel
      inverso, ningún descubrimiento en red local. Contrato en
      `contracts/device-bridge.md`. _Requisitos: 6.1, 6.2_
      **HECHO.** `OutboundBridge` + `presence`, 13 tests en verde. La invariante «nunca escucha» se comprueba recorriendo el fuente, y se verificó que el test **falla** al introducir un `createServer`.
- [x] T006 [P] Fijar en el empaquetado `KIROCREW_HOME`, `KIRO_HOME` y
      `KIROCREW_WORKSPACE` dentro de la ubicación declarada, más la telemetría
      desactivada, **antes del primer arranque** — `KIROCREW_HOME` no gobierna el
      workspace del agente y un simple `--version` ya materializa el data home.
      _Requisitos: 13.2, 13.5_
      **HECHO.** `auphere_edition.runtime_env` con `assert_isolated`, que falla cerrado si falta una de las tres. 6 tests, escritos en rojo antes de implementar.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ Ninguna historia empieza hasta que esta fase esté completa.**

- [x] T007 Migración `apps/api/alembic/versions/0106_local_workstation.py` con las cuatro
      tablas de `data-model.md` —`partner_devices`, `local_executables`,
      `local_argument_grants`, `local_executions`— **todas con `tenant_id` y RLS
      forzada**. `partner_devices` **no** lleva columna de estado: la presencia se deriva
      de `last_heartbeat_at`. Unicidad `(tenant_id, executable)` con `removed_at IS NULL`.
      _Requisitos: 2.1, 4.1, 8.1_
      **HECHO.** Aplicada contra Postgres real. Las cuatro tablas con `ENABLE` + `FORCE` + 1 política cada una; `test_21` en verde con ellas dentro.
- [x] T008 [P] Modelos SQLAlchemy de las cuatro entidades en
      `apps/api/src/nexus_api/db/models/local_workstation.py`, con `outcome` restringido a
      `completada|expirada|terminada|denegada` y `denial_reason` a la lista cerrada
      `ejecutable_no_permitido|metacaracteres|fuera_del_directorio|sin_verificar|dispositivo_ausente`.
      _Requisitos: 8.1, 8.3_
      **HECHO.** Registrados en `db/models/__init__.py` y presentes en `Base.metadata`. Vocabulario cerrado de `outcome` y `denial_reason` repetido por CHECK en la base.
- [x] T009 Repositorios en `apps/api/src/nexus_api/repositories/local_workstation.py` que
      **no aceptan `tenant_id` del llamante**: lo toman del contexto de petición
      (`SET LOCAL app.tenant_id`) como el resto de la plataforma. _Requisitos: 2.1, 8.2_
      **HECHO.** Ningún método público acepta `tenant_id`; sale de `require_current_tenant()`. `test_10_repos_reject_explicit_tenant` en verde. Los permisos de argumentos usan uuid5 determinista + UPSERT.
- [x] T010 Endpoints de consola en `apps/api/src/nexus_api/api/console/local_workstation.py`
      para alta y archivado de ejecutables y para el alta del dispositivo. **La lista
      blanca solo se modifica aquí, por una persona** — nunca desde el turno.
      _Requisitos: 2.1, 4.3_
      **HECHO.** Cinco rutas bajo `/console/clients/{ref}/workstation`, con permisos nuevos `workstation:read` y `workstation:write` — este último **no** lo tiene el rol *builder*. `test_console_scope` en verde (416).

**Checkpoint**: base lista. Las historias pueden empezar.

---

## Phase 2b: Las puertas de la constitución

- [ ] T011 [P] Test de aislamiento de la **garantía 2 (tool whitelist)** en
      `apps/api/tests/isolation/test_26_local_tool_catalog_exhaustive.py`: el catálogo de
      una sesión es exactamente la lista blanca del tenant, el partner no puede añadir
      nada, y si no se puede garantizar la sesión no abre. En rojo bloquea el merge (§I).
      _Requisitos: 5.1, 5.2, 5.3, 5.4_
- [ ] T012 [P] Test de aislamiento de la **garantía 6 (log y traza)** en
      `apps/api/tests/isolation/test_27_local_execution_audit_tenant_tagged.py`: toda
      ejecución **y toda denegación** quedan etiquetadas por tenant. _Requisitos: 8.1, 8.2, 8.3_
- [ ] T013 [P] Test de aislamiento de la **garantía 1 (RLS)** en
      `apps/api/tests/isolation/test_28_local_allowlist_device_rls.py`: lista blanca y
      dispositivos son inalcanzables entre tenants y el `tenant_id` nunca llega del
      llamante. El nº 25 queda reservado a la VM de la beta 5. _Requisitos: 2.1, 4.1_
- [ ] T014 Dejar escrita la licencia de las dos dependencias nuevas —KiroCrew
      `0.7.0`@`37933a5` y `@agentclientprotocol/claude-agent-acp` `0.75.1`, ambas
      Apache-2.0— con el párrafo citado (§2 concesión, §4.d `NOTICE`, §6 marcas
      excluidas), y **conservar el `NOTICE`** en el paquete distribuido (§VIII).
      _Requisitos: 9.1_
- [ ] T015 Conectar el **consumo de modelo** de las sesiones locales al medidor que ve el
      partner, y decir en qué pantalla lo ve. **No se factura reloj de máquina**: la
      máquina es del partner. _Requisitos: 10.1, 10.2_

> **El orden no es un error.** T011–T013 prueban lo que las fases 3 y siguientes
> implementan: el test se escribe y **se ve en rojo** antes (§VII). Que un test
> preceda a su implementación es la regla, no una inconsistencia.

**Checkpoint**: las puertas tienen dueño. Sin esto `/speckit-analyze` no da verde.

---

## Phase 2c: La frontera de aprobación (Requisito 7)

**Propósito**: separar las dos escaleras. La del sustrato se queda para lo que pasa
**dentro de la máquina**; la nuestra, durable y auditada, para todo lo que toque a
un cliente final. Sin esto, US1 ejecutaría sin que nadie haya dibujado la frontera.

**⚠️ Va antes de las historias a propósito**: el Requisito 7 no pertenece a ninguna
historia de usuario —sale de §IV, no de un recorrido del partner— y por eso es
justo el que se cae si se ordena solo por historias.

### Tests para el Requisito 7 ⚠️

- [ ] T016 [P] Test en `apps/api/tests/integration/test_end_client_approval_boundary.py`:
      una acción que toca datos de un cliente final pasa por `companion.actions` y la
      auditoría nombra a la **persona** que decidió, no al agente que ejecutó.
      _Requisitos: 7.1_
- [ ] T017 [P] Test en `apps/api/tests/integration/test_machine_scoped_ladder.py`: una
      acción limitada a la máquina se resuelve con la escalera local y **no consume una
      aprobación durable**. _Requisitos: 7.2_
- [ ] T018 [P] Test en `apps/api/tests/unit/test_approval_expiry_denies.py`: una
      aprobación que caduca sin respuesta deniega la acción — deny-on-silence, nunca
      allow-on-silence. _Requisitos: 7.3_
- [ ] T019 [P] Test en `apps/edition/tests/test_no_end_client_credentials.py`: el
      ambiente donde corre el agente no contiene ninguna credencial de cliente final,
      comprobado sobre el entorno real del proceso y no sobre la configuración.
      _Requisitos: 7.4_

### Implementación del Requisito 7

- [ ] T020 Clasificador de alcance de la acción en
      `apps/api/src/nexus_api/services/action_scope.py`: decide si una acción se queda en
      la máquina o toca a un cliente final, y **falla hacia la escalera durable** cuando no
      lo puede determinar. _Requisitos: 7.1, 7.2_
- [ ] T021 Caducidad con denegación por silencio, y saneado del ambiente del proceso del
      agente para que ninguna credencial de cliente final entre en él.
      _Requisitos: 7.3, 7.4_

**Checkpoint**: la frontera existe y está probada. Ahora sí pueden empezar las
historias.

---

## Phase 3: User Story 4 - Ninguna herramienta ajena entra en la sesión (P1) 🎯 primera por dependencia

**Goal**: el catálogo de una sesión es exactamente la lista blanca del tenant.

**Independent Test**: en una máquina con herramientas ajenas configuradas, abrir una
sesión y enumerar el catálogo.

### Tests para US4 (§VII: se escriben y se ven en rojo antes de implementar) ⚠️

- [ ] T022 [P] [US4] Test de contrato del servidor MCP en
      `apps/edition/tests/contract/test_console_mcp_catalog.py`: el catálogo publicado es
      igual al `agent_config.tools` del tenant, ni una entrada más.
      _Requisitos: 5.1, 5.2_
- [ ] T023 [P] [US4] Test de fail-closed en
      `apps/edition/tests/contract/test_session_refuses_unverifiable_catalog.py`: si no se
      puede garantizar el catálogo, **la sesión no abre**. _Requisitos: 5.3_
- [ ] T024 [P] [US4] Test de inalcanzabilidad en
      `apps/edition/tests/contract/test_disabled_capabilities.py`: navegador, control de
      escritorio, canal no oficial y carga de apps no son alcanzables — no basta con que
      no estén listados. _Requisitos: 13.1, 13.3, 13.4_

### Implementación de US4

- [ ] T025 [US4] Servidor MCP de la edición en `apps/edition/src/auphere_edition/mcp_console.py`
      sobre las herramientas `console.*`, filtrado por la lista blanca del tenant. Contrato
      en `contracts/console-mcp.md`. _Requisitos: 5.1, 5.4_
- [ ] T026 [US4] Llevar a producción el envoltorio validado en T001, en
      `apps/edition/src/auphere_edition/wrapper/`. _Requisitos: 5.1, 5.2_
- [ ] T027 [US4] Registrar el intento cuando el ambiente declara herramientas
      adicionales, sin exponerlas. _Requisitos: 5.2_
- [ ] T028 [US4] Desactivar de forma inalcanzable navegador, control de escritorio, canal
      no oficial y cargador de apps. _Requisitos: 13.1, 13.3, 13.4_

**Checkpoint**: US4 funciona y se prueba sola.

---

## Phase 4: User Story 3 - La lista blanca no se negocia en el turno (P1)

**Goal**: un ejecutable ausente de la lista no se ejecuta y **no se puede aprobar en
caliente**; lo que sí se aprueba son argumentos de un ejecutable ya permitido.

**Independent Test**: pedir un ejecutable ausente, comprobar que se deniega sin
ofrecer aprobación; añadirlo por consola y comprobar que ya se puede usar.

### Tests para US3 ⚠️

- [ ] T029 [P] [US3] Test en `apps/api/tests/integration/test_local_allowlist_gate.py`:
      ejecutable ausente → denegado, y **no aparece como decisión pendiente aprobable**.
      _Requisitos: 2.2, 2.6_
- [ ] T030 [P] [US3] Test en `apps/api/tests/unit/test_argv_metacharacters.py`: tuberías,
      encadenamiento, subshells, redirecciones y sustitución de comandos se rechazan en
      `executable` y en **cada** elemento de `args`, esté o no permitido el ejecutable.
      _Requisitos: 2.4_
- [ ] T031 [P] [US3] Test en `apps/api/tests/integration/test_argument_grants.py`:
      argumentos nuevos piden aprobación durable, y al concederla queda `decided_by` en la
      auditoría. _Requisitos: 2.3, 2.5_

### Implementación de US3

- [ ] T032 [US3] Gate de validación en
      `apps/api/src/nexus_api/services/local_exec_gate.py`: lista blanca, metacaracteres y
      **fail-closed** — lo que no se puede verificar se deniega y no se ofrece.
      _Requisitos: 2.2, 2.4, 2.6_
- [ ] T033 [US3] Grants de argumentos con **uuid5 determinista + UPSERT** sobre
      `(tenant, ejecutable, firma de argv)`, apoyados en `companion.actions` para la
      aprobación durable — no se crea un segundo mecanismo de aprobación.
      _Requisitos: 2.3, 2.5_
- [ ] T034 [US3] Pantalla de consola para añadir y archivar ejecutables, con la persona
      que lo hizo. La lista arranca **vacía** por tenant. _Requisitos: 2.1_

**Checkpoint**: US3 y US4 funcionan de forma independiente.

---

## Phase 5: User Story 1 - El teammate arregla el build (P1)

**Goal**: el teammate ejecuta el build, lee el log, propone, aprueba una vez y
vuelve a ejecutar, sin que el partner escriba un comando.

**Independent Test**: un proyecto real del partner cuyo build falla por una causa
conocida.

### Tests para US1 ⚠️

- [ ] T035 [P] [US1] Test de integración del recorrido completo en
      `apps/api/tests/integration/test_fix_the_build.py`. _Requisitos: 1.1, 1.2_
- [ ] T036 [P] [US1] Test en `apps/api/tests/unit/test_workdir_containment.py`: `cwd`
      absoluto, con `..` o que deje de resolver dentro de sí mismo → denegado con
      `fuera_del_directorio`, comprobado **en el momento de usarse**, no solo al
      declararse. _Requisitos: 1.1, 1.4_
- [ ] T037 [P] [US1] Test en `apps/api/tests/unit/test_tool_per_destination.py`: existe
      `shell_local` y **no** existe ninguna herramienta de ejecución con parámetro de
      destino; destino ambiguo → denegado. _Requisitos: 1.2, 1.3_
- [ ] T038 [P] [US1] Suite de contención de escrituras en **macOS**, los seis ataques
      —symlink final, TOCTOU, symlink de padre, padre intercambiado, carrera de creación
      exclusiva, enlace duro—. _Requisitos: 3.1, 3.3_
- [ ] T039 [P] [US1] La misma suite en **Windows**, con rutas relativas NT.
      _Requisitos: 3.2, 3.3_
- [ ] T040 [P] [US1] Test en `apps/api/tests/integration/test_execution_ceilings.py`:
      una ejecución que no termina se corta al vencer el límite **con todo su árbol de
      procesos**, y al cerrar la sesión no quedan huérfanos. _Requisitos: 12.1, 12.2, 12.3, 12.4, 12.5_

### Implementación de US1

- [ ] T041 [US1] Herramienta `shell_local` con `args` como **lista, nunca una cadena**, y
      `cwd_relative` relativo al `workdir`. Contrato en `contracts/shell-local-tool.md`.
      _Requisitos: 1.1, 1.2_
- [ ] T042 [US1] Contención de escrituras en macOS. _Requisitos: 3.1, 3.3_
- [ ] T043 [US1] Contención de escrituras en Windows con rutas relativas NT.
      _Requisitos: 3.2, 3.3_
- [ ] T044 [US1] Límite de reloj y recogida del árbol de procesos al vencer y al cerrar
      sesión; si un proceso no se puede terminar, se **nombra** en vez de darlo por
      terminado. _Requisitos: 12.1, 12.2, 12.3, 12.4, 12.5_
- [ ] T045 [US1] Registrar cada intento —ejecución y denegación— sin guardar la salida
      del comando: se guarda que ocurrió, no lo que dijo. _Requisitos: 8.1, 8.3_

**Checkpoint**: el diferencial funciona de punta a punta.

---

## Phase 6: User Story 2 - El catálogo dice la verdad sobre la máquina (P1)

**Goal**: cuando la máquina no está, la interfaz lo dice como estado y las
herramientas locales desaparecen del catálogo.

**Independent Test**: desconectar la máquina a mitad de tarea y mirar la pantalla y
el catálogo del turno siguiente.

### Tests para US2 ⚠️

- [ ] T046 [P] [US2] Test en `apps/api/tests/integration/test_device_presence.py`: al
      caducar el latido, las herramientas locales salen del catálogo y el teammate **no
      afirma resultados de comandos que no ejecutó**. _Requisitos: 4.1, 4.2_
- [ ] T047 [P] [US2] Test en `apps/api/tests/unit/test_absence_is_designed.py`: sin
      dispositivo no hay control desactivado ni pantalla que explique lo que no se tiene.
      _Requisitos: 4.4_

### Implementación de US2

- [ ] T048 [US2] Latido y **derivación** del estado desde `last_heartbeat_at` — sin
      columna de estado, para que la pantalla no pueda quedarse mintiendo si muere el
      proceso que la actualizaría. _Requisitos: 4.1, 4.2_
- [ ] T049 [US2] Composición del catálogo del turno según la presencia.
      _Requisitos: 4.2_
- [ ] T050 [US2] Estado en la interfaz —«desconectado desde las 23:10»— y `reconectando`
      mientras el puente se recupera. Es estado, no error. _Requisitos: 4.3, 6.2_

**Checkpoint**: las cuatro historias funcionan de forma independiente.

---

## Phase 7: Requisito 11 - Subagentes *(condición resuelta aquí dentro)*

**⚠️ La condición se comprueba en T052, y es lo primero de la fase.** Si ahí se
demuestra que nuestro cliente no puede contestar la aprobación, se retira el
Requisito 11, se borran las otras dos tareas y se escribe la razón. Ya **no** es una
apuesta a ciegas: T002 dejó establecido el predicado (`has_dashboard_surface()`, que
una clave con prefijo `dashboard:` satisface) y la cola global de aprobaciones con
sus endpoints, así que esto se construye contra un contrato conocido.

- [ ] T051 [P] Test en `apps/desktop/tests/test_spawn_approval_surface.py`: el estado
      mostrado del subagente coincide con el real **incluido el rechazo** — la evaluación
      observó un `✅` para un subagente rechazado, y esa mentira no se hereda.
      _Requisitos: 11.2, 11.3_
- [ ] T052 Lanzamiento de subagentes con la cáscara de escritorio como superficie que
      contesta la aprobación, **y verificación de punta a punta**: originar la sesión con
      una clave que satisfaga `has_dashboard_surface()`, lanzar un `spawn`, contestarlo
      desde nuestro cliente por la cola global, y comprobar que el subagente corre.
      Es la condición de esta fase y va primero. _Requisitos: 11.1_
- [ ] T053 Estado `bloqueado` cuando un subagente espera a otro, y no pintado como
      ocioso. _Requisitos: 11.4_

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T054 [P] Retirar las marcas ajenas de la **superficie visible**: catálogo de cadenas
      en inglés (17 ocurrencias), empaquetado e instaladores (386) y las constantes de
      ruta. **No** se renombran los identificadores internos: la licencia no lo exige y
      hacerlo impediría seguir aguas arriba. _Requisitos: 9.1_
- [ ] T055 [P] Añadir una comprobación que falle si un bump del sustrato reintroduce
      marcas en superficie visible — no hay constante central de marca, así que esto es
      vigilancia recurrente, no una tarea que se cierra. _Requisitos: 9.2_
- [ ] T056 [P] Enlace de vuelta desde la KB: `[[15-kirocrew-y-alternativas]]` §9 y
      `[[14-mvp-y-fases]]` §3 apuntan a `specs/001-puesto-trabajo-partner/`. El puente es
      obligatorio en las dos direcciones. _Requisitos: §IX (constitución)_
- [ ] T057 Firma y notarización del paquete. **Bloqueada fuera de este plan**: los
      certificados tienen plazo de entrega y hoy no están —en esta máquina solo hay
      «Apple Development», que no sirve para distribuir, y los OV de Windows duran 460
      días desde marzo de 2026—. _Requisitos: 9.1, 9.2_
- [ ] T058 Ejecutar la validación completa de `quickstart.md`. _Requisitos: 1.1, 12.1_

---

## Dependencies & Execution Order

### Orden de fases

- **Phase 0 (las dos puertas)**: primero, sin excepción. T001 puede detener el plan.
- **Phase 1 (Setup)**: después de T001. T003 depende de que la composición sea viable.
- **Phase 2 (Foundational)**: bloquea todas las historias.
- **Phase 2b (puertas de la constitución)**: en paralelo con las historias, pero
  **cerrada antes del merge**.
- **Phase 3 → 4 → 5 → 6**: por dependencia de seguridad, no por número.
- **Phase 7**: solo si T002 está en verde.
- **Phase 8**: al final, salvo T057 que depende de un plazo externo.

### Dependencias entre historias

- **US4** no depende de ninguna. Va primero porque US1 sin ella ejecutaría sin
  catálogo demostrable.
- **US3** no depende de US4 para probarse, pero entregar US1 sin US3 sería ejecutar
  sin lista blanca acotada.
- **US1** se prueba sola, y **no se entrega** antes que US3 y US4.
- **US2** es independiente de las tres.

### Paralelismo

- T004, T005 y T006 en paralelo tras T003.
- T008 en paralelo tras T007; T011, T012 y T013 en paralelo entre sí.
- Los bloques de tests de cada historia, en paralelo dentro de su fase.
- T038 y T039 en paralelo si hay las dos máquinas.

---

## Implementation Strategy

### MVP — y aquí el MVP no es la historia 1 sola

1. Phase 0 — las dos puertas. **Parar si T001 falla.**
2. Phase 1 + Phase 2 — base.
3. Phase 3 (US4) + Phase 4 (US3) — el catálogo y la lista blanca.
4. Phase 5 (US1) — el diferencial.
5. **PARAR Y VALIDAR**: el recorrido de `quickstart.md` §CE-001, con los doce ataques
   de contención en verde.

Entregar US1 sin 3 y 4 sería ejecutar en la máquina de una persona sin lista blanca
acotada ni catálogo demostrable. No es un MVP: es un incidente.

### Entrega incremental

1. Base lista → nada visible todavía.
2. + US4 + US3 → el gate existe y se puede auditar, aunque aún no ejecute nada útil.
3. + US1 → **el diferencial**. Demo.
4. + US2 → la pantalla deja de mentir cuando la máquina se va.
5. + Phase 7 → subagentes, si T002 lo permitió.

---

## Notes

- **Dos tareas citan una obligación constitucional en vez de un criterio**: T014
  (licencias) cita `9.1` porque es distribuir lo que obliga a conservar el `NOTICE`,
  y T056 cita `§IX` porque el puente con la KB no tiene número de requisito. Es
  deliberado y se deja escrito: mapear un control a la política que lo exige es
  trazabilidad, no un hueco.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Los tests se ven **fallar** antes de implementar (§VII).
- Si alguna tarea obliga a modificar un fichero del núcleo del sustrato, se detiene:
  esa es la frontera entre componer y forkear.
