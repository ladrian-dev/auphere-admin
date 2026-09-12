# Contrato · el aviso del proveedor

**Spec**: [../spec.md](../spec.md) · **Decisiones**: [../research.md](../research.md) §D3, §D4, §D6
**Fecha**: 2026-09-12 · Conserva ADR-022 §13–§15

---

## `POST /webhooks/billing`

Llamante **externo**. No es una clase nueva —`/webhooks/meta` y
`/webhooks/tiktok` ya existen y su patrón se copia— pero **éste acredita
saldo**, y eso es lo que hay que contener.

### La secuencia, y nada entre medias

```text
1. leer el cuerpo EN CRUDO (bytes)
2. verificar la firma            → 400, y se registra el intento
3. INSERT por provider_event_id  → si choca: 200 y parar
4. resolver el partner
5. encolar el trabajo
6. 200
```

**En crudo y sin parsear** (paso 1): la firma se calcula sobre los bytes
exactos. Si el framework deserializa y vuelve a serializar, un espacio invalida
la firma. Es el mismo motivo por el que `/webhooks/meta` ya lee `body` crudo.

**El `INSERT` antes de actuar** (paso 3) es la idempotencia real. No se delega
al trabajo de fondo: se decide en la puerta, con una restricción de base de
datos. Dos entregas simultáneas del mismo evento — que pasan — hacen que una
gane el `INSERT` y la otra reciba `200` sin acreditar nada.

**Menos de 500 ms** hasta el `200`. El proveedor **espera hasta 10 segundos**
nuestra respuesta a `checkout.session.completed` antes de redirigir al cliente.

### Códigos

| Código | Cuándo |
|---|---|
| `200` | Recibido y encolado · o ya visto |
| `400` | Firma inválida o ausente |
| `500` | **Solo** si no pudimos ni registrar el evento. Provoca el reintento del proveedor, que es lo correcto: preferimos el reintento a perder un aviso de dinero |

Un fallo **procesando** no devuelve `500`: el evento ya está registrado y se
reintenta desde nuestro lado. Devolver `500` ahí haría que el proveedor
reenviara algo que ya tenemos.

---

## Los eventos, y qué hace cada uno

| Evento | Efecto |
|---|---|
| `invoice.paid` | Conceder o renovar el nivel: `tier_code`, `state='current'`, copiar `weekly_pool_tokens` al partner, `current_period_end` |
| `invoice.payment_failed` | `state='payment_failed'`. **Nada más cambia todavía** |
| `customer.subscription.updated` | Aplicar el mapeo de estado (research §D6) y el nivel |
| `customer.subscription.deleted` | `state='canceled'`, pool a Free, `purchased_expires_at` a 12 meses |
| `checkout.session.completed` | Si es compra de crédito: **`add_purchased`** |
| `checkout.session.async_payment_succeeded` | Lo mismo. Métodos diferidos |
| `invoice.finalization_failed` | **Alertar al operador**, con `last_finalization_error`. **No degrada al partner** |
| `invoice.upcoming` | Avisar al partner de la renovación próxima. Es con lo que se cumple R5.6: avisar **antes** |

**No estamos suscritos a `invoice.created`**, y es deliberado: un endpoint que
no responde correctamente a ese evento hace que el proveedor **retrase la
finalización de todas las facturas con cobro automático hasta 72 horas**
(verificado 2026-09-12). No lo necesitamos — el dinero llega con `invoice.paid`.

> Y un matiz de esa misma página que importa con **esta** cuenta: «Responding
> properly to `invoice.created` includes handling **all webhook endpoints
> configured for your account**». El castigo es de la cuenta entera, no de un
> endpoint. Si la cuenta de Andrés Matos tuviera otra integración con un
> endpoint roto, nos afectaría. Se comprueba al arrancar y se anota en el
> runbook.

**`invoice.finalization_failed` sí está, y es la avería más silenciosa de las
dos** (research §D10): una factura que no finaliza deja la suscripción
`active` —el partner trabaja con normalidad— y **no se cobra nada**. No hay
síntoma. No degrada al partner: **alerta al operador**.

---

## Las dos reglas duras

### 1. Ningún camino de aquí resta saldo

El manejador **solo** llama a `add_purchased`. No importa `debit_wallet`, y hay
un **test estructural** que falla si algún día lo importa.

Un reembolso **no** retira crédito automáticamente: lo decide un operador, con
rastro. Verificado como decisión, no como olvido (research §D3).

### 2. El cuerpo es dato; el objeto se recupera

El cuerpo dice **qué pasó**. El **importe y el estado** se leen llamando a la
API del proveedor con el identificador del objeto.

Dos razones que coinciden: el proveedor avisa de que el cuerpo puede estar
obsoleto, y el principio III dice que lo que llega de fuera es dato y nunca
instrucción. Un importe que viniera en el cuerpo **no acredita nada**.

---

## Idempotencia de la compra: dos anclas, no una

`checkout.session.completed` y `checkout.session.async_payment_succeeded`
**pueden llegar los dos para la misma compra**. Son eventos distintos, así que
la restricción sobre `provider_event_id` no los detiene.

Por eso el cumplimiento se ancla además en **`checkout_session_id`**: antes de
acreditar, se comprueba si ya hay un evento `processed` con esa sesión.

Y antes de todo eso: **`payment_status != 'unpaid'`**. Una sesión completada con
pago pendiente no es una compra.

---

## Lo que sale hacia el proveedor

Toda llamada que **crea o modifica** algo lleva **clave de idempotencia**, con
el patrón de nombre de ADR-022 §15:

```text
<dominio>:<entidad>:<id nuestro>:<acción>[:<discriminante>]

billing:sub:7f3a…:create
billing:sub:7f3a…:upgrade:team:2026-W37
billing:credit:7f3a…:5000:2026-09-12T10:03:11Z
```

**Nunca lleva el identificador del proveedor** — lleva el nuestro (research
§D5.1). Así la clave sigue siendo válida si la cuenta cambia.

**Y en el sentido contrario**: toda sesión de Checkout se abre con
`client_reference_id = <nuestro partner_id>`, y toda suscripción lleva el mismo
valor en `metadata`. Por eso el manejador **resuelve el partner desde el propio
aviso** y no buscando por `stripe_customer_id` — que es lo que mantiene esa
columna como referencia borrable y hace inocuo el `UPDATE` del runbook de
migración (research §D10).

**La discriminante importa**: sin ella, un partner que sube a `team`, baja y
vuelve a subir reutilizaría la clave del primer intento y el proveedor
devolvería la respuesta antigua sin hacer nada. La semana la distingue.

---

## Lo que nunca se registra

**Ningún dato de tarjeta**, en ningún log, traza ni columna. El proveedor no nos
lo manda; aun así el `payload` se filtra al guardar y hay un test de aislamiento
que lo comprueba (garantía 6).

Tampoco se registra **contenido de conversación**: este camino pasa cerca del
camino del turno, y es exactamente el error que
`tests/isolation/test_wallet_events_are_logged.py` ya vigila para el libro.

---

## Configuración

| Variable | Qué es |
|---|---|
| `BILLING_WEBHOOK_SECRET` | Secreto de firma del endpoint |
| `BILLING_API_KEY` | Clave secreta de la cuenta |
| `BILLING_PUBLIC_KEY` | Clave publicable |

**Sin valor por defecto y sin `change-me`.** Si faltan, la aplicación **arranca
igual** pero el paquete de cobro queda **cerrado**: las rutas responden
`503 billing_unavailable` y el webhook `400`. Arrancar sin cobro es un estado
honesto; arrancar con un secreto de mentira acepta avisos falsos.
