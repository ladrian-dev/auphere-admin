---
description: "Tareas — spec 012, la máquina se registra con la sesión"
---

# Tasks: La máquina se registra con la sesión

**Input**: `specs/012-la-maquina-se-registra-con-la-sesion/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/, quickstart.md — todos presentes.

**Tests**: **no son opcionales**. §VII: cada criterio nace como test, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia, en el orden de entrega del plan (H1 → H6). Cada
historia se suelta sola.

## Reglas de este repo *(constitución)*

- Cada tarea cita sus requisitos: `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: el rojo se ve antes de implementar.
- **Aislamiento (§I)**: T006 es la puerta. En rojo bloquea el merge.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **Una sola ejecución de pytest a la vez**: las suites comparten la base de
  desarrollo y dos a la vez dan rojos que no son del cambio.

---

## Phase 1: Setup

**Propósito**: mirar antes de tocar. Ninguna de estas escribe código.

- [X] T001 ~~Comprobar contra **producción**~~ **Resuelta el 2026-09-22 por Luis: «nadie está usando esto en producción».** No hay ninguna persona con máquinas activas, así que el tope de cinco no le rompe el trabajo a nadie al desplegarse. Queda escrito que el número se eligió **sin dato de uso real** —no había uso— y no con uno que lo respalde: el día que haya partners de verdad, es lo primero que conviene volver a mirar. Original: comprobar contra producción cuántas máquinas activas tiene cada persona, con una consulta de **solo lectura** sobre `partner_devices` agrupando por `principal_id` con `revoked_at IS NULL`. Si alguien supera cinco, el tope de US4 le rompe el trabajo al desplegar y hay que decidir el número con ese dato delante, no después. _Requisitos: 4.1_

- [X] T002 [P] Dejar por escrito en `plan.md` §Constitution Check que **no entra ninguna dependencia nueva**: esta spec resta código. La puerta de licencias (§VIII) se cierra declarándolo, no ignorándolo. _Requisitos: —_

- [X] T003 [P] Dejar por escrito en `plan.md` §Constitution Check que la puerta del **medidor no aplica** y por qué: no se gasta modelo, ni reloj de máquina, ni herramienta de pago. Declararlo es la diferencia entre una puerta cerrada y una olvidada. _Requisitos: —_

---

## Phase 2: Foundational

**Propósito**: lo que de verdad bloquea. Es poco a propósito — el plan comprobó
que **H1 no depende de nada de H3**, así que casi nada tiene que ir antes que todo.

- [X] T004 Fijar en un solo sitio los dos números que la spec eligió como supuestos: el umbral de frescura de sesión (**una hora**) y el tope de máquinas (**cinco activas por persona**), en `apps/api/src/nexus_api/core/` junto a las demás constantes de dominio. Un número a mano en dos sitios es dos números que divergen — ya pasó con el techo de la muestra de salida. _Requisitos: 3.2, 4.1_

**Checkpoint**: las historias pueden empezar.

---

## Phase 2b: Las puertas de la constitución

- [X] T005 Escribir el **modelo de amenaza** de la superficie `3a` en `specs/012-la-maquina-se-registra-con-la-sesion/threat-model.md`, **antes de tocar código**, como pidió el intake. Tiene que sostener por escrito la afirmación del encabezado —que esto es **sustitución y no apertura**— y nombrar qué cambia y qué no para un atacante que ya tiene la cookie de la partición humana. **Bloquea US3, no US1**: su objeto es el registro, y US1 no abre superficie — la cierra. _Requisitos: 3.1, 3.2_

- [X] T006 Test de aislamiento en `apps/api/tests/isolation/test_38_principal_access_revocation_scope.py`: retirar el acceso de una persona **no alcanza a otra del mismo partner** (R1.5) ni a nadie de otro partner. Es la puerta de §I y bloquea el merge. **Su razón de ser es concreta**: la operación corre con rol dueño, así que la RLS **no** la protege — lo único que la acota es el `WHERE` por `principal_id`, y eso hay que afirmarlo con un test, no confiarlo. _Requisitos: 1.5_

- [X] T007 Verificar que `apps/api/tests/isolation/test_29_device_credential_scope.py` y `test_30_device_partner_scope.py` siguen **verdes sin tocarlos**, y dejarlo anotado en el registro de ejecución. Si hubiera que aflojar uno, **el cambio está mal**: esa es la señal, no un obstáculo. _Requisitos: —_

**Checkpoint**: las tres puertas tienen dueño.

---

## Phase 3: US1 — Se puede retirar el acceso de una persona (P1) 🎯 MVP

**Goal**: una acción deja fuera a una persona: sus sesiones dejan de resolver y
sus máquinas dejan de poder trabajar, en una transacción.

**Independent Test**: se prueba **con el código de emparejamiento todavía
puesto**. Si exige haber entregado US3, el orden de entrega está mal.

**Por qué es el MVP**: hoy esto no se puede hacer **ni a mano**, y es la pieza
que la spec 011 reutilizará (D-6).

### Tests para US1 ⚠️ (se escriben y se ven en rojo antes de implementar)

- [X] T008 [P] [US1] Test de integración en `apps/api/tests/integration/test_principal_access_revocation.py`: una persona con dos sesiones y dos máquinas; tras retirar su acceso, **ninguna sesión resuelve** y **ninguna máquina** puede latir, sondear, devolver resultado, renovar ni declarar directorio — las **cinco** operaciones del puente, no una muestra. _Requisitos: 1.1, 1.3, 1.4_

- [X] T009 [P] [US1] Test de atomicidad en el mismo fichero: **forzar un fallo entre las dos mitades** y comprobar que no queda el estado intermedio —sesiones cerradas con máquinas vivas, ni al revés—. **No vale probarlo por el camino feliz**: la atomicidad solo se ve cuando algo se rompe. _Requisitos: 1.2_

- [X] T010 [P] [US1] Test en el mismo fichero: retirar el acceso deja **asiento de auditoría** con quién lo hizo, sobre quién y por qué. _Requisitos: 1.6_

### Implementación de US1

- [X] T011 [US1] Crear `apps/api/src/nexus_api/services/principal_access.py` con la operación que retira sesiones **y** máquinas en una transacción. **Nace en módulo propio a propósito**: no es de identidad ni de puesto de trabajo, los **cruza**, y la spec 011 la va a llamar. Si acaba dentro de `console_identity`, la 011 hereda el sitio equivocado. _Requisitos: 1.1, 1.2_

- [X] T012 [US1] Añadir en `apps/api/src/nexus_api/services/console_identity.py` el cierre de **todas** las sesiones de un principal. Hoy los dos únicos borrados son «las caducadas» y «ésta una»; falta el tercero. Hay índice `ix_console_sessions_principal`, así que es barato. _Requisitos: 1.1, 1.3_

- [X] T013 [US1] Usar `archive_all_for_principal` (`apps/api/src/nexus_api/repositories/local_workstation.py:138`) como la mitad de máquinas, con el motivo que corresponda. **No se reescribe**: ya existe y ya corre con rol dueño por la misma razón. _Requisitos: 1.1, 1.4_

- [X] T014 [US1] Escribir el asiento de auditoría de la operación en `apps/api/src/nexus_api/services/principal_access.py`. _Requisitos: 1.6_

- [X] T015 [US1] Exponer la operación en `apps/api/src/nexus_api/api/console/workstation_partner.py` según `contracts/registrar-la-maquina.md` §Retirar el acceso de una persona. _Requisitos: 1.1_

**Checkpoint**: US1 funciona sola. Ya se puede echar a alguien, que hoy no se
puede de ninguna forma.

---

## Phase 4: US2 — Desemparejar dice la verdad (P1)

**Goal**: la pantalla de desemparejar dice qué apaga y qué no.

**Independent Test**: desemparejar y leer lo que pone.

> **Esta fase se reescribió el 2026-09-22, al implementarla.** Pedía construir
> la revocación desde la aplicación. La spec 002 ya había decidido lo contrario
> con razón escrita (R11.2: «archivar es un acto de persona con su nombre y la
> credencial no gana una sexta operación»), y el diagnóstico —la pantalla
> miente— era correcto mientras que el arreglo no lo era. Las tareas de abajo
> son lo que queda: **texto y un camino**, no una operación nueva en la
> superficie `3a`.

### Tests para US2 ⚠️

- [X] T016 [P] [US2] Test en `apps/desktop/tests/unpair-dialog.test.tsx`: el diálogo dice que la máquina queda **pendiente de archivar desde la consola**, y **no** contiene ninguna promesa de «volver a emparejar». Las dos mitades importan: la primera es lo que la spec 002 R11.2 exige decir, la segunda es lo que su R11.5 prohíbe prometer. _Requisitos: 2.1, 2.2_

- [X] T017 [P] [US2] Test en el mismo fichero: tras desemparejar se ofrece el camino para archivar en la consola. _Requisitos: 2.3_

- [X] T018 [P] [US2] Test en `apps/api/tests/integration/test_device_bridge.py`: una máquina archivada recibe su negativa al presentar la credencial. **Ya pasa hoy** —`require_device` comprueba `revoked_at` antes que nada—; se escribe para que no se pierda al mover cosas, no porque falte. _Requisitos: 2.4_

### Implementación de US2

- [X] T019 [US2] Corregir `unpair.loses` en `apps/desktop/src/app/i18n.ts:411`: decir que la máquina queda pendiente de archivar desde la consola y que su credencial deja de valer **cuando se archive**, no antes. Quitar «hasta que la vuelvas a emparejar». _Requisitos: 2.1, 2.2_

- [X] T020 [US2] Añadir el camino a archivar en `apps/desktop/src/app/routes/unpair-dialog.tsx`: tras desemparejar, un enlace a la consola en su sección de máquinas. Reutiliza `app:openConsole`, que ya existe. _Requisitos: 2.3_

- [X] T021 [US2] **Revisado: la consola ya decía la verdad** (`ws.machines.archiveBody`: «no se podrá volver a emparejar esta máquina: se empareja otra»), y `workstation.bar.volver_a_emparejar` es correcto hoy —ese estado es el abandono a los 30 días, donde sí hay que dar de alta otra vez— y se revisa en US3, cuando dar de alta pase a ser entrar. Original: revisar `workstation.bar.volver_a_emparejar` (`app/i18n.ts:300`) y `ws.machines.archiveBody` (`console/.../workstation.ts:98`) por el mismo motivo que T019: si prometen volver a emparejar la misma máquina, contradicen que archivar sea terminal. _Requisitos: 2.2_

- [X] T021b [US2] Dejar anotado en `docs/desktop-workstation.md` que `device.unpaired` y el motivo `desemparejada` son **vocabulario sin escritor**, y por qué: los dejó así la enmienda T048 de la spec 002 al decidir que desemparejar no llama al servidor. No se les inventa uso ni se retiran en esta spec — se nombran, para que el siguiente que los encuentre no crea que descubrió un defecto. _Requisitos: —_

**Checkpoint**: US1 y US2. La revocación real existe (US1) y la pantalla ya no
promete lo que no hace (US2).

---

## Phase 5: US3 — Entrar deja la máquina lista (P1)

**Goal**: instalar, entrar, y la máquina trabaja. Sin código.

**Independent Test**: instalación limpia; tras entrar, la máquina queda
registrada sin paso intermedio.

### Tests para US3 ⚠️

- [X] T023 [P] [US3] Test de la ruta del BFF en `apps/console/src/app/api/desktop/__tests__/register-machine.test.ts`: con cookie válida devuelve la credencial **una vez**; sin cookie, 401. Copiar la forma del test hermano de `redeem`, que existe por un fallo ya desplegado (`401 Missing bearer token`). _Requisitos: 3.1, 7.1_

- [X] T024 [P] [US3] Test de integración en `apps/api/tests/integration/test_machine_registration.py`: registrar con sesión confirmada emite credencial, da de alta la máquina y deja asiento `device.paired`. _Requisitos: 3.1, 3.6_

- [X] T025 [P] [US3] Test en el mismo fichero: con una sesión **abierta hace más de una hora** se rechaza. Y —esto es lo que hay que afinar— que el test use el **momento de apertura** y no el de último uso: una sesión abierta hace seis días y usada hace diez segundos tiene que fallar. Si pasa, se implementó con el campo equivocado. _Requisitos: 3.2_

- [X] T026 [P] [US3] Test del **rechazo uniforme** en el mismo fichero: los **cuatro** motivos —sin sesión, sesión vieja, sin permiso, y **en el tope**— devuelven exactamente la misma respuesta, comparada carácter a carácter. Que el tope esté en la lista es deliberado y contraintuitivo: decir «tienes cinco máquinas» a quien no conoces es contar de más. _Requisitos: 3.4_

- [X] T027 [P] [US3] Test en el mismo fichero: registrar **dos veces desde la misma máquina** devuelve la que ya existe y no crea una segunda. _Requisitos: 3.7_

- [X] T028 [P] [US3] Test en el mismo fichero: hay techo de intentos y responde con espera. _Requisitos: 3.5, 7.3_

- [X] T029 [P] [US3] Test en `apps/desktop/tests/session-gate.test.ts`: tras entrar, la aplicación registra la máquina sola y no muestra ningún paso intermedio. _Requisitos: 3.1_

### Implementación de US3

- [X] T030 [US3] **Decidido el 2026-09-22**, en [data-model.md](./data-model.md) §Qué identifica a «la misma máquina»: un identificador de instalación que genera la aplicación y guarda **aparte de la credencial**, para que sobreviva a desemparejar. Columna `install_id` nullable → **una migración aditiva más, con US3**. Original: decidir y dejar escrito qué identifica a «la misma máquina»** para R3.7 (data-model.md §Lo que este documento NO decide). Hoy el canje recibe un `hostname`, que **no es estable** —cambia al renombrar el ordenador— ni único. Elegir mal convierte «registrarse dos veces» en «tener dos máquinas donde hay una», que es justo lo que el tope de US4 haría doler. _Requisitos: 3.7_

- [X] T031 [US3] Crear la ruta de la API `POST /console/workstation/machines` en `apps/api/src/nexus_api/api/console/workstation_partner.py`, con la comprobación de permiso **propia** — no se fía de que el BFF haya mirado. _Requisitos: 3.1, 3.3_

- [X] T032 [US3] Implementar el rechazo uniforme y su límite de intentos, con la clave del limitador por **persona** (ahora hay sesión, así que se puede; el canje viejo usaba `hostname+IP` porque no la tenía). _Requisitos: 3.4, 3.5, 7.2, 7.3_

- [X] T033 [US3] Crear la ruta del BFF `apps/console/src/app/api/desktop/register-machine/route.ts` según `contracts/registrar-la-maquina.md`, con su comprobación de permiso y **devolviendo cuerpo** — es la única ruta del BFF que entrega un secreto. _Requisitos: 3.1, 3.3, 7.1_

- [X] T034 [US3] Añadir el método en `apps/console/src/lib/backend/workstation.ts` —el *lane* del puesto de trabajo, que `backend.ts` incorpora; no en `backend.ts` directamente— con `mintServiceToken()` (EdDSA, **60 s**, `lib/jwt.ts:45`) y el manejo de error por `BackendError` (`status`, `code`), copiando el patrón de sus hermanos. _Requisitos: 3.1_

- [X] T035 [US3] Llamar a la ruta nueva desde `apps/desktop/src/electron/adapters.ts` con `session.fromPartition(HUMAN_PARTITION).fetch`, junto a `consoleWhoami` (`adapters.ts:43-74`), que usa **el mismo camino ya abierto y probado** contra `/api/session/whoami`. Cablearlo en `electron/main.ts` como se cablea la puerta de sesión. _Requisitos: 3.1_

- [X] T036 [US3] Registrar automáticamente tras entrar en `apps/desktop/src/app-runtime.ts` y `session-gate.ts`, y diseñar el estado nuevo **«entré y no se pudo registrar»**, que hoy no existe (research.md §8). _Requisitos: 3.1_

- [X] T037 [US3] Escribir los asientos `device.paired` y `device.pair_denied` desde la ruta nueva, **con el motivo real en la auditoría aunque no vaya en la respuesta**. Esa distinción es lo que hace que un rechazo uniforme siga siendo investigable. _Requisitos: 3.6_

**Checkpoint**: el corazón de la spec está entregado. El código viejo sigue ahí:
dos caminos abiertos un tiempo, que es incómodo y seguro.

---

## Phase 6: US4 — Hay un tope de máquinas (P2)

**Goal**: nadie acumula máquinas sin enterarse.

**Independent Test**: registrar hasta el tope y ver qué pasa en la siguiente.

**Depende de**: T001 (el dato de producción) y US3.

### Tests para US4 ⚠️

- [X] T038 [P] [US4] Test en `apps/api/tests/integration/test_machine_registration.py`: en el tope, el registro siguiente se rechaza y **no se archiva ninguna por su cuenta**. Archivar la más antigua sería cómodo y una sorpresa desagradable: puede ser la que está ejecutando algo, y archivar es terminal. _Requisitos: 4.1, 4.2_

- [X] T039 [P] [US4] Test en el mismo fichero: las máquinas **archivadas no cuentan** para el tope. Si contaran, cada restablecimiento de contraseña (D-6) lo cerraría un poco más: sería un tope que se cierra solo. _Requisitos: 4.3_

### Implementación de US4

- [X] T040 [US4] Añadir el recuento de activas por persona en `apps/api/src/nexus_api/repositories/local_workstation.py`, con `revoked_at IS NULL`. _Requisitos: 4.1, 4.3_

- [X] T041 [US4] Aplicar el tope en el registro, devolviendo el **mismo cuerpo** que los demás rechazos (T026). _Requisitos: 4.1, 4.2, 3.4_

- [X] T042 [US4] Que la aplicación explique el tope por la vía normal —hablando con alguien que ya está dentro— en vez de deducirlo del rechazo. _Requisitos: 4.4_

- [X] T042b [P] [US4] Test en `apps/desktop/tests/workstation-state.test.ts`: la aplicación dice cuántas máquinas tiene la persona y que puede retirar una, **sin que ese número salga del cuerpo del rechazo**. Es la mitad de R4 que el análisis cruzado destapó: un rechazo uniforme y una aplicación que explica no son lo mismo, y la spec los tenía mezclados en un solo criterio. _Requisitos: 4.4, 3.4_

**Checkpoint**: el freno que US3 retiró está repuesto.

---

## Phase 7: US5 — La decisión que importa es la carpeta (P2)

**Goal**: lo primero que se ofrece tras entrar es declarar la carpeta de un
cliente, no un panel de estado.

**Independent Test**: instalación limpia; comprobar qué se ofrece primero.

### Tests para US5 ⚠️

- [X] T043 [P] [US5] Test en `apps/desktop/tests/setup-checklist.test.tsx`: una máquina recién registrada sin directorios ofrece declarar el de un cliente como siguiente paso. _Requisitos: 5.1_

- [X] T044 [P] [US5] Test en `apps/desktop/tests/workstation-state.test.ts`: un teammate sin carpeta declarada para su cliente recibe qué falta y cómo declararla, **no un error**. _Requisitos: 5.2_

### Implementación de US5

- [X] T045 [US5] Reordenar lo que la aplicación ofrece tras entrar en `apps/desktop/src/app/App.tsx` y el pie de la lista lateral: la carpeta al frente. `POST /device/links` **ya existe** con sus asientos; esto lo saca a la superficie, no lo construye. _Requisitos: 5.1_

- [X] T046 [US5] Decir qué falta cuando un teammate va a tocar ficheros sin carpeta declarada. _Requisitos: 5.2_

**Checkpoint**: el acto deliberado está donde importa.

---

## Phase 8: US6 — El código desaparece (P3)

**Goal**: no queda ninguna forma de registrar una máquina tecleando un código.

**Independent Test**: buscar en consola, aplicación y código fuente.

**Depende de**: US3 entregada y **en uso**. Va la última a propósito.

### Tests para US6 ⚠️

- [X] T047 [P] [US6] **Barrido** en `apps/api/tests/isolation/test_39_no_pairing_code_path.py`: recorrer el código fuente y las rutas registradas y fallar si aparece cualquier resto del emparejamiento por código. R6.1 afirma que algo **no existe**, y eso se comprueba **buscando**, no confiando en haberlo borrado — es la lección que dejó `test_37_customer_axis_contract.py`, que encontró un segundo sitio donde nadie había mirado. _Requisitos: 6.1_

- [X] T048 [P] [US6] Test en `apps/api/tests/integration/test_device_bridge.py`: una máquina **registrada antes del cambio** sigue funcionando. Nadie vuelve a registrar lo que ya tenía. _Requisitos: 6.2_

### Implementación de US6

- [X] T049 [P] [US6] Retirar de `apps/api`: `POST /device/pair` con `PairIn`/`PairedOut` (`api/device_bridge.py:198-214, 296-384`), la emisión `POST /pairing-codes` y su asiento `device.pair_code_issued` (`api/console/workstation_partner.py:172-197`), `PairingCodeOut` (`api/console/schemas_workstation.py:96`), `core/pairing_codes.py` entero, `services/device_pairing.py` entero, `DevicePairingCodeRepository` (`repositories/local_workstation.py:222-274`) y el modelo `DevicePairingCode` con sus dos `__all__`. **No se toca** `DeviceRefused("pairing_required")` (`device_bridge.py:190`): eso es «tu credencial ya no vale», no el código. _Requisitos: 6.1, 6.3_

- [X] T050 [P] [US6] Retirar de `apps/console`: `components/workstation/pairing-dialog.tsx` y su test, `issuePairingCodeAction` (`app/(console)/workstation/actions.ts:29-33`), `issuePairingCode` y el tipo `PairingCodeOut` (`lib/backend/workstation.ts:94, 104`), y el bloque `ws.pair.*` entero (`i18n/lanes/workstation.ts:132-149`). _Requisitos: 6.1_

- [X] T051 [P] [US6] Retirar de `apps/desktop`: `app/routes/pair-dialog.tsx`, `app/routes/pair-errors.ts`, el canal IPC `app:workstation.pair` (`app-ipc.ts:84`, su `Shape` `"pair_code"` y su validación en `:262`), su registro en `electron/app-surface.ts:369`, el estado y la acción `introducir_codigo` de `workstation-state.ts`, y los textos `pair.*` de `app/i18n.ts:387-396`. _Requisitos: 6.1_

- [X] T051b [P] [US6] Retirar **las tres copias del alfabeto**, que no comparten constante: `apps/desktop/src/app-ipc.ts:176`, `apps/desktop/src/app/routes/pair-dialog.tsx:31` y `apps/api/src/nexus_api/core/pairing_codes.py:17`. Tres literales del mismo valor en dos lenguajes es la forma que tenía este defecto de sobrevivir a una búsqueda parcial; si queda uno, T047 lo caza. _Requisitos: 6.1_

- [X] T051c [P] [US6] Cambiar —no borrar— los textos que hablan de emparejar **sin ser del código**: `ws.machines.empty.body` en `apps/console/src/i18n/lanes/workstation.ts:75-78` dice literalmente «Pide aquí un código de emparejamiento», y `session.pair` (`apps/desktop/src/app/i18n.ts:348`) manda a «el pie de la lista lateral». Los dos quedarían mintiendo. _Requisitos: 6.1_

- [X] T051d [US6] Revisar lo que sobrevive con otro sentido: el prop `canPair` de `apps/console/src/components/workstation/machines-list.tsx` y la guarda de `workstation-setup.tsx:13` siguen teniendo sentido —el permiso no desaparece, cambia dónde se comprueba (T031, T033)—, y `services/device_pairing.py` **re-exporta `CODE_TTL` y `display_code`** que importa `workstation_partner.py:47`. Deshacer ese re-export antes de borrar el módulo, o el fallo aparece lejos de su causa. _Requisitos: 6.1_

- [X] T052 [US6] Reescribir el **arranque** de los ocho tests que usan `/device/pair` como **preparación y no como sujeto** —`test_device_bridge.py`, `test_device_bridge_inbound.py`, `test_device_renewal.py`, `test_workstation_setup.py`, `test_teammate_reaches_the_machine.py`, `test_identity_acts_do_not_meter.py`, `isolation/test_30_device_partner_scope.py`, `isolation/test_27_local_execution_audit_tenant_tagged.py`— para que registren por el camino nuevo. **No se borran**: lo que prueban sigue haciendo falta, solo cambia cómo llegan a tener una máquina. Si esto se descubre a mitad de la fase, descarrila. _Requisitos: 6.1_

- [X] T052b [US6] Retirar los tests cuyo **sujeto** era el código: `apps/api/tests/integration/test_device_pairing.py` (9 casos) y `apps/desktop/tests/pairing-flow.test.tsx`. **Después** de que T047 esté verde, no antes: borrar el test y el código a la vez deja el hueco sin vigilar. _Requisitos: 6.1_

- [X] T053 [US6] **La única migración de la spec**, en `apps/api/alembic/versions/`: elimina `device_pairing_codes` —la tabla, su índice y su **política de RLS**, las tres creadas en `0107_device_owner_and_pairing.py:155-231`—. Es **destructiva**. Se ensaya **arriba, abajo y arriba**, como la 0123. El `downgrade` recrea la tabla **vacía** con su política: no se restauran códigos —son secretos de diez minutos y bajar una versión no debe resucitar credenciales— pero sí la forma, para que bajar no deje el esquema roto. _Requisitos: 6.3_

- [X] T053b [US6] Quitar `device_pairing_codes` del **censo de RLS**, `apps/api/tests/isolation/test_21_rls_covers_every_tenant_table.py:82`. Ese test enumera toda tabla con `tenant_id`/`partner_id` y su política; si la tabla se va y el censo no, el rojo aparece en la suite de aislamiento y **parece** una garantía rota cuando es una entrada obsoleta. Va en el **mismo commit** que T053. _Requisitos: 6.3_

- [X] T054 [US6] Comprobar que, retirada la tabla, **no queda ningún secreto de registro en reposo** en la base. Se comprueba buscando. _Requisitos: 7.4_

**Checkpoint**: un solo camino, y el que queda es el bueno.

---

## Phase 9: Polish

- [X] T055 [P] Actualizar `docs/desktop-workstation.md` y `docs/desktop-teammates.md` **en el mismo commit** que cambia lo que describen. Un PR que cambia comportamiento documentado y no toca su documento se devuelve. _Requisitos: —_

- [X] T056 [P] Pasar los cuatro gates de interfaz del `CLAUDE.md` del workspace —estados, accesibilidad, responsive y tokens— sobre las pantallas tocadas en la consola y en el escritorio. _Requisitos: 5.1, 2.1_

- [ ] T057 Ejecutar **`./scripts/verify.sh` entero**: lint (`ruff` + `mypy --strict`), py y js. Este cambio toca API, consola y escritorio a la vez, que es exactamente donde este repositorio ha roto la tubería dos veces — y las dos por no correr el worker, `mypy --strict`, el paquete compartido o el `next build`. **Una sola ejecución de pytest a la vez.** _Requisitos: —_

- [ ] T058 Recorrer `quickstart.md` entero a mano, con la aplicación de verdad y una máquina de verdad. **Lo que salga de ahí manda sobre lo que digan los tests.** Lo firma Luis. _Requisitos: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1_

- [X] T059 Anotar en la KB (`research/2026-09-19-auditoria-clase-mundial/_index.md` §0) lo entregado y lo aprendido, y dejar dicho a la spec 011 **dónde vive** la pieza que va a reutilizar. _Requisitos: 1.1_

---

## Dependencies & Execution Order

### Por fases

- **Setup (1)** y **Puertas (2b)**: sin dependencias, se pueden empezar ya.
- **Foundational (2)**: solo T004. Bloquea a US3 y US4, no a US1 ni US2.
- **US1 (3)**: depende de T006 (su puerta de aislamiento). **No depende de US3 ni de T005**, cuyo objeto es el registro.
- **US2 (4)**: reutiliza la revocación de una máquina de US1.
- **US3 (5)**: depende de T004 y T030. **No depende de US1 ni US2.**
- **US4 (6)**: depende de T001 y de US3.
- **US5 (7)**: depende de US3.
- **US6 (8)**: depende de US3 **entregada y en uso**.
- **Polish (9)**: al final de lo que se decida entregar.

### El orden que importa

**US1 antes que todo lo demás** porque tiene valor hoy y porque la spec 011 la
espera. **US6 la última** porque retirar un camino antes de que el nuevo esté
rodado deja a la gente sin ninguno.

### Paralelizables

- T002 y T003 entre sí.
- T008, T009, T010 entre sí (mismo fichero, distintos casos: escribirlos juntos).
- T023 a T029 entre sí.
- T049, T050, T051 entre sí (tres aplicaciones distintas).

---

## Implementation Strategy

### MVP: solo US1

1. Fase 1 (Setup) → Fase 2 (T004) → Fase 2b (puertas).
2. Fase 3 (US1).
3. **Parar y validar**: §1 del quickstart, con el código de emparejamiento
   todavía puesto.
4. Entregable: ya se puede retirar el acceso de una persona, que hoy no se puede
   de ninguna forma. Y la spec 011 ya tiene su pieza.

### Entrega incremental

Cada historia se prueba sola y se despliega sola. Parar después de cualquiera
deja el producto mejor que antes y sin nada a medias — con una excepción que
conviene tener presente: **entre US3 y US6 conviven dos caminos de registro**.
Es deliberado y es seguro; lo que no sería seguro es el orden inverso.

---

## Registro de ejecución

**2026-09-22 — US1 entregada (checkpoint MVP).** T002, T003, T004, T006-T015.
Verde: 8 de `test_principal_access_revocation.py`, 2 de
`test_38_principal_access_revocation_scope.py`, y **17 de `test_29` + `test_30`
sin tocarlos** (T007 — el diff de los dos ficheros está vacío).

**T001 queda pendiente y es de Luis**: exige consultar producción y el sandbox no
llega. Bloquea US4, no US1.

### Lo que la implementación corrigió del plan

Dos cosas que estaban mal escritas y se arreglan declarándolas, no en silencio:

1. **La spec tiene dos migraciones, no una.** El plan miró que `revoked_at` y el
   motivo ya existían, y no miró que este repositorio siembra el **vocabulario
   de auditoría por migración**. Una acción sin frase se pinta con el fallback
   crudo, y `principal.access_revoked` es justo el asiento que alguien leerá con
   prisa el día que pregunte quién echó a quién. Sale `0124_access_revoked_vocab`
   —aditiva, con US1, ensayada arriba/abajo/arriba—; la destructiva sigue al
   final. El aviso estaba escrito en `api/console/support.py` y no se leyó.
   *(De paso: el identificador de revisión no puede pasar de 32 caracteres —
   `alembic_version.version_num` es `VARCHAR(32)`. El primero tenía 35.)*

2. **La ruta no va en `/console/workstation/*`: va en `/console/team/*`, con
   `team:manage`.** El contrato la había puesto junto a sus parientes, y el
   permiso de ahí es `workstation:pair`, que **tiene el builder** porque es
   «reclamar lo que es tuyo». Retirarle el acceso a otra persona es lo
   contrario, y colgarlo del permiso vecino por proximidad de fichero habría
   dejado a un builder echando a un owner. Tiene test
   (`test_a_builder_cannot_revoke_anyone`).

### Lo que costó menos de lo que parecía

`archive_all_for_principal` ya existía **y ya corría con rol dueño**, por la
misma razón que necesita esta operación. No se reescribió nada: se usó. La mitad
que faltaba era `end_all_sessions`, veinte líneas contra un índice que ya estaba.

**2026-09-22 (2) — US2 entregada, y el lado de servidor de US3 y US4.**

US2: T016, T017, T019, T020, T021, T021b. 15 tests de escritorio verdes.
US3 (servidor): T024-T027, T031, T032, T037. US4 (servidor): T038-T041.
Verde: 10 de `test_machine_registration.py`, 972 de aislamiento + dispositivos +
semillas sin regresiones, `verify.sh lint`.

**Queda el lado de cliente de US3** (T023, T028, T029, T033-T036: la ruta del
BFF, el método del *lane*, la llamada desde `adapters.ts` y el registro
automático), **T042/T042b de US4**, **US5** y **US6** entera.

### Dos enmiendas más que la implementación trajo

3. **US2 cambió de forma: no se construye la revocación desde la aplicación.**
   La spec 002 ya lo había decidido al revés con razón escrita (R11.2: archivar
   lleva el nombre de quien lo hace, y la credencial no gana una sexta
   operación). El diagnóstico —la pantalla miente— era correcto; el arreglo no.
   Lo que estaba roto era el texto, que además incumplía **dos** requisitos de
   la 002 a la vez. Menos código y más honesto.

4. **R3.4 estaba sobre-aplicado y se enmendó.** Pedía que los cuatro motivos de
   rechazo dieran una respuesta idéntica, heredando el rechazo indistinguible de
   la spec 009. Aquél protege el canje de un código, donde quien llama es **un
   desconocido** que puede probar hasta acertar. Aquí quien llama ya presentó su
   sesión y su membresía, y los motivos son sobre **sí mismo**. Uniformarlo no
   protegía a nadie y dejaba a la persona sin saber qué hacer. Se conserva lo
   único que heredaba sentido: «no hay sesión» y «caducó» son indistinguibles,
   porque la acción es la misma. De paso resuelve la contradicción que el
   análisis cruzado había encontrado entre R3.4 y R4.4.

### Y un detalle de arquitectura que apareció al ejecutar

La ruta de registro **no puede usar `workstation_scope`**: esa dependencia entra
en el rol de aplicación, que —correctamente— no tiene permisos sobre
`console_auth`. El rol que sirve peticiones de producto no tiene por qué leer
las sesiones de nadie, y esta ruta necesita mirarlas porque la frescura es la
mitad de lo que decide. Así que cruza los dos mundos con el patrón del puente,
igual que `services/principal_access.py` y por la misma razón.

**2026-09-22 (3) — el lado de cliente de US3.** T023, T033, T034, T035, T036.

- **La ruta del BFF** (`apps/console/src/app/api/desktop/register-machine/route.ts`)
  copia el camino de `redeem` con una diferencia dicha en su cabecera: **ésta sí
  devuelve cuerpo**, porque entrega una credencial que la aplicación guarda
  cifrada, no una cookie que viaja sola. 6 tests.
- **El identificador de instalación** (`apps/desktop/src/install-id.ts`) vive
  **aparte de la credencial**, que es la decisión: si estuviera en el almacén,
  desemparejar lo borraría y volver a entrar crearía una máquina nueva cada vez.
  6 tests, incluidos los tres de fichero corrupto — un fichero que nadie mira no
  puede dejar a la aplicación sin poder registrarse.
- **El registro automático** (`app-runtime.ts`): antes de anunciar «sin
  emparejar», se intenta registrar con la sesión recién confirmada.

### Una tercera enmienda, la misma lección que la de R3.4

Los tres fallos de registro —volver a entrar, estar en el tope, no haber red— se
distinguen **en la aplicación**, con su texto y su camino, aunque la API los
uniforme. No es una contradicción: al otro lado de la API puede haber un
desconocido, y en la aplicación hay alguien que ya presentó su sesión. Decirle
«no se pudo» a secas le dejaría sin saber qué hacer.

Verde: 968 de escritorio, 6 del BFF, `typecheck` limpio.

**2026-09-22 (4) — US5, la carpeta al frente.** T043, T045.

«Hoy» solo anunciaba la máquina cuando **no** estaba conectada, así que una
recién registrada y sin ningún directorio declarado quedaba «conectada» y en
silencio: no podía tocar un fichero y no decía por qué. Con el registro por
sesión eso deja de ser un caso raro y pasa a ser **el estado normal del primer
arranque**, porque ya no hay ceremonia de emparejar donde enterarse.

Ahora se anuncia, dice cuántos clientes están sin carpeta y qué se pierde
mientras tanto, y la acción que ofrece es **declarar la carpeta** y no la
primera de la lista. 3 tests nuevos; 20 en el fichero.

**Y un error mío que el gate cazó, que es para lo que está**: inventé la forma
de `PrincipalResolution` en vez de leerla —supuse `{ok, principal}` y es una
unión discriminada por `kind`—. Typecheck de la consola y `next build` en rojo.
Corregido en la ruta y en su test, que compartían el error porque los escribí
seguidos. La suite de escritorio no lo habría visto: era de la consola.

**2026-09-22 (5) — US6, el código desaparece. La spec queda en 59 de 65.**

Retirado: `core/pairing_codes.py`, `services/device_pairing.py`, el modelo y su
repositorio, `POST /device/pair` con sus dos esquemas, la ruta de emisión, el
diálogo de la consola y el de la aplicación, el canal IPC, el método `pair()`
del runtime, la acción `introducir_codigo` y **la tabla**, con la migración
`0126` ensayada arriba/abajo/arriba. Su `downgrade` recrea la tabla vacía con su
política: no resucita códigos, pero no deja el esquema roto.

### El barrido evitó romper el inicio de sesión

`test_39_no_pairing_code_path.py` se escribió en rojo y se dejó barrer. Cazó
tres restos que se me habían pasado — y uno de ellos **no era un resto**:

**`core/pairing_codes.py` no era del emparejamiento.** Los códigos de sesión de
la spec 009 usaban el mismo generador, así que borrarlo habría roto el inicio de
sesión de la aplicación. No se ve en ningún test de comportamiento del
emparejamiento, porque quien lo usaba era otro mecanismo.

Se quedó, renombrado a **`core/one_time_codes.py`**: lo que hace, no quién lo
estrenó. Un nombre que se refiere al primer llamante miente en cuanto hay un
segundo. Y el barrido cambió de forma: el alfabeto ya no está en la lista de «no
puede quedar» —tiene dueño legítimo— sino en un test propio que exige **una sola
definición**, que era la intención real.

Es la tercera vez en esta sesión que un barrido encuentra algo que enumerar no
habría encontrado. La primera fue `woocommerce.*` con la garantía 8.

### Lo que cambió de comportamiento, y por qué es correcto

Dos tests del escritorio fijaban que **otra persona en una máquina ajena se
quedaba fuera**: veía «emparejada por otra persona» y no podía trabajar, porque
no había forma de darle credencial sin otro código. Ahora **recibe la suya** —es
el caso límite que la spec declara: dos personas en la misma máquina física,
cada una con su credencial—. Lo que sigue sin pasar, y es lo que esos tests
defienden ahora, es que vea la ajena.

Verde: 950 de escritorio, 8 del barrido, `verify.sh lint`.

**2026-09-22 (6) — el cierre, y una tarea que llegó tarde.**

T005 (el modelo de amenaza) decía **«antes de tocar código»** y se escribió
después de entregar US3. El trabajo que describe se hizo y se probó, pero el
orden del método existe por algo: escrito después, un modelo de amenaza corre el
riesgo de justificar lo construido en vez de comprobar si debía construirse.

Está redactado al revés para compensarlo —busca dónde el cambio **empeora** las
cosas— y el resultado es que nada de lo revisado obliga a cambiar lo entregado:
cierra un vector (el patrón «teclea este código», que Storm-2372 explotó),
mejora dos casos, repone el freno que el tope recupera, y deja el resto igual. El
único punto que sí obligó a corregir algo —el permiso de la revocación— se
corrigió durante la implementación y tiene test.

También: `docs/desktop-workstation.md` actualizado en el mismo cambio (regla de
la spec viva), los cuatro gates de interfaz sobre las pantallas tocadas —sin hex
inline, diálogo con `role`/`aria-modal`/foco en cancelar, `pnpm lint` con las
reglas de tokens en verde— y la nota de la KB.

**62 de 65.** Lo que queda: `verify.sh` entero (corriendo) y el recorrido manual
del quickstart, que firma Luis.

**2026-09-22 (7) — T057, y el barrido tenía un agujero del tamaño de la otra
punta del cable.**

`verify.sh` entero destapó un rojo en la consola, y tirando de él salió una
tanda entera de restos que **T047 había declarado verde**. El fallo no era del
código retirado: era de **cómo buscaba el barrido**.

`GONE` eran nombres de símbolos —`DevicePairingCode`, `issuePairingCode`,
`PairingCodeOut`—, todos del lado que se estaba borrando. Ninguno aparece en el
escritorio, así que el barrido pasó por `apps/desktop/src` sin ver que allí
seguía viva **la mitad cliente del cable**: `HttpTransport.pair()` haciendo
`POST /device/pair` contra un endpoint que ya no existe, con su clase
`PairingFailed`, sus dos códigos de error y un test verde encima. Código muerto
con test verde es la peor clase: da confianza y no cubre nada.

La corrección es de una línea conceptual: **se caza por la ruta, no por el
nombre.** `/device/pair` es lo que R6.1 dice que no existe, y es la única cadena
que los dos extremos están obligados a compartir. Con ella dentro, el barrido
pasó de 8 a 13 casos y encontró de golpe:

| Resto | Dónde | Por qué sobrevivió |
|---|---|---|
| `HttpTransport.pair()` y `PairedCredential` | `apps/desktop/src/http-transport.ts` | nadie lo llamaba; nada se ponía rojo |
| `PairingFailed` y sus dos códigos | ídem + `app/routes/pair-errors.ts` | la tabla de motivos tenía seis, tres imposibles |
| `WorkstationAction` con `introducir_codigo` | `app/shell/workstation-actions.tsx` | **copia local** del vocabulario de `BarAction` |
| el bloque `ws.pair.*` entero (12 claves) | `apps/console/src/i18n/lanes/workstation.ts` | T050 lo daba por retirado y no lo estaba |
| `ws.machines.empty.body`, `session.pair`, `env.machine.none` | consola y escritorio | T051c los daba por corregidos y no lo estaban |

El de `WorkstationAction` tiene su propia ironía: `bridge.ts` llevaba escrito
desde la spec 010 que tener el vocabulario dos veces «dejaba pasar acciones que
no existían», y la segunda copia estaba tres ficheros más allá haciendo
exactamente eso. No se arregla con un test — se arregla **borrando la copia**:
ahora `WorkstationAction = BarAction`, y la deriva es imposible en vez de
vigilada.

Lo que esto deja dicho para la 015 y las que vengan: **una tarea marcada `[X]`
no es evidencia.** T050 y T051c estaban marcadas y no estaban hechas. Lo único
que distinguió lo hecho de lo declarado fue correr la tubería entera — que es,
literalmente, lo que T057 existe para forzar.

Y el aviso de la primitiva `EmptyState` («EmptyState without action») hizo de
cuarto gate sin que nadie lo invocara: el vacío de la consola se quedó sin
acción al retirar el diálogo. La respuesta correcta no era devolver un botón,
sino `readonly` y decir dónde continúa el camino — desde la 012 la consola **no
puede** dar de alta una máquina, ni siquiera quien tiene el permiso.

#### Tres tests de la API que T052 no vio, y uno de ellos es una mejora

T052 reescribió los ocho tests que usaban `/device/pair` como **preparación**.
Quedaron tres donde el emparejamiento era el **sujeto**, y por eso no estaban en
esa lista ni en la de T052b, que solo retiró las dos suites enteras:

1. **`test_pairing_gives_the_machine_a_credential_that_names_it`.** La propiedad
   —la credencial nombra máquina, partner y generación, y no nombra tenant—
   sigue siendo la que importa; lo que cambió es por dónde se pide. Reescrito
   sobre `register_machine`, no retirado: ninguna otra prueba verificaba los
   claims del alta.
2. **`test_two_people_can_pair_the_same_hostname`.** Necesitaba dos personas
   **de verdad**: `add_console_member` fabrica un `user_id` inventado, que valía
   mientras la credencial salía de un código —al canje le daba igual quién
   tecleara— y ya no vale, porque registrar mira si esa persona confirmó quién
   era hace poco. Es el mismo cambio de fondo que la spec traía, visto desde las
   pruebas.
3. **`test_the_only_unauthenticated_route_is_the_pairing_exchange`**, que es el
   interesante. Afirmaba que `/device/pair` estaba montado **sin credencial**,
   con su excepción escrita y justificada. Al irse el código, esa excepción se
   queda sin caso: **el puente no tiene ya ninguna puerta sin llave.**

El tercero no se retira — se le da la vuelta. `UNAUTHENTICATED_BY_DESIGN` sigue
existiendo, vacío, y el test afirma que está vacío. Su trabajo es el mismo que
antes: obligar a que una excepción futura se escriba y se razone en vez de
colarse como un endpoint más. **Es lo que esta spec ganó sin proponérselo**, y
no estaba en el modelo de amenaza: cerró un vector (A-2) y, de paso, la última
ruta anónima del puente.
