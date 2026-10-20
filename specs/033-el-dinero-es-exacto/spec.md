# Especificación: el dinero es exacto

**Rama**: `033-el-dinero-es-exacto` · **Creada**: 2026-10-18 · **Estado**: Aprobada para plan

**Entrada**: owner, 2026-10-18 — «los datos de contabilidad han tenido fallas al mostrar
lo que los clientes tienen en sus cuentas, y también problemas cuando les recargamos.
Debe ser exacta y perfecta; el dinero es un punto crítico y delicado». Decisiones del
mismo día: los partners recargan saldo (Stripe o Auphere) y lo asignan a sus clientes;
el tope de cada cliente es **mensual de calendario**; los turnos de los clientes gastan
**solo saldo recargado**.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola y panel de operador |
| **Garantías de aislamiento tocadas** | **1** (RLS forzada de `usage_ledger`, `partner_wallets`, `partner_allocations`: toda lectura y escritura nueva fija el GUC del partner del path o de la persona; nunca se levanta la RLS). Barrido: `tests/isolation/test_24_partner_wallet_rls.py` se amplía con la conciliación |
| **Nota de KB que la justifica** | `[[ADR-044-el-dinero-es-exacto]]` · `.specify/bugs/doble-cobro-del-tope/` (dos seguimientos abiertos) |
| **Qué se mide** | Es el medidor. No se gasta nada nuevo |

## Origen

Medido en el código el 2026-10-18 (`develop` = `28a5b562`):

1. **Una recarga se cuenta como gasto.** La recarga del admin escribe un asiento con
   `tenant_id` nulo y `qty` positiva; los tres lectores de gasto suman todo asiento que no
   acabe en `:allocation`, así que cada recarga aparece como «gasto fuera de clientes» en
   el Inicio y el Consumo del partner. Lo mismo las caducidades de crédito.
2. **El admin y la consola hablan en unidades distintas.** El admin enseña créditos y
   recarga «tokens» (por defecto 1000 = US$ 0,01); la consola enseña US$.
3. **La recarga no es atómica ni idempotente.** Abono, asiento y auditoría van en tres
   transacciones; la clave del asiento es un UUID nuevo en cada llamada. Un reintento abona
   dos veces; un fallo a mitad deja saldo sin asiento.
4. **El libro no se puede cuadrar.** Las compras por Stripe no escriben asiento; el
   saldo es una columna que nada contrasta.
5. **Un débito puede perderse.** Si el débito de un turno falla, el consumidor lo registra
   en el log y acusa la entrada del stream igual.
6. **La puerta y el cobro miran bolsillos distintos.** La puerta de un turno abre con
   incluido + comprado; el cobro solo gasta comprado. Con solo incluido, los turnos pasan
   **sin cobrarse** (seguimiento abierto de `doble-cobro-del-tope`).
7. **El «saldo» de un cliente no es dinero.** La consola lite enseña lo que queda del tope
   del cliente aunque el partner no tenga saldo. Y el tope se repone **semanal** mientras
   al lado se enseña el gasto **del mes**.
8. **Las alertas de saldo calculan el % contra un número obsoleto**
   (`companion_monthly_token_cap`): tras una recarga dicen «0 % usado».
9. **El admin llama «coste» a la suma en coma flotante de `messages.cost_usd`**, que es
   nuestro coste, junto a cifras de venta.

## Clarifications

### Session 2026-10-18

- Q: ¿Período del tope por cliente? → A: **Mensual de calendario** (owner). Se repone el día 1.
- Q: ¿Qué bolsillo pagan los turnos de los clientes? → A: **Solo el saldo recargado** (owner). El pool incluido es de Companion y teammates.
- Q: ¿Qué unidad ve una persona? → A: **US$** en todas partes; «créditos» y «tokens» no se enseñan a nadie (owner).
- Q: ¿Qué se concilia? → A: **El saldo recargado**, que es el dinero. El pool incluido es una asignación semanal que se repone entera; no es dinero y no se concilia.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Una recarga es exacta y no se duplica (P1)

Un operador recarga US$ 50 a un partner desde su ficha. Escribe el importe en dólares,
confirma viendo el importe y el saldo resultante, y la recarga queda en el libro con su
nombre. Si pulsa dos veces o la red reintenta, se abona una sola vez.

**Escenarios**:
1. **Dado** un partner con US$ 10, **cuando** el operador recarga US$ 50, **entonces** el saldo es US$ 60 en el admin y en la consola, y el libro tiene un asiento «Recarga de Auphere» de US$ 50.
2. **Dado** la misma recarga enviada dos veces con la misma clave, **cuando** llegan, **entonces** el saldo sube US$ 50 una sola vez y hay un solo asiento y una sola auditoría.
3. **Dado** una recarga, **cuando** el partner abre su Inicio o su Consumo, **entonces** la recarga no aparece como gasto.

### Historia 2 — El libro cuadra (P1)

**Escenarios**:
1. **Dado** cualquier secuencia de recargas (admin y Stripe), débitos y caducidades, **cuando** se concilia, **entonces** saldo recargado = Σ recargas − Σ débitos de recargado − Σ caducidades.
2. **Dado** un partner, **cuando** el operador abre Dinero, **entonces** ve «El libro cuadra» o la diferencia exacta.

### Historia 3 — Lo que ve un cliente es lo que tiene (P1)

**Escenarios**:
1. **Dado** un cliente con tope restante US$ 30 y su partner con US$ 5 de saldo, **cuando** abre su Panel, **entonces** su saldo dice US$ 5.
2. **Dado** el día 1 de un mes, **cuando** pasa el cron, **entonces** el tope del cliente vuelve entero; un tope repuesto ese mes no se repone otra vez.
3. **Dado** un partner con solo pool incluido, **cuando** llega un mensaje a un cliente suyo, **entonces** el turno no se abre (la puerta mira el saldo recargado).

### Historia 4 — Ningún débito se pierde (P1)

**Escenarios**:
1. **Dado** un débito que falla, **cuando** el consumidor procesa la entrada, **entonces** no la acusa; se reintenta y, tras 5 intentos, va al DLQ con error.

### Casos límite

- Libro ilegible: la cifra se pinta como «—» y la pantalla en estado parcial; nunca cero.
- Recarga con importe 0, negativo, con céntimos de más o superior a US$ 10 000: 422.
- Una compra de Stripe notificada dos veces: un solo asiento (clave por sesión de Checkout).

## Requisitos *(obligatorio)*

### Requisito 1 — Una sola unidad visible

1. El admin DEBE mostrar saldos, recargas y asientos en US$ y NO DEBE mostrar créditos.
2. WHEN el operador recarga THEN el sistema DEBE recibir el importe en centavos de US$ y convertirlo con la única conversión de `billing/pricing.py`.

### Requisito 2 — El libro registra cada movimiento de dinero

1. Todo asiento DEBE llevar un tipo: `debit`, `credit_admin`, `credit_stripe`, `expiry` o `allocation_legacy`.
2. WHEN se abona una recarga (admin o Stripe) THEN el sistema DEBE escribir saldo y asiento en la misma transacción.
3. El sistema DEBE contar como gasto solo los asientos `debit`.
4. El sistema DEBE ofrecer la conciliación del saldo recargado de un partner: saldo guardado frente a Σ créditos − Σ débitos de recargado − Σ caducidades.

### Requisito 3 — Recarga atómica e idempotente

1. `POST /admin/partners/{id}/wallet/purchased` DEBE aceptar `amount_cents` (1–1 000 000) y `idempotency_key`, y NO DEBE aceptar campos extra.
2. WHEN llega una clave ya usada para ese partner THEN el sistema DEBE devolver el saldo sin abonar otra vez.
3. Abono, asiento y auditoría (con el operador) DEBEN ir en una transacción.
4. Una compra de Stripe DEBE abonarse con clave `stripe_credit:{sesión}`; una segunda notificación NO DEBE abonar.

### Requisito 4 — Ningún débito se pierde

1. IF el débito de un turno falla THEN el consumidor NO DEBE acusar la entrada.
2. IF una `IntegrityError` no es la del duplicado THEN el débito DEBE fallar, no darse por duplicado.

### Requisito 5 — Puerta y cobro, el mismo bolsillo

1. La puerta de un turno de canal y el estado «sin cupo» DEBEN exigir saldo **recargado** > 0 y tope restante > 0.

### Requisito 6 — El tope del cliente es mensual

1. El tope de un cliente DEBE reponerse una vez por mes de calendario (UTC), y NO DEBE reponerse con el pool semanal.
2. El saldo que ve un cliente DEBE ser `min(tope restante, saldo recargado del partner)`.

### Requisito 7 — Alertas y admin honestos

1. El % usado de las alertas de saldo DEBE calcularse sobre el gasto del período y el saldo, no sobre `companion_monthly_token_cap`.
2. El uso por partner en el admin DEBE mostrar el gasto del libro en US$ y, aparte, el coste de Auphere calculado en decimal.
3. `PUT /console/clients/{ref}/allocation` DEBE escribir auditoría con la persona.

### Entidades clave

- **Asiento (`usage_ledger`)**: partner (RLS FORCE por `partner_id`), cliente opcional, cantidad positiva, bolsillo, **tipo** nuevo, clave única.
- **Tope del cliente (`partner_allocations`)**: gana el **mes** al que corresponde su reposición.

## Criterios de éxito

- **CE-001**: tras 1 000 movimientos aleatorios de todos los tipos, el libro cuadra al crédito.
- **CE-002**: la misma recarga enviada 5 veces abona una vez.
- **CE-003**: el saldo y el gasto del mes de un cliente coinciden al centavo en admin, consola del partner y consola lite.

## Fuera de alcance

- Conciliar el pool incluido — es una asignación semanal, no dinero.
- Cambiar qué significa mover tope entre clientes: el tope es un límite de gasto, no dinero; el dinero lo vigila la puerta en cada turno.
- Facturación fiscal — sigue siendo precondición de `docs/billing.md`.
