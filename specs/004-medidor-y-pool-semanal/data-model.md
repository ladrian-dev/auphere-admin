# Fase 1 — Modelo de datos

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Fecha**: 2026-09-11

Esta spec **no crea ninguna tabla**. Añade tres columnas, cambia la semántica de
dos que ya existen y deprecia una. Todo lo demás ya estaba.

---

## Lo que se añade

### `model_profiles.quota_weight` — `numeric(6,3) NULL`

Cuánto pesa un token de cuota de este modelo, normalizado al cerebro medio del
catálogo cerrado (Terra = `1.000`).

| | |
|---|---|
| **Dueño** | Catálogo de plataforma. **Sin `tenant_id` y sin RLS**, como el resto de `model_profiles`: qué modelos existen y qué cuestan es igual para todos |
| **`NULL` significa** | *«este modelo no se sirve por el camino de cuota de LLM»*. **No** significa peso 1 |
| **Rango** | `CHECK (quota_weight IS NULL OR quota_weight > 0)`. Un peso de cero haría infinito el pool |
| **Escala** | Tres decimales bastan: con ellos, agotar 1 M de pool cuesta entre 3,5144 $ y 3,5154 $ en los seis modelos del catálogo — 0,03 % |
| **Quién lo lee** | `nexus_worker.metering.pricing.get_catalog()`, cacheado con TTL de 300 s. Cero consultas nuevas por turno |
| **Quién lo escribe** | Una migración para la carga inicial; después, el panel de operador con auditoría |

Valores iniciales en el §D1 de [`research.md`](./research.md).

### `partners.weekly_pool_tokens` — `bigint NOT NULL`

El tamaño del consumo incluido que se repone cada siete días.

| | |
|---|---|
| **Dueño** | El partner. Tabla `partners`, que es entidad de primer nivel: **no tiene `tenant_id`** y un cliente final no tiene forma de nombrarla |
| **Siembra** | `round(companion_monthly_token_cap × 7 / 30.44)` — preserva el volumen mensual (R2.6) |
| **Rango** | `CHECK (weekly_pool_tokens >= 0)`. Cero es válido y significa «sin consumo incluido», que es un estado explicable |
| **Se cambia** | Sin despliegue y sin migración (R2.9). El partner no lo ve como cantidad (R7.3) |

### `model_profiles` y `meter_prices` — filas, no columnas

No hay cambio de esquema: se cargan las tarifas que faltan en `model_profiles`
(las tres del catálogo cerrado, hoy a `NULL` desde la `0095`) y las filas de
`meter_prices` que hoy no existen.

---

## Lo que cambia de significado

### `partner_wallets.included_remaining` + `included_expires_at`

**Las columnas no cambian. Cambia el período.**

| | Antes | Después |
|---|---|---|
| Vencimiento | Día 1 del mes siguiente, igual para todos | Siete días desde el ancla **del partner** |
| Tamaño al reponer | `companion_monthly_token_cap` | `weekly_pool_tokens` |
| Quién lo gasta | Companion, teammates, **y los clientes finales** | Companion y teammates. **Los clientes finales, no** (R5.2) |
| Qué es para la pantalla | Un número entre otros | **El** número: `budget_out.remaining` es esta columna (D5) |

El ancla se deriva de `partners.created_at` — sin columna nueva, ver §D3 del
research.

### `partner_allocations` — el tope por cliente

**Deja de ser una porción del libro y pasa a ser un tope de gasto por cliente.**

| | Antes | Después |
|---|---|---|
| Se calcula contra | `included` efectivo + `purchased` | **`purchased` solamente** (R6.1) |
| Se repone | Mensualmente, con el `included` | **Mensualmente, por su cuenta** (R6.2) |
| Qué limita | Cuánto del libro puede quemar un cliente | Cuánto del saldo **comprado** puede quemar un cliente |

**Por qué sigue siendo mensual** aunque el pool pase a semanal: no es una porción
de lo incluido, es un límite de gasto que el partner fija para no llevarse una
sorpresa con un cliente. Un límite de gasto que se reinicia cada semana es cuatro
veces más permisivo y no lo pidió nadie.

`allocatable_for()` y `set_allocation()` pasan a calcular sobre `purchased`; la
invariante **«la suma de topes no supera el saldo sobre el que se calculan»**
(R6.5) se conserva, solo cambia contra qué se compara.

---

## Lo que se deprecia

### `partners.companion_monthly_token_cap`

**Deja de leerse en esta spec. No se borra.**

Era el origen del defecto: el mismo número dimensionaba el tope que se comparaba
contra la suma de ejecuciones **y** la recarga de un libro que gastaban además
los clientes finales y las ejecuciones locales.

Se marca deprecada en el modelo, nombrando en el comentario la migración que la
eliminará. Borrarla en la misma migración que crea su sustituta dejaría un
`downgrade()` incapaz de devolver los datos, y la regla del repositorio pide
`downgrade()` real probado contra un dump de producción.

---

## Entidades, y a quién pertenece cada una

| Entidad | Tabla | Pertenece a | Cómo la alcanza la RLS |
|---|---|---|---|
| Libro del partner | `partner_wallets` | **Partner** | `ENABLE` + `FORCE` por `partner_id` (migración `0094`) |
| Asiento de consumo | `usage_ledger` | **Partner** | `ENABLE` + `FORCE` por `partner_id` |
| Tope por cliente | `partner_allocations` | **(Partner, tenant)** | `ENABLE` + `FORCE` por `partner_id` |
| Perfil de modelo | `model_profiles` | **Plataforma** | **Sin RLS, a propósito**: es catálogo, igual para todos |
| Precio por medidor | `meter_prices` | **Plataforma** | Sin RLS, mismo motivo |
| Tamaño de pool y ancla | `partners` | **Partner** | Entidad de primer nivel, sin `tenant_id` |
| Consumo por evento | `usage_records` | **Tenant** | `ENABLE` + `FORCE` por `tenant_id`, particionada por mes |

**Lo que esto garantiza para R7 y para el aislamiento**: todo lo que esta spec
toca del lado del dinero vive en tablas **de partner o de plataforma**. Ninguna
lleva `tenant_id`, así que **no existe superficie por la que un cliente final
pueda alcanzarlo** — no hay que quitarle un permiso, es que no hay puerta. El
test de aislamiento comprueba lo contrario: que ninguna respuesta de un endpoint
orientado a cliente final nombre pool, saldo ni precio.

---

## Transiciones de estado del libro

```
        ┌──────────── se agota el incluido ───────────┐
        │                                             ▼
  ┌───────────┐                              ┌─────────────────┐
  │ INCLUIDO  │                              │ SOBRE COMPRADO  │
  │  vigente  │                              │ (R5.3, sin      │
  └───────────┘                              │  intervención)  │
        ▲                                    └─────────────────┘
        │ vencimiento semanal                          │
        │ (R2.1, R2.3 — lo no gastado NO se acumula)   │ se agota
        │                                              ▼
  ┌───────────┐                              ┌─────────────────┐
  │ REPUESTO  │◄──── el cron, por caducidad ─│ EN PAUSA POR    │
  │ al tamaño │      no por calendario (R2.4)│ TOPE (R5.4)     │
  │  completo │                              │ nada se cancela │
  └───────────┘                              └─────────────────┘
```

Tres invariantes que ninguna transición puede romper:

1. **`purchased` nunca caduca** (R2.5). Ni al renovar, ni al cambiar de período,
   ni al vaciarse el incluido.
2. **Nada se cancela al entrar en pausa** (R5.4). Las confirmaciones pendientes
   siguen vivas; es el camino que la spec 003 ya construyó.
3. **Un asiento no se reescribe** (R3.5). Cambiar un factor no revalúa lo ya
   debitado.
