# Cómo se cobra, y qué hay que configurar para que funcione

**Spec**: `specs/005-membresias-y-cobro/` · **ADR**: `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`
**Estado**: las cinco historias implementadas (115 tareas). Claves aprovisionadas
en **staging** (2026-09-13); en **producción, no** — ver «Las cuatro claves» abajo.

---

> **Estado desde el 2026-10-18 (spec 034): las membresías están apagadas.** Los
> niveles Free/Pro/Team/Business son del **Teammate** y vuelven con él. Con
> `NEXUS_MEMBERSHIP_ENABLED` sin definir (el defecto, `false`): no hay topes de
> teammates ni de personas, el pool semanal se repone sin mirar la suscripción, los
> endpoints de planes, portal y cancelación responden 404 y los avisos de suscripción
> del proveedor se registran sin efecto. **Siguen vivos** la compra de crédito
> (`POST /console/billing/credit`) y los recibos. Y con o sin el interruptor, solo una
> sesión de Checkout `mode=payment` con `metadata.kind=credit` abona saldo. Lo que
> sigue describe la spec 005 tal como funciona con el interruptor encendido.

> **Desde la spec 033 (2026-10-18) el libro tiene tipos y cuadra.** Cada asiento de
> `usage_ledger` dice qué es (`debit`, `credit_admin`, `credit_stripe`, `expiry`,
> `opening_credit|opening_debit`, `allocation_legacy`) y el gasto es solo `debit`. Toda
> recarga — del panel de Auphere en US$ o por Stripe — es una transacción idempotente:
> saldo, asiento y auditoría juntos, con clave del formulario o de la sesión de
> Checkout. El panel concilia el saldo recargado con el libro
> (`GET /admin/partners/{id}/wallet/reconcile`); la migración 0158 dejó la diferencia
> histórica como asiento de apertura. Los turnos de los clientes se abren y se cobran
> con **saldo recargado**; el pool semanal es de Companion y teammates. El tope por
> cliente se repone **una vez por mes de calendario** y lo que ve un cliente como saldo
> nunca supera el recargado de su partner.

## Pagos del partner fuera de Stripe (2026-10-20)

- **Quien paga es el partner**, no su cliente. Los pagos por transferencia, cripto u otro medio se anotan en el Admin, en **Partners → el partner → Facturas → «Pagos recibidos fuera de Stripe»**, eligiendo el cliente y el mes que cubren.
- **Anotar un pago suma su importe al saldo recargado del partner**, una vez, con un asiento `credit_manual` (clave `tenant_payment:<id>`) y auditoría `wallet.admin_purchased` a nombre del operador.
- **Anular un pago descuenta ese abono** (`credit_reversal`, auditoría `wallet.payment_reversed`). Si el partner ya gastó ese saldo, la anulación se rechaza: el saldo nunca queda en negativo por una corrección.
- No sube el tope de ningún cliente: el partner reparte el saldo desde su consola.
- Los pagos anotados antes de este cambio quedan como registro, sin abono (decisión del owner).
- Un cliente directo de Auphere (sin partner) se sigue anotando en su ficha y no abona nada.

## Tarjeta guardada, recarga automática y pospago (spec 041)

- **Tarjeta.** El partner guarda su tarjeta en la página de Stripe (Checkout `mode=setup`) desde Facturación. Auphere guarda solo ids, marca, últimos 4 y caducidad (`partner_billing`).
- **Cómo se cobra.** El partner elige entre tres modos:
  - **Manual**: compra saldo a mano, como siempre.
  - **Recarga automática**: si el saldo baja de un mínimo, se cobra una cantidad fija (mínimo US$5) y se abona.
  - **Pospago**: solo con la línea de crédito que concede Auphere desde el panel (`partner_wallets.credit_limit`). El saldo puede bajar hasta menos esa línea (CHECK en la base). El día 1, hora de Madrid, se cobra la deuda y el saldo vuelve a cero.
- **Cada cobro es una factura de Stripe** (`collection_method=charge_automatically`, pagada fuera de sesión).
  - El saldo sube una sola vez por factura, con `credit_stripe` y la clave `stripe_invoice:<id>`. Da igual que se abone al pagar o al llegar `invoice.paid`.
  - Los cobros quedan en `partner_charges`, con una clave única por intento.
- **Rechazos.** Tres seguidos paran los cobros automáticos hasta que el partner cambie la tarjeta. La factura de cada intento rechazado se anula en Stripe, y un rechazo cuenta una vez aunque llegue también `invoice.payment_failed`.
- **Facturas.** Cada cobro guarda el id de su factura de Stripe, también si se rechaza. «Ver factura» (consola y Admin) pide a Stripe la página de la factura en cada clic; un cobro anterior sin id se busca por `metadata.charge_id`.
- **3D Secure.** Si el banco pide confirmar (`authentication_required`), el cobro queda en `action_required` y no cuenta como rechazo.
  - Se guarda el enlace de la factura (`action_url`), se envía al correo de facturación (o al de contacto) y sale en Facturación con «Confirmar el pago».
  - Mientras espera no se abre otra recarga. `invoice.paid` lo liquida.
  - Si el aviso se pierde, cada pasada del cron pregunta a Stripe por los cobros en espera y liquida los ya pagados (`refresh_waiting_charges`), por el mismo camino y sin abonar dos veces.
- **Pospago sin cobrar.** Si el cobro del pospago falla o espera confirmación, la línea se congela en lo que ya se debe (`credit_frozen_at`).
  - La línea concedida queda en `granted_credit_limit` y vuelve al pagarse.
  - Se reintenta como mucho una vez al día (clave `postpaid:{partner}:{mes}:{día}`).
  - El Panel del Admin lo avisa como «línea de pospago congelada».
- **Correo de facturación.** Lo edita el propio partner en Facturación (permiso `billing:manage`, auditado como `console.billing.email_update`) o Auphere desde el Admin. Vacío, los avisos van al correo de contacto. Ahí llega el aviso de 3D Secure.
- **Sin claves de Stripe** no se cobra ni se registra nada.
- **Cron.** `partner-charges-cron` en el worker: recargas cada 5 minutos, pospago el día 1 y reintento diario si la línea está congelada.
- **Objetos de Stripe.** Desde stripe-python 13 no son `dict`: se leen con `billing.provider.field`, nunca con `.get` (así se perdieron en staging una compra de saldo y una recarga pagada, 2026-10-20).
- **Webhook.** Usa los eventos que ya estaban suscritos: `checkout.session.completed`, `invoice.paid` e `invoice.payment_failed`. Las facturas de estos cobros se procesan aunque las membresías estén apagadas.

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

## Qué vale una unidad de cuota

**Spec**: `specs/007-pesos-de-cuota-por-carril/` · **Contrato**:
[`quota-unit-v2.md`](../specs/007-pesos-de-cuota-por-carril/contracts/quota-unit-v2.md)

La unidad que come el tope se deriva de los tokens nativos con **un peso por
carril**, no con uno por modelo:

```
cuota = redondeo( entrada_no_cacheada x w_in
                + lectura_de_caché    x w_cache
                + salida              x w_out )
```

Los tres pesos viven en `model_profiles` (columnas `quota_weight_*`) y se
derivan de la tarifa de **su propio carril**:

```
w_carril = 2,2 x price_carril_per_mtok / 10
```

- **2,2x es el objetivo**: margen del **54,5 %**, el mismo en los tres carriles
  de todos los modelos. Por eso **el margen no depende de la mezcla** de trabajo
  que haga el partner — que es la propiedad entera.
- **1,50x es el suelo**: nunca por debajo, en ningún carril y en ningún modelo,
  **nunca en promedio**. Lo vigila
  `tests/integration/test_quota_floor.py`, que lee el **catálogo real de la
  base** y no una lista escrita en el test.

**Los tres o ninguno.** `NULL` en los tres significa «este modelo no se sirve por
el carril de cuota de LLM» —`openai/whisper-1` los tiene a NULL y sigue
funcionando por minutos—, y un modelo con dos pesos y uno nulo lo rechaza un
`CHECK` del esquema y `weights_for` en el código.

**Si alguien cambia una tarifa y olvida el peso**, `weight_drift` lo detecta al
cargar el catálogo y lo registra con el modelo y el carril, distinguiendo la
divergencia que sigue sobre el suelo de la que lo cruza. No bloquea el arranque:
una divergencia no puede tumbar la plataforma, pero tampoco puede ser invisible.

> **Un cambio de pesos no revalora nada.** La unidad no cambia de definición,
> cambia su tasa de conversión desde los tokens nativos. Un millón de unidades
> sigue siendo un millón; lo que cambia es cuánto trabajo compra. Por eso el
> despliegue es reversible por revert.

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

### El script: catálogo, webhook y portal

Lo ejecuta **una persona con las claves**, una vez por entorno:

| Entorno | Modo de Stripe | Webhook | Consola |
|---|---|---|---|
| **staging** | test (`sk_test_`) | `api.staging.auphere.com/webhook/billing` | `console.staging.auphere.com` |
| **prod** | live (`sk_live_`) | `api.auphere.com/webhook/billing` | `console.auphere.com` |

```bash
BILLING_API_KEY=sk_test_... uv run --project apps/api python scripts/sync_billing_catalog.py --env staging --dry-run
```

```bash
BILLING_API_KEY=sk_test_... uv run --project apps/api python scripts/sync_billing_catalog.py --env staging --apply
```

Para producción, lo mismo con `--env prod` y la clave `sk_live_`. Pide escribir
«prod» antes de aplicar.

> **La guardia que importa.** `--env` es obligatorio y el script **se niega a
> correr si la clave y el entorno no se corresponden**. El cruce caro es una
> clave *live* contra staging: apuntaría el webhook de producción al entorno de
> pruebas, los cobros reales aterrizarían allí y se aplicarían contra una base
> de datos que no es la de los clientes. Dinero cobrado que no acredita a
> nadie, y sin ningún error a la vista.

Crea tres cosas, todas idempotentes:

1. **Los precios**, reconocidos por `metadata.tier_code` y no por su nombre
   visible — que es texto comercial y cambia.
2. **El webhook**, idempotente por URL, con exactamente los eventos que la API
   maneja. La lista está sincronizada con `HANDLED_EVENTS` por un test que
   falla si divergen, y **`invoice.created` no está** (ver la mina de abajo).
3. **El portal del cliente**: tarjeta, facturas y baja a fin de período.
   Cambiar de plan está **deshabilitado** a propósito — sería una segunda vía
   que salta nuestros topes, y el `409` que impide bajar por debajo del uso
   vive en nuestra API.

Al terminar imprime los `UPDATE` de `stripe_price_id`, el
`NEXUS_BILLING_WEBHOOK_SECRET` **en tu terminal y en ningún otro sitio**
(Stripe solo lo revela al crear el endpoint), y la lista de lo que queda a
mano.

> **Los `stripe_price_id` son por entorno.** Modo test y modo live son
> catálogos distintos dentro de la misma cuenta: los ids de staging no sirven
> en producción. Cada uno va a la base de datos de su entorno.

Vive fuera de `apps/` a propósito: un comando de la API lo dejaría a un `POST`
de crear precios en producción.

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

## La escalera de impago, en una tabla

| Estado | ¿Repone el pool? | ¿Gasta crédito comprado? | Aviso |
|---|:--:|:--:|---|
| Al corriente | Sí | Sí | — |
| Pago fallido | **No** | Sí | `billing.payment_failed` |
| Impagada | **No** | Sí | `billing.unpaid` |
| Cancelada | **No** | Sí, 12 meses | `billing.canceled` |

**El único efecto de los cuatro estados es si el pool se repone.** Ni un
teammate se archiva, ni una tarea se cancela, ni una confirmación pendiente se
invalida, ni se borra una conversación. Un impago es un problema de
facturación; el trabajo de alguien no se toca por eso.

El primer escalón **no degrada nada** a propósito: abre la ventana entre el
aviso y el efecto que R5.6 pide.

### La caducidad del crédito

`purchased_expires_at` es **`NULL` mientras la cuenta vive**. Esa es la
invariante «el crédito comprado no caduca mientras la cuenta viva» escrita de
forma que no se puede violar por accidente: no hay fecha que comparar.

Al cancelar se pone a doce meses; al volver, a `NULL` otra vez, sin que nadie
reponga nada a mano. El cron `expire-credit-cron` corre a diario y **deja
asiento en `usage_ledger`** con la clave `credit_expired:<partner>:<fecha>` —
que además es lo que impide que un tick repetido descuente dos veces.

> Esto **resta** saldo, que es lo que D3 prohíbe a los avisos externos. No lo
> contradice: lo decide una regla nuestra, con fecha nuestra, y deja apunte. La
> diferencia es quién decide.

---

## Cambiar de plan: quién hace qué

| | Quién lo hace | Cómo |
|---|---|---|
| **Prorratear el dinero al subir** | **Stripe** | `proration_behavior='create_prorations'` sobre la suscripción viva |
| **Programar la bajada** | **Stripe** | *Subscription Schedule* con `proration_behavior='none'` |
| **Completar el pool de la semana** | Nosotros | Es nuestro libro; el proveedor no sabe qué es |

Calcular los días de un ciclo por nuestra cuenta sería reimplementar —peor—
algo que el proveedor ya hace, y que además tiene que **coincidir con lo que el
partner lee en su factura**. Dos respuestas a la misma pregunta es como empieza
una disputa de facturación.

**Subir es inmediato y no abre página de pago**: quien ya paga no tiene que
volver a introducir su tarjeta para subir de plan. **Bajar espera a fin de
período** y no reclama el pool en curso — esa semana ya está pagada.

Al completar el pool se suma **la diferencia de tamaño**, no el tamaño nuevo:
reiniciar regalaría lo ya consumido, y no tocarlo cobraría el nivel nuevo sin
darlo.

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

## Los dos documentos

| | Qué es | Quién lo emite |
|---|---|---|
| **Factura** | El **documento fiscal** | El proveedor |
| **Recibo** | Lo que el proveedor no sabe: desglose por cliente y la conversión de las comisiones desde CLP | Nosotros |

El recibo dejó de decir «total a pagar» y de llevar vencimiento. Dejarlo en los
dos pide pagar dos veces — y aunque nadie pague dos veces, obliga a averiguar
cuál de los dos era el bueno.

Se llega a las facturas desde la consola, por el portal del proveedor. No se
construye una pantalla de facturas propia: traería datos de pago a nuestra
infraestructura y duplicaría un documento que ya existe, con el riesgo de que
las dos versiones dejen de coincidir.

---

## Las cuatro claves, y por qué el orden importa

Nada de esto funciona en un entorno desplegado hasta que existan cuatro claves.
Están en `nexus/staging/app`; en `nexus/prod/app` no:

| Clave | staging | producción |
|---|---|---|
| `NEXUS_CONSOLE_BASE_URL` | `https://console.staging.auphere.com` | `https://console.auphere.com` |
| `NEXUS_BILLING_API_KEY` | `sk_test_…` | `sk_live_…` |
| `NEXUS_BILLING_PUBLIC_KEY` | `pk_test_…` | `pk_live_…` |
| `NEXUS_BILLING_WEBHOOK_SECRET` | `whsec_…` de test | `whsec_…` de live |

Las tres de `BILLING` van juntas o no van: `billing_enabled` es todo o nada, así
que con dos de tres las rutas de cobro responden `503 billing_unavailable` y el
despliegue miente sin dar un solo error.

`NEXUS_CONSOLE_BASE_URL` es a donde el proveedor devuelve al partner después de
pagar. Sin ella el cobro se completa —el webhook es servidor a servidor— y el
acuse aterriza en un `localhost`. En producción el guard de `config.py` se niega
a arrancar antes de dejar que eso pase; **en staging solo avisa.**

El orden no se negocia —**secreto primero, Terraform después**— porque una
definición de tarea que pide una clave ausente del secreto no arranca. La
secuencia completa, con los dos entornos y la app de escritorio, está en
[`go-live-consola-y-teammates.md`](go-live-consola-y-teammates.md).

---

## Precondición de despliegue: el tratamiento fiscal

Se puede construir y probar todo esto sin resolverlo. **Lo que no se puede es
cobrarle a alguien.** ADR-022 apagó los impuestos para un canal de dos agencias
con inversión del sujeto pasivo; una membresía de 20 $ vendible a cualquiera es
otro problema — B2C posible, IVA europeo y ventanilla única, IVA chileno.

Es asesoría, no ingeniería, y bloquea el primer cobro real.
