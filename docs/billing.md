# Cómo se cobra, y qué hay que configurar para que funcione

**Spec**: `specs/005-membresias-y-cobro/` · **ADR**: `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`
**Estado**: Historia 1 implementada (contratar un nivel). El resto, en curso.

---

## El reparto, en una frase

**El proveedor cobra; el libro decide.** Stripe mueve dinero y nos avisa. Quién
puede gastar y cuánto lo dice `partner_wallets`, que es nuestro. Esa separación
es ADR-037 D3 y es la que hace que una caída del proveedor no apague a ningún
agente — y que cambiar de cuenta de Stripe no toque el saldo de nadie.

## Las dos vías de dinero

| | Qué es | Dónde cae |
|---|---|---|
| **Suscripción** | El nivel: Free · Pro · Team · Business | `partner_subscriptions` + el pool semanal del partner |
| **Crédito** | Compra de una vez, a 10 $ por millón de unidades | `partner_wallets.purchased_remaining` |

Las dos por página alojada del proveedor. **Ningún dato de tarjeta entra aquí**,
ni en base de datos ni en logs, y hay un test de aislamiento que lo vigila.

## Lo que se publica de cada nivel, y lo que no

La pantalla de planes enseña **los topes** —cuántos agentes, cuántas personas—
y un **múltiplo de consumo** («4× el de Pro»). **Nunca el tamaño del pool.**

Las cifras son provisionales (ADR-037) y van a ajustarse. Publicarlas
convertiría cada ajuste de capacidad en un recorte o un regalo visible, que es
justo lo que la Spec A R7.3 prohíbe en la pantalla de consumo y que no deja de
ser cierto en la de planes. Ninguno de los seis referentes del mercado publica
el número de tokens de su plan.

El múltiplo **se calcula** desde `weekly_pool_tokens`. No se guarda a propósito:
una columna habría que acordarse de actualizarla, y el día que se olvide la
pantalla mentiría.

---

## Configuración de la cuenta del proveedor

**Esto no es opcional y no se puede automatizar.** Tres de las cuatro cosas de
abajo no se exponen por API; la aplicación avisa al arrancar y alguien tiene
que mirarlas.

| Ajuste | Por qué, y qué pasa si falta |
|---|---|
| Tras agotar reintentos, la suscripción va a **`unpaid`** | Stripe lo pone **solo si el panel lo dice** (verificado 2026-09-12). Con el valor de fábrica un impago salta de `past_due` a `canceled` y **el escalón intermedio de la escalera no ocurre nunca** |
| **Smart Retries** encendido | Es la escalera de reintentos. Sin ella no hay reintentos que agotar |
| **Días de aviso de renovación** | Dispara `invoice.upcoming`, que es con lo que se avisa **antes** de degradar |
| El **endpoint de webhook** registrado, con los eventos de `contracts/webhook.md` | Sin él no llega nada |

### El catálogo de precios

Lo crea un script idempotente, y **lo ejecuta una persona con las claves**:

```bash
BILLING_API_KEY=sk_test_... uv run python scripts/sync_billing_catalog.py --dry-run
```

```bash
BILLING_API_KEY=sk_test_... uv run python scripts/sync_billing_catalog.py --apply
```

Idempotente por la clave del nivel, que viaja en `metadata.tier_code`.
Ejecutarlo dos veces no duplica precios. Vive fuera de `apps/` a propósito: un
comando de la API lo dejaría a un `POST` de crear precios en producción.

Al terminar imprime los `UPDATE` que escriben los `stripe_price_id` en
`membership_tiers`.

---

## Las dos averías silenciosas

Las dos dejan de facturar **sin ningún síntoma**. Conviene conocerlas.

### 1 · No responder a `invoice.created` congela la facturación 72 horas

> Si Stripe no recibe una respuesta correcta a `invoice.created`, retrasa la
> finalización de **todas** las facturas con cobro automático hasta 72 horas.

De **todos** los partners, no solo del evento. Y el castigo es de la cuenta
entera: *«includes handling all webhook endpoints configured for your
account»*. Por eso **no estamos suscritos a ese evento** —no lo necesitamos, el
dinero llega con `invoice.paid`— y hay un test que comprueba que sigue fuera.

Si la cuenta tuviera otra integración con un endpoint roto, nos afectaría
igual. Merece mirarlo al arrancar con una cuenta que no es solo nuestra.

### 2 · Una factura que no finaliza es cobertura sin cobro

> *Subscriptions remain active if invoices can't be finalized, which means that
> users may still be able to access your product while you're not able to
> collect payments.*

La suscripción sigue activa, el partner trabaja con normalidad, y no se cobra
nada. Estamos suscritos a `invoice.finalization_failed` y el manejador
**alerta al operador sin degradar al partner** — no es culpa suya. La causa más
probable el día que se encienda Stripe Tax es
`automatic_tax.status = requires_location_inputs`.

---

## Cambiar de cuenta de Stripe

La cuenta es de **Andrés Matos**, socio de Auphere, mientras se completa el
registro fiscal de la empresa. Se cobra de verdad con ella y se migrará.

**Stripe no traspasa clientes ni suscripciones entre cuentas: se recrean**, y
cada partner vuelve a introducir su tarjeta. Lo que **no** se pierde es el
saldo, porque el libro es nuestro.

El procedimiento entero está en
[`specs/005-membresias-y-cobro/runbook-migracion-cuenta.md`](../specs/005-membresias-y-cobro/runbook-migracion-cuenta.md).
Lo que más importa de él: **no canceles las suscripciones en Stripe hasta que
la cuenta nueva haya cobrado un ciclo completo.** Nuestro estado se revierte con
un `UPDATE`; el de Stripe, no.

---

## Precondición de despliegue: el tratamiento fiscal

Se puede construir y probar todo esto sin resolverlo. **Lo que no se puede es
cobrarle a alguien.** ADR-022 apagó los impuestos para un canal de dos agencias
con inversión del sujeto pasivo; una membresía de 20 $ vendible a cualquiera es
otro problema — B2C posible, IVA europeo y ventanilla única, IVA chileno.

Es asesoría, no ingeniería, y bloquea el primer cobro real.
