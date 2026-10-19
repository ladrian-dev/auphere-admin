# Especificación: las consolas son gratis mientras el Teammate se termina

**Rama**: `034-consolas-sin-suscripcion` · **Creada**: 2026-10-18 · **Estado**: Aprobada para plan

**Entrada**: owner, 2026-10-18 — «la consola actualmente no tiene una suscripción; la
suscripción será después que terminemos el producto de Teammate, así que las consolas
serán gratis para partners y clientes. Libera todas las funciones y deshabilita las
suscripciones en el área de facturación». Aclaración: «las 4 suscripciones Free, Pro,
Team y Business son de Teammate, no de la consola»; Facturación conserva **recibos y
compra de crédito por Stripe**.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Se cierran puertas, no se abre ninguna |
| **Garantías de aislamiento tocadas** | Ninguna. Ningún endpoint cambia de ámbito |
| **Nota de KB que la justifica** | `[[ADR-043-consolas-sin-suscripcion]]` · `[[docs/billing.md]]` (spec 005) |
| **Qué se mide** | Sin cambio: el medidor y el libro siguen igual; solo deja de depender del estado de una suscripción |

## Origen

Medido el 2026-10-18. La spec 005 montó cuatro niveles de membresía con Stripe y los
cablea en cuatro sitios: el tope de teammates y de personas (`membership_limits`), la
reposición del pool semanal (solo con suscripción al corriente), la pantalla de planes
de Facturación y los avisos del escritorio. En producción no hay ninguna suscripción. Un
partner sin fila es «Free»: cero teammates y una sola persona, aunque la consola sea
gratis. Además, el cobro de una sesión de Checkout de **suscripción** pasaría por el
mismo camino que una compra de crédito y se abonaría como saldo (no hay prueba que lo
impida).

## Clarifications

### Session 2026-10-18

- Q: ¿Se borran las membresías? → A: **No: se apagan tras un interruptor** (`membership_enabled`, apagado por defecto). Vuelven con el Teammate.
- Q: ¿Qué queda en Facturación? → A: **Recibos y compra de crédito por Stripe** (owner).
- Q: ¿Qué topes se liberan? → A: **Teammates y personas** sin límite; el pool semanal se repone siempre.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un partner usa todo sin contratar nada (P1)

**Escenarios**:
1. **Dado** un partner sin suscripción, **cuando** invita a su segunda persona o crea su primer teammate, **entonces** se crea; no hay `tier_limit_reached`.
2. **Dado** un partner con suscripción cancelada o impagada, **cuando** caduca su pool semanal, **entonces** se repone igual.

### Historia 2 — Facturación sin planes (P1)

**Escenarios**:
1. **Dado** la consola, **cuando** el partner abre Facturación, **entonces** ve su correo de facturación, la compra de crédito y sus recibos; no ve planes, ni botón de portal del proveedor, ni cancelar.
2. **Dado** cualquier llamada a membresía, checkout de nivel, portal o cancelación, **cuando** llega, **entonces** responde 404 como si no existiera.

### Historia 3 — Una suscripción nunca se abona como saldo (P1)

**Escenarios**:
1. **Dado** una sesión de Checkout en modo `subscription`, **cuando** llega su `checkout.session.completed`, **entonces** no se abona crédito.

### Casos límite

- El escritorio pide la membresía y recibe 404: no pinta el plan ni el aviso de tope (ya trata la ausencia como «sin dato»).
- Con el interruptor encendido todo vuelve a la spec 005 sin migración.

## Requisitos *(obligatorio)*

### Requisito 1 — Interruptor

1. El sistema DEBE leer `membership_enabled` de la configuración, apagado por defecto.

### Requisito 2 — Topes liberados

1. WHILE `membership_enabled` está apagado, el sistema NO DEBE rechazar un teammate ni una persona por el nivel del partner.
2. WHILE `membership_enabled` está apagado, el sistema DEBE reponer el pool semanal sin mirar el estado de la suscripción.

### Requisito 3 — Facturación

1. WHILE `membership_enabled` está apagado, `GET /console/billing/membership`, `POST /console/billing/checkout`, `GET /console/billing/portal` y `DELETE /console/billing/subscription` DEBEN responder 404.
2. `POST /console/billing/credit` DEBE seguir funcionando.
3. `GET /console/billing` DEBE decir si las membresías están encendidas, y la pantalla NO DEBE pintar planes ni el enlace al portal cuando no lo están; SÍ DEBE pintar la compra de crédito.

### Requisito 4 — Solo el crédito se abona

1. IF una sesión de Checkout completada no es `mode=payment` con `metadata.kind=credit` THEN el sistema NO DEBE abonar saldo, con el interruptor encendido o apagado.
2. WHILE `membership_enabled` está apagado, los avisos de suscripción del proveedor DEBEN registrarse y no cambiar ningún estado.

## Criterios de éxito

- **CE-001**: un partner nuevo invita a 5 personas y crea 3 teammates sin error.
- **CE-002**: Facturación sin ningún rastro de planes; compra de crédito y recibos visibles.

## Fuera de alcance

- Borrar tablas o el catálogo de niveles — vuelven con el Teammate.
- Cambiar el precio del crédito o su conversión — spec 033.
