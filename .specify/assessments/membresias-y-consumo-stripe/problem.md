# Problem: se mide todo y no se cobra nada

- **Slug**: membresias-y-consumo-stripe
- **Fecha**: 2026-09-11

## A quién le duele

- **A Auphere.** Hay un libro contable por partner, transaccional, idempotente,
  con RLS forzada y con avisos al 80 % y al 100 % — y **ninguna forma de que
  entre un dólar**. La única puerta de recarga en producción lleva token de
  admin. Cobrar hoy es un `POST` a mano o SQL.
- **Al partner que quiere empezar.** No puede darse de alta, no puede pagar, no
  puede comprar saldo. Lo que en las seis referencias del §2 de
  [`research.md`](./research.md) es un botón, aquí es una conversación.
- **A quien tenga que decidir un precio.** El margen de teammates **no se puede
  calcular**: el modelo por defecto es Sol y su tarifa está a NULL, así que
  `_turn_cost_usd` devuelve `None` en cada turno y `usage_records.cost_usd`
  queda sin valorar. No es que el margen sea malo — es que no existe el dato.
- **A quien mire un número en pantalla.** Ya hay dos cifras del mismo gasto que
  pueden discrepar (§1.3 de [`research.md`](./research.md)), y el pool semanal,
  hecho a la ligera, añadiría una tercera.

## Qué duele exactamente

1. **El aparato está construido y desconectado.** `partner_wallets`,
   `usage_ledger`, `partner_allocations`, `debit_wallet`, `quota_tokens`,
   `wallet_renewal_cron`, `wallet_alerts`, la consola de Consumo y las seis
   pestañas del panel de admin. Todo eso existe y funciona. Lo único que falta
   entre eso y un negocio es **la entrada de dinero y el concepto de
   membresía**.

2. **El tope de hoy mide un alcance y financia otro.**
   `partners.companion_monthly_token_cap` hace dos trabajos incompatibles: es el
   cap contra el que se compara la suma de `companion.runs` **y** es la cantidad
   con la que `renew_included_if_expired` recarga un wallet que también gastan
   los turnos de canal de los clientes y las ejecuciones locales. Un partner
   cuyos clientes vacíen el wallet verá `budget` al 20 % y recibirá un 409
   `wallet_empty`. El propio `wallet.py` lo llama deuda **D5**.

3. **El modelo por defecto es el más caro de los tres que vendemos, y no tiene
   precio cargado.** `llm_companion_model = "openai/gpt-5.6-sol"`, y `gpt-5.6-sol`
   entró en la migración `0095` con las cinco columnas de tarifa a NULL. Cada
   turno de teammate desde entonces está medido y **sin valorar**. Los precios
   existen y son públicos: §3.2 de [`research.md`](./research.md).

4. **El pool plano en tokens es 18 veces más caro en un modelo que en otro.**
   Sol cuesta $6,42 por millón de tokens de cuota; Luna, $0,35. Con el pool
   plano y el modelo a elección del partner, el peor caso del plan no está
   acotado por nada que nosotros controlemos.

5. **El recibo mensual no tiene dónde poner esto.** `partner_receipt.py` emite
   comisión, suscripción o inactivo, y **no menciona ni una vez** `PartnerWallet`,
   `UsageLedger`, `UsageRecord` ni la cuota (cero coincidencias en sus 465
   líneas, medido el 2026-09-11). No es que le falte una línea: es que el
   documento que cobramos **no mira el libro que mide**. Es la pieza que un
   cobro nuevo dejaría incompleta sin que salte ningún test.

6. **`billing_plans` existe y describe otra cosa.** Tiene `code`, `name`,
   `monthly_amount_cents` y `active`, y hoy la apunta `tenants.billing_plan_id`:
   es el plan de **un cliente final**, no el de un partner. Reutilizar la tabla
   sin decidir a quién pertenece cada fila es cómo se acaba con dos conceptos en
   una tabla y un `WHERE` que nadie entiende en seis meses.

7. **ADR-022 está aprobado y contradice el modelo.** Decide explícitamente *«nada
   de metered billing: no vendemos por uso»* y un `Subscription Item` por
   cliente final. Un pool semanal con caída a créditos **es** venta por uso.
   Escribir la spec sin enmendar la ADR viola el principio IX.

8. **No hay tope de teammates ni de personas.** `partners.max_clients` limita
   clientes finales. No existe `max_teammates` ni límite de miembros. P4 pide
   exactamente eso, y es columna nueva, no reutilización.

9. **Fiscalidad tomada para otro negocio.** ADR-022 apagó Stripe Tax para un
   canal de dos agencias con inversión del sujeto pasivo. Una membresía de 20
   USD vendible a cualquiera cambia el problema: hay umbrales de registro por
   país y el obligado a remitir sigue siendo el comerciante, no Stripe.

10. **`meter_prices` está a precios provisionales de agosto**, y lo dice su
    propia columna `note`. Seis filas, todas `media.*`. Ítem C2 del plan de
    pendientes, abierto.

## Objetivos

- Un partner puede **pagar** una membresía, ver qué le da y usarla, sin que nadie
  de Auphere toque nada.
- El **pool semanal** existe, se reinicia solo, y **es el mismo número** que
  miran la consola, el panel de admin y la aplicación. Ni uno más.
- Agotado el pool, el trabajo **sigue** con los créditos comprados, y cuando no
  hay créditos **se para y se dice**, con los estados que ya existen.
- El **margen es calculable**: toda tarifa de los modelos que vendemos, cargada
  y fechada; todo turno con `cost_usd` distinto de NULL.
- **Nada desaparece** cuando no se paga: ni un teammate, ni una tarea, ni una
  confirmación pendiente.
- El **cliente final no ve nada de esto**, y hay un test que lo prueba.

## No objetivos

- **La landing.** P6: lo que se construya aquí es la fuente de la verdad.
- **La VM y su reloj.** No existe todavía; lo que sí hace falta es que la unidad
  del pool admita sumarla después sin ser otro contador (§4 de
  [[teammates/08-coste-y-precio]]).
- **El canal de venta directa de ADR-007** (Esencial/Pro/Business 360 al cliente
  final). Esto es la membresía del partner, no el plan del cliente.
- **El cobro al cliente final del partner.** Sigue sin haber Connect y sigue sin
  hacer falta: el partner factura a su cliente por su cuenta.
- **Prorrateo entre monedas.** USD primero; CLP existe en el recibo y se decide
  aparte.
- **SSO, SCIM y marca del partner** (CP-35 a CP-37). Son de Fase 2 y no dependen
  de esto.

## Cómo se sabrá que está resuelto

1. Un partner nuevo entra, elige el plan de 20 USD, paga con tarjeta y **está
   trabajando** sin que nadie de Auphere intervenga.
2. El pool se agota a mitad de semana; el trabajo **continúa** contra los
   créditos comprados sin que la persona tenga que hacer nada, y la pantalla
   dice de qué bolsillo está saliendo.
3. Sin créditos y con el pool agotado, la tarea queda **`en pausa por tope`**,
   las confirmaciones siguen vivas, y la pantalla dice dónde se arregla. (Es el
   camino que la spec 003 ya construyó; aquí solo cambia el motivo.)
4. La consola, el panel de admin y la pantalla Cuenta enseñan el **mismo número**
   del mismo período, y la diferencia entre lo atribuido y el total se explica
   en pantalla — la línea ya existe.
5. Un pago confirmado sube el saldo **una vez**, aunque Stripe reentregue el
   evento cinco veces.
6. Una consulta sobre `usage_records` del mes devuelve `complete = true`: cero
   filas sin valorar para los modelos que vendemos.
7. Una respuesta de cualquier endpoint de cliente final **no menciona** plan,
   pool, saldo ni precio. Con test en `tests/isolation/`.
8. Un impago no borra nada: el teammate sigue en la nómina, la tarea sigue en su
   estado, y el motivo está en pantalla.
