# T110 — Recorrido en staging

**Fecha:** 2026-10-09 · **Commit:** `da4b1596` (desplegado por `deploy-staging`:
CI y migraciones 0147–0155 en verde).

## Preparación (por la API del admin, sin panel de admin en staging)

Staging no tiene proyecto de Vercel para el admin (`auphere-admin` es solo
producción), así que el acceso se encendió con las mismas rutas que llama la
pestaña «Acceso», con el token de admin de `nexus/staging/app`:

1. **Operador.** Staging no tenía ninguna cuenta de operador
   (`operator_auth.principals` vacía). Se creó `contacto@ladrian.dev` (rol
   `admin`, id `8b3288b3-974f-4218-b669-9838f3893bea`) con una tarea suelta de
   ECS (la definición de migraciones con el comando sustituido); contraseña
   aleatoria generada dentro de la tarea y nunca impresa.
2. **Cliente.** El único de staging con un número real de WhatsApp activo:
   **Demo Farmacia Amacrux** (`61b3b6e2-50e2-476f-ab64-0b44cebbe184`,
   `+34672138367`). La migración 0153 le había creado su «Agente principal» con
   la versión 4 y le había asignado el número.
3. **Partner.** No era elegible (`no_partner`): no estaba en `partner_tenants`.
   Se ligó a **Demo (staging)** (`external_client_ref = demo-farmacia-amacrux`),
   el partner que indica su slug. En staging no está definida
   `NEXUS_AUPHERE_PARTNER_SLUGS`, así que no hay forma de marcarlo como cliente
   directo de Auphere.
4. **Acceso** encendido con Panel, Bandeja de entrada y Consumo, e
   **invitación** a `contacto+lite@ladrian.dev` (`email_sent: true`).

## Recorrido

Luis aceptó la invitación, entró como la persona del cliente y probó la consola
lite de punta a punta, incluido el mensaje real al número de la farmacia:
«quedó perfecto» (2026-10-09). No se cronometró la latencia de un mensaje nuevo
(CE-004) con instrumentos; la impresión fue de llegada inmediata.

## Lo que no se hizo

- El recorrido local del quickstart (la verificación completa
  `./scripts/verify.sh` sí está en verde sobre el mismo commit).
- La prueba e2e automática (T105): se sustituyó por la prueba manual. Para
  correrla: `E2E_BASE_URL=https://console.staging.auphere.com
  E2E_CLIENT_EMAIL=contacto+lite@ladrian.dev E2E_CLIENT_PASSWORD=… pnpm test:e2e lite`.
