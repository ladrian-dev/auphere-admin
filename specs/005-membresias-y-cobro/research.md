# Fase 0 · Investigación y decisiones de diseño

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Fecha**: 2026-09-12

Ocho decisiones. Las tres primeras eligen el proveedor y dónde vive; las
tres siguientes son el diseño del cobro; las dos últimas son las que hacen que
la cuenta de Stripe pueda cambiar de dueño sin drama.

Todo lo que se afirma aquí sobre el comportamiento de Stripe está **verificado
el 2026-09-12** contra su documentación oficial, con la página citada. Lo que no
se pudo verificar se dice que no se pudo.

---

## D1 · El proveedor es Stripe, y la dependencia es `stripe` de PyPI

**Decisión**: Stripe, integrado con la biblioteca oficial `stripe` (PyPI),
**15.6.1**, publicada el **2026-09-01**.

**Por qué Stripe y no otro**: la evaluación
(`.specify/assessments/membresias-y-consumo-stripe/research.md` §4) ya comparó
las opciones. Lo que decide no es el precio —las comisiones son comparables—
sino tres cosas concretas de esta spec:

1. **Página de pago alojada** con suscripción y pago único en el mismo objeto,
   lo que deja el dato de tarjeta enteramente fuera de nuestra infraestructura.
2. **Escalera de impago configurable** (reintentos, correos, qué pasa al final),
   que es exactamente D6 de ADR-037 y que si no la trae hay que escribirla.
3. **Relojes de prueba**: permiten avanzar un cliente un mes en un test de
   integración. Sin eso, los criterios de R5 son inverificables hasta que un
   cliente real deje de pagar, que es el peor momento para descubrir un fallo.

Y una razón de continuidad: **ADR-022 ya eligió Stripe** para el canal de
agencias, y sus §13–§15 —el diseño del webhook— **se conservan**. Cambiar de
proveedor aquí obligaría a reescribir lo que ya está razonado.

**La licencia, leída entera** (§VIII). `stripe-python` se distribuye bajo
**MIT**. El texto del `LICENSE` del paquete:

> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software […]

MIT no alcanza el uso en red, no impone reciprocidad y no restringe el uso
multi-tenant. **Es un sí.** `tests/unit/test_no_new_dependencies.py` vigila la
lista: añadirla exige tocar su BASELINE en el mismo commit que este párrafo.

**Lo que se rechazó**:

| Alternativa | Por qué no |
|---|---|
| Hablar con la API REST a pelo, sin biblioteca | Ahorra una dependencia MIT y **cuesta** la verificación de firma del webhook, que es criptografía que no conviene escribir a mano. Mal negocio |
| Paddle / Lemon Squeezy (merchant of record) | Resolverían el problema fiscal asumiendo ellos la obligación —que es real y está abierto—, pero su comisión es del orden del 5 % + fijo contra el ~2,9 % de Stripe, y **el margen del nivel de 20 $ ya es lo que más aprieta**. Se anota como opción si la asesoría fiscal lo aconseja |

---

## D2 · Todo lo del proveedor vive detrás de una frontera, en `billing/`

**Decisión**: un paquete `nexus_api.billing` con el cliente del proveedor
aislado, y **ningún `import stripe` fuera de él**.

**Por qué**: la migración de cuenta es un hecho comprometido, no una hipótesis.
Un cambio de cuenta toca claves, catálogo y clientes; si `stripe` está importado
en ocho módulos, ese cambio se convierte en una excavación. Con una frontera, el
resto del código conoce «una suscripción» y «una compra».

**Cómo se vigila**: un test estructural, al estilo de los que ya existen en
`tests/unit/`, que recorre `src/` y **falla si aparece `import stripe` fuera de
`nexus_api/billing/`**. Una regla que no se comprueba deja de existir en dos
meses.

---

## D3 · La conciliación va en una sola dirección: lo de fuera suma, nunca resta

**Decisión**: **ningún** camino que arranque en un aviso del proveedor puede
disminuir `included_remaining` ni `purchased_remaining`. El webhook solo llama a
`add_purchased`, y la única resta del sistema sigue siendo `debit_wallet` desde
el camino del turno.

**Por qué, y esto es lo importante**: un aviso externo que pudiera restar
convierte cualquier fallo del proveedor —un evento duplicado leído al revés, un
reembolso mal interpretado, un evento de prueba que llega a producción— en
**saldo que desaparece de la cuenta de un cliente**. Sumar de más es un error
que se ve, se explica y se corrige. Restar de más es dinero que el cliente pagó
y ya no tiene, y lo descubre cuando su agente se calla.

**Consecuencia incómoda que se acepta**: un reembolso **no** retira crédito
automáticamente. Queda como decisión de un operador, con rastro. Es
deliberadamente manual: es raro, y el coste de automatizarlo mal es el que
acabamos de describir.

**Reutilización verificada**: `add_purchased(partner_id, qty)` en
`metering/wallet.py` ya suma al cubo comprado, es idempotente por fila y está
probado. El webhook no escribe SQL nuevo: llama a lo que ya existe.

---

## D4 · El webhook: firma, registro, encolar, 200 — y la mina de las 72 horas

**Decisión**: se conserva íntegro el diseño de ADR-022 §13–§15.

```text
POST /webhooks/billing
  1. leer el cuerpo EN CRUDO (bytes, sin parsear)
  2. verificar la firma con el secreto del endpoint  → 400 si falla
  3. INSERT del evento por su id  → si ya existía, responder 200 y parar
  4. encolar el trabajo
  5. responder 200
```

Cuatro cosas que no son estilo:

**(a) El cuerpo en crudo.** La firma se calcula sobre los bytes exactos. Si el
framework parsea y vuelve a serializar, la firma deja de validar por un espacio.

**(b) El registro ANTES de actuar.** El `INSERT` con restricción única sobre el
identificador de evento es lo que hace la idempotencia real: el quinto reenvío
del mismo pago choca contra la restricción y no acredita nada. La idempotencia
no se delega al trabajo de fondo, se decide en la puerta.

**(c) No se confía en el cuerpo, se recupera el objeto.** El cuerpo dice qué
pasó; **el importe y el estado se leen de la API del proveedor**. Stripe lo pide
porque el cuerpo puede estar obsoleto; el principio III lo pide porque lo que
llega de fuera es dato, no instrucción. Coinciden.

**(d) Responder rápido y trabajar aparte.** No es una meta de rendimiento: el
proveedor **espera hasta 10 segundos** nuestra respuesta a
`checkout.session.completed` antes de redirigir al cliente a la página de
gracias.

### La mina

Verificado el 2026-09-12 en la documentación oficial de Stripe sobre webhooks:

> **Si el endpoint no responde correctamente a `invoice.created`, Stripe retrasa
> la finalización de *todas* las facturas con cobro automático hasta 72 horas.**

No las de ese partner: **todas**. Y el sistema no se cae — simplemente deja de
facturar, en silencio, durante tres días.

**Cómo se contiene**:

1. **No suscribirse a `invoice.created`.** No lo necesitamos: el acceso se
   concede con `invoice.paid`. Un evento al que no se está suscrito no espera
   respuesta.
2. Si algún día hiciera falta, el manejador responde 200 **inmediatamente** y
   hace el trabajo aparte, sin excepción.
3. Una alerta en el panel de operador cuando el registro de eventos lleva un
   número anómalo de fallos: es la señal temprana de esta avería.

### Los eventos a los que sí nos suscribimos

| Evento | Qué hacemos | Por qué ese y no otro |
|---|---|---|
| `invoice.paid` | Conceder o renovar el acceso al nivel | Es el momento en que hay dinero. Verificado: **el acceso se concede cuando la suscripción está `active`** |
| `invoice.payment_failed` | Primer escalón de la escalera | Es lo que abre el período de reintentos |
| `customer.subscription.updated` | Reflejar el estado y el nivel | Cubre el cambio de plan y los cambios de estado del proveedor |
| `customer.subscription.deleted` | Último escalón: cancelada | El fin del ciclo de vida |
| `checkout.session.completed` | **Acreditar el crédito comprado** | Es el evento de la compra de una vez |
| `checkout.session.async_payment_succeeded` | Acreditar, igual que el anterior | Métodos de pago diferidos. Sin este, una compra válida no acredita nunca |

**Regla verificada para los dos últimos**: hay que comprobar
`payment_status != 'unpaid'` antes de cumplir, y **el cumplimiento debe ser
idempotente** porque los dos eventos pueden llegar para la misma sesión. Nuestro
`INSERT` por identificador de evento no basta ahí —son eventos distintos— así
que la idempotencia se ancla además en **el identificador de la sesión**.

**Reintentos**: en modo real Stripe reintenta hasta **3 días** con espera
creciente. Un fallo transitorio se recupera solo; no hay que construir cola de
reproceso.

---

## D5 · Que la cuenta de Stripe pueda cambiar de dueño

**Contexto**: la cuenta es de **Andrés Matos**, socio de Auphere, mientras se
completa el registro fiscal de la empresa. Se cobra de verdad con ella. Se
migrará.

**El hecho duro, verificado**: **Stripe no traspasa clientes, suscripciones ni
métodos de pago entre cuentas.** Los datos de tarjeta pueden migrarse por un
proceso asistido por Stripe entre cuentas que cumplen PCI, pero las
suscripciones no se mueven: se recrean. En la práctica, **cada partner vuelve a
pasar por la página de pago**.

**Tres decisiones que abaratan eso**:

### 1. Ningún identificador del proveedor es clave de nada nuestro

`stripe_customer_id`, `stripe_subscription_id`, `stripe_price_id` son **columnas
de referencia, anulables, sin clave foránea y sin unicidad global**. Nada las
usa para buscar un partner salvo el propio webhook, y ahí se resuelven a nuestro
identificador en el primer paso.

**Qué compra esto**: migrar es `UPDATE`, no reconstruir. Poner los tres a `NULL`
deja el sistema en un estado válido: el partner conserva su nivel, su pool y su
saldo, y lo único que le falta es una suscripción activa en la cuenta nueva.

### 2. El mapeo nivel → precio es una tabla, no un literal

`membership_tiers` lleva `stripe_price_id` como **una columna más**. Los niveles
se identifican por su clave nuestra (`free`, `pro`, `team`, `business`).
Recrear el catálogo en la cuenta nueva es actualizar cuatro filas.

### 3. El catálogo se crea con un script idempotente parametrizado por cuenta

`scripts/sync_billing_catalog.py`, ejecutado por **Luis con sus claves**.
Idempotente por la clave del nivel: ejecutarlo dos veces no duplica precios.
Fuera de `apps/` a propósito, para que no se pueda disparar desde la API.

### La ventaja que ya está ganada, y conviene decirla

**Migrar de cuenta no toca el saldo de ningún partner.** El libro es nuestro
(ADR-037 D3): `included_remaining` y `purchased_remaining` viven en nuestra base
de datos. Se pierde el método de pago y la suscripción; **el crédito comprado se
queda donde está**.

Si el proveedor fuera la fuente de verdad del saldo —que es lo que habrían hecho
los *credit grants* de Stripe— esta migración sería una reconstrucción contable
cliente por cliente. Es un argumento retrospectivo a favor de D3 que no teníamos
cuando se decidió.

El procedimiento completo está en
[runbook-migracion-cuenta.md](./runbook-migracion-cuenta.md).

---

## D6 · La escalera de impago: cuatro estados nuestros, un mapeo explícito

**Decisión**: `partner_subscriptions.state` con cuatro valores —
`current` → `payment_failed` → `unpaid` → `canceled` — y un mapeo **explícito y
exhaustivo** desde los estados del proveedor.

**Por qué no reutilizar `partners.status`**: verificado en el repositorio, solo
admite `'active' | 'suspended'` y **significa otra cosa**: si el partner está
operativo. Un partner impagado **sigue estando operativo** para leer su
historia, y meterlo en `suspended` lo apagaría entero.

**El mapeo**, desde los estados de suscripción de Stripe verificados el
2026-09-12 (`trialing`, `active`, `incomplete`, `incomplete_expired`,
`past_due`, `unpaid`, `canceled`, `paused`):

| Estado del proveedor | El nuestro | Qué significa para el partner |
|---|---|---|
| `trialing`, `active` | `current` | Todo normal |
| `past_due` | `payment_failed` | Un cobro falló y se está reintentando. **Nada cambia todavía** |
| `unpaid` | `unpaid` | Se agotaron los reintentos. **Se pausa el consumo del pool**; el crédito comprado sigue gastándose |
| `canceled`, `incomplete_expired` | `canceled` | Fin. El pool se apaga; el crédito comprado vive 12 meses |
| `incomplete` | `current` | Aún no hubo primer pago. El nivel no está concedido, así que no hay nada que degradar |
| `paused` | `unpaid` | No lo usamos, pero **el mapeo no puede tener agujeros** |

**Un estado que no esté en la tabla hace fallar el manejador** y deja el estado
anterior intacto. Por defecto no se cae en `current`: un estado desconocido que
se lea como «al corriente» es acceso regalado, y silencioso.

**Lo que la escalera NO hace, y es la mitad del diseño** (§IV, «borrar no
existe»):

- No se archiva ningún teammate.
- No se cancela ninguna tarea.
- **Ninguna confirmación pendiente se pierde**, y una pendiente se puede
  responder sin saldo — esto ya estaba resuelto en la spec 003 R9.3, y la Spec A
  encontró y arregló el `_require_wallet` que lo rompía. No se vuelve a romper.
- No se borra ni una conversación. Todo se puede leer.

Lo único que la escalera hace es **pausar el consumo del pool**, reutilizando el
estado «en pausa por tope» que la spec 003 ya tiene en pantalla.

---

## D7 · Prorrateo: subir completa, bajar espera, y el crédito no se toca

**Decisión** (ADR-037 D7, se implementa tal cual):

**Subir de nivel es inmediato.** El proveedor cobra la diferencia prorrateada, y
**nuestro pool de la semana en curso se COMPLETA hasta el tamaño del nivel
nuevo**. No se reinicia.

La diferencia importa: un partner que subió el jueves con 100 000 gastados de
500 000 pasa a tener `900 000` disponibles de 1 000 000 — no vuelve a 1 000 000
completo, porque eso regalaría lo ya consumido, ni se queda en 400 000, que
sería cobrarle el nivel nuevo sin dárselo. Se le suma la diferencia de tamaño.

**Bajar de nivel es a fin de período**, con un *Subscription Schedule* y
`proration_behavior='none'`. Nada se devuelve, nada se corta a mitad de semana.

**Ningún cambio de plan toca `purchased_remaining`.** El crédito comprado es
dinero ya pagado y no es del plan.

---

## D8 · El crédito comprado caduca a los 12 meses, pero solo tras la baja

**Decisión**: una columna de caducidad sobre el cubo comprado que **es `NULL`
mientras la cuenta vive**. Se rellena al cancelar, con fecha a 12 meses. Si el
partner vuelve, se pone a `NULL` otra vez.

**Por qué así y no con un cron que reste**: la invariante que hay que preservar
es *«el crédito comprado no caduca mientras la cuenta viva»*. Expresarla como
`NULL` la hace **imposible de violar por accidente**: no hay fecha que comparar.
Un cron que decidiera a quién caducar tendría que reimplementar «¿está viva esta
cuenta?» y podría equivocarse.

**Cómo se aplica**: el trabajo de fondo pone a cero los cubos cuya fecha ya pasó
y **deja asiento en el libro** con su motivo. No es una resta silenciosa: es un
apunte que se puede explicar.

> **Ojo con D3**: esto *resta* saldo. No lo contradice — D3 prohíbe que **un
> aviso externo** reste. Esto es una regla nuestra, con fecha nuestra, escrita
> en el libro. La distinción es la que importa: quién decide.

---

## Lo que NO se usa de Stripe, y por qué

**Los *credit grants*.** Verificado en la evaluación (§5.2): se aplican **al
finalizar la factura**, solo sobre precios medidos con *Meters*, y hay un límite
de **100 concesiones sin usar por cliente**. Ninguna de las tres cosas encaja:
nuestro tope tiene que **parar un turno antes de que ocurra**, no descontarlo a
fin de mes. El tope es de la plataforma; el proveedor cobra.

**Stripe Tax, de momento.** Calcula y cobra el impuesto; **no asume la
obligación fiscal**. Encenderlo sin saber dónde estamos obligados a declarar es
cobrar un impuesto que quizá no sabemos remitir. **Precondición de despliegue,
no de especificación**: se resuelve con asesoría, y bloquea salir a producción,
no escribir el código.

---

## Lo que no se pudo verificar

- **El importe exacto de la comisión** que Stripe aplica a la cuenta de Andrés
  Matos: depende del país de la cuenta y del método de pago, y no se consultó el
  panel (no opero esa cuenta). Los márgenes del `concept.md` usan ~2,9 % + 0,30 $
  como estimación declarada.
- **Si esa cuenta tiene ya *Stripe Tax* activo o algún producto creado**: lo
  comprueba el script de catálogo en su primera ejecución, que es idempotente
  precisamente por esto.
