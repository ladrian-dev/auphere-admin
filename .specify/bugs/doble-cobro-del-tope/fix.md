# Bug Fix: el tope por cliente se descuenta dos veces y el gasto mostrado sale inflado

- **Slug**: doble-cobro-del-tope
- **Fixed**: 2026-10-10
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El tope de un cliente lo baja ahora una sola vez `debit_wallet`, por lo que de
verdad cobró. Se quitó la segunda llamada (`debit_allocation`) y se borró la
función. Las sumas de gasto ignoran los asientos `…:allocation` que quedan en
el libro. La migración `0156` devuelve a cada cliente lo descontado de más en
su semana en curso, lo que desmuda a los dos clientes de producción que estaban
a cero.

## Alcance medido en producción (solo lectura, 2026-10-10)

Con permiso de Luis, con `SET TRANSACTION READ ONLY` y la tarea de
migraciones:

- Primer asiento `:allocation` en producción: **2026-09-13 18:24**; desde
  entonces 1 159 asientos y 2 659 839 créditos descontados de más (754 asientos
  en octubre).
- 6 topes, 5 con valor y **2 a cero por el bug**, con el agente mudo:

| Partner | Cliente | Tope | Quedaba | Cobrado en la semana | Tras 0156 |
|---|---|---|---|---|---|
| amacrux | Amigable Cobro | 1 200 000 | **0** | 601 027 | 598 973 |
| facelad | New Air Climatización | 50 000 | **0** | 0 | 50 000 |
| facelad | Barber Supply | 50 000 | 46 347 | 0 | 50 000 |
| auphere-internal-partner | Flor y Encanto | 4 639 000 | 3 847 098 | 397 399 | 4 241 601 |

Todos los partners afectados renovaron en la semana (`included_expires_at`
futuro) y ninguno cambió el tope en ella, que es lo que la migración supone.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/metering/consumer.py` | modified | Fuera la llamada a `debit_allocation`; el comentario cuenta por qué |
| `apps/api/src/nexus_api/metering/wallet.py` | modified | Borradas `debit_allocation` y `_debit_allocation_locked`; `ALLOCATION_KEY_SUFFIX` y `_spend_only()` en `credit_burn`, `credit_burn_by_agent` y `credit_burn_by_day` |
| `apps/api/alembic/versions/0156_repair_double_cap_debit.py` | added | Reparación de la semana en curso; `downgrade` vacío a propósito |
| `apps/api/tests/integration/test_channel_debit_once.py` | added test | Los cuatro efectos del bug contra la base real |
| `apps/api/tests/integration/test_migration_repair_double_cap_debit.py` | added test | La reparación: restaura, no baja, no toca lo ajeno, idempotente |
| `apps/api/tests/isolation/test_24_partner_wallet_rls.py` | modified test | La garantía «el cobro de un cliente no toca el tope de otro», ahora sobre `debit_wallet` |
| `apps/worker/tests/unit/test_allocation_debit_wiring.py` | modified test | Una sola llamada, con `tenant_id`; `debit_allocation` ya no existe |
| `docs/consola-lite.md` | modified | La «dependencia abierta» pasa a arreglada |
| `specs/030-consola-lite-del-cliente/tasks.md` | modified | Nota en la condición previa a abrir Consumo |

## Diff Highlights

```python
# wallet.py — lo que el bug escribió sigue en el libro, pero no es gasto
ALLOCATION_KEY_SUFFIX = ":allocation"

def _spend_only() -> sa.ColumnElement[bool]:
    return ~UsageLedger.idempotency_key.like(f"%{ALLOCATION_KEY_SUFFIX}")
```

```sql
-- 0156 — por tope con asientos :allocation en la semana
remaining = LEAST(cap, GREATEST(remaining, cap - lo_cobrado_en_la_semana))
```

## Tests Added or Updated

- `test_channel_debit_once.py::test_a_channel_turn_lowers_the_client_cap_once`:
  el tope baja una vez y el monedero lo mismo; un solo asiento y ninguno
  `:allocation`.
- `…::test_nothing_charged_means_nothing_off_the_cap`: sin créditos comprados no
  baja el tope ni hay asiento (el gasto fantasma).
- `…::test_half_the_cap_spent_still_answers`: con la mitad del tope gastada,
  `allow_channel_turn` sigue abierto (el agente no se calla).
- `…::test_old_allocation_entries_are_not_spend`: los tres lectores de gasto
  ignoran un asiento `:allocation` antiguo.
- `test_migration_repair_double_cap_debit.py::test_the_week_s_over_debit_goes_back_to_each_client`.
- `test_24_partner_wallet_rls.py::test_a_clients_debit_lowers_only_its_own_cap`
  (sustituye a `test_debit_allocation_does_not_touch_wallet_or_other_client`).
- `test_allocation_debit_wiring.py`: tres pruebas nuevas en lugar de las tres
  que fijaban las dos llamadas.

## Local Verification

- Los cuatro tests de `test_channel_debit_once.py` se vieron **en rojo** antes
  del arreglo, cada uno por su efecto: el tope quedaba en 6 000 en vez de 8 000;
  bajaba a 8 000 sin cobro; quedaba en 0 con la mitad gastada (puerta cerrada);
  el gasto sumaba 4 000 en vez de 2 000. Tras el arreglo, verdes.
- `pytest tests/integration/test_channel_debit_once.py tests/isolation/test_24_partner_wallet_rls.py tests/integration/test_no_external_debit.py` → 22 passed.
- `pytest tests/integration/test_migration_repair_double_cap_debit.py tests/integration/test_migration_reversibility.py` → 3 passed.
- Worker `tests/unit/test_allocation_debit_wiring.py` → 4 passed.
- La prueba de la migración se escribió después de la migración. Para que no
  fuera vacía, se comprobó con la migración inutilizada (sin filas a reparar):
  falla con `assert 0 == 7000`.
- `./scripts/verify.sh` completo: ver `test.md`.

## Deviations from Assessment

- La fórmula de reparación no es «`remaining` + Σ asientos `:allocation`», como
  proponía el diagnóstico, sino `cap − lo cobrado en la semana`, con
  `GREATEST(remaining, …)` para no bajar nunca. Con los datos de producción, la
  suma de asientos se pasaba de lo correcto: el suelo a cero del primer
  descuento (`max(0, …)`) perdía parte de lo descontado (Amigable Cobro:
  600 375 frente a 598 973). `cap − cobrado` es la verdad por definición, sin
  esos restos.
- La semana se fecha con `included_expires_at − 7 días`. Responde a la pregunta
  abierta del diagnóstico: el periodo es semanal desde la spec 004 y la
  reposición del tope va con la renovación.

## Follow-ups

- **Desplegar cuanto antes**: dos clientes de producción están mudos ahora
  mismo, y el código actual sigue descontando dos veces hasta que entre el
  arreglo. La migración corre en el despliegue (bloqueante) y los desmuda.
- **Al desplegar, el gasto del mes baja** en el Inicio y Consumo de los
  partners y en la consola lite: deja de contar lo duplicado. Avisar a amacrux
  y facelad.
- Hallazgos relacionados del diagnóstico, para evaluar aparte:
  - Con solo créditos incluidos, la puerta deja pasar turnos de canal que no se
    cobran a nadie. Es el caso de facelad: New Air vuelve a contestar con el
    arreglo, pero sin cobro.
  - Las caducidades de créditos (`expire_credit_cron`, `tenant_id` nulo) entran
    como gasto en `credit_burn` del partner entero.
