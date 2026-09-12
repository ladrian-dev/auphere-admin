---

description: "Tareas — el medidor dice la verdad"
---

# Tasks: el medidor dice la verdad

**Input**: documentos de diseño en `/specs/004-medidor-y-pool-semanal/`

**Prerequisites**: [plan.md](./plan.md) · [spec.md](./spec.md) ·
[research.md](./research.md) · [data-model.md](./data-model.md) ·
[contracts/](./contracts/) · [quickstart.md](./quickstart.md)

**Tests**: obligatorios. Constitución §VII — el criterio de aceptación **es** el
test, se ve en rojo antes de implementar, y un `skip` puntúa como aprobado sin
cubrir nada. Las comprobaciones llevan el identificador `V01`–`V43` del
[quickstart](./quickstart.md) para que se pueda cruzar la cobertura de un vistazo.

**Organization**: por historia, en orden de despliegue. Cada historia se puede
llevar a producción sola.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ir en paralelo (ficheros distintos, sin dependencias abiertas)
- **[Story]**: `US1`–`US4`, mapeadas a las historias de la spec

---

## Phase 1: Setup

**Purpose**: lo único que hay que preparar antes de tocar nada. No hay proyecto
nuevo, ni dependencia nueva, ni estructura nueva.

- [X] T001 Añadir a `.github/workflows/ci.yml` dos trabajos que ejecuten las suites de `packages/companion-ui` (144 pruebas) y de `apps/desktop` (307), hoy ausentes del fichero.
      **Va primero y no es alcance prestado**: esta spec modifica `packages/companion-ui`, que comparten la consola y la aplicación de escritorio. Sin esto, «CI en verde» no quiere decir «todo verde», y romper las dos superficies a la vez no lo detecta nadie al fusionar.
      _Requisitos: —_ (puerta de plan; **protege contra regresión** los criterios 7.1 y 7.4, no los implementa)

**Checkpoint**: la integración continua ejecuta lo que esta spec va a tocar.

---

## Phase 2: Foundational (prerrequisitos bloqueantes)

**Purpose**: utilidades de prueba que las cuatro historias necesitan.

**⚠️ CRÍTICO**: ninguna historia empieza hasta que esto esté.

- [X] T002 [P] Añadir en `apps/api/tests/conftest.py` una fábrica de partner con libro: crea `partners`, `partner_wallets` e `included_expires_at` en un estado dado, para no repetir el montaje en cada suite.
      _Requisitos: 2.1, 4.1, 5.1_
- [X] T003 [P] Añadir en `apps/api/tests/conftest.py` una fábrica de consumo: asienta un débito por un carril concreto (Companion · canal de cliente · ejecución local) para poder probar la separación de bolsillos sin levantar el runtime entero.
      _Requisitos: 5.1, 5.2_

> **El reloj no necesita utilidad nueva**: `renew_included_if_expired()` y
> `effective_included()` ya aceptan `now` inyectable, y `next_period_end()`
> también. Verificado antes de escribir esta fase.

**Checkpoint**: cimientos listos; las historias pueden empezar.

---

## Phase 2b: Las puertas de la constitución

**Purpose**: las tres comprobaciones que `/speckit-analyze` no deja pasar.

- [ ] T004 [P] **Puerta de aislamiento · garantía 1 (Postgres RLS)** — test en `apps/api/tests/isolation/test_budget_reads_wallet_scope.py`: con dos partners con libros distintos, la lectura del presupuesto de uno **nunca** devuelve el saldo del otro; y con `app.partner_id` ausente, devuelve cero filas en vez de un 500. En rojo bloquea el merge (§I).
      _Requisitos: 4.1, 4.5_ · V26
- [ ] T005 [P] **Puerta de aislamiento · garantía 1 (fuga a cliente final)** — test en `apps/api/tests/isolation/test_pool_not_exposed_to_tenant.py`: ninguna respuesta de un endpoint orientado a cliente final menciona pool, saldo, tope ni precio. Estructural sobre el esquema OpenAPI, copiando el patrón que CP-21 ya usa para el contenido de conversación.
      _Requisitos: 4.6_ · V26
- [ ] T006 [P] **Puerta de aislamiento · garantía 6 (log + trace)** — test en `apps/api/tests/isolation/test_wallet_events_are_logged.py`: cada renovación semanal y cada débito dejan su asiento y su evento con el partner identificado, y **ningún** log lleva contenido de conversación.
      _Requisitos: 2.1, 5.6_
- [ ] T007 [P] **Puerta de licencias** — test en `apps/api/tests/unit/test_no_new_dependencies.py` que compara la lista de dependencias declaradas contra la instantánea de esta rama y falla si aparece una nueva. El plan declara **ninguna**; `stripe` es de la Spec B y no puede colarse aquí (§VIII).
      _Requisitos: —_ (puerta de plan, no de spec)
- [ ] T008 **Puerta del medidor** — dejar escrito en [`contracts/quota-unit.md`](./contracts/quota-unit.md) que lo que gasta es **modelo y solo modelo** (ni reloj de máquina ni herramienta de pago), y que el partner lo ve en Consumo de la consola y en Cuenta de la aplicación como **barra y fecha**. Ya está redactado: la tarea es verificar que sigue siendo cierto al cerrar la spec.
      _Requisitos: 7.1, 7.2_

**Checkpoint**: las tres puertas tienen dueño.

---

## Phase 3: Historia 1 — Auphere puede ver su margen (P1) 🎯 MVP

**Goal**: que cada turno tenga un coste calculable. Hoy el modelo por defecto del
Companion es `openai/gpt-5.6-sol` y su tarifa está a `NULL` desde la `0095`: el
margen no es malo, es invisible.

**Independent Test**: se despliega sola. Pedir el coste de un mes con tráfico y
ver que no quedan filas sin valorar para los modelos que el producto vende.

### Tests de la Historia 1 (§VII — se escriben y se ven en ROJO antes de implementar) ⚠️

- [X] T009 [P] [US1] Test en `apps/api/tests/unit/test_model_catalog_prices.py`: los tres modelos del catálogo cerrado tienen entrada, entrada cacheada y salida; y `price_cache_write_per_mtok` sigue **ausente**, no a cero — el test lo afirma explícitamente, con el motivo en el docstring (OpenAI no cobra la escritura de caché, igual que razonó la `0076` para `gpt-4o`).
      _Requisitos: 1.1, 1.2_ · V01, V02
- [X] T010 [P] [US1] Test en `apps/api/tests/integration/test_reprice_backfill.py`: aplicar la migración revalora lo que estaba sin valorar y **no toca** lo que ya tenía coste; aplicarla dos veces no cambia una fila.
      _Requisitos: 1.3_ · V03
- [X] T011 [P] [US1] Test en `apps/api/tests/integration/test_cost_completeness.py`: un consumo de modelo sin tarifa sigue sin valorar y se cuenta aparte (`complete = false` y el recuento de filas sin precio); un mes con tráfico de los modelos que vendemos responde `complete = true`.
      _Requisitos: 1.4_ · V04, V05
- [X] T012 [P] [US1] Test en `apps/api/tests/unit/test_meter_prices_complete.py`: todo medidor conocido o tiene precio unitario o está declarado como no valorable; ninguno desaparece en silencio de un total.
      _Requisitos: 1.6_ · V06

### Implementación de la Historia 1

- [X] T013 [US1] Crear la migración `apps/api/alembic/versions/0114_sold_model_prices.py` que carga en `model_profiles` las tarifas de `openai/gpt-5.6-sol` (**4,00** entrada / **0,40** cacheada / **20,00** salida), `openai/gpt-5.6-terra` (**2,00** / **0,20** / **12,00**) y `openai/gpt-5.6-luna` (**0,20** / **0,02** / **1,20**), dejando `price_cache_write_per_mtok` en `NULL`. Copiar **verbatim** el `_PRICE_EXPR` y el `UPDATE` idempotente de la `0076` — una migración es un hecho histórico y no puede cambiar de resultado porque alguien edite un módulo compartido seis meses después. Con `downgrade()` real.
      _Requisitos: 1.1, 1.2, 1.3_
- [X] T014 [US1] En el docstring de la `0114`, dejar escrita **la fuente y la fecha** de cada tarifa (`developers.openai.com/api/docs/pricing`, consultada 2026-09-11), como hizo la `0076`. Revisar una tarifa dentro de un año no puede obligar a investigar de cero.
      _Requisitos: 1.5_
- [X] T015 [US1] En la misma `0114`, añadir las filas de `meter_prices` que faltan, o declarar explícitamente cuáles no se valoran. Hoy la tabla tiene **6 filas y todas son `media.*`**, con `note` marcándolas `provisional 2026-08`.
      _Requisitos: 1.6_
- [ ] T016 [US1] Ejecutar la migración contra un dump de producción y probar el `downgrade()`, como pide la regla 3 de `[[nexus/PLAN-CONSOLE-V1]]`.
      **Mitad hecha el 2026-09-11**: `downgrade()` probado contra la base local con datos — los tres modelos vuelven a `NULL` y las tarifas de Anthropic y `gpt-4o` quedan intactas, que es lo que su comentario promete. **Falta el dump de producción**, que no está disponible en esta máquina. Se queda abierta a propósito: media tarea marcada entera es cómo se cuela un `downgrade()` que nadie probó donde importa.
      _Requisitos: 1.3_

**Checkpoint**: el margen es calculable. **Desplegable sola.** Cierra el ítem
**C1** y parte de **C2** del plan de pendientes.

---

## Phase 4: Historia 2 — Una sola cifra, y es verdad (P1)

**Goal**: quitar el segundo contador. Hoy un partner puede ver `budget` al 20 % y
recibir `409 wallet_empty` a la vez. Es una **supresión**, no una adición.

**Independent Test**: gastar por dos carriles distintos —un turno de Companion y
un turno de canal de un cliente— y comprobar que el total sube por los dos y que
las tres superficies lo ven igual.

### Tests de la Historia 2 (§VII — en ROJO antes de implementar) ⚠️

- [ ] T017 [P] [US2] **El test que hoy falla**, en `apps/api/tests/integration/test_budget_matches_wallet.py`: consumir por canal hasta vaciar el libro y comprobar que el presupuesto lo refleja. Hoy diría 20 % con el libro vacío. Se escribe **antes** y se ve en rojo: es la prueba de que el defecto existe.
      _Requisitos: 4.1, 4.3_ · V21
- [ ] T018 [P] [US2] Test en `apps/api/tests/integration/test_three_surfaces_agree.py`: las lecturas de consola, operador y aplicación derivan del mismo dato y del mismo período en la misma petición.
      _Requisitos: 4.3_ · V22, CE-001
- [ ] T019 [P] [US2] Test en `apps/api/tests/unit/test_attribution_gap.py`: cuando el total supera lo atribuido a teammates, la diferencia se nombra y **no** se reparte entre los que sí aparecen.
      _Requisitos: 4.4_ · V23
- [ ] T020 [P] [US2] Test en `apps/api/tests/unit/test_wallet_fail_closed.py`: con el libro ilegible, el saldo es cero y no hay llamada al modelo.
      _Requisitos: 4.5_ · V24
- [ ] T021 [P] [US2] Test **estructural** en `apps/api/tests/unit/test_single_meter.py`: no queda ningún segundo tope de otro alcance comparándose contra la misma cifra. Falla si alguien reintroduce una suma sobre ejecuciones como total.
      _Requisitos: 4.6_ · V25, CE-008
- [ ] T022 [P] [US2] Tests en `apps/api/tests/integration/test_pocket_separation.py`: teammates y Companion gastan incluido primero y comprado después; el canal de clientes **nunca** toca el incluido; el mismo turno reprocesado no descuenta dos veces.
      _Requisitos: 5.1, 5.2, 5.6_ · V27, V28, V31
- [ ] T023 [P] [US2] Tests en `apps/api/tests/integration/test_allocation_on_purchased.py`: el disponible para asignar se calcula sobre **comprado**; el tope por cliente se repone mensualmente; un cliente que agota su tope calla solo él; la suma de topes no supera el saldo; los avisos al 80 % y 100 % siguen llegando sin duplicar.
      _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5_ · V32, V33, V34, V35, V36

### Implementación de la Historia 2

- [ ] T024 [US2] En `apps/api/src/nexus_api/metering/wallet.py`, añadir el parámetro `allow_included: bool = True` a `debit_wallet`. El valor por defecto `True` es deliberado: los dos llamantes que sí pueden gastar incluido no cambian una línea. Ver decisión **D4** del [research](./research.md).
      _Requisitos: 5.1, 5.2_
- [ ] T025 [US2] En `apps/worker/src/nexus_worker/metering/consumer.py`, pasar `allow_included=False` en el débito del canal. Es el cambio que hace que el consumo de clientes finales deje de comerse el pool de la aplicación.
      _Requisitos: 5.2_
- [ ] T026 [US2] En `apps/api/src/nexus_api/metering/wallet.py`, hacer que `allocatable_for()` y `set_allocation()` calculen contra `purchased_remaining` en vez de contra el disponible total, conservando la invariante «la suma de topes no supera el saldo sobre el que se calculan».
      _Requisitos: 6.1, 6.5_
- [ ] T027 [US2] En `apps/api/src/nexus_api/api/console/companion.py`, reescribir `budget_out()` para que tome `cap` y `remaining` **del libro** en vez de de la suma de `companion.runs`. `remaining` pasa a ser la columna que la plataforma consulta para dejar pasar, no una resta. Tabla campo a campo en [`contracts/budget-object.md`](./contracts/budget-object.md).
      _Requisitos: 4.1_
- [ ] T028 [US2] En el mismo fichero, degradar `sum_partner_companion_tokens()` a **atribución**: sigue recorriendo membresías bajo RLS porque el reparto sí es por persona, pero deja de presentarse como total. Dejar el porqué en el docstring.
      _Requisitos: 4.2_
- [ ] T029 [US2] En `apps/api/src/nexus_api/api/console/teammates.py`, consumir el `budget_out` nuevo sin duplicar lógica: **una sola implementación**, que es lo que R9.1 de la spec 003 ya exigía.
      _Requisitos: 4.2, 4.3_
- [ ] T030 [US2] Retirar `_require_wallet` como comprobación **separada** del presupuesto, o dejarla explícitamente como la misma lectura: hoy son dos caminos que pueden discrepar y ése es el defecto. Documentar cuál de las dos se elige y por qué.
      _Requisitos: 4.6_

**Checkpoint**: el número que se enseña y el número que decide son el mismo. **D5
del plan de pendientes queda cerrado.**

---

## Phase 5: Historia 3 — El pool se reinicia cada semana (P2)

**Goal**: el consumo incluido pasa a semanal, anclado a la fecha de alta del
partner. Y la pantalla deja de dar cifras: barra y fecha.

**Independent Test**: gastar, adelantar el reloj más allá del límite semanal del
partner, y ver que el pool vuelve solo sin que nadie ejecute nada a mano.

### Tests de la Historia 3 (§VII — en ROJO antes de implementar) ⚠️

- [ ] T031 [P] [US3] Tests en `apps/api/tests/unit/test_weekly_period.py`: el vencimiento cae a siete días del ancla, no el día 1 del mes; dos partners dados de alta en días distintos vencen en días distintos (**no hay lunes global**).
      _Requisitos: 2.1, 2.2_ · V07, V08
- [ ] T032 [P] [US3] Tests en `apps/api/tests/integration/test_weekly_renewal.py`: al vencer, el pool vuelve completo y lo no gastado **no se suma**; con el proceso detenido tres días, al volver repone de inmediato.
      _Requisitos: 2.3, 2.4_ · V09, V10
- [ ] T033 [P] [US3] Test en `apps/api/tests/unit/test_purchased_never_expires.py`: `purchased` sobrevive a la renovación, al cambio de período y al vaciado del incluido. Invariante.
      _Requisitos: 2.5_ · V11
- [ ] T034 [P] [US3] Test en `apps/api/tests/integration/test_monthly_volume_preserved.py`: el volumen mensual de cada partner no cambia al migrar de mes a semana.
      _Requisitos: 2.6_ · V12, CE-007
- [ ] T035 [P] [US3] Test en `apps/api/tests/integration/test_partner_created_with_pool.py`: un partner recién creado nace con pool y con su vencimiento puesto **en el mismo acto**; no hay ventana en la que exista sin saldo esperando a un proceso de fondo.
      _Requisitos: 2.7_ · V13
- [ ] T036 [P] [US3] Test en `apps/api/tests/integration/test_pool_size_is_data.py`: cambiar el tamaño del pool no exige migración ni despliegue.
      _Requisitos: 2.9_ · V14, CE-009
- [ ] T037 [P] [US3] Tests en `apps/api/tests/integration/test_pause_and_fallthrough.py`: agotado el incluido a mitad de ciclo el trabajo continúa **sin intervención**; sin incluido y sin comprado queda en pausa por tope con las confirmaciones vivas y **nada cancelado ni archivado**.
      _Requisitos: 5.3, 5.4_ · V29, V30, CE-004, CE-005
- [ ] T038 [P] [US3] Tests de interfaz en `apps/desktop/src/app/routes/__tests__/account.test.tsx` y en la consola: la pantalla del partner muestra proporción y fecha y **no** la cifra del pool; el medidor conserva sus tres valores y su texto alternativo; el saldo **comprado** sigue en unidades.
      _Requisitos: 7.1, 7.4, 7.6_ · V37, V39, V40
- [ ] T039 [P] [US3] Test en `apps/admin/src/app/(dashboard)/partners/[id]/__tests__/wallet.test.tsx`: el panel de operador **sigue** mostrando las cifras absolutas del pool. Es la mitad que se olvida: R7 quita el número de la pantalla del partner, **no** de la de quien tiene que conciliar una factura. Sin este test, alguien aplica el recorte a las dos superficies y Auphere se queda sin poder diagnosticar.
      _Requisitos: 7.2_ · V38
- [ ] T040 [P] [US3] Test en `packages/companion-ui/src/components/__tests__/composer.test.tsx`: el aviso de pausa ya no pinta «X de Y», y el texto de desbloqueo dice las salidas que ahora existen.
      _Requisitos: 7.1, 7.5_ · V41, V42
- [ ] T041 [P] [US3] Test de no regresión en `packages/companion-ui`: el medidor de **ventana de contexto** y el del **turno** siguen intactos. R7 abstrae el pool, no todo número en pantalla.
      _Requisitos: 7.1_ · V43

### Implementación de la Historia 3

- [ ] T042 [US3] En `apps/api/src/nexus_api/metering/wallet.py`, reescribir `next_period_end()` para devolver el siguiente múltiplo de siete días contado desde `partners.created_at`. **`renew_included_if_expired()` no se toca**: ya dispara por caducidad y no por calendario, así que el cron horario sirve igual (decisión **D3** del research).
      _Requisitos: 2.1, 2.2, 2.4_
- [ ] T043 [US3] Crear la migración `apps/api/alembic/versions/0115_quota_weight_and_weekly_pool.py` con la columna `partners.weekly_pool_tokens bigint NOT NULL`, `CHECK (weekly_pool_tokens >= 0)`, sembrada como `round(companion_monthly_token_cap × 7 / 30.44)` para preservar el volumen mensual. Con `downgrade()` real.
      _Requisitos: 2.6, 2.9_
- [ ] T044 [US3] En `apps/api/src/nexus_api/db/models/partner.py`, marcar `companion_monthly_token_cap` como **deprecada** nombrando en el comentario la migración que la eliminará. **No se borra aquí**: crear la sustituta y borrar la original en la misma migración deja un `downgrade()` incapaz de devolver los datos.
      _Requisitos: 2.6_
- [ ] T045 [US3] Hacer que el alta de partner deje el pool y el vencimiento puestos **en la misma transacción** que crea el partner, con el mismo criterio que `seed_default_allocation` ya usa para la cuota de un cliente: *«la cuota y el cliente nacen en la misma transacción o no nace ninguno»*.
      _Requisitos: 2.7_
- [ ] T046 [US3] En `apps/api/src/nexus_api/api/console/schemas_companion.py`, cambiar el formato de `period` a semana ISO (`YYYY-Www`) y actualizar la descripción del campo.
      _Requisitos: 2.8_
- [ ] T047 [US3] En `packages/companion-ui/src/messages.ts`, corregir las nueve cadenas: las dos que pintan cifras (`companion.meter.month.detail`, `companion.paused.body`), las seis que dicen «mes», y sobre todo **`companion.paused.unblock`**, que hoy dice *«esperar no lo desbloquea»* y **pasa a ser falsa** — con el pool semanal esperar sí lo desbloquea, y con la caída a comprado muchas veces ni se pausa. El texto nuevo dice las dos salidas que ahora existen antes de la de escribirnos.
      _Requisitos: 5.5, 7.1, 7.5_
- [ ] T048 [US3] En `packages/companion-ui/src/components/composer.tsx`, quitar las cifras del aviso de pausa y dejar el período y la fecha de reposición.
      _Requisitos: 7.1_
- [ ] T049 [US3] En `apps/desktop/src/app/routes/account.tsx`, cambiar la línea «X de Y tokens» por proporción y fecha. **Conservar el `role="meter"` con sus tres valores y su `aria-valuetext`**: una barra sin valores no le dice nada a quien usa lector de pantalla.
      _Requisitos: 7.1, 7.4_
- [ ] T050 [US3] En `apps/console/src/app/(console)/usage/page.tsx`, mismo criterio para el pool incluido. **El saldo comprado sigue en unidades**: es dinero que el partner pagó y tiene derecho a verificar.
      _Requisitos: 7.1, 7.6_
- [ ] T051 [US3] En `apps/admin/src/app/(dashboard)/partners/[id]/`, confirmar que el panel de operador **sigue** enseñando las cifras absolutas y añadir el control para cambiar `weekly_pool_tokens`, con su evento de auditoría nombrando a la persona.
      _Requisitos: 2.9, 7.2, 7.3_

**Checkpoint**: el pool se repone solo cada semana y la pantalla dice la verdad
sin dar cifras.

---

## Phase 6: Historia 4 — El pool cuesta lo mismo con cualquier cerebro (P2)

**Goal**: meter el factor por modelo dentro de `quota_tokens()`, donde ya vive el
factor de lectura de caché. **Depende de la Historia 1**: los factores se
calibran con las tarifas cargadas.

**Independent Test**: agotar un pool del mismo tamaño con cada uno de los tres
cerebros y comprobar que el coste en dólares coincide.

### Tests de la Historia 4 (§VII — en ROJO antes de implementar) ⚠️

- [ ] T052 [P] [US4] **Test de propiedad** en `apps/api/tests/unit/test_quota_weight_invariance.py`: se recorre **el catálogo entero**, no un caso suelto, y se comprueba que agotar un pool de tamaño fijo cuesta lo mismo con cada modelo — banda **3,5144 $–3,5154 $** por millón, 0,03 % de desviación.
      _Requisitos: 3.2_ · V15, CE-002
- [ ] T053 [P] [US4] Test en `apps/api/tests/unit/test_weight_is_data.py`: los factores están declarados como dato y **no** se derivan de la tarifa vigente; cambiar una tarifa no mueve el contador del partner.
      _Requisitos: 3.3_ · V16
- [ ] T054 [P] [US4] Test en `apps/api/tests/unit/test_missing_weight_refuses.py`: un modelo con factor ausente **no atiende ni un turno** y el error lo nombra y dice qué le falta.
      _Requisitos: 3.4_ · V17, CE-010
- [ ] T055 [P] [US4] Test en `apps/api/tests/unit/test_voice_unaffected_by_weight.py`: `openai/whisper-1` tiene el factor ausente **y sigue funcionando**, porque se mide por minutos y no pasa por la cuota de LLM. Es el error que alguien "arreglará" en seis meses poniéndole un `1.0`.
      _Requisitos: 3.4_ · V18
- [ ] T056 [P] [US4] Test en `apps/api/tests/unit/test_weight_change_does_not_revalue.py`: cambiar un factor **no** revalúa asientos ya escritos. Un asiento es un hecho contable.
      _Requisitos: 3.5_ · V19
- [ ] T057 [P] [US4] Test **estructural** en `apps/api/tests/unit/test_all_callers_pass_weight.py`: recorre los llamantes de `quota_tokens` y falla si alguno no pasa `model_weight`. Más barato que descubrirlo cuadrando una factura.
      _Requisitos: 3.1_ · V20

### Implementación de la Historia 4

- [ ] T058 [US4] En `apps/api/src/nexus_api/metering/quota.py`, añadir `model_weight: Decimal` a `quota_tokens()` como parámetro **obligatorio y sin valor por defecto**: un defecto de `1` convertiría el olvido de pasarlo en un cobro silencioso a la baja. El factor se aplica al total y **antes** del redondeo final con `ROUND_HALF_UP`, para no redondear dos veces.
      _Requisitos: 3.1_
- [ ] T059 [US4] En la migración `0115`, añadir `model_profiles.quota_weight numeric(6,3) NULL` con `CHECK (quota_weight IS NULL OR quota_weight > 0)` — un peso de cero haría el pool infinito — y sembrar: Luna **0,100** · Haiku 4.5 **0,457** · Terra **1,000** · Sonnet 4.6 **1,371** · gpt-4o **1,724** · Sol **1,828**; `whisper-1` queda en `NULL`. `NULL` significa «este modelo no se sirve», **no** «peso 1».
      _Requisitos: 3.3, 3.4_
- [ ] T060 [US4] En `apps/api/src/nexus_api/db/models/model_profile.py`, declarar `quota_weight` con el comentario que explica por qué es dato y no cálculo derivado de la tarifa.
      _Requisitos: 3.3_
- [ ] T061 [US4] En `apps/worker/src/nexus_worker/metering/pricing.py`, añadir `quota_weight` a `ModelPrice` y al catálogo cacheado. **Cero consultas nuevas por turno**: el catálogo ya se lee en el camino del turno con TTL de 300 s.
      _Requisitos: 3.1_
- [ ] T062 [US4] Hacer que los **tres** llamantes resuelvan y pasen el factor: `api/console/companion.py`, `apps/worker/.../metering/consumer.py` y `services/local_workstation_metering.py`. Si uno lo olvidara, su consumo entraría al libro con otra unidad — el defecto de la Historia 2, reaparecido en el camino de escritura.
      _Requisitos: 3.1_
- [ ] T063 [US4] Implementar la negativa de **R3.4**: modelo en catálogo con factor ausente → error legible que lo nombra, por el mismo camino que ya rechaza un modelo fuera de catálogo. **Y acotarlo en el código**: la negativa aplica solo al carril de cuota de LLM, no a `voice.minutes` ni a `media.*`.
      _Requisitos: 3.4_
- [ ] T064 [US4] Verificar que la indicación relativa `bajo · medio · alto · desconocido` de `services/model_choices.py` sigue publicándose por teammate, y que **no** aparece un importe en dólares en la fila de un turno (decisión 14 de la KB).
      _Requisitos: 3.6_

**Checkpoint**: el peor caso de cada plan es un número conocido de antemano y no
una elección del partner.

---

## Phase 7: Polish & cross-cutting

- [ ] T065 [P] Actualizar `specs/003-teammates-app-escritorio/contracts/teammates-api.md`: el campo `budget` cambia de período y de origen. **En el mismo commit que el cambio**, como pide el `CLAUDE.md` del repositorio.
      _Requisitos: 4.3_
- [ ] T066 [P] Actualizar `docs/desktop-teammates.md` §«Un solo medidor»: sigue siendo cierto que hay un solo medidor, pero ahora el objeto sale del libro y el período es semanal. El documento describe lo que esta spec cambia, así que se actualiza aquí.
      _Requisitos: 4.1, 4.2_
- [ ] T067 [P] Actualizar `docs/companion/CONTRACT-V2.md` §6 si describe el tope mensual o el texto de pausa.
      _Requisitos: 5.5, 7.5_
- [ ] T068 Escribir en la KB la nota de cierre y enlazar desde `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` a esta carpeta de spec (§IX: el puente es obligatorio en las dos direcciones).
      _Requisitos: —_
- [ ] T069 Ejecutar el recorrido de humo de [`quickstart.md`](./quickstart.md), los siete pasos, sobre el entorno local.
      _Requisitos: todos_
- [ ] T070 Ejecutar las tres suites completas y dejar las cifras en el PR: `tests/unit`, `tests/isolation` (bloquea merge) y `tests/integration`, más `vitest` de consola, aplicación y `@nexus/companion-ui`.
      _Requisitos: todos_

---

## Dependencies & Execution Order

### Entre fases

- **Setup (T001)** → primero de todo. Sin CI ejecutando `companion-ui`, romper la
  consola y la aplicación a la vez no lo detecta nadie.
- **Foundational (T002–T003)** → bloquea las cuatro historias.
- **Puertas (T004–T008)** → pueden ir en paralelo con las historias, pero
  **ninguna historia se cierra** sin su puerta en verde.
- **Historias** → en el orden de abajo.
- **Polish (T065–T070)** → al final, salvo T065 y T066, que van **en el commit
  del cambio que describen**.

### Entre historias

```
US1 (tarifas) ──────────────┬──────────► US4 (peso por modelo)
                            │            los factores se calibran
                            │            con las tarifas cargadas
US2 (un solo medidor) ──────┴──────────► US3 (período semanal)
   independiente de US1                   los textos y la barra
                                          suponen el dato del libro
```

- **US1 (P1)**: sin dependencias. **Desplegable sola. Es el MVP.**
- **US2 (P1)**: sin dependencias de US1. Se puede hacer en paralelo.
- **US3 (P2)**: después de US2 — la barra y los textos suponen que el número ya
  sale del libro.
- **US4 (P2)**: después de US1 — los factores salen de las tarifas.

### Dentro de cada historia

Tests en rojo → migración → modelo → servicio → interfaz. Sin excepciones (§VII).

### Paralelismo

- T002 y T003 a la vez.
- Las cinco puertas (T004–T008) a la vez.
- Todos los bloques de tests marcados `[P]` dentro de una historia, a la vez.
- **US1 y US2 a la vez** si hay dos personas: no se tocan.

---

## Parallel Example: Historia 2

```bash
# Los siete tests de la Historia 2, a la vez — ficheros distintos:
Task: "test_budget_matches_wallet.py — el test que hoy falla"
Task: "test_three_surfaces_agree.py — CE-001"
Task: "test_attribution_gap.py"
Task: "test_wallet_fail_closed.py"
Task: "test_single_meter.py — estructural"
Task: "test_pocket_separation.py"
Task: "test_allocation_on_purchased.py"
```

---

## Implementation Strategy

### MVP: solo la Historia 1

1. T001 (CI) → T002–T003 (cimientos) → T009–T016.
2. **Parar y validar**: el coste de un mes con tráfico responde `complete = true`.
3. Desplegar. Cierra **C1** del plan de pendientes y hace visible un margen que
   hoy no existe. **No cambia comportamiento de producción**: solo valora lo que
   ya se medía.

### Entrega incremental

1. **US1** → desplegar. El margen es calculable.
2. **US2** → desplegar. Se acaba la contradicción entre pantalla y realidad, y
   los clientes finales dejan de comerse el pool de la aplicación. **Cierra D5.**
3. **US3** → desplegar. Pool semanal y pantalla sin cifras.
4. **US4** → desplegar. El peor caso queda acotado, y con eso la **Spec B** puede
   publicar precios defendibles.

### Qué NO desbloquea esto

Ninguna historia de aquí permite cobrar. Stripe, las membresías y la escalera de
impago son la **Spec B**, y dependen de que esto esté en producción.

---

## Notes

- `[P]` = ficheros distintos, sin dependencias abiertas.
- Cada tarea cita sus requisitos; una tarea sin trazabilidad no entra.
- Los tests se ven **fallar** antes de implementar. Un `skip` no cubre nada.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **Cobertura**: las 43 comprobaciones `V01`–`V43` del quickstart están cubiertas
  por T009–T012 (V01–V06), T031–T037 (V07–V14, V29–V30), T052–T057 (V15–V20),
  T017–T021 + T004–T005 (V21–V26), T022 (V27–V28, V31), T023 (V32–V36) y
  T038–T041 (V37–V43).
