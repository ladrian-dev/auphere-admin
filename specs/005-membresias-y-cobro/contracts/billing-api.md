# Contrato · lo que la consola llama

**Spec**: [../spec.md](../spec.md) · **Modelo**: [../data-model.md](../data-model.md)
**Fecha**: 2026-09-12

Superficie **`0`** (API de consola). Cada llamada llega con el token EdDSA de 60
segundos que acuña la consola; la API revalida la pertenencia en
`partner_memberships`. **La consola nunca lleva una credencial del backend**, y
tampoco lleva una del proveedor de pago.

> Todas estas rutas cuelgan de `/console/billing`, que **ya existe** con un
> `GET` que devuelve las facturas internas. Se amplía, no se sustituye.

---

## `GET /console/billing/membership`

El estado de la membresía. Es lo que pinta la pantalla entera.

```json
{
  "tier": {
    "code": "pro",
    "display_name": "Pro",
    "monthly_price_cents": 2000,
    "max_teammates": 2,
    "max_members": 1
  },
  "state": "current",
  "state_changed_at": "2026-09-01T10:00:00Z",
  "current_period_end": "2026-10-01T10:00:00Z",
  "pending_tier": null,
  "usage": { "teammates": 1, "members": 1 },
  "purchased_expires_at": null,
  "catalog": [ { "code": "free", "...": "..." } ]
}
```

**Decisiones de forma, y cada una tiene su razón**:

- **`usage` viene con el objeto.** Sin él, la pantalla tendría que pedir la
  lista de teammates solo para saber si el botón va apagado, y habría un
  instante en que muestra un botón que va a fallar (§V).
- **No hay `pool_size` ni cifras de saldo aquí.** Eso lo da
  `/console/companion/budget`, que es el medidor único (Spec A). **Un segundo
  sitio que diga cuánto queda es un segundo medidor**, y ese fue el defecto D5
  que la Spec A acabó de arreglar.
- **`catalog` se devuelve entero**, filtrado por `is_public`. La pantalla de
  cambio de plan no necesita otra llamada.
- **`pending_tier` explícito.** Un partner que ya pidió bajar tiene que ver que
  lo pidió; si no, lo vuelve a pedir.

---

## `POST /console/billing/checkout`

Abre la página de pago del proveedor, para **contratar o cambiar de nivel**.

```json
{ "tier_code": "team" }
```

→ `200 { "url": "https://..." }` · la consola redirige.

**Reglas**:

| Situación | Respuesta |
|---|---|
| El partner **no tiene** suscripción | Se crea sesión de suscripción |
| Ya tiene una y **sube** de nivel | **No se abre página nueva.** Se modifica la suscripción, se cobra la diferencia prorrateada y el pool de la semana **se completa** (research §D7). Devuelve `{"url": null, "applied": true}` |
| Ya tiene una y **baja** de nivel | Se programa a fin de período. `{"url": null, "applied": false, "effective_at": "..."}` |
| `tier_code` es `free` teniendo plan | Es una **cancelación**: usa `DELETE` |
| `tier_code` no existe o no es público | `422` |
| El nivel destino tiene **menos** topes que lo que ya usa | `409 tier_below_usage`, con cuántos sobran. **No se archiva nada** (§IV) |

Ese último caso es el que hay que hacer bien: bajar a un nivel con 2 teammates
teniendo 5 **no puede** archivar tres. Se rechaza y se le dice al partner qué
tiene que hacer él.

**Quién puede**: una persona con permiso de facturación. **La auditoría nombra a
esa persona** (§IV), no al partner.

---

## `POST /console/billing/credit`

Compra de crédito de una vez.

```json
{ "amount_cents": 5000 }
```

→ `200 { "url": "https://..." }`

- Solo **USD** en esta versión.
- Mínimo y máximo por compra, validados en la API. Un máximo protege de un cero
  de más tecleado.
- **Esta llamada no acredita nada.** Abre la página. El crédito entra cuando el
  pago se confirma, por el webhook. Es la mitad de lo que hace innecesario
  `POST /console/wallet/purchased`, que esta spec borra.

---

## `GET /console/billing/portal`

→ `200 { "url": "..." }` — el portal del proveedor, donde el partner cambia la
tarjeta, ve sus facturas y se da de baja.

**Por qué se delega y no se construye**: las facturas del proveedor son **el
documento fiscal** (decidido el 2026-09-12). Construir nuestra propia pantalla
de tarjetas significaría tocar datos de tarjeta, que es exactamente lo que la
página alojada evita.

---

## `DELETE /console/billing/subscription`

Cancelar.

- Surte efecto **a fin de período**, no al instante: el partner pagó la semana.
- **Nada se archiva** (§IV): ni teammates, ni tareas, ni confirmaciones
  pendientes. Solo deja de renovarse el pool.
- Pone `purchased_expires_at` a **12 meses** (research §D8).
- Reversible hasta que el período acabe, y la pantalla lo dice.

---

## Lo que cambia en `/console/companion/budget`

**Nada en su forma.** Gana significado: el `pool_size` que ya devuelve pasa a
salir del nivel concedido en vez de un valor puesto a mano.

Se dice explícitamente porque **la tentación es añadirle campos de membresía**,
y ese objeto es el medidor único. Si necesita saber su plan, la pantalla llama a
`/console/billing/membership`.

---

## Errores

| Código | Cuándo | Qué ve el partner |
|---|---|---|
| `409 tier_below_usage` | La bajada no cabe | Cuántos teammates o personas sobran, y que los quite él |
| `409 subscription_pending` | Ya hay un cambio programado | Cuál, y que puede anularlo |
| `402 payment_required` | El proveedor rechazó de entrada | Que revise su método de pago, con enlace al portal |
| `503 billing_unavailable` | El proveedor no responde | **Que lo intente en un momento. No que «algo salió mal»** (§V) |

Ninguno de estos filtra el mensaje crudo del proveedor a la pantalla: se
registra entero y se traduce. Un mensaje de una API externa mostrado tal cual es
contenido externo puesto delante de una persona (§III).
