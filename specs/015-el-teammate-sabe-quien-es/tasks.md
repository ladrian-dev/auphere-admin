---

description: "Tareas — spec 015, el teammate sabe quién es"
---

# Tareas: El teammate sabe quién es, qué día es y qué puede hacer de verdad

**Entrada**: `specs/015-el-teammate-sabe-quien-es/` — spec.md, plan.md,
research.md, data-model.md, contracts/lo-que-el-teammate-lee.md, quickstart.md

**Tests**: **no son opcionales** (§VII). Cada criterio nace como test, se ve en
rojo, y solo entonces se implementa. Esta spec tiene **tres rojos que no son el
camino feliz** y están marcados con ⚠️ donde toca.

---

## Reglas de este repo que aquí aprietan

- **Cada tarea cita sus requisitos** con `_Requisitos: N.m_`.
- **Una sola ejecución de `pytest` a la vez**: las suites comparten la base de
  desarrollo. Comprobarlo con `ps -eo pid,etime,command | grep "[p]ytest"` antes
  de lanzar, no solo recordarlo.
- **Los commits los ejecuta Luis**: se entrega el mensaje y se para.
- **El worker se toca de lleno**, que es donde este repositorio ha roto la
  tubería dos veces.

---

## Phase 1: Setup

**Propósito**: dejar escritas las tres puertas del Constitution Check antes de
tocar nada. Son declaraciones, no trabajo — pero sin ellas `/speckit-analyze`
para el plan.

- [X] T001 Verificar y marcar la puerta de **licencias**: comprobar que esta spec no añade ninguna dependencia — `git diff` sobre `apps/api/pyproject.toml`, `apps/worker/pyproject.toml` y `apps/desktop/package.json` tiene que quedar vacío al terminar. Dejarlo escrito en el Constitution Check del plan, que ya lo afirma. _Requisitos: —_

- [X] T002 Verificar y marcar la puerta del **medidor**: no aplica, y la razón va escrita — esta spec no añade ninguna llamada al modelo ni ninguna herramienta de pago. El único efecto sobre el consumo es de entrada y lo acota el Requisito 3, que tiene sus propias tareas (T014-T016). _Requisitos: 3.4_

- [X] T003 [P] Medir el margen del prefijo **de verdad y no por estimación**: contar los tokens de `SYSTEM_PROMPT` con el contador del proveedor, hoy (7.044 caracteres) y tras retirar los 631 de T020. Anotar los dos números en `research.md` §M-2, que hoy solo tiene la medida en caracteres y lo dice. Si el margen sobre el mínimo cacheable resultara estrecho, **T020 cambia de forma** y hay que decirlo antes de tocarlo. _Requisitos: 3.1_

---

## Phase 2: Foundational

**Propósito**: la pieza que las cuatro historias usan. **Ninguna historia puede
empezar sin esto.**

- [X] T004 Crear `apps/worker/src/nexus_worker/runtime/turn_clock.py` **moviendo** `_now_note` desde `runtime/pipeline.py:652-673` —con `_WEEKDAYS_ES` y el repliegue a UTC con marca visible (`:657-662`)—, y dejar en `pipeline.py` la importación. **Se mueve, no se copia**: copiarlo crearía la tercera fuente del mismo texto, que es el defecto que esta spec viene a cerrar. _Requisitos: 5.2, 5.5_

- [X] T005 Comprobar que **el agente de canal sigue verde sin tocar ni uno de sus tests** tras T004: `cd apps/api && uv run pytest tests/ -k "pipeline or handler or now_note" -q`. Si hay que modificar un test del canal para que pase, **el movimiento está mal** y es la señal — se revierte y se hace de otra forma. _Requisitos: 5.2_

**Checkpoint**: el reloj del turno vive en su sitio y el canal no se ha enterado.

---

## Phase 3: US1 — Lo que dice tener es lo que tiene (P1) · **MVP**

**Meta**: un teammate deja de prometer lo que no tiene, dice qué le falta y con
qué se arregla, y su identidad llega antes que la historia.

**Prueba independiente**: se crea un teammate por cada combinación de
interruptores y se le pregunta qué puede hacer; lo que conteste se compara con lo
que el servidor le entregó. Sin nada más de esta spec, los interruptores dejan de
mentir.

### Tests para US1 ⚠️

- [X] T006 [P] [US1] ⚠️ **El rojo que no cuenta si es `ImportError`.** Escribir en `apps/api/tests/unit/test_teammate_self_description.py` el test de la derivación por familias. Falla contra una función que no existe, así que **primero va la firma vacía de T010** y luego este test en rojo **por aserción**. Un `ImportError` no demuestra nada sobre el comportamiento. _Requisitos: 2.1, 2.3_

- [X] T007 [P] [US1] Test en `apps/api/tests/unit/test_teammate_self_description.py`: un teammate de **solo publicar** recibe una descripción que nombra publicar y confirmar, **no nombra ninguna lectura**, y nombra que le faltan las lecturas con el interruptor que las daría. Es el caso contado en el research: 2 herramientas en `build`. _Requisitos: 2.1, 2.3_

- [X] T008 [P] [US1] Test del **caso de cero herramientas**, que no es teórico: solo-publicar en modo `consult` entrega cero. La descripción DEBE decir que no tiene ninguna, por qué, y darle salida a la `<regla_madre>` en vez de dejarle una instrucción que equivale a callarse. _Requisitos: 2.5_

- [X] T009 [P] [US1] Tests en `apps/api/tests/unit/test_turn_messages.py`: (a) la identidad va en la **posición 2** y no se mueve con un historial de 40 mensajes; (b) el conocimiento **ya no lleva la identidad pegada delante**; (c) **sin teammate la lista de mensajes es exactamente la de hoy**. _Requisitos: 1.1, 1.2, 1.5_

### Implementación de US1

- [X] T010 [US1] Firma vacía de `describe_for_teammate(teammate, *, mode, machine_present)` en `apps/api/src/nexus_api/services/teammate_catalog.py`, **al lado de `for_teammate`** y leyendo de las mismas constantes. Al lado y no dentro: `for_teammate` devuelve nombres para el toolbelt y ésta devuelve prosa para el prompt; un retorno mezclado obligaría a cada llamante a cargar con lo que no usa. _Requisitos: 2.1_

- [X] T011 [US1] Implementar la derivación por familias: lecturas, propuestas de configuración y prueba, publicar, mover consumo y modelo, invitar y pedir ayuda, confirmar, y ejecutar en la máquina. **Las familias salen de `READ_TOOLS`, `PROPOSE_TOOLS`, `TRIAL_TOOLS`, `APPLY_TOOLS` y `MACHINE_TOOL`** del mismo módulo — no se enumeran los 44 nombres, que ya viajan en los *schemas*. _Requisitos: 2.1, 2.4_

- [X] T012 [US1] El mapa **interruptor → nombre legible** en el mismo módulo, con el comentario de por qué vive ahí: es **una segunda fuente en potencia** y la puerta de US2 lo recorre. Para `shell_local` la condición es distinta y se dice entera — vincular una máquina al cliente y que esté presente—, no «activa un interruptor». _Requisitos: 2.3, 2.4_

- [X] T013 [US1] Ampliar `system_prompt_for` en `services/teammate_catalog.py:132-141` para que componga el bloque entero: quién es, qué puede, qué le falta y con qué, la salida de la regla madre cuando no tiene lecturas, la línea de que **los teammates no se hablan entre ellos** (R2.7), y las cuatro frases de comportamiento que ya existen. _Requisitos: 1.1, 2.3, 2.5, 2.7_

- [X] T014 [US1] `build_messages` en `apps/worker/src/nexus_worker/runtime/companion/prompt.py:352-369` gana el parámetro `identity`, que se inserta **tras el prefijo y antes de `history`**. El conocimiento **se queda donde está**: es material de consulta y su sitio es cerca del turno. _Requisitos: 1.1, 1.2_

- [X] T015 [US1] Dejar de pegar la identidad al conocimiento en `apps/api/src/nexus_api/api/console/companion.py:1229-1234` y pasarla por el parámetro nuevo. Es el cambio que hace que la identidad deje de viajar de polizón. _Requisitos: 1.1_

- [X] T016 [US1] ⚠️ **El corte 2, que es lo que hace que esto no salga caro.** Añadir el `cache_control` que falta en la cabecera de `apps/worker/src/nexus_worker/runtime/llm.py:204-249`: **corte 1** tras el último bloque del texto compartido, **corte 2** tras el bloque de identidad. *(Numeración posicional, fijada en `plan.md` §D-2: corte 3 es el móvil del final. «El tercero» también sería cierto —es el tercero que existirá— y no se usa, para que nadie implemente el que no era.)* Sin el corte 2, `_with_prompt_caching` fusiona los dos mensajes iniciales y **los 7 KB compartidos se escriben una vez por teammate**. Hay sitio: Anthropic admite cuatro y esta ruta usa dos (`llm.py:176-179`, y `cache_tail=True` en `companion.py:1720`). _Requisitos: 1.4, 3.1_

- [X] T017 [US1] Test en `apps/api/tests/unit/test_prompt_cache_breakpoints.py`, **sin llamar al proveedor**: `_with_prompt_caching` es pura, así que se le da una lista con prefijo + identidad + historia y se afirma **dónde caen los `cache_control` y qué queda en cada tramo**. R3.2 lo exige explícitamente. _Requisitos: 3.1, 3.2_

- [X] T017b [US1] Test del **coste, que es lo que R3.3 afirma y ninguna otra tarea cubría**: armar el mismo turno con teammate y sin teammate, y comprobar que lo que crece es **exactamente** el bloque de identidad más el de entorno — ni un mensaje más, ni un campo más, ni una repetición del conocimiento. Es la forma de que «solo lo que ocupan los dos bloques nuevos» sea una aserción y no una intención. _Requisitos: 3.3, 3.4_

- [X] T018 [US1] `unknown_tool` en `apps/api/src/nexus_api/companion/tools/runner.py:198-208` deja de enumerar `TOOLS_BY_NAME` entero y enumera **solo las del teammate**. Cuando no tiene ninguna, lo dice en vez de devolver una lista vacía sin explicación. **No se toca `not_in_catalog` (`:222-234`) ni el recorte por modo (`:238-245`).** _Requisitos: 2.6_

- [X] T019 [P] [US1] Test en `apps/api/tests/unit/`: la respuesta de `unknown_tool` de un teammate **no contiene** ninguna herramienta que ese teammate no tenga. Es la garantía 2 reforzada: hoy se le enseñan las 44. _Requisitos: 2.6_

- [X] T020 [US1] Retirar del prefijo las **dos afirmaciones de capacidad** de `prompt.py:108-121` —631 caracteres exactos, de «Tienes herramientas de» hasta «Un pack es un YAML»— y sustituirlas por una frase que remita al bloque propio. **Se queda** lo prohibido siempre (`:128-131`: borrar clientes, facturación, claves, la revelación de IA) porque es verdad para todos y no depende de ningún interruptor, y **se quedan** los párrafos del pack y de la propuesta, que describen el mecanismo sin prometer nada. _Requisitos: 2.2_

- [X] T021 [US1] Comprobar que `apps/api/tests/unit/test_companion_graph.py:49` —el que congela `SYSTEM_PROMPT` con `"{" not in SYSTEM_PROMPT`— **sigue verde sin tocarlo**. T020 quita texto; no interpola nada. Si hubiera que aflojarlo, el cambio está mal. _Requisitos: 1.3_

**Checkpoint US1**: los interruptores dejan de mentir. **Entregable solo.**

---

## Phase 4: US2 — El desajuste no puede volver (P1)

**Meta**: separar lo prometido de lo entregado pone algo en rojo antes de
fusionarse.

**Prueba independiente**: se añade una herramienta de mentira al catálogo y se
comprueba que la puerta falla. Si no falla, la puerta no vigila.

> **Va aquí y no al final aunque sea «solo tests».** Sin ella, US1 se degrada con
> el primer catálogo que alguien toque y el trabajo se deshace solo. Es además el
> tramo más barato de los cuatro.

### Tests para US2 ⚠️

- [X] T022 [US2] ⚠️ **El rojo que R4.6 exige por escrito.** Escribir la **mitad (a)** de la puerta en `apps/api/tests/isolation/test_40_prompt_matches_catalog.py`: barrido sobre `SYSTEM_PROMPT` que falla si el texto compartido afirma tener alguna familia de herramientas. **Con el código de hoy falla**, porque las dos afirmaciones están ahí. Escribirla **antes** de T020 y dejar constancia del rojo. _Requisitos: 4.1, 4.6_

- [X] T023 [US2] La **mitad (b)**: recorrer **las 128 combinaciones enteras** —2⁵ estados de interruptores × 2 modos × máquina presente/ausente— y exigir que cada herramienta que `for_teammate` entrega esté cubierta por una familia descrita, y que ninguna familia descrita cubra herramientas que no se entregan. **Enteras, no muestreadas**: 128 casos parametrizados son baratos y muestrear deja un agujero por donde no se mira. _Requisitos: 4.2_

- [X] T024 [US2] Comprobar la puerta **rompiéndola**, que es lo único que demuestra que vigila: (a) añadir una herramienta de mentira a `ALL_TOOLS` sin tocar la descripción → falla nombrando la familia que falta; (b) mover una herramienta de familia → falla; (c) añadir un interruptor sin ampliar el mapa de T012 → falla. Deshacer las tres. _Requisitos: 4.3, 4.4_

- [X] T025 [US2] Dejar anotado en el propio fichero **por qué la puerta NO busca nombres de herramienta citados en el texto**: comprobado que el prompt cita tres nombres y los tres existen, así que un lint por nombres **nacería en verde vigilando nada**. Es la lección que la spec 012 pagó con un barrido que buscaba símbolos y no la ruta compartida. _Requisitos: 4.5_

- [X] T026 [US2] La puerta vive en `tests/isolation/` **aunque no toque RLS**, y el fichero lo dice: es la costura del principio «la whitelist de herramientas es exhaustiva» —garantía 2— y el precedente directo es `test_33_teammate_catalog_is_subset.py`, que vigila lo mismo un paso más abajo. _Requisitos: 4.2_

- [X] T027 [US2] Comprobar que `apps/api/tests/isolation/test_33_teammate_catalog_is_subset.py` **sigue verde sin tocarlo**. Vigila que el catálogo del teammate sea subconjunto del del Companion; esta spec no lo cambia, solo lo describe. Si hay que aflojarlo, el cambio está mal. _Requisitos: 4.2_

**Checkpoint US2**: el trabajo de US1 no se deshace solo. **Entregable solo.**

---

## Phase 5: US3 — El teammate sabe cuándo está (P2)

**Meta**: «el viernes» significa el viernes, y «¿está vencido?» tiene respuesta.

**Prueba independiente**: se le pregunta qué día es y si algo con fecha pasada
está vencido.

### Tests para US3 ⚠️

- [X] T028 [P] [US3] Test en `apps/api/tests/unit/test_turn_environment.py`: el bloque de entorno lleva fecha, día de la semana, ISO, hora y zona, y la instrucción de **no deducir el año del propio conocimiento**. Se afirma contra el texto que `turn_clock` produce, que es el mismo que ya usa el agente de canal. _Requisitos: 5.1, 5.2_

- [X] T029 [P] [US3] ⚠️ **El caso feo, que no es el camino feliz.** Test: con la zona horaria vacía, malformada o desconocida, el turno **no se rompe**, se usa UTC, y **el texto dice que es UTC**. Si el test solo prueba una zona válida, no está probando el requisito. _Requisitos: 5.5_

- [X] T030 [P] [US3] Test: el bloque de entorno va **justo antes del turno de la persona**, no junto a la identidad. Los dos quieren sitios opuestos —la identidad lo más al principio, el entorno lo más fresco— y juntarlos obliga a elegir mal para uno. _Requisitos: 5.1_

- [X] T031 [P] [US3] Test: el bloque dice **si la máquina del teammate está presente**, y cambia cuando la presencia cambia. _Requisitos: 5.6_

### Implementación de US3

- [X] T032 [US3] Construir el bloque de entorno en el armado del turno, reutilizando `turn_clock` de T004. Se inserta **justo antes del mensaje de la persona**. _Requisitos: 5.1, 5.2_

- [X] T033 [US3] La zona horaria de **la persona que escribe** viaja desde la aplicación. **No entra en `PAGE_CONTEXT_KEYS`** (`prompt.py:304`): ese esquema es cerrado y **se valla con `fence_only`** porque lleva nombres escritos por terceros, y una zona IANA validada no lo es. Meterla ahí enseñaría al modelo a desconfiar de un dato fiable. _Requisitos: 5.3_

- [X] T034 [US3] WHERE el turno trata de un cliente concreto, nombrar **también** la zona de ese cliente (`tenant.timezone`, `db/models/tenant.py:66`) **sin sustituir** a la de la persona. Son dos datos distintos y el requisito pide los dos. _Requisitos: 5.4_

- [X] T035 [US3] Que la aplicación de escritorio mande su zona (`Intl.DateTimeFormat().resolvedOptions().timeZone`) en el turno, y validarla en el servidor antes de usarla. _Requisitos: 5.3_

**Checkpoint US3**: las fechas dejan de ser un campo de minas. **Entregable solo.**

---

## Phase 6: US4 — Dos teammates con los mismos permisos son dos agentes (P3)

**Meta**: el partner escribe cómo trabaja cada teammate, y cada uno trabaja así.

**Prueba independiente**: se le escriben instrucciones a un teammate y se
comprueba que las sigue; se le escriben contrarias a otro con los mismos
permisos y se comprueba que se comportan distinto.

> **Es el único tramo con migración y el único que toca §III.** Va el último a
> propósito: si algo se suelta de esta spec, que sea esto, con las tres primeras
> ya entregadas.

### Tests para US4 ⚠️

- [X] T036 [US4] ⚠️ **La puerta de aislamiento, y no se prueba por el camino feliz.** `apps/api/tests/isolation/test_41_instructions_do_not_widen.py`: escribirle a un teammate instrucciones que **pidan explícitamente por su nombre una herramienta que no tiene** —«usa siempre `console.propose_publish` al terminar»— y comprobar que `for_teammate` devuelve **exactamente lo mismo** que sin ellas. Si el test pasa sin haber intentado el ataque, no está probando nada. _Requisitos: 6.3_

- [X] T037 [P] [US4] Test: un teammate **sin** instrucciones se comporta como antes de esta spec. Nadie tiene que reconfigurar nada, y `NULL` ≠ cadena vacía. _Requisitos: 6.2, 6.7_

- [X] T038 [P] [US4] Test en `apps/api/tests/integration/test_teammates_crud.py`: `PATCH` con 4.001 caracteres devuelve **422 con el límite en el mensaje** y **no trunca**. _Requisitos: 6.5_

- [X] T039 [P] [US4] Test: cambiar las instrucciones deja asiento `teammate.updated` con `instructions` dentro de `fields`. **Este test falla contra el `CHECK` de hoy**, que es justo lo que T041 arregla. _Requisitos: 6.6_

- [X] T040 [P] [US4] Test: instrucciones que contradicen lo globalmente prohibido **no ganan** — lo prohibido sigue en el prefijo y no depende del teammate. _Requisitos: 6.4_

### Implementación de US4

- [X] T041 [US4] **La única migración de la spec**, en `apps/api/alembic/versions/`: añade `teammates.instructions` `TEXT` **nullable y sin `server_default`** —`NULL` significa «no escritas» y el R6.2 depende de esa distinción; un `DEFAULT ''` convertiría todas las filas existentes en «escritas y vacías»—, y **reemplaza** `teammate_changes_fields_check` para incluir `'instructions'`. Se ensaya **arriba, abajo y arriba**. _Requisitos: 6.1, 6.6_

- [X] T042 [US4] El `downgrade` de T041: **retirar `'instructions'` de los arrays de `teammate_changes` ANTES de estrechar el `CHECK`**, y borrar las filas que se queden sin ningún campo (`array_length >= 1` es parte de la restricción). Se pierde el registro de que alguien cambió las instrucciones; no se pierde nada más. **Probarlo con una fila que nombre ese campo puesta**, o no se ha probado nada. _Requisitos: 6.6_

- [X] T043 [US4] Comprobar que **el vocabulario de auditoría NO necesita migración**: `teammate.updated` ya existe (`alembic/versions/0110_teammate_audit_vocab.py:32`) y es la acción que ya se escribe al editar. Cambia qué campos se nombran, no qué acción se registra. **Leer la migración, no suponerlo** — es exactamente lo que no se hizo en la spec 012 y costó una enmienda. _Requisitos: 6.6_

- [X] T044 [US4] ⚠️ **El barrido del vocabulario de cuatro sitios.** Ampliar a `instructions` los **cuatro** lugares que enumeran los campos sin constante compartida, en dos lenguajes: el `CHECK` (`apps/api/src/nexus_api/db/models/teammate.py:113`), la unión de tipos (`apps/desktop/src/app/bridge.ts:79`), los textos `changes.field.*` (`apps/desktop/src/app/i18n.ts:115`) y la frase que los enumera (`apps/desktop/src/app/routes/change-notes.tsx:37`). **Es la forma exacta del defecto que la spec 012 pagó**: si queda uno, las notas de cambio mienten o revientan. _Requisitos: 6.6_

- [X] T045 [US4] `instructions: str | None = Field(default=None, max_length=4000)` en `apps/api/src/nexus_api/api/console/schemas_teammates.py`, en el esquema de entrada y en el de salida. **El tope vive en el esquema y no en la base**: un tope de producto que cambie no debería exigir una migración. _Requisitos: 6.1, 6.5_

- [X] T046 [US4] `PATCH /console/teammates/{id}` acepta el campo: `null` borra, ausente no cambia nada, y el cambio entra en `TeammateChange.fields`. Sin permiso sigue siendo 403, como cualquier otra edición. _Requisitos: 6.1, 6.6_

- [X] T047 [US4] Meter las instrucciones dentro del bloque de identidad que creó T013, **marcadas como lo que son**: instrucción que el partner escribió para este teammate. Es la única costura entre US4 y US1, y es una línea. _Requisitos: 6.1_

- [X] T048 [P] [US4] El campo en las dos pantallas del escritorio: `apps/desktop/src/app/routes/new-teammate.tsx` y `routes/teammate-settings.tsx`. **Opcional, y vacío no se pinta como pendiente ni como error** (§V: la ausencia se diseña). El tope se anuncia **antes** de rebasarlo, nunca se trunca en silencio. _Requisitos: 6.2, 6.5_

- [X] T049 [P] [US4] Textos nuevos en `apps/desktop/src/app/i18n.ts`: la etiqueta del campo, su ayuda —qué es y qué no: no amplía permisos— y el aviso del tope. _Requisitos: 6.2, 6.5_

**Checkpoint US4**: dos teammates con los mismos permisos son dos agentes.

---

## Phase 7: Polish

- [X] T050 [US4] Pasar los **cuatro gates de interfaz** del `CLAUDE.md` del workspace —estados, accesibilidad, responsive y tokens— sobre las dos pantallas del escritorio que toca T048. Es texto largo en un campo: `text-wrap: pretty`, `min-width: 0` en los hijos flex, y probarlo con una cadena alemana. _Requisitos: 6.2_

- [X] T051 Escribir la **frontera del §III** en `docs/desktop-teammates.md`, sección propia y **en el mismo commit** que cambia lo que describe: (a) lo que el partner configura —oficio e instrucciones— es **instrucción a propósito**, porque ese mismo partner ya escribe entero el prompt del agente de sus clientes finales; (b) lo que el teammate **lee** —ficheros, salidas, contexto de pantalla, resultados de herramienta— es **dato, siempre**, con el vallado de hoy; (c) **contra quién NO protege**: no protege del partner comprometido, y esa mitigación es de otra capa. _Requisitos: 7.1, 7.2, 7.3, 7.4_

- [X] T052 Anotar en `docs/desktop-teammates.md` que esto **regulariza `job`**, que lleva desde la spec 003 metiendo 80 caracteres del partner en un `role: "system"` sin que ninguna spec lo dijera. No es un defecto que se introduzca: es uno existente que pasa de supuesto a escrito. _Requisitos: 7.1_

- [ ] T053 Ejecutar **`./scripts/verify.sh` entero**: lint (`ruff` + `mypy --strict`), py y js. **El worker se toca de lleno**, que es exactamente donde este repositorio ha roto la tubería dos veces y las dos por no correr el worker ni `mypy --strict`. La consola no se toca —comprobado al planificar— pero **su `next build` se corre igual**, porque «no debería moverse» no es una comprobación. **Una sola ejecución de `pytest` a la vez**, y comprobarlo antes de lanzar. _Requisitos: —_

- [ ] T054 Recorrer `quickstart.md` entero a mano, con la aplicación de verdad. **Lo que salga de ahí manda sobre lo que digan los tests**: un teammate que pasa 128 casos parametrizados y suena a otro agente cuando le hablas no está entregado. Mirar con calma el hilo largo (H1 §5) y el caso de cero herramientas. Lo firma Luis. _Requisitos: 1.2, 2.5, 5.1, 6.1_

  **Esta tarea es la dueña de los siete criterios de éxito**, y es la única que puede serlo: son observables por un partner, no por un test. Cada uno con su paso del quickstart:

  | Criterio | Dónde se comprueba | Cuál es la señal |
  |---|---|---|
  | **CE-001** dos teammates, mismos permisos, distinto carácter | H4 §1 | Las respuestas se reconocen como lo que se pidió |
  | **CE-002** todo lo que dice tener es cierto | H1 §1 y §3 | Nada que no tenga; nada que tenga y no nombre |
  | **CE-003** sin herramientas, explica por qué | H1 §2 | Contesta, en vez de callarse |
  | **CE-004** fechas correctas en la zona de quien pregunta | H3 | «El viernes» es el viernes; lo vencido, vencido |
  | **CE-005** el nombre inventado enseña solo las suyas | H1 §4 | Ningún nombre que ese teammate no tenga |
  | **CE-006** el desajuste no llega a fusionarse | H2 | La puerta **falla** al romperla a propósito |
  | **CE-007** el coste crece solo los dos bloques | lo fijan T017 y T017b | El corte 1 se sigue escribiendo una vez para todos |

  _Criterios de éxito: CE-001, CE-002, CE-003, CE-004, CE-005, CE-006, CE-007_

- [X] T055 Anotar en la KB (`research/2026-09-19-auditoria-clase-mundial/_index.md` §0) lo entregado y lo aprendido, y **corregir la fila 015 de §5**, que hoy describe el conjunto entero —toolset, autonomía, plan visible, compactación, reintentos, barrido de zombis, techos de duración, instrucciones propias y memoria de equipo— cuando esta spec se lleva **solo las instrucciones propias** más lo que la investigación del 2026-09-22 añadió. El resto espera a su evaluación (decisión D-A). _Requisitos: —_

---

## Dependencies & Execution Order

### Por fases

```
Setup (T001-T003)
   ↓
Foundational (T004-T005) ← bloquea US3; el resto puede empezar
   ↓
US1 (T006-T021) ──┬─→ US2 (T022-T027)
                  ├─→ US3 (T028-T035)
                  └─→ US4 (T036-T049)
   ↓
Polish (T050-T055)
```

### El orden que importa

- **T010 antes que T006.** El test tiene que fallar por aserción, no por
  `ImportError`. Es la única inversión aparente de «test primero» en toda la
  spec, y está aquí por la razón contraria: para que el rojo signifique algo.
- **T022 antes que T020.** La mitad (a) de la puerta tiene que verse roja **con
  las afirmaciones todavía puestas**. Si se escribe después, nace verde.
- **T016 no es opcional ni posterior.** Sin el punto de corte, T014 y T015
  entregan algo correcto y **caro**: los 7 KB compartidos escritos una vez por
  teammate.
- **T041 y T044 van en el mismo commit.** Ensanchar el `CHECK` sin ampliar los
  tres sitios de TypeScript deja las notas de cambio mintiendo; ampliarlos sin el
  `CHECK` revienta al guardar.
- **T042 se prueba con la fila puesta.** Un `downgrade` que baja sobre una tabla
  vacía no ha probado su parte difícil.
- **T005 justo tras T004.** Si el canal necesita que se le toque un test, el
  movimiento está mal y hay que saberlo antes de seguir.

### Paralelizables

- T001, T002, T003 entre sí.
- T007, T008, T009 entre sí (ficheros distintos), **después** de T006/T010.
- T028 a T031 entre sí.
- T037 a T040 entre sí.
- T048 y T049 entre sí (escritorio), **después** de T045.

---

## Implementation Strategy

### MVP: solo US1

T001-T005 + T006-T021. Deja entregado que **los interruptores dejan de mentir**,
sin migración y sin tocar la base. Es el tramo que quita la mentira; todo lo
demás añade verdades encima.

### Entrega incremental

Cada checkpoint es soltable:

| Tras | Qué tiene el partner |
|---|---|
| US1 | Un teammate que dice la verdad sobre sí mismo |
| US2 | Y que no puede volver a dejar de decirla |
| US3 | Y que sabe qué día es |
| US4 | Y que trabaja como su partner le dijo |

### Lo que NO entrega ninguno de los cuatro

**Un trabajador para el cliente del partner.** 40 de las 44 herramientas
administran la consola de Auphere. Está escrito al principio de la spec y se
repite aquí porque es donde se lee cuando se ejecuta.

---

## Registro de ejecución

**2026-09-22 — Setup, Foundational, US1 y US2. 28 de 56.**

Parada entregable: **los interruptores dejan de mentir, y no pueden volver a
hacerlo.** Sin migración y sin tocar la base.

### Lo que la ejecución corrigió de mí mismo

**Escribí la implementación antes que el test.** T010 decía firma vacía primero,
y me salté el paso. No se arregla declarándolo: se arregla **vaciando el cuerpo**
y viendo el rojo. Se hizo así — 13 fallos y 3 pases, **todos por aserción y
ninguno por `ImportError`**, que era exactamente lo que la tarea pedía—, y solo
entonces se restauró.

**La puerta encontró un agujero mío en su primera ejecución.** `console.apply` se
entrega con cualquier permiso que proponga, la descripción lo cuenta en prosa, y
**ninguna familia lo declaraba cubierto**. Describir algo sin declararlo deja a
la puerta mirando a otro lado. De ahí sale `_DESCRIBED_NAMES`, que la puerta lee
del módulo en vez de reconstruirlo — reconstruirlo sería una segunda fuente, y
entonces podría estar de acuerdo consigo misma.

### T024 destapó que la puerta no cazaba lo que el plan prometía

Romperla a propósito es lo único que demuestra que vigila, y al hacerlo:

| Rotura | ¿La cazó? |
|---|---|
| Interruptor nuevo sin etiqueta | Sí |
| Prosa incondicional de vuelta al prefijo | Sí |
| **Mover una herramienta de familia** | **NO** |

**Sus dos mitades leían el mismo `_FAMILY_NAMES`**, así que estaba de acuerdo
consigo misma mientras el catálogo decía otra cosa. Es la misma forma del
defecto que la spec 012 pagó con un barrido que buscaba símbolos de un solo
lado.

El arreglo es un **ancla independiente**: `permissions_to_tool_names`, que es
quien decide de verdad qué da cada interruptor. Lo que una familia describe tiene
que ser exactamente lo que su interruptor entrega. Con eso, las dos roturas de
mover herramientas (vaciar una familia y mover una a otra) fallan.

### Un falso positivo que empujaba a borrar una guarda

La mitad (a) señalaba «**No** tienes acceso a las conversaciones de los clientes
finales» — que es una **prohibición**, no una promesa. Un test que empuja a
borrar una guarda para ponerse verde es peor que no tener test. De ahí el
`(?<!No )` de `_AFIRMACIONES`, y su comentario.

### Un test que cambió de sujeto, no de intención

`test_the_prompt_says_it_proposes_but_does_not_apply` afirmaba que el prefijo
enumera «herramientas de lectura» y «de propuesta». Su razón —de CO-04— sigue
siendo buena: *una capacidad negada que sí existe hace que el agente se niegue a
usar sus herramientas*. Lo que cambió es **quién puede decir esa verdad**: el
prefijo no lo sabe, el bloque por teammate sí. Se reescribió —no se aflojó— y
ahora afirma lo contrario: que esas frases **no pueden volver**.

### Lo que se midió, en vez de estimarse

T003 se cerró con `tiktoken`: el prefijo pasa de **1.879 a 1.724 tokens**, con el
mínimo cacheable en 512. Margen de **3,4×**. La salvedad queda escrita en
`research.md`: es el tokenizador de OpenAI, no el de Anthropic, y sirve para este
margen pero no serviría si alguien acercara el prefijo a 600 tokens.

### El worker, otra vez

`verify.sh lint` cayó en **el worker y solo en el worker** —un import muerto tras
mover `_now_note`, y tres `mypy --strict` por pasar `object` donde se espera
`str | None`—. Es literalmente donde este repositorio ha roto la tubería dos
veces. El arreglo del segundo no es un `cast`: es `_as_text`, que estrecha en el
límite, porque un objeto que no sea texto llegaría al modelo como su `repr`.

### El worker cazó lo más grave, y el aviso estaba escrito en el fichero

`test_llm_resilience.py::TestPromptCaching` se puso rojo: yo había partido la
cabecera del caché **para todo el mundo**. Y unas líneas más abajo, en ese mismo
`llm.py`, estaba escrito por qué `cache_tail` está apagado por defecto:

> «El agente de cliente y los dos playgrounds usan este mismo proveedor y son
> **carga viva**, así que cambiarles el comportamiento para arreglar un problema
> del Companion es exactamente cómo se rompe algo que funcionaba.»

Hice literalmente eso. **Habría cambiado el reparto de puntos de corte de tres
agentes en producción** para resolver algo que solo le pasa al Companion con
teammate.

El arreglo no es aflojar el test: es `split_header`, **apagado por defecto**, y
encendido en el único sitio que lo necesita —el proveedor del Companion, donde
ya vivía `cache_tail=True` por la misma razón—. El test recuperó sus 36 sin que
nadie lo tocara, que es la señal que este repositorio usa. Y se añadió
`test_off_by_default_nothing_changes_for_the_channel_agent`, para que la próxima
vez el rojo llegue antes.

> **Y de paso, una observación que no se arregla aquí.** El agente de canal mete
> `_now_note` dentro de su bloque de sistema inicial, y esa nota **cambia cada
> minuto**. Con un solo punto de corte, eso invalida su prefijo cacheado entero
> muy a menudo. `split_header` lo arreglaría — y por eso mismo **no se enciende
> para él en esta spec**: es carga viva, no está medido, y no es el problema que
> esta spec vino a resolver. Anotado para quien lo mida.

**2026-09-22 (2) — US3 y US4. 54 de 56.**

### US3 · dos defectos, y uno estaba en el código original

**Una zona horaria vacía no marcaba el repliegue.** `ZoneInfo("" or "UTC")`
resuelve **sin lanzar**, así que el `except` no entraba y el nombre se quedaba
en blanco: la nota decía «en la zona horaria de la persona ():». Estaba así
desde que se escribió para el agente de canal —allí no salta porque
`bundle.timezone` trae «UTC» por defecto— y se arregló al mover la función,
normalizando antes del `try`. Lo cazó el caso feo de T029, que es justo el que
no es el camino feliz.

**Y la nota decía «del negocio» a quien habla con su teammate.** El texto era
del agente de canal, que trabaja para un negocio; el teammate trabaja para una
persona. Se parametrizó el dueño de la zona **con el valor del canal por
defecto**, para que su texto siga siendo byte a byte el de antes — y hay test
que lo afirma.

### US4 · el vocabulario tenía un quinto sitio que el plan no contó

El plan enumeró **cuatro**: el `CHECK` de `teammate_changes`, la unión de
`bridge.ts`, los textos `changes.field.*` y la frase que los enumera. Con los
cuatro puestos, cambiar las instrucciones **seguía sin dejar nota en el hilo**.

El quinto era `CHANGED_FIELDS` (`db/models/teammate.py`), un filtro que
descarta **en silencio** los campos que no considera dignos de nota. No
revienta, no avisa: simplemente no escribe. Lo encontró el test de auditoría de
T039, que era el único que miraba el resultado y no el 200.

> **Es la tercera vez en dos specs que un vocabulario repetido tiene una copia
> más de las contadas.** La 012 lo pagó con el cliente muerto del escritorio;
> aquí, con una nota que no se escribía. La regla que sale de las tres: cuando
> se cuentan N sitios, se busca el N+1 **antes** de dar por hecho que son N.

### La migración, probada por donde duele

`0127` ensayada arriba/abajo/arriba, y el `downgrade` **con las filas difíciles
sembradas a mano**: una que solo nombra `instructions` y otra mixta. La primera
desaparece —violaría `array_length >= 1`—, la segunda sobrevive como `['job']`,
y la columna se va. Bajar sobre una tabla vacía no habría probado nada de eso.

### Y la quinta vez que solapé dos pytest

Lancé la suite de un fichero **mientras `verify.sh py` corría, sabiéndolo**,
porque «es un fichero, tarda ocho segundos». Resultado: ~30 `ERROR at
setup/teardown` en tests que no tenían nada que ver, y diez minutos tirados. No
existe el pytest pequeño: comparte la misma base. La memoria del proyecto quedó
corregida con este caso concreto, porque la regla genérica ya estaba y no bastó.

### Lo que queda

**T053** (`verify.sh` entero, corriendo) y **T054**, el recorrido manual del
quickstart, que firma Luis.
