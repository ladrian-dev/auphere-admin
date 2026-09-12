# Fase 1 · Modelo de datos

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Decisiones**: [research.md](./research.md)
**Fecha**: 2026-09-12

Dos tablas nuevas de catálogo y estado, una de registro, cinco columnas nuevas y
una columna que cambia de significado. Dos migraciones: **0116** y **0117**.

> **Revision id ≤ 32 caracteres.** `alembic_version.version_num` es
> `varchar(32)`. Una revisión más larga hace su trabajo y **luego** revienta al
> registrarse — pasó en la Spec A con `0114`. `0116_membership_tiers` (20) y
> `0117_billing_events` (19) caben.

---

## Aviso de terminología: `billing_plans` YA EXISTE y no es esto

Verificado en `db/models/billing.py`: `billing_plans` es **el precio mensual del
servicio gestionado que se le cobra a un tenant** (`tenants.billing_plan_id`).
Es de la relación Auphere ↔ cliente final del partner, y **no tiene nada que ver
con la membresía del partner**.

Por eso lo nuevo se llama **`membership_tiers`** y no `plans`. Meter la
membresía del partner en `billing_plans` mezclaría dos relaciones comerciales
distintas en una tabla, y el día que un partner tenga las dos cosas —su
membresía y sus clientes facturados— la consulta no sabría cuál es cuál.

---

## Tabla nueva · `membership_tiers` (migración 0116)

El catálogo de niveles. **De plataforma, sin RLS**: es el mismo para todos y no
es de nadie.

| Columna | Tipo | Nulo | Regla |
|---|---|:--:|---|
| `code` | `varchar(20)` **PK** | no | `'free' \| 'pro' \| 'team' \| 'business'`, por CHECK. **La clave es nuestra**, no del proveedor (research §D5.2) |
| `display_name` | `varchar(40)` | no | Lo que ve el partner |
| `monthly_price_cents` | `integer` | no | `>= 0`. Free es `0`. Enteros de centavos, como el resto del repositorio |
| `weekly_pool_tokens` | `bigint` | no | `>= 0`. Se copia a `partners.weekly_pool_tokens` al conceder el nivel |
| `max_teammates` | `integer` | no | `>= 0`. **No existía nada equivalente** |
| `max_members` | `integer` | no | `>= 1`. Personas en `partner_memberships` |
| `stripe_price_id` | `varchar(64)` | **sí** | **Referencia reemplazable.** Sin unicidad, sin clave foránea. `NULL` en Free y tras cambiar de cuenta |
| `sort_order` | `smallint` | no | Orden en pantalla. Que no lo decida el precio: un nivel futuro podría desordenarlo |
| `is_public` | `boolean` | no | `true` por defecto. Un nivel retirado deja de ofrecerse **sin borrarse** (§IV) |

**Filas iniciales**, de `concept.md` de la evaluación (cifras **provisionales**
por decisión de producto, ADR-037):

| `code` | precio | pool semanal *(interno)* | teammates | personas | consumo publicado |
|---|---:|---:|---:|---:|---|
| `free` | 0 | 100 000 | 0 | 1 | — |
| `pro` | 2 000 | 500 000 | 2 | 1 | base |
| `team` | 6 000 | 2 000 000 | 6 | 3 | **4× el de Pro** |
| `business` | 15 000 | 6 000 000 | 12 | 8 | **12× el de Pro** |

> **`weekly_pool_tokens` es interno y no se publica.** Lo que el partner ve de
> cada nivel son **sus topes duros** —cuántos agentes y cuántas personas— y,
> para los niveles por encima del base, **un múltiplo de consumo calculado**
> desde esta columna. Las razones, en research §D9: las cifras son
> provisionales, y un número en una tabla de precios convierte cada ajuste de
> capacidad en un recorte o un regalo visible.
>
> El múltiplo **se calcula, no se guarda**: `weekly_pool_tokens` del nivel
> dividido por el del nivel de pago más bajo, redondeado al entero. Si algún día
> se ajusta un pool, el múltiplo se ajusta solo — **no hay nada que se pueda
> quedar desfasado**, que es la razón de no hacerlo columna.

Cambiar una cifra es un `UPDATE`, **sin desplegar** (R1.5).

---

## Tabla nueva · `partner_subscriptions` (migración 0116)

El estado de la suscripción de un partner. **Una fila por partner**, y por eso
`partner_id` es la clave primaria: no se historifica aquí — para eso está la
auditoría.

**RLS `ENABLE` + `FORCE` por `partner_id`**, igual que `partner_wallets`
(migración 0094).

| Columna | Tipo | Nulo | Regla |
|---|---|:--:|---|
| `partner_id` | `uuid` **PK** | no | FK a `partners.id`, `ON DELETE CASCADE` |
| `tier_code` | `varchar(20)` | no | FK a `membership_tiers.code`. Por defecto `'free'` |
| `state` | `varchar(20)` | no | `'current' \| 'payment_failed' \| 'unpaid' \| 'canceled'`, por CHECK (research §D6) |
| `current_period_end` | `timestamptz` | sí | Lo dice el proveedor. `NULL` en Free |
| `pending_tier_code` | `varchar(20)` | sí | La bajada programada a fin de período (research §D7). FK a `membership_tiers.code` |
| `stripe_customer_id` | `varchar(64)` | **sí** | **Referencia.** Índice para que el webhook resuelva rápido, **pero no es clave de nada** |
| `stripe_subscription_id` | `varchar(64)` | **sí** | Igual |
| `state_changed_at` | `timestamptz` | no | Cuándo se movió en la escalera. Es lo que la pantalla necesita para decir desde cuándo |

**Por qué `partners.status` no sirve**: verificado en `db/models/partner.py:85`,
tiene `CHECK (status IN ('active','suspended'))` y significa **si el partner
está operativo**. Un impagado sigue estando operativo para leer su historia.

**Invariantes**:

- Un partner sin fila **es Free**. La ausencia es un estado válido y se diseña
  (§V): no hay que sembrar filas para que el sistema funcione.
- `state = 'canceled'` ⟹ el nivel efectivo es Free, **independientemente de
  `tier_code`**. Se conserva el `tier_code` para saber de dónde vino.

---

## Tabla nueva · `billing_events` (migración 0117)

El registro de avisos recibidos. **De plataforma, sin RLS**: es nuestro rastro
de integración, no dato de un partner.

Conserva el diseño de ADR-022 §14.

| Columna | Tipo | Nulo | Regla |
|---|---|:--:|---|
| `id` | `uuid` **PK** | no | Nuestro |
| `provider_event_id` | `varchar(80)` | no | **UNIQUE.** Es la idempotencia: el `INSERT` que choca es el reenvío |
| `event_type` | `varchar(80)` | no | Tal cual lo manda el proveedor |
| `checkout_session_id` | `varchar(80)` | sí | **La segunda ancla de idempotencia** (research §D4): dos eventos distintos pueden cumplir la misma compra |
| `partner_id` | `uuid` | sí | Resuelto en el primer paso. `NULL` si no se pudo resolver — y eso es una alerta, no un descarte |
| `status` | `varchar(20)` | no | `'received' \| 'processed' \| 'failed' \| 'ignored'` |
| `payload` | `jsonb` | no | **Sin dato de tarjeta.** Lo que el proveedor manda no lo lleva; aun así se filtra al guardar, y hay un test de aislamiento que lo comprueba (garantía 6) |
| `error` | `text` | sí | Por qué falló |
| `received_at` / `processed_at` | `timestamptz` | no / sí | |

**Índice parcial** sobre `checkout_session_id` cuando no es `NULL`: es la
consulta del camino de cumplimiento.

**Nada se borra.** Un evento fallido se reintenta y cambia de `status`.

---

## Columnas nuevas sobre tablas existentes

### `partner_wallets.purchased_expires_at` — `timestamptz`, **NULL** (0117)

La caducidad del crédito comprado (research §D8).

- **`NULL` mientras la cuenta vive.** Es la invariante *«el crédito comprado no
  caduca mientras la cuenta viva»* expresada de forma que **no se puede violar
  por accidente**: no hay fecha que comparar.
- Se rellena a `now() + 12 meses` al cancelar.
- Vuelve a `NULL` si el partner reactiva.

> **No confundir con `included_expires_at`**, que existe desde antes y es
> semanal. Son dos bolsillos con dos relojes distintos, que es justo lo que
> ADR-037 D1 quería.

### `partners.weekly_pool_tokens` — **cambia de dueño, no de tipo**

Existe desde 0115 con `DEFAULT 115000`. Lo que cambia es **quién lo escribe**:
hasta ahora lo ponía el operador a mano; a partir de aquí **lo copia el nivel
concedido**.

La columna se queda donde está a propósito. El camino del turno la lee para
renovar el pool, y meter un `JOIN` a `membership_tiers` en ese camino sería
poner el catálogo en la ruta caliente del gasto.

### `partners.max_clients` — **NO cambia**

Decidido con Luis el 2026-09-12: sigue siendo **independiente del plan**. Un
partner puede tener un nivel pequeño y muchos clientes, o al revés. Se anota
aquí porque es exactamente el tipo de columna que alguien uniría al nivel
«por coherencia» y rompería un acuerdo comercial.

---

## Lo que se borra

**`POST /console/wallet/purchased`** (`api/console/wallet.py`). Hoy es un 404
opaco en producción y su propia docstring dice que esta spec la sustituye. El
crédito entra por el aviso del pago confirmado; una puerta que añade saldo sin
pago no debe existir ni apagada.

Se borra **el endpoint**, no el modelo ni `add_purchased`, que el webhook
reutiliza.

---

## Diagrama de relaciones

```text
membership_tiers ──┬─< partner_subscriptions (tier_code)
   (catálogo)      └─< partner_subscriptions (pending_tier_code)
                                  │ 1:1
                              partners ──1:1── partner_wallets
                                  │                 (+ purchased_expires_at)
                                  └──< partner_memberships   (max_members)
                                  └──< teammates             (max_teammates)

billing_events ──(partner_id, sin FK dura)──> partners
```

`billing_events.partner_id` **sin clave foránea a propósito**: un evento que
llega antes de que exista el partner, o de una cuenta que no reconocemos, tiene
que poder registrarse igual. Perder el rastro de un aviso de dinero por una
restricción de integridad es peor que tener una fila huérfana.

---

## Reglas de validación que salen de los requisitos

| Regla | De dónde sale | Dónde se comprueba |
|---|---|---|
| No se puede crear el teammate `n+1` si `n = max_teammates` | R1.3 | `services/membership_limits.py`, con test |
| El nivel Free **no muestra** el botón de crear teammate | R1.4, §V | Consola, con test de UI |
| Cambiar cifras de un nivel **no requiere desplegar** | R1.5 | Son `UPDATE` sobre `membership_tiers` |
| El mismo pago notificado cinco veces acredita **una** | R4 | UNIQUE sobre `provider_event_id` + ancla por sesión |
| Ningún camino externo resta saldo | R4, D3 | Test estructural: el paquete `billing/` no importa `debit_wallet` |
| Subir completa el pool de la semana, no lo reinicia | R6, D7 | Test unitario con el pool a medio gastar |
| Un estado del proveedor desconocido **falla**, no cae en `current` | D6 | Test con un estado inventado |
