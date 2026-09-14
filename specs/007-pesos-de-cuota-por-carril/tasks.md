---

description: "Tareas de la spec 007 — la cuota cobra por carril"
---

# Tasks: la cuota cobra por carril

**Input**: documentos de diseño en `/specs/007-pesos-de-cuota-por-carril/`

**Prerequisites**: [plan.md](./plan.md) · [spec.md](./spec.md) ·
[research.md](./research.md) · [data-model.md](./data-model.md) ·
[contracts/quota-unit-v2.md](./contracts/quota-unit-v2.md) ·
[quickstart.md](./quickstart.md)

**Tests**: obligatorios (§VII). Se escriben, **se ven en rojo**, y sólo entonces
se implementa. Y en esta spec hay una vuelta de tuerca que el encargo pide
explícitamente: **el test del invariante se rompe a propósito** para comprobar
que vigila. Un test que pasa no demuestra nada por sí solo.

## Reglas de este repo

- Cada tarea cita sus requisitos: `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **Producción tiene tres clientes reales con tráfico.**

---

## Phase 1: Setup

**Propósito**: saber de dónde se parte, para que un rojo nuevo se distinga de uno
que ya estaba.

- [X] T001 Ejecutar `./scripts/verify.sh` **entero** en `007-pesos-de-cuota-por-carril`
      y guardar la cola en crudo en `specs/007-pesos-de-cuota-por-carril/evidence/baseline.txt`.
      Entero, no la mitad: lo que se olvida es el worker, `mypy --strict`, el
      paquete compartido y el `next build`. _Requisitos: 3.2_

---

## Phase 2: Foundational (prerrequisitos bloqueantes)

**Propósito**: el catálogo tiene que saber los tres pesos antes de que nada pueda
cobrarlos.

**⚠️ Ninguna historia puede empezar hasta que esta fase esté completa.**

### Tests primero

- [X] T002 [P] Test de la migración en `apps/api/tests/integration/test_migration_0120.py`:
      tras `upgrade`, los seis modelos servibles tienen los tres pesos y valen
      `2,2 × price_carril ÷ 10`; `openai/whisper-1` los tiene **a NULL** y sigue
      en el catálogo; `quota_weight` **sigue existiendo**; `downgrade` + `upgrade`
      no pierde datos. **Y el caso que vigila el cambio de escala**: los pesos de
      los modelos que ya cabían en tres decimales quedan con el **mismo valor**
      tras pasar a seis — ampliar la resolución no puede mover por su cuenta lo
      que nadie decidió mover, y esto corre sobre la base de tres clientes con
      tráfico. _Requisitos: 1.1, 1.2, 1.7, 2.4, 2.5_
- [X] T003 [P] Test de los `CHECK` en el mismo fichero: insertar un modelo con
      **dos** pesos y uno nulo **debe** violar la restricción («los tres o
      ninguno»), y un peso ≤ 0 también. _Requisitos: 1.1, 1.6_
- [X] T004 [P] Test de `weights_for` en `apps/api/tests/unit/test_missing_weight_refuses.py`
      (amplía el que ya existe): un modelo al que le falta **un solo** carril
      levanta `UnweightedModel` nombrando el modelo; uno sin ninguno, también; y
      un modelo fuera del carril de cuota de LLM **no** se ve afectado.
      _Requisitos: 1.6, 1.7_

### Implementación

- [X] T005 Migración `apps/api/alembic/versions/0120_quota_weights_per_lane.py`:
      añade `quota_weight_input`, `quota_weight_cache_read` y
      `quota_weight_output` como `NUMERIC(12,6)` nulables; `CHECK` de positividad
      por columna y `CHECK` de «los tres nulos o los tres no nulos»; siembra
      `2,2 × price_<carril>_per_mtok ÷ 10` **leyendo las tarifas de la propia
      fila**, nunca de una lista escrita a mano — una lista se desincroniza del
      catálogo el día que alguien añade un modelo. `quota_weight` **no se borra**
      (el `downgrade()` tiene que poder devolver los datos). Los pesos que ya
      cabían en la escala vieja conservan su valor exacto. _Requisitos: 1.1, 1.2, 2.4, 2.5_
- [X] T006 [P] `apps/api/src/nexus_api/db/models/model_profile.py`: las tres
      columnas en el ORM; `quota_weight` marcada como deprecada en el comentario,
      con la migración que la borrará pendiente. _Requisitos: 1.1_
- [X] T007 [P] `apps/worker/src/nexus_worker/metering/pricing.py`: `ModelPrice`
      gana los tres campos y `_CATALOG_SQL` los selecciona. El catálogo cacheado
      (TTL 300 s) es el único sitio desde donde se leen: **cero consultas nuevas
      en el camino caliente**. _Requisitos: 1.1_
- [X] T008 `apps/api/src/nexus_api/metering/pricing_policy.py`: `weights_for()`
      devuelve los tres pesos del modelo y levanta `UnweightedModel` si **falta
      alguno**. `weight_for()` se conserva hasta que no quede llamante y entonces
      se retira. _Requisitos: 1.6, 1.7_

**Checkpoint**: el catálogo sabe los tres pesos. Nadie los cobra todavía.

---

## Phase 2b: Las puertas de la constitución

- [X] T009 Ampliar `apps/api/tests/isolation/test_pool_not_exposed_to_tenant.py`:
      los tres nombres nuevos entran en `FORBIDDEN`. **Se ve en rojo primero** —
      añadiendo un nombre nuevo a una ruta de cliente final a propósito — para
      comprobar que la lista vigila de verdad y no pasa por vacía. Garantía
      tocada: **1, Postgres RLS**, por el lado de no abrir puerta. Un rojo aquí
      **bloquea el merge** (§I). _Requisitos: 7.4_
- [X] T010 **Licencias (§VIII): no aplica, y es una decisión.** Esta spec no
      instala ninguna dependencia: `Decimal` es biblioteca estándar, SQLAlchemy y
      Alembic ya están. No hay licencia que leer ni párrafo que citar.
      _Requisitos: —_
- [X] T011 **Medidor: es el objeto entero de la spec.** Lo que gasta es modelo, y
      el partner lo ve en **Consumo** de la consola, en la misma unidad de
      siempre. Esta tarea comprueba que la pantalla sigue diciendo la verdad tras
      el cambio: `apps/api/tests/integration/test_metering_end_to_end.py` afirma
      que lo debitado y lo mostrado coinciden. _Requisitos: 3.3, 5.5_

**Checkpoint**: las puertas tienen dueño. Sin esto `/speckit-analyze` no da verde.

---

## Phase 3: US1 — Ningún carril se vende por debajo del suelo (P1) 🎯 MVP

**Goal**: el margen deja de depender de la mezcla. 54,5 % en los dieciocho
carriles, y ningún carril por debajo de 1,50x.

**Independent Test**: se recorre el catálogo real de la base y ningún carril de
ningún modelo queda bajo el suelo. Se demuestra solo, sin desplegar y sin tocar a
ningún partner.

### Tests primero ⚠️

- [X] T012 [P] [US1] `apps/api/tests/integration/test_quota_floor.py`: para
      **cada modelo del catálogo leído de la base** y cada carril, comprobar
      `peso × 10 ÷ precio_carril ≥ 1,50` **sobre el valor almacenado**, después
      del redondeo de la columna. Un caso por carril y por modelo; el fallo
      **nombra el modelo y el carril**. Contra una lista escrita en el test, no:
      pasaría en verde el día que alguien añada un modelo. _Requisitos: 2.1, 2.2, 2.3_
- [X] T013 [P] [US1] `apps/api/tests/unit/test_quota_lanes.py`: la fórmula del
      contrato — `unc × w_in + cache × w_cache + out × w_out`, **un solo
      redondeo** `ROUND_HALF_UP`, `cache_write` sigue valiendo 0, y la constante
      global `0,1` ya no interviene. _Requisitos: 1.3, 1.4, 1.5_
- [X] T014 [P] [US1] `apps/api/tests/unit/test_quota_margin.py`: con el turno de
      teammate (5 K / 4 K / 3 K) y la bolsa agotada todas las semanas del mes,
      los tres planes dan margen positivo — Pro 51 %, Team 34 %, Business 21 %.
      _Requisitos: 4.1_
- [X] T015 [P] [US1] `apps/api/tests/unit/test_quota_pool_invariance.py`: el
      coste de agotar un millón de unidades varía **menos del 2 %** entre los
      modelos del catálogo con una mezcla pesada en salida, donde hoy varía un
      78 %. _Requisitos: 4.1, 4.2_
- [X] T016 [P] [US1] `apps/worker/tests/unit/test_turn_quota_lanes.py`: una misma
      llamada produce la **misma cifra** en `_turn_quota` del worker y en el
      camino de la API. El test falla si divergen. _Requisitos: 3.1, 3.2_

### Implementación

- [X] T017 [US1] `apps/api/src/nexus_api/metering/quota.py`: `quota_tokens()`
      pasa a tomar los tres pesos y a cuantizar **una sola vez**;
      `billable_qty_for_meter()` aplica el peso del carril a cada fila nativa;
      `CACHE_READ_QUOTA_WEIGHT` y `cache_read_quota_tokens()` se retiran cuando
      no queda llamante. El docstring deja de afirmar la propiedad de la 004 como
      cierta sólo en el punto de calibración. _Requisitos: 1.2, 1.3, 1.4, 3.3, 4.3_
- [X] T018 [US1] `apps/worker/src/nexus_worker/metering/consumer.py`:
      `_turn_quota` y la línea de `billable_qty` pasan a los tres pesos. Sigue
      agrupando por **llamada** y no por turno: el peso es del modelo y una tarea
      puede encadenar cerebros distintos. _Requisitos: 1.2, 3.1_
- [X] T019 [US1] Migración `apps/api/alembic/versions/0121_companion_run_native_input.py`:
      añade `uncached_input_tokens integer NULL` a `companion.runs`.
      `input_tokens` **no se toca y no se rellena hacia atrás** — el nativo no se
      puede recuperar de la cuota sin asumir el factor 0,1, que es la suposición
      de la que esta spec sale. Un `NULL` declarado vale más que un número
      reconstruido. _Requisitos: 1.2_
- [X] T020 [US1] `apps/worker/src/nexus_worker/runtime/companion/graph.py`:
      `_billable_input` deja de ponderar y el estado acumula **nativos**
      (entrada no cacheada y lectura de caché por separado). El medidor de
      **ventana de contexto** sigue usando `prompt_tokens` bruto: son dos
      preguntas distintas con dos números distintos, y eso no cambia.
      _Requisitos: 1.2, 3.1_
- [X] T021 [US1] `apps/api/src/nexus_api/api/console/companion.py`: deja de
      des-ponderar (`input_tokens − 0,1 × cache_read` desaparece), debita con los
      tres pesos, escribe `uncached_input_tokens` y deja de escribir
      `input_tokens`. `_turn_cost_usd` valora nativos directamente, sin
      reconstruir nada. _Requisitos: 1.2, 3.1, 3.3_
- [X] T022 [US1] Romper el invariante a propósito y comprobar que T012 **se pone
      rojo** nombrando modelo y carril (quickstart §1). Dejar la evidencia —
      salida cruda del fallo — en `specs/007-pesos-de-cuota-por-carril/evidence/floor-red.txt`.
      Un test que pasa no demuestra que vigile. _Requisitos: 2.3_

**Checkpoint**: ningún carril bajo el suelo, y hay una prueba que lo vigila y que
se ha visto fallar.

---

## Phase 4: US2 — El partner no ve un salto en su factura (P2)

**Goal**: la corrección no llega como una subida de precio a quien no tiene la
culpa.

**Independent Test**: la mezcla típica de cliente final no sube en ningún modelo
del catálogo.

### Tests primero ⚠️

- [X] T023 [P] [US2] `apps/api/tests/unit/test_quota_end_customer.py`: el turno
      de cliente final (10 K / 8 K / 1 K) **no sube** en ninguno de los seis
      modelos **más de un 2 %**, y **baja** en los que el producto sirve; en
      `claude-sonnet-4-6` baja de 5.210 a 5.148 unidades (−1,2 %). **Medido: no
      baja en los seis.** El cambio sigue el ratio salida/entrada del proveedor
      — `gpt-4o` (4,0x) −16,0 %, `sol`/`sonnet`/`haiku` (5,0x) −1,2 %,
      `terra`/`luna` (6,0x) **+1,9 %**: los dos últimos tenían la salida
      subvencionada de más. _Requisitos: 5.1, 5.6_
- [X] T024 [P] [US2] En el mismo fichero: la factura de un partner con tres
      clientes a 7.200 turnos/mes pasa de 1.125,36 $ a 1.111,97 $. Es el caso que
      hace la afirmación comprobable en euros y no en porcentajes.
      _Requisitos: 5.1_
- [X] T025 [P] [US2] `apps/api/tests/integration/test_quota_no_revaluation.py`:
      tras aplicar las dos migraciones, **ningún saldo cambia** —
      `partner_wallets`, `partner_allocations` y `usage_ledger` quedan idénticos —
      y ningún `usage_records.billable_qty` histórico se recalcula.
      _Requisitos: 5.1, 5.2, 5.3_

### Implementación

- [X] T026 [US2] Comprobar que **ninguna** de las dos migraciones lleva backfill
      ni reprecio, a diferencia de la `0114` y la `0076`. Si el `UPDATE` que
      recalculaba `cost_usd` se copió por inercia, se quita: aquí no toca.
      _Requisitos: 5.2_
- [X] T027 [US2] `apps/api/src/nexus_api/metering/wallet.py`: un débito se calcula
      con los pesos **vigentes en el momento del débito**. No se guarda la tarifa
      con el asiento y no conviven dos tarifas. Verificar que no hace falta
      cambiar nada y **dejarlo escrito** si así es — una comprobación que no deja
      rastro se repite. _Requisitos: 5.4, 5.5_

**Checkpoint**: nadie paga de más y ningún saldo se movió.

---

## Phase 5: US3 — Cambiar una tarifa no rompe el suelo en silencio (P3)

**Goal**: que la próxima vez que alguien toque un precio, el sistema lo diga.

**Independent Test**: se altera la tarifa de un carril sin tocar su peso y la
incoherencia se detecta.

### Tests primero ⚠️

- [X] T028 [P] [US3] `apps/api/tests/integration/test_quota_weight_drift.py`:
      cambiar `price_output_per_mtok` de un modelo sin tocar su peso hace que la
      comprobación de coherencia lo señale **nombrando modelo y carril**.
      _Requisitos: 6.1_
- [X] T029 [P] [US3] En el mismo fichero: una divergencia que deja el carril
      **sobre** el suelo se distingue de una que lo hunde **por debajo** — son
      dos situaciones distintas y no pueden dar el mismo aviso. _Requisitos: 6.2_
- [X] T030 [P] [US3] Un modelo nuevo con tarifas y **sin** pesos no se puede
      servir por el carril de cuota, y el motivo lo nombra. _Requisitos: 1.6, 6.2_

### Implementación

- [X] T031 [US3] Comprobación de coherencia que recalcula `2,2 × precio ÷ 10` y lo
      compara con el peso guardado, con la tolerancia del redondeo de la columna.
      Es la alternativa «derivar en runtime» que `research.md` D1 rechazó como
      fórmula, **ejecutada como comprobación**: lo bueno de la idea sin el
      acoplamiento. _Requisitos: 6.1, 6.2_
- [X] T032 [US3] Conectar esa comprobación donde alguien la vea: mismo criterio
      que `pricing.catalog_load_failed` — se registra al cargar el catálogo, con
      el modelo y el carril, sin bloquear el arranque. Una divergencia no puede
      tumbar la plataforma, pero tampoco puede ser invisible. _Requisitos: 6.1_

**Checkpoint**: las tres historias funcionan de forma independiente.

---

## Phase 6: Polish y documentación

- [X] T033 [P] Enmendar `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`
      **en el mismo commit** que cambia el comportamiento: retirar las dos
      afirmaciones que la medición refuta (los márgenes 62 %/39 % del peor caso y
      la propiedad del pool como si fuera universal), bajar el margen objetivo de
      **65 % a 54,5 %**, y dejar escrito que las cifras del ADR correspondían a un
      multiplicador de 2,857x que la `0115` nunca implementó. _Requisitos: 7.1_
- [X] T034 [P] `apps/api/src/nexus_api/billing/pricing.py`: el comentario de
      `CREDIT_USD_PER_MILLION` dice hoy «65 % target margin» y **ningún carril lo
      cobra**. Pasa a 54,5 %, con la referencia a esta spec. _Requisitos: 7.2_
- [X] T035 [P] `docs/billing.md`: la spec viva describe los tres pesos, el
      objetivo y el suelo, y **va en el mismo commit** que el código que describe.
      _Requisitos: 7.3_
- [X] T036 [P] Marcar `specs/004-medidor-y-pool-semanal/contracts/quota-unit.md`
      como **superado** por `007/contracts/quota-unit-v2.md`. Dos contratos de la
      misma unidad divergen, que es el argumento que este repo ya aplica a las
      listas de puertas. _Requisitos: 7.3_
- [X] T037 Recorrer `quickstart.md` entero, los siete pasos, y dejar la salida
      cruda en `specs/007-pesos-de-cuota-por-carril/evidence/quickstart.txt`.
      _Requisitos: 2.3, 4.2, 5.1_
- [X] T038 `./scripts/verify.sh` **entero**, y **leer la cola en crudo** — no un
      resumen propio. Comparar contra `evidence/baseline.txt` de T001: lo que
      importa es que no haya rojos **nuevos**. _Requisitos: 3.2_
- [ ] T039 Entregar el mensaje de commit y **parar**. Los commits los ejecuta la
      persona. _Requisitos: —_

---

## Dependencies & Execution Order

### Entre fases

- **Setup (1)**: sin dependencias.
- **Foundational (2)**: depende de Setup. **Bloquea las tres historias**: nadie
  puede cobrar un peso que el catálogo no guarda.
- **Puertas (2b)**: pueden correr en paralelo con las historias, pero
  `/speckit-analyze` no da verde sin ellas.
- **US1 (3)**: depende de Foundational. **Es el MVP.**
- **US2 (4)**: depende de US1 — no se puede afirmar que la factura no sube hasta
  que la fórmula nueva existe.
- **US3 (5)**: depende de Foundational, no de US1 ni de US2. Se puede adelantar
  si hay manos.
- **Polish (6)**: depende de que las historias que se vayan a entregar estén
  hechas. T033–T036 van **en el mismo commit** que el código, no después.

### Dentro de US1, una dependencia dura

`T019 → T020 → T021` es **secuencial y en ese orden**: la columna antes que quien
la escribe, y el productor del nativo antes que el consumidor. Invertirlo deja
una ventana en la que el Companion debita con una cifra que ya no significa lo
que el otro lado cree.

### Paralelizable

- T002–T004 (tests de Foundational) entre sí.
- T006 y T007 entre sí (ficheros distintos, servicios distintos). **T005 va
  antes**: el ORM no puede declarar una columna que no existe.
- T012–T016 (tests de US1) entre sí.
- T023–T025, T028–T030, T033–T036 entre sí.
- **T017 y T018 no son paralelos aunque sean ficheros distintos**: son las dos
  mitades de la misma fórmula y T016 falla si una va sin la otra.

---

## Implementation Strategy

### MVP (sólo US1)

1. Phase 1 → 2 → 2b.
2. Phase 3 completa, incluido **T022**: romper el invariante y verlo en rojo.
3. **PARAR Y VALIDAR**: quickstart §1 a §2.
4. Con esto el dinero deja de salir. US2 y US3 son garantías sobre el cambio, no
   el cambio.

### Entrega incremental

1. Foundational → el catálogo sabe los pesos, nadie los cobra.
2. US1 → **se despliega y se para el desangre**.
3. US2 → se demuestra que nadie paga de más.
4. US3 → se protege contra la próxima vez.

### Despliegue

`develop` → staging automático, y **se mira el consumo real de un partner antes
de tocar `main`**. El cambio es reversible por revert, porque nada se revalora
(D5): volver a los pesos viejos restaura el comportamiento sin dejar filas con
dos interpretaciones.

---

## Notes

- `[P]` = ficheros distintos, sin dependencias.
- Los tests se ven **fallar** antes de implementar (§VII).
- Un test que hace `skip` puntúa como aprobado y **no cubre nada**.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Producción tiene tres clientes reales con tráfico.
