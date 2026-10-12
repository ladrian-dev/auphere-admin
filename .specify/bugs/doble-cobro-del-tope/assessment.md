# Bug Assessment: el tope por cliente se descuenta dos veces y el gasto mostrado sale inflado

- **Slug**: doble-cobro-del-tope
- **Created**: 2026-10-10
- **Source**: pasted text (detectado al construir la spec 030; ver `docs/consola-lite.md`, «Dependencia abierta»)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> Doble cobro del tope por cliente. El saldo asignado a un cliente (su tope
> mensual, «allocation» del monedero del partner) baja el doble de rápido que
> lo que de verdad gasta. La sospecha es que en el medidor cada turno de un
> cliente descuenta el consumo dos veces del tope del cliente: una vez dentro
> de `debit_wallet` y otra con `debit_allocation`, ambos llamados por el
> consumidor del medidor. Consecuencia visible: el cliente ve un saldo que cae
> el doble que el gasto real y el partner ve agotarse el tope de su cliente
> antes de tiempo (los turnos podrían llegar a bloquearse por tope agotado).
> Hay que reproducirlo, confirmar o descartar la causa, y medir desde cuándo
> pasa y a quién afecta en producción.

## Symptom

Por cada turno de canal de un cliente con partner, el tope del cliente
(`partner_allocations.remaining`) baja **dos veces** lo gastado, y el gasto que
enseñan la consola del partner y la consola lite cuenta **dos veces** ese
consumo. Lo esperado: el tope baja una vez lo que de verdad se cobró y el gasto
mostrado es lo cobrado.

Son tres efectos de la misma causa:

1. **El tope se agota a la mitad.** `allow_channel_turn` no deja abrir el turno
   con `remaining <= 0`, así que el agente del cliente **deja de contestar** con
   la mitad de su tope gastado, hasta la siguiente reposición.
2. **El gasto mostrado sale inflado** hasta el doble: Inicio y Consumo del
   partner, Panel y Consumo de la consola lite y el desglose por agente.
3. **Gasto fantasma.** Si el partner no tiene créditos comprados, `debit_wallet`
   no cobra nada (el canal no puede gastar incluido), pero `debit_allocation`
   baja el tope igualmente y apunta un gasto que no ocurrió.

## Reproduction

1. Un partner con créditos comprados y un cliente con fila en
   `partner_allocations` (`cap = remaining = 10 000`).
2. Un turno de canal de ese cliente que pese 2 000 créditos; el consumidor del
   medidor llama a `_debit_channel_wallet`.
3. Resultado: `partner_wallets.purchased_remaining` baja 2 000 (correcto),
   `partner_allocations.remaining` baja **4 000**, y `usage_ledger` tiene dos
   asientos del cliente — `channel:<turn>:purchased` (2 000) y
   `channel:<turn>:allocation` (2 000) — que `credit_burn` suma: **4 000** de
   gasto.
4. Variante del gasto fantasma: con `purchased_remaining = 0` (y algo de
   incluido, para que el turno pase la puerta), el wallet no cobra nada y aun
   así el tope baja 2 000 y aparece un asiento `:allocation` de 2 000.

**Visto en staging** (consulta de solo lectura sobre `usage_ledger`,
2026-10-10):

| Mes | Cliente | Cobrado de verdad | Asientos `:allocation` |
|---|---|---|---|
| 2026-09 | QA-generica-20260825 | 1 asiento · 2 000 | 1 asiento · 2 000 |
| 2026-09 | Prueba WhatsApp 016 | **0** | 17 asientos · **28 570** |

El primer asiento `:allocation` de staging es del **2026-09-02 20:16**, el día
del commit que añadió la segunda llamada.

[NEEDS CLARIFICATION: alcance en producción — ver «Open Questions».]

## Suspected Code Paths

- `apps/api/src/nexus_api/metering/wallet.py:1005-1016` (`_debit_locked`) —
  con `tenant_id`, ya descuenta `spent` de `partner_allocations.remaining`, en
  la misma transacción que el wallet. Está así desde que nació el fichero
  (`c0d910ba`, 2026-08-22).
- `apps/worker/src/nexus_worker/metering/consumer.py:343-369`
  (`_debit_channel_wallet`) — después de `debit_wallet(..., tenant_id=...)`
  llama a `debit_allocation` con la misma cantidad. Añadido en `4ea24a7c`
  (2026-09-02, en `main`) sobre una premisa falsa: el comentario dice que
  `remaining` «no bajaba nunca».
- `apps/api/src/nexus_api/metering/wallet.py:1096-1153`
  (`_debit_allocation_locked`) — vuelve a descontar `min(qty, remaining)` del
  tope **sin mirar lo que el wallet cobró de verdad**, y escribe un asiento en
  `usage_ledger` (`bucket = included`, clave `…:allocation`, con `tenant_id`).
- `apps/api/src/nexus_api/metering/wallet.py:567-660` (`credit_burn`,
  `credit_burn_by_agent`, `credit_burn_by_day`) — suman `usage_ledger.qty` sin
  excluir los asientos `:allocation`. De aquí sale el gasto que enseñan la
  consola del partner (`console_home`, `api/console/usage.py: spend_report`),
  la consola lite (`services/lite_home.py`, `api/console/lite/usage.py`) y las
  alertas de saldo (`services/wallet_alerts.py`).
- `apps/api/src/nexus_api/api/admin/partner_wallet.py:131` — el único lector
  que sí excluye `:allocation` («Sin filas de allocation de cliente»): prueba
  de que esos asientos nunca debieron contarse como gasto.
- `apps/api/src/nexus_api/metering/wallet.py:455-482` (`allow_channel_turn`) y
  `apps/worker/src/nexus_worker/runtime/dispatcher.py:216` — la puerta que deja
  mudo al cliente con el tope a cero.
- `apps/worker/tests/unit/test_allocation_debit_wiring.py` — fija con dobles que
  se llame a los dos libros. Como cada llamada es un doble independiente, el
  doble descuento contra una base real nunca se vio.

## Root Cause Hypothesis

`debit_wallet` ya descuenta el tope del cliente, de forma atómica y por lo que
de verdad cobró (`spent`). El 2026-09-02 se añadió en el consumidor una segunda
llamada, `debit_allocation`, creyendo que el tope no se descontaba nunca. Desde
entonces cada turno de canal lo descuenta dos veces. Además, la segunda llamada
escribe un asiento de libro que los informes de gasto, escritos después (specs
026–030), suman como si fuera consumo. **Confianza: alta**: se ve en el código,
el historial de git lo fecha y staging lo confirma con datos.

## Proposed Remediation

**Preferred**: una sola fuente de verdad para el tope, la que ya era atómica.

1. **Dejar de descontar dos veces.** Quitar la llamada a `debit_allocation` del
   consumidor: `debit_wallet` ya baja el tope por lo cobrado de verdad, en la
   misma transacción que el wallet. Eso arregla también el gasto fantasma: sin
   cobro no hay descuento. Borrar `debit_allocation` y
   `_debit_allocation_locked`, que se quedan sin llamantes, para que no
   vuelvan a cablearse por error. Reescribir `test_allocation_debit_wiring.py`
   como prueba del contrato correcto: una sola llamada, con `tenant_id`.
2. **Que el histórico no siga inflando el gasto.** Excluir los asientos
   `…:allocation` en `credit_burn`, `credit_burn_by_agent` y
   `credit_burn_by_day`, como ya hace el admin. Se corrige sin borrar filas del
   libro: el histórico queda auditable y los informes dejan de contarlo.
3. **Devolver a cada cliente lo que se le descontó de más** en el periodo en
   curso, con una migración de datos. Para cada tope:
   `remaining = LEAST(cap, remaining + Σ qty de sus asientos :allocation desde
   la última reposición)`. Es exacto, porque cada asiento `:allocation` es
   justo un descuento de más. Desbloquea hoy a quien esté mudo por el bug, en
   vez de esperar a la siguiente reposición. Ver la pregunta sobre cómo fechar
   «la última reposición».

**Alternatives**:
- *Quitar el descuento de dentro de `debit_wallet` y dejar `debit_allocation`.*
  Descarta la atomicidad (dos transacciones), mantiene el gasto fantasma (la
  segunda no sabe lo que la primera cobró) y deja vivos los asientos que
  inflan el gasto. Peor en todo.
- *No reparar los datos y esperar a la reposición.* Más simple y sin
  migración. Pero si en producción hay clientes mudos por el bug, siguen mudos
  hasta su siguiente periodo.
- *Borrar los asientos `:allocation` del libro.* Simplifica los lectores, pero
  destruye la traza de lo que pasó. El filtro del paso 2 da el mismo resultado
  sin perder nada.

**Files likely to change**:
- `apps/worker/src/nexus_worker/metering/consumer.py`
- `apps/api/src/nexus_api/metering/wallet.py`
- `apps/api/alembic/versions/0156_…` (reparación de los topes del periodo en curso)
- `apps/worker/tests/unit/test_allocation_debit_wiring.py`
- `apps/api/tests/integration/test_no_external_debit.py` y
  `apps/api/tests/isolation/test_24_partner_wallet_rls.py` (usan `debit_allocation`)
- `docs/consola-lite.md` («Dependencia abierta») y `docs/billing.md` si describe el doble libro

**Tests to add or update**:
- **Integración contra la base real** (lo que faltó): un turno de canal de un
  cliente con tope baja `remaining` exactamente lo cobrado, una vez; el wallet
  baja lo mismo; hay un solo asiento de canal por cubo y ninguno `:allocation`.
- **Gasto fantasma**: sin créditos comprados, el turno no baja el tope ni deja
  asiento.
- **Informes**: con un asiento `:allocation` antiguo sembrado, `credit_burn`,
  `credit_burn_by_agent` y `credit_burn_by_day` no lo cuentan; el Panel lite y
  el Inicio del partner enseñan lo cobrado.
- **Reparación**: la migración devuelve a `remaining` lo descontado de más en el
  periodo y nunca pasa de `cap`; es idempotente y reversible en la prueba de
  reversibilidad.
- La prueba de la puerta: un cliente con la mitad del tope gastado sigue
  pudiendo abrir turno.

## Risks & Considerations

- **Dinero.** El cobro real al partner (`partner_wallets`) es correcto; solo
  están mal el tope por cliente y el gasto que se enseña. El arreglo no toca lo
  que el partner paga.
- **Al desplegar, los informes bajan.** El gasto del mes del partner y del
  cliente baja de golpe (deja de contar lo duplicado). Es la cifra verdadera,
  pero un partner atento lo verá: conviene decirlo en las notas del despliegue.
- **La reparación sube topes en producción.** Una migración de datos sobre
  `partner_allocations`: tiene que acotarse al periodo en curso, no superar
  nunca `cap` y ser idempotente (un segundo `upgrade` no puede devolver dos
  veces). Se mide antes en producción con una consulta de solo lectura.
- **RLS.** `partner_allocations` y `usage_ledger` tienen RLS FORCE por partner:
  la migración corre como el rol de migraciones (sin RLS), como las anteriores.
- **Hallazgos relacionados, fuera de alcance** (para otra evaluación):
  - La puerta (`allow_channel_turn`) deja pasar un turno si el wallet tiene
    créditos **incluidos**, pero el canal solo puede gastar **comprados**: con
    solo incluido, el cliente recibe turnos que no se cobran a nadie.
  - Los asientos de caducidad de créditos (`expire_credit_cron`, `tenant_id`
    nulo) entran en `credit_burn` del partner entero como si fueran gasto fuera
    de clientes. Hay que confirmarlo.

## Open Questions

- [NEEDS CLARIFICATION: **alcance en producción.** Cuántos clientes tienen tope,
  cuánto se les descontó de más en el periodo en curso, y si alguno está ahora
  mismo a 0 por el bug (mudo). Se mide con la misma consulta de solo lectura
  que en staging (`SET TRANSACTION READ ONLY`); necesita permiso para leer la
  base de producción.]
- [NEEDS CLARIFICATION: **cómo fechar «la última reposición»** de cada partner
  para acotar la reparación. La reposición va con la renovación del saldo
  incluido (`renew_included_if_expired` en `wallet_renewal_cron.py`); hay que
  ver si queda constancia del momento (un asiento, un evento o
  `included_expires_at` menos el periodo) o si basta con el inicio del mes en
  curso.]
