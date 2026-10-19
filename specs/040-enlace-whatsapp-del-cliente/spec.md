# Especificación: el dueño conecta su WhatsApp desde su propio dispositivo

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Implementada (falta probar Meta en staging)

**Entrada**: owner, 2026-10-19 — «Cuando voy a conectar el canal de WhatsApp por
coexistencia necesito poder copiar y compartir el link para que se abra desde la computadora
o teléfono del cliente y no desde el computador del partner… por seguridad es mejor que lo
rellene el cliente desde sus dispositivos, que normalmente ya están logueados a sus cuentas
de Meta».

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `1` — una página que abre alguien sin cuenta. La autoriza un token de un solo uso, que caduca a los 7 días y se puede anular. La API solo la atiende con la credencial de servicio de la consola (`require_console_service`), como las invitaciones y el cambio de contraseña |
| **Garantías de aislamiento tocadas** | **1** — la conexión corre bajo el GUC del cliente del enlace. `channel_signup_links` no tiene RLS a propósito (migración 0160): la página solo conoce el token, igual que `signup_requests` |
| **Nota de KB** | `[[ADR-030-whatsapp-coexistence]]` / Embedded Signup |
| **Qué se mide** | Nada nuevo |

## Requisitos

1. **Quién crea el enlace.**
   - El operador lo crea en el Admin (`POST /admin/tenants/{id}/channels/whatsapp/signup-link`, firmado por el operador).
   - Un miembro del partner con `channels:write` lo crea en la consola (`POST /console/clients/{ref}/channels/whatsapp/signup-link`).
   - El modo es coexistencia por defecto, o Cloud API.
2. **Cómo se guarda.** Solo se guarda el SHA-256 del token. El enlace es de un solo uso, caduca a los 7 días y se puede anular. Crear, anular y conectar quedan auditados.
3. **La página del dueño** (`/connect/whatsapp/{token}`, consola, pública en el proxy).
   - Dice para qué negocio es y abre el Embedded Signup de Meta en el dispositivo del dueño.
   - Un enlace usado, caducado, anulado o inexistente lo dice sin revelar de quién era.
4. **La conexión** sigue el camino de la consola:
   - cupo de canales del partner antes de llamar a Meta;
   - `complete_meta_signup`;
   - «número en uso» como 409;
   - la fila del conector `whatsapp_meta`;
   - activar el cliente si ya puede atender.
   - Si dos pestañas envían a la vez, el bloqueo de fila deja conectar solo a una.
5. **Límite.** Hay un máximo de 10 llamadas por minuto y token.
6. **El token no se queda en la página** (revisión crítica, 2026-10-19).
   - El enlace llega a `/connect/whatsapp/{token}`, que guarda el token en una cookie httpOnly (`/connect`, una hora) y redirige con 303 a `/connect/whatsapp`.
   - La página que carga el SDK de Meta no lleva el token en su dirección ni en el historial, y la acción lo lee de la cookie.
   - `/connect/*` envía `Referrer-Policy: no-referrer`.
   - Al conectar, la cookie se borra.
7. **Dónde se ofrece.**
   - En el Admin: la primera tarjeta del paso «Conectar WhatsApp» y, en Canales, los enlaces enviados sin usar con «Anular».
   - En la consola: «Enviar enlace al cliente» junto a «Conectar WhatsApp», también en la app de escritorio.
   - Se comparte copiando, por WhatsApp o por correo.

## Pendiente fuera del código

- El dominio de la consola de cada entorno debe estar entre los permitidos del SDK de JavaScript de la app de Meta (Facebook Login for Business). Probar el flujo completo con una cuenta real en staging antes de producción.
