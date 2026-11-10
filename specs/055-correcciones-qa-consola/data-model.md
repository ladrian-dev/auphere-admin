# Modelo de datos: Correcciones de QA de la consola

## Migración `0220_service_category`

Aditiva y sin rellenar datos. Baja: quitar la columna.

| Tabla | Cambio | Regla |
|---|---|---|
| `reservation_services` | `category VARCHAR(40) NULL` | `NULL` es «sin categoría». Nunca se guarda vacía |

La tabla ya es de tenant, con RLS por `tenant_id`. La migración no toca las políticas.

## Servicio (`ReservationService`)

| Campo | Cambio |
|---|---|
| `category` | Nuevo, opcional |
| `currency` | Mismo tipo. Al guardar un importe toma la moneda del negocio. Sin moneda conocida y sin importe vale `XXX`, y nunca se pinta |
| `price_minor` | Se reescala al cambiar la moneda del negocio |

**Normalizar la categoría**: recortar, colapsar espacios, cortar en 40 caracteres si llega por una vía sin validar, y vacía equivale a `NULL`. Si un servicio vivo del mismo cliente ya usa esa categoría, sin distinguir mayúsculas, se adopta su forma.

## Perfil del negocio (`BusinessProfile`)

Sin cambios de forma. `price_currency` puede seguir vacío, y entonces:

| Moneda del perfil | Mercado del tenant | Moneda conocida |
|---|---|---|
| USD | cualquiera | USD |
| vacía | ES | EUR |
| vacía | ninguno o desconocido | **ninguna**, en vez de CLP |

## Reservas (`Reservation`)

Sin cambios. Conservan su `currency` y su `price_minor`.

## Invitaciones (`PartnerInvitation`, `ClientInvitation`)

Sin cambios de forma. Reenviar marca la anterior como `revoked` y crea otra, como ya hacen las funciones de reenvío. Cada reenvío se audita con actor `system:password_reset`.

## Transiciones de moneda

```text
sin moneda ──elegir en el modal o en Datos básicos──▶ con moneda
con moneda ──cambiar, con confirmación──▶ otra moneda, y sus servicios con ella
```

Cuando el negocio pasa a tener moneda o la cambia, todos sus servicios toman esa moneda, y los que tienen importe se reescalan. Si algo falla no cambia nada, porque todo va en la misma transacción.
