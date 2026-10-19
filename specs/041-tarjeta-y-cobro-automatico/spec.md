# Especificación: la tarjeta del partner, la recarga automática y el pospago

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Implementada (falta probar con Stripe en staging)

**Entrada**: owner, 2026-10-19 — «Poder corregir el flujo para que un partner pueda agregar
su tarjeta por Stripe para pagos recurrentes y el cobro de su factura mensual del consumo».
Decisión del owner el mismo día: **las dos opciones**, recarga automática y pospago mensual,
a elección del partner.

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — la tarjeta se introduce en la página de Stripe y su número nunca llega a Auphere; solo se guardan ids, marca, últimos 4 y caducidad |
| **Garantías de aislamiento tocadas** | **1** — `partner_billing` y `partner_charges` con FORCE RLS por `app.partner_id`, como el saldo (`tests/isolation/test_21…`, `PARTNER_FORCE_TABLES`) |
| **Nota de KB** | `[[ADR-048-tarjeta-y-cobro-automatico]]` · `[[ADR-044-el-dinero-es-exacto]]` |
| **Qué se mide** | Nada nuevo: los cobros abonan el saldo con `credit_stripe` |

## Requisitos

1. **Guardar la tarjeta.**
   - El partner guarda o cambia la tarjeta en Stripe Checkout `mode=setup` (`POST /console/billing/card`).
   - Con `checkout.session.completed` en modo setup, el worker la pone como método por defecto del cliente de Stripe y guarda marca, últimos 4 y caducidad.
   - Quitarla (`DELETE`) la desvincula y devuelve el cobro a manual.
2. **Tres modos de cobro** (`PUT /console/billing/charging`):
   - `manual`: el partner compra saldo, como hasta ahora.
   - `auto_recharge`: necesita tarjeta, un mínimo de saldo y una recarga de US$5 o más.
   - `postpaid`: necesita tarjeta y una línea de crédito que concede Auphere.
3. **Línea de crédito.**
   - Va en `partner_wallets.credit_limit` y la fija el operador (`PUT /admin/partners/{id}/credit-limit`, firmado y auditado).
   - La base de datos impone `purchased_remaining >= -credit_limit`.
   - No se puede bajar por debajo de lo que el partner ya debe.
   - Quitarla devuelve a manual a un partner que estaba en pospago.
4. **Débito con línea.**
   - Dentro de la línea, los turnos de canal siguen sirviéndose y el saldo baja de cero.
   - El débito parte del valor guardado, nunca del que se muestra, para que una deuda no se perdone.
   - Sin línea, todo sigue igual: se corta en cero.
5. **Cada cobro es una factura de Stripe** cobrada a la tarjeta fuera de sesión. Cada cargo tiene así su documento fiscal.
   - **Recarga automática.** Cada 5 minutos, si el saldo está por debajo del mínimo y no hay un cobro en curso.
   - **Pospago.** El día 1 (hora de Madrid) se cobra la deuda redondeada al céntimo hacia arriba. La clave lleva el mes, así que repetirlo no cobra dos veces.
6. **El saldo sube en un solo sitio** (`settle_paid_invoice`), con la clave `stripe_invoice:<id>`.
   - Funciona igual al pagar en el momento que al llegar `invoice.paid` después.
   - El libro sigue cuadrando (`reconcile_purchased`).
7. **Tarjeta rechazada.**
   - Cuenta como intento fallido. Con 3 seguidos, los cobros automáticos se paran con el motivo a la vista.
   - Una tarjeta nueva los reanuda.
   - Sin claves de Stripe no se cobra ni se registra nada: la facturación cerrada no es una tarjeta rechazada.
8. **3D Secure** (revisión crítica, 2026-10-19).
   - Si el banco pide confirmar el cobro (`authentication_required`), el cobro queda «pendiente de confirmar», no rechazado: no cuenta como intento fallido.
   - El cobro guarda el enlace de la factura de Stripe (`action_url`). Se envía al correo de facturación del partner y aparece en su consola con «Confirmar el pago».
   - Mientras espera, no se abre otra recarga. `invoice.paid` lo liquida.
9. **Pospago que no se cobra.**
   - Si el cobro del pospago falla o queda pendiente de confirmar, la línea se **congela** en lo que ya se debe: no se consume más a crédito.
   - La línea concedida se guarda en `partner_billing.granted_credit_limit` y vuelve al pagarse.
   - El cobro se reintenta como mucho una vez al día, con una clave por mes y día. Tres rechazos lo paran hasta cambiar la tarjeta.
   - En el Panel del Admin sale como «línea de pospago congelada».
10. **Pantallas.**
   - Consola, Facturación: tarjeta, modo y cobros.
   - Admin, ficha del partner, Dinero: tarjeta, modo, estado, línea con confirmación, deuda y cobros.

## Pendiente fuera del código

- Probar en staging con las claves de prueba de Stripe: guardar una tarjeta 4242, provocar una recarga y un cierre de pospago, y una tarjeta rechazada (4000 0000 0000 0341).
- El tratamiento fiscal que `docs/billing.md` marca como bloqueante del primer cobro real sigue aplicando.
