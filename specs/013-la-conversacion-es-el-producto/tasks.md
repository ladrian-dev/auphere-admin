---

description: "Tareas de la spec 013 — la conversación es el producto"
---

# Tasks: La conversación es el producto

**Input**: documentos de diseño en `/specs/013-la-conversacion-es-el-producto/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: NO son opcionales. La constitución §VII dice que cada criterio de
aceptación nace como test y que el rojo se ve antes de la implementación.

**Organization**: por historia de usuario, para que cada una se pueda soltar sola.

## Reglas de este repo *(constitución)*

- Cada tarea cita sus requisitos: `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Test primero (§VII): se escribe, se ve en rojo, y solo entonces se implementa.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias)
- **[Story]**: a qué historia pertenece (US1…US7)

---

## Phase 1: Setup

**Propósito**: dar de alta lo único que esta spec instala.

- [X] T001 Añadir `react-markdown@10.1.0`, `remark-gfm@4.0.1` y `remend@1.3.1` a
      `packages/companion-ui/package.json`, y actualizar el lockfile con `pnpm install`
      desde la raíz. **Ojo al lockfile único**: añadir una dependencia en un paquete puede
      romper el typecheck de otro, y quitarla no lo deshace — comprobar con
      `./scripts/verify.sh js` antes de dar la tarea por hecha.
      _Requisitos: 2.1_

- [X] T002 Dejar escritas las tres licencias en `apps/desktop/THIRD-PARTY-LICENSES.md`
      con el párrafo citado de cada una (MIT para `react-markdown` y `remark-gfm`,
      Apache-2.0 para `remend`), copiando los textos verificados en
      [research.md](./research.md) §5. **Es la puerta de licencias de §VIII**, no un trámite.
      _Requisitos: 2.1_

**Checkpoint**: las dependencias están, con su licencia por escrito.

---

## Phase 2: Foundational

**Propósito**: lo que más de una historia necesita. Es poco, a propósito: esta spec
no añade infraestructura.

- [X] T003 Extender el tipo del resumen de run en `packages/companion-ui/src/wire.ts`
      *(la tarea decía `types.ts`; los tipos de cable viven en `wire.ts` — corregido al
      implementar, porque una tarea que apunta a un fichero que no existe engaña)*
      con `prompt: string | null`. **Hecha solo su mitad**: el tipo de resultado de
      ejecución (`output`, `truncated`, `available`) es de US3 y entra con ella —
      declararlo ahora sería código muerto hasta entonces.
      _Requisitos: 1.1_ · *(3.1 queda con US3)*

**⚠️ CRÍTICO**: ninguna historia empieza antes de T003, porque las dos primeras
comparten estos tipos.

**Checkpoint**: los contratos existen en TypeScript.

---

## Phase 2b: Las puertas de la constitución

**Propósito**: las comprobaciones que `/speckit-analyze` no deja pasar.

- [X] T004 [P] Test de frontera en `apps/api/tests/isolation/test_36_thread_text_scope.py`:
      pedir los runs de una conversación de otra persona del mismo partner responde como
      si no existiera, y buscar no devuelve contenido ajeno. **No es una de las siete
      garantías** —la spec no toca ninguna— pero por aquí viaja **texto de una
      conversación**, y una frontera por la que pasa texto merece su test. En rojo
      bloquea el merge.
      _Requisitos: 1.3, 7.2_

- [X] T005 Licencias: cubierta por T002. *(La puerta del medidor **no aplica**: esta
      spec no gasta modelo, reloj de máquina ni herramienta de pago — la conversación no
      gasta, gasta el turno, y lo mide la 004. Borrarla es una decisión, no un descuido.)*
      _Requisitos: —_

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: US1 — El hilo recuerda la conversación entera (P1) 🎯 MVP

**Goal**: al reabrir un hilo se ve lo que escribió la persona y lo que respondió el
teammate, en orden.

**Independent Test**: escribir, cerrar la aplicación, abrir, y encontrar las dos
mitades. No necesita ninguna otra historia.

### Tests para US1 ⚠️ *(se escriben y se ven en rojo antes de implementar)*

- [X] T006 [P] [US1] Test de contrato en `apps/api/tests/integration/test_thread_runs_carry_prompt.py`:
      el resumen de run incluye `prompt` con el texto tal como se escribió, y el orden es
      ascendente por `started_at`. Rojo esperado: hoy el resumen tiene cuatro campos.
      _Requisitos: 1.1, 1.2_

- [X] T007 [P] [US1] Test en `apps/api/tests/integration/test_thread_runs_carry_prompt.py`:
      con un run **en marcha**, el `prompt` ya viaja — es lo que permite recargar a mitad
      de respuesta sin perder lo escrito.
      _Requisitos: 1.4_

- [X] T008 [P] [US1] Test de pantalla en `packages/companion-ui/tests/thread-remembers-user-messages.test.tsx`
      *(ruta corregida: las suites de este paquete viven en `tests/`, no junto al componente)*:
      dado un hilo con varios runs, el timeline pinta la burbuja de la persona **antes**
      de los eventos de ese run.
      _Requisitos: 1.2_

### Implementación de US1

- [X] T009 [US1] Ampliar `CompanionRunSummaryOut` y la consulta de `list_thread_runs` en
      `apps/api/src/nexus_api/api/console/companion.py` para traer el `content` del
      mensaje `role="user"` de cada run. **Un run tiene exactamente uno** (data-model), así
      que es un `JOIN`, no una segunda lista. `null` solo ante la anomalía de no haber fila.
      _Requisitos: 1.1, 1.2_

- [X] T010 [US1] Pintar la burbuja de la persona en
      `packages/companion-ui/src/components/timeline.tsx`, antes de los eventos de su run.
      **Aparece en la aplicación y en la consola**: las dos tienen hoy el mismo hueco.
      _Requisitos: 1.2, 1.4_

- [X] T011 [US1] Ejecutar `./scripts/verify.sh js` **entero** y la suite de la API.
      Esta historia toca el paquete compartido: la suite de escritorio sola no vale.
      _Requisitos: 1.1, 1.2_

**Checkpoint**: el hilo es una conversación. **Se puede parar aquí y haber entregado
lo que más se nota.**

---

## Phase 4: US2 — Lo que el agente escribe se puede leer (P1)

**Goal**: listas, tablas, énfasis, enlaces y código con su formato, y el código se copia.

**Independent Test**: pedir una respuesta con las tres formas y leerla sin descifrar
sintaxis.

### Tests para US2 ⚠️

- [X] T012 [P] [US2] Test en `packages/companion-ui/src/components/__tests__/markdown.test.tsx`:
      un mensaje con título, lista, tabla GFM, énfasis y bloque de código produce los
      elementos correspondientes, no un párrafo con el texto en crudo.
      _Requisitos: 2.1_

- [X] T013 [P] [US2] Test de seguridad en el mismo fichero: un mensaje con `<script>`,
      con `<img src="http://…">` y con un enlace `javascript:` **no** produce ninguno de
      los tres. Es el requisito que justifica la elección de librería (research §5) y el
      que más barato es dar por bueno sin comprobar.
      _Requisitos: 2.3_

- [X] T014 [P] [US2] Test de streaming en el mismo fichero: con énfasis y código inline
      **abiertos y sin cerrar**, se pinta algo legible y el resto del mensaje no se rompe.
      _Requisitos: 2.4_

- [X] T015 [P] [US2] Test en el mismo fichero: un mensaje de 50 000 caracteres pinta una
      parte, dice que hay más, y permite ver el resto.
      _Requisitos: 2.5_

- [X] T016 [P] [US2] Test en el mismo fichero: copiar un bloque de código da exactamente
      el código, sin el resto del mensaje ni las comillas del cercado.
      _Requisitos: 2.2_

### Implementación de US2

- [X] T017 [US2] Crear `packages/companion-ui/src/components/markdown.tsx`: `react-markdown`
      con `remark-gfm`, **sin `rehype-raw`**, y `remend` aplicado al texto antes de
      pintarlo. Bloquear imágenes y acotar `urlTransform` a protocolos seguros.
      **El único sitio del paquete que pinta texto de un mensaje.**
      _Requisitos: 2.1, 2.3, 2.4_

- [X] T018 [US2] Cambiar `timeline.tsx` para que el texto de un mensaje pase por
      `markdown.tsx` en vez del `<p whitespace-pre-wrap>` de hoy.
      _Requisitos: 2.1_

- [X] T019 [US2] Botón de copiar en los bloques de código, con el texto original —no el
      pintado— y su estado de «copiado».
      _Requisitos: 2.2_

- [X] T020 [US2] **El parpadeo de las tablas a medias**: pintar por bloques y no repintar
      los ya cerrados, con un rebote de 50-100 ms. GFM exige la fila delimitadora, así que
      una cabecera se ve como párrafo hasta completarse; **esto es trabajo de la
      implementación, no de la librería** (research §5), y sin esta tarea se cuela como
      defecto de la v1.
      _Requisitos: 2.4_

- [X] T021 [US2] Acotar lo que se pinta de un mensaje enorme, con «ver el resto».
      _Requisitos: 2.5_

- [X] T022 [US2] Los cuatro gates de interfaz sobre el mensaje renderizado: estados,
      `a11y-audit` (contraste del código y de las tablas, foco del botón de copiar),
      `responsive-audit` (una tabla ancha en la ventana mínima) y `design-tokens` (ni un
      hex suelto en el Markdown).
      _Requisitos: 2.1, 2.2_

- [X] T023 [US2] `./scripts/verify.sh js` entero. Toca el paquete compartido **y** añade
      dependencias: es el escenario exacto que ha roto la tubería dos veces.
      _Requisitos: 2.1_

**Checkpoint**: se puede leer lo que el agente escribe. **Se puede parar aquí.**

---

## Phase 5: US3 — Se ve lo que el comando hizo (P1)

**Goal**: quien aprueba un comando ve lo que hizo, sin que eso se guarde en ningún sitio
durable.

**Independent Test**: aprobar un `make build` que falla y leer el motivo en pantalla.

**⚠️ La historia de más riesgo de la spec.** Toca tres capas y roza un contrato congelado.
Leer [contracts/la-salida-en-vivo.md](./contracts/la-salida-en-vivo.md) antes de empezar.

### Tests para US3 ⚠️

- [X] T024 [P] [US3] **El test de que algo NO está**, primero y antes que nada, en
      `apps/api/tests/integration/test_exec_output_is_not_durable.py`: tras una ejecución
      con salida, **ninguna tabla contiene ese texto** —ni `local_executions`, ni la
      auditoría, ni ninguna otra—. Se comprueba consultando, no confiando: es el criterio
      más fácil de dar por bueno sin mirar (CE-005).
      _Requisitos: 3.2_

- [X] T025 [P] [US3] Test en el mismo fichero: la clave efímera caduca, y pasados los
      quince minutos la respuesta es `available: false` — que **no es un error**.
      _Requisitos: 3.2, 3.3_

- [X] T026 [P] [US3] Test de regresión en `apps/api/tests/integration/test_local_exec_two_readers.py`:
      publicar para dos lectores **no cambia lo que recibe el turno**. Hoy `await_result`
      hace `LPOP` y se lleva el payload; romperlo dejaría al modelo sin la salida que
      acaba de ganar, y es una regresión cara y silenciosa.
      _Requisitos: 3.1_

- [X] T027 [P] [US3] Test de alcance en el mismo fichero: otra persona del mismo partner
      no obtiene la salida de una ejecución que no aprobó.
      _Requisitos: 3.1_

- [X] T028 [P] [US3] Test de pantalla en `packages/companion-ui/src/components/__tests__/exec-result.test.tsx`:
      se ve el desenlace, el código de salida y la muestra; la salida va marcada como
      **contenido leído** y distinguible de lo que dice el teammate; si se recortó, se dice.
      _Requisitos: 3.4, 3.5_

- [X] T029 [P] [US3] Test en el mismo fichero: con `available: false`, la tarjeta **dice**
      que la salida no se conserva, en vez de dejar un hueco que parezca un fallo (§V).
      _Requisitos: 3.3_

### Implementación de US3

- [X] T030 [US3] En `apps/api/src/nexus_api/services/local_dispatch.py`, que
      `publish_result` deje **dos** cosas: la cola que el turno consume, **con su
      comportamiento intacto**, y una clave de solo lectura con TTL de quince minutos.
      _Requisitos: 3.1, 3.2_

- [X] T031 [US3] Ruta que sirve la salida en
      `apps/api/src/nexus_api/api/console/workstation.py`, bajo el **alcance de cliente que
      ya existe**, devolviendo `outcome, exit_code, output, truncated, available`.
      _Requisitos: 3.1, 3.5_

- [X] T032 [US3] Crear `packages/companion-ui/src/components/exec-result.tsx`, **hermano**
      de `exec-card.tsx`. **No se toca la tarjeta de aprobación**: su comentario dice
      «nunca la salida: la salida es del turno siguiente, no de la decisión» y sigue siendo
      verdad — decidir y ver son dos momentos distintos.
      _Requisitos: 3.1, 3.3, 3.4, 3.5_

- [X] T033 [US3] Pedir la salida desde la pantalla por el `Transport` del paquete
      (`transport.ts`), para que la aplicación la pida por IPC y la consola por `fetch`,
      sin dos implementaciones.
      _Requisitos: 3.1_

- [X] T034 [US3] Los cuatro gates de interfaz sobre la tarjeta de resultado. Atención al
      estado `available: false`, que es el que más fácil se queda sin diseñar.
      _Requisitos: 3.3_

- [X] T035 [US3] Actualizar `docs/desktop-teammates.md` **en el mismo commit**: hoy dice
      que la muestra «llega al modelo» y a partir de aquí también llega a la persona, con
      su caducidad. Es la regla de la spec viva.
      _Requisitos: 3.1, 3.3_

- [X] T036 [US3] `./scripts/verify.sh` completo —lint, py y js—, más la suite del worker.
      Esta historia toca API, paquete compartido y dos clientes.
      _Requisitos: 3.1, 3.2_

**Checkpoint**: se deja de tener que creer al agente. **Se puede parar aquí.**

---

## Phase 6: US4 — Una conversación por asunto (P2)

**Goal**: varias conversaciones con el mismo teammate, y volver a la última.

**Independent Test**: crear una segunda conversación y alternar entre las dos.

**Sin migración y sin API nueva**: `companion.threads` ya lo soporta desde la 003 y la API
ya lista y crea (research §3). Es la aplicación.

### Tests para US4 ⚠️

- [X] T037 [P] [US4] Test en `apps/desktop/tests/thread-selection.test.ts`: con varias
      conversaciones, abrir la aplicación lleva a la última en la que se trabajó, y crear
      una nueva no toca las anteriores.
      _Requisitos: 4.1, 4.2_

- [X] T038 [P] [US4] Test en el mismo fichero: con una tarea en marcha en otra
      conversación, se dice dónde está.
      _Requisitos: 4.3_

- [X] T039 [P] [US4] Test en el mismo fichero: el título se deriva de lo primero que se
      escribió, recortado, y **no** se le pide al modelo que titule — sería un turno de más
      y un gasto por una etiqueta.
      _Requisitos: 4.4_

### Implementación de US4

- [X] T040 [US4] Cambiar `app:thread.open` en `apps/desktop/src/electron/app-surface.ts`:
      **dejar de coger siempre `listed.data.find(t => !t.archived_at)`**. Listar, recordar
      la última y permitir crear.
      _Requisitos: 4.1, 4.2_

- [X] T041 [US4] Canales nuevos en `apps/desktop/src/app-ipc.ts` para listar, crear y
      cambiar de conversación, **validando la entrada** como el resto (el `preload` expone
      una función por canal, nunca un `invoke` genérico).
      _Requisitos: 4.1_

- [X] T042 [US4] Selector de conversación en `apps/desktop/src/app/routes/thread.tsx`, con
      algo que permita distinguirlas sin abrirlas.
      _Requisitos: 4.4_

- [X] T043 [US4] Derivar el título de lo primero escrito al crear la conversación, en vez
      del literal `"Hilo"` de hoy.
      _Requisitos: 4.4_

- [X] T044 [US4] Los cuatro gates sobre el selector. Estado vacío incluido: una
      conversación recién creada no tiene nada que enseñar y eso se diseña.
      _Requisitos: 4.1_

**Checkpoint**: los asuntos dejan de mezclarse.

---

## Phase 7: US6 — Al abrir, se puede escribir (P2)

**Goal**: lo primero que se ve es dónde escribir, no un panel de estado.

**Independent Test**: abrir y escribir sin pasar por ninguna otra pantalla.

**Depende de US4**: hace falta saber a qué conversación llevar.

### Tests para US6 ⚠️

- [X] T045 [P] [US6] Test en `apps/desktop/tests/hoy-composer.test.tsx`: con al menos un
      teammate, hay dónde escribir y se ve a quién.
      _Requisitos: 6.1_

- [X] T046 [P] [US6] Test en el mismo fichero: **sin ningún teammate**, lo primero es
      crear uno y **no** hay un composer que no lleve a ninguna parte (§V: la ausencia se
      diseña).
      _Requisitos: 6.2_

- [X] T047 [P] [US6] Test en el mismo fichero: con la máquina ausente se puede conversar
      igual, y el estado de la máquina sigue alcanzable sin ocupar el centro.
      _Requisitos: 6.3, 6.4_

### Implementación de US6

- [X] T048 [US6] Rehacer `apps/desktop/src/app/routes/hoy.tsx`: el composer y el selector
      de teammate al centro; la máquina y lo pendiente, alcanzables y a un lado.
      _Requisitos: 6.1, 6.4_

- [X] T049 [US6] El caso sin teammates, con su propia pantalla.
      _Requisitos: 6.2_

- [X] T050 [US6] Los cuatro gates sobre la pantalla de inicio. Es **la primera impresión
      del producto**: aquí los gates no son trámite.
      _Requisitos: 6.1, 6.2_

**Checkpoint**: la aplicación parece una herramienta de trabajo.

---

## Phase 8: US5 — Se puede corregir el tiro (P2)

**Goal**: copiar, editar y reintentar sin reescribir.

**Independent Test**: editar el último mensaje, reenviarlo, y copiar una respuesta.

### Tests para US5 ⚠️

- [X] T051 [P] [US5] Test en `packages/companion-ui/src/components/__tests__/message-actions.test.tsx`:
      editar y reenviar rehace el turno desde ahí, y la conversación **no** queda con dos
      versiones mezcladas.
      _Requisitos: 5.1_

- [X] T052 [P] [US5] Test en el mismo fichero: copiar da el texto **tal como se escribió**,
      no el pintado — con Markdown de por medio, son dos cosas distintas.
      _Requisitos: 5.2_

- [X] T053 [P] [US5] Test en el mismo fichero: con un turno en marcha, editar y reintentar
      no están disponibles **y se dice por qué**, en vez de que el control falle al pulsar.
      _Requisitos: 5.3_

- [X] T054 [P] [US5] Test en el mismo fichero: con una decisión pendiente, se pide esa
      decisión antes que aceptar un mensaje nuevo.
      _Requisitos: 5.4_

### Implementación de US5

- [X] T055 [US5] Acciones sobre un mensaje en `packages/companion-ui/src/components/timeline.tsx`:
      copiar, editar y reintentar, con sus objetivos de al menos 24×24 px.
      _Requisitos: 5.1, 5.2_

- [X] T056 [US5] Rehacer el turno desde un mensaje editado, sin dejar dos versiones.
      _Requisitos: 5.1_

- [X] T057 [US5] Los estados que bloquean —turno en marcha, decisión pendiente— dichos con
      palabras.
      _Requisitos: 5.3, 5.4_

- [X] T058 [US5] Los cuatro gates y `./scripts/verify.sh js`: toca el paquete compartido.
      _Requisitos: 5.1_

**Checkpoint**: se deja de reescribir lo ya escrito.

---

## Phase 9: US7 — Encontrar lo que se dijo (P3)

**Goal**: buscar dentro de lo hablado.

**Independent Test**: buscar un término de hace semanas y saltar ahí.

**Depende de US4**: sin varias conversaciones, buscar tiene poco que encontrar.

### Tests para US7 ⚠️

- [X] T059 [P] [US7] Test en `apps/api/tests/integration/test_conversation_search.py`:
      buscar devuelve en qué conversaciones **propias** aparece el término.
      _Requisitos: 7.1_

- [X] T060 [P] [US7] Test en el mismo fichero: **no** devuelve contenido de otra persona.
      Complementa a T004 desde el otro lado.
      _Requisitos: 7.2_

- [X] T061 [P] [US7] Test de pantalla: sin coincidencias se dice que no hay, de forma
      distinguible de estar cargando (§V).
      _Requisitos: 7.3_

### Implementación de US7

- [X] T062 [US7] Búsqueda en `apps/api/src/nexus_api/api/console/companion.py`, bajo
      `app.principal_id`. **Sin índice nuevo**: R7 es P3 y se resuelve con lo que hay; si
      hiciera falta un índice, es otra decisión y otro coste (data-model).
      _Requisitos: 7.1, 7.2_

- [X] T063 [US7] Extender ⌘K en `apps/desktop/src/app/App.tsx` para que además de navegar,
      encuentre.
      _Requisitos: 7.1_

- [X] T064 [US7] Los cuatro gates sobre los resultados de búsqueda.
      _Requisitos: 7.3_

**Checkpoint**: la memoria deja de ser la de la persona.

---

## Phase 10: Cierre

- [ ] T065 Recorrer [quickstart.md](./quickstart.md) entero a mano, con la aplicación
      construida. Lo que salga de ahí manda sobre lo que digan los tests.
      _Requisitos: todos_

- [X] T066 Actualizar `docs/desktop-teammates.md` con lo que esta spec cambió del timeline,
      y la KB (`research/2026-09-19-auditoria-clase-mundial/_index.md`) marcando 013 como
      entregada. **El puente es obligatorio en las dos direcciones** (§IX).
      _Requisitos: todos_

- [X] T067 `./scripts/verify.sh` completo **y** la suite del worker. La lista de lo que
      este repositorio olvida es siempre la misma: el worker, `mypy --strict`, el paquete
      compartido y el `next build`.
      _Requisitos: todos_

---

## Dependencies & Execution Order

### Orden de fases

- **Setup (T001-T002)**: sin dependencias.
- **Foundational (T003)**: **bloquea US1 y US3**, que comparten los tipos.
- **Puertas (T004-T005)**: en paralelo con las historias; T004 tiene que estar antes de
  fusionar US1 o US7.
- **Historias**: en el orden del plan — US1 → US2 → US3 → US4 → US6 → US5 → US7.
- **Cierre (T065-T067)**: al final de lo que se decida entregar.

### Dependencias entre historias

| Historia | Depende de | Por qué |
|---|---|---|
| US1 | T003 | El tipo del resumen de run |
| US2 | T001, T002 | Las dependencias y su licencia |
| US3 | T003 | El tipo del resultado de ejecución |
| US4 | — | Independiente |
| US6 | **US4** | Hace falta saber a qué conversación llevar |
| US5 | US2 | Copiar «el original y no lo pintado» solo tiene sentido con Markdown |
| US7 | **US4** | Sin varias conversaciones hay poco que buscar |

US1, US2, US3 y US4 son **independientes entre sí**: se pueden repartir.

### Paralelismo

Todos los bloques de test marcados `[P]` dentro de una historia van a la vez. Y las
cuatro primeras historias se pueden llevar en paralelo si hay gente, con la única
condición de T003 hecho.

---

## Parallel Example: US3

```bash
# Los seis tests de la historia 3, a la vez — y antes de tocar implementación:
Task: "T024 ninguna tabla contiene la salida"
Task: "T025 la clave efímera caduca"
Task: "T026 el turno sigue recibiendo lo suyo"
Task: "T027 otra persona no obtiene esa salida"
Task: "T028 la tarjeta enseña desenlace, código y muestra"
Task: "T029 con available:false se dice, no se deja un hueco"
```

---

## Implementation Strategy

### MVP: solo US1

1. Setup (T001-T002) — en realidad solo hace falta para US2; para US1 basta T003.
2. T003.
3. US1 completa (T006-T011).
4. **Parar y validar**: reabrir un hilo y ver la conversación entera.
5. Entregar.

**US1 sola ya arregla lo que más se nota**: hoy el hilo recuerda media conversación.

### Entrega incremental

Cada historia se suelta sola. El orden del plan va de menos a más riesgo, así que parar
en cualquier punto deja algo entregado y nada a medias. **US3 es la de más riesgo y la
que más confianza da**: si hay que elegir dos, son US1 y US3.

---

## Notes

- `[P]` = ficheros distintos, sin dependencias entre sí.
- **Ninguna tarea pide migración.** Si alguna lo parece, algo se entendió mal: releer
  [data-model.md](./data-model.md).
- Toda tarea que toque `packages/companion-ui` arrastra `./scripts/verify.sh js` entero.
  Es el paquete que este repositorio olvida y que le ha roto la tubería dos veces.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.

---

## Bitácora de implementación

### 2026-09-20 · US1 entregada (T003, T004, T006-T011)

**Lo que hay que saber antes de seguir con US2 o US3.**

**Una guarda existente se enmendó, y no a la ligera.**
`test_the_run_listing_carries_no_transcript` afirmaba que el listado de runs lleva
«metadatos y nada más», con un motivo bueno: los cuerpos viven en `…/events`, que
tiene su propio guardián, y duplicarlos sería «abrir una segunda puerta sin
portero».

Ese argumento **no cubre el mensaje de la persona**, porque ese mensaje no está en
`events` ni lo ha estado nunca: hay una fila de `companion.messages` que no
devolvía nadie. No hay primera puerta que duplicar. Y portero sí hay —el 404
opaco—, ahora probado dos veces: por el test vecino y por `test_36`.

La guarda **sigue en pie** para lo que protegía: ni respuesta del modelo, ni
razonamiento, ni resultado de herramienta.

**Dos rutas de las tareas estaban mal** y se corrigieron sobre la marcha: el tipo
va en `wire.ts` (no `types.ts`) y las suites de `companion-ui` viven en `tests/`.

**Un fallo fue de mi fixture, no del código.** El primer test del orden daba las
tres frases invertidas: `now()` en Postgres es el sello de la **transacción**, así
que tres runs creados en la misma compartían `started_at` y el orden quedaba
indefinido. En producción no pasa —cada run nace en su petición—, pero deja
anotado que **el orden no tiene desempate**: si algún día dos runs comparten
sello, el resultado es arbitrario.

**Una acción nueva en el reductor**: `replayed_prompt`, distinta de `prompt`.
Aquélla marca el run como activo y en marcha, y al reproducir un hilo viejo eso
pintaría como vivo un turno que terminó hace días.

**Verificado**: 4 tests de API + 3 de aislamiento + 4 de pantalla en rojo antes y
verdes después · `verify.sh js` entero · `verify.sh lint` · suite completa de la
API.

### 2026-09-20 (2) · US2 entregada (T001-T002, T012-T023)

**T020 partía de una premisa parcialmente falsa, y se descubrió al probarla.**
La tarea daba por hecho que habría que partir el texto en bloques y memorizar
los cerrados para que no parpadearan. **El test pasó sin escribir una línea**:
React reconcilia por tipo y posición, así que un bloque ya cerrado conserva su
nodo aunque el Markdown se vuelva a parsear entero.

Lo que sí cambia de forma es el bloque **en curso** —una cabecera de tabla se ve
como párrafo hasta que llega la fila delimitadora que GFM exige— y eso no es un
defecto: hasta ese momento no hay información para saber qué va a ser.

**Queda una preocupación real y sin medir**: volver a parsear todo el texto en
cada trozo es trabajo cuadrático sobre un mensaje largo. Es coste, no parpadeo.
Optimizarlo sin medirlo sería añadir maquinaria a ciegas, así que se deja
anotado y no se toca.

**Dos ajustes que salieron de probar, no de planificar:**

* `remend` exporta por **defecto**, no con nombre. El import de la tarea no
  habría compilado.
* Copiar un bloque daba el código **con el salto final que añade el cercado**.
  Se quita: pegar en una terminal algo que termina en salto lo ejecuta solo, y
  nadie espera eso de un botón que dice «copiar».
* Los botones quedaban **justo** en los 24 px de WCAG 2.2, sin margen. Subidos
  a la siguiente medida de la escala de 4 px.

**Verificado**: 11 tests nuevos en rojo antes y verdes después · 175 del paquete
compartido · `verify.sh js` entero **antes** de escribir código (por el lockfile
único) **y** después.

### 2026-09-20 (3) · US3, la mitad de servidor (T024-T027, T030, T031)

**Lo que está hecho**: `publish_result` deja el payload en **dos** sitios —la
cola que el turno consume con `LPOP`, intacta, y una clave de solo lectura con
su propio TTL—, `read_output_for_screen` la lee sin consumirla, y
`GET /console/clients/{ref}/workstation/executions/{id}/output` la sirve bajo el
alcance de cliente que ya existía.

**El TTL no es un número nuevo.** `RESULT_TTL_SECONDS` ya valía 900 segundos, así
que los «quince minutos» que la spec declaró coinciden con lo que había. Buena
señal: el plazo no se inventó para encajar el requisito.

**El test que afirma que algo NO está se escribió primero y barre el esquema
entero**: recorre `information_schema.columns` y busca la salida en **toda**
columna de texto o JSON de la base. No es «miré las tablas que se me ocurrieron»
— es que si alguien la escribe en una tabla nueva dentro de seis meses, este
test lo caza.

**Lo que falta de US3** (T028, T029, T032, T033, T034, T035, T036): la tarjeta de
resultado en `packages/companion-ui`, su estado `available: false`, el paso por
el `Transport`, los gates de interfaz y la actualización de
`docs/desktop-teammates.md`. El camino del dato está entero y probado; lo que no
existe todavía es la pantalla que lo enseña.

### 2026-09-21 · US3 (pantalla), US4, US6, US5 y US7 — la spec completa

**US3, la mitad que faltaba.** El timeline **no tenía representación de una
ejecución**: ni `exec.dispatched` ni `exec.completed` se consumían en el
cliente. T032 daba por hecho que existía la tarjeta y solo había que añadirle
un hermano; en realidad hubo que crear el carril entero —tipo de ítem, dos
casos del reductor y componente—. La tarjeta de aprobación **no se tocó**.

**US4 costó una línea de lógica y varias de cableado.** La elección vive ahora
en `thread-selection.ts`, pura y probada aparte; el proceso principal solo
ejecuta lo que decide. Dos detalles que salieron de escribir los tests:
`last_run_at` nulo **no** es «vieja» sino «recién creada» —descartarla mandaría
a la persona a otra parte justo después de crearla—, y un id recordado que ya
no existe no puede dejar la pantalla en blanco.

**US6 movió el centro de la primera pantalla.** Sin teammates **no se pinta el
composer**: un sitio donde escribir que no lleva a ninguna parte es peor que no
tenerlo. Lo escrito en Hoy viaja al hilo y se envía allí, donde vive el turno.

**US5.** Lo que se copia es el original y no lo pintado — con Markdown de por
medio son dos cosas distintas. Copiar sigue disponible aunque editar y
reintentar no lo estén: no cambia nada, y bloquearlo sería castigar sin motivo.

**US7 sin índice nuevo**, como decía el data-model. Una conversación aparece
una vez aunque el término salga cinco: la lista es de conversaciones, no de
coincidencias. Y la paleta distingue «buscando» de «no hay», que §V exige.

**Cuatro fallos que fueron míos, no del código**, y los cuatro los cazó una
prueba o una guarda del repo:

1. Un comentario de Python colado en TypeScript (revertido).
2. Un comentario JSX entre atributos, que no es válido.
3. Un fixture con `state` en vez de `status` — lo destapó **la guarda de i18n
   que se escribió el 2026-09-20**, que registra la clave ausente en vez de
   tumbar el render.
4. Un `eslint-disable` de una regla que este repo no configura.

**Y una decisión de vocabulario**: el test buscaba «decisión» y la aplicación ya
decía «confirmación pendiente». Ganó el texto existente — inventar un tercer
término es como se empieza a divergir.

**Los canales IPC son un contrato con test propio**: añadir tres obligó a
declararlos, que es exactamente para lo que está.
