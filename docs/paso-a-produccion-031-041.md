# Paso a producción: specs 031–041

`develop` → `main`. Son 50 commits: el Admin nuevo (031, 035–039), módulos por
partner (032), el dinero exacto (033), consolas sin suscripción (034), el
enlace de WhatsApp para el dueño (040) y la tarjeta con cobro automático (041).
Entran **cinco migraciones**: `0158` → `0162`.

Probado en staging el 2026-10-20: tarjeta (4242, Link, 0341 rechazada, 3D
Secure), recarga automática, parada tras tres rechazos, quitar tarjeta, «Ver
factura», compra de saldo, correo de facturación, enlace de WhatsApp (crear,
sustituir, anular, página del dueño sin token), Teammate y auditoría. El Admin
se revisó en local. **No probado fuera de los tests: el pospago** (nadie lo
tiene hasta que Auphere conceda una línea) y **el alta real con Meta** desde
el enlace.

---

## La regla: primero la API, después las consolas

En staging, Vercel publicó la consola nueva al instante y la API vieja siguió
media hora más: nadie podía entrar («sin acceso»). Al fusionar a `main` pasa lo
mismo: `deploy-prod` (API y worker en AWS) espera a CI y a un revisor, y
`auphere-console` se despliega en cuanto llega el commit. Por eso la consola se
pausa antes de fusionar y se suelta al final.

La API nueva sí sirve a la consola vieja: lo nuevo son rutas y campos que la
consola vieja no pide.

---

## 0 · Antes (el día anterior o antes de empezar)

- [ ] **Stripe live**
  - Datos públicos de la empresa: nombre **Auphere** (en test sale «Andres Matos»).
  - Métodos de pago (Configuración → Pagos): decidir si se permite **Link**.
    Funciona, pero guarda el método sin los cuatro últimos dígitos.
  - El endpoint de webhook live recibe `checkout.session.completed`,
    `invoice.paid` e `invoice.payment_failed`.
- [ ] **Meta**: añadir `console.auphere.com` a los dominios permitidos de la app
  (lo necesita la página del dueño, `/connect/whatsapp`).
- [ ] **Tratamiento fiscal** de las facturas decidido.
- [ ] **Correo**: el aviso de 3D Secure se envía con Resend
  (`auphere-charge-confirm-*`). Sin `RESEND_API_KEY` real en producción no sale
  el correo (el aviso en la consola sí). Desde la spec 051, además, las
  plantillas tienen que estar publicadas y `scripts/check_email_templates.py` en
  verde (`docs/correos.md`).
- [ ] **Admin en Vercel** (`auphere-admin`, admin.auphere.com): hoy se
  despliega a mano y sin Root Directory. Con el monorepo necesita
  **Root Directory `apps/admin`** e **«Include source files outside of the Root
  Directory»**, como `auphere-admin-staging` (creado el 2026-10-20 y que compila
  así).

## 1 · Copia de la base

- [ ] Snapshot manual del clúster Aurora de producción antes de migrar.

## 2 · Pausar la consola de producción

- [ ] Vercel → `auphere-console` → Settings → Git: desactivar los despliegues
  automáticos (o `gitProviderOptions.createDeployments = "disabled"` por API).

## 3 · Fusionar y desplegar la API

- [ ] Fusionar el PR `develop` → `main`.
- [ ] Aprobar `deploy-prod` en GitHub (entorno `production`). Espera a `ci`,
  corre la task de migración (**bloqueante**, `0158`→`0162`) y rueda los
  servicios.
- [ ] Comprobar la salud contra el ALB (no el hostname, que va por Cloudflare):

```bash
curl -s https://nexus-prod-317439020.eu-south-2.elb.amazonaws.com/health
```

## 4 · Soltar la consola y desplegar el Admin

- [ ] Reactivar los despliegues de `auphere-console` y redesplegar el último
  commit de `main`.
- [ ] Desplegar el Admin (`auphere-admin`) desde `main`.

## 5 · Comprobar en producción

- [ ] Entrar en la consola con un partner real: Panel, Facturación (sección
  «Tarjeta y cobro automático», correo de facturación editable), Teammate.
- [ ] Una compra de saldo pequeña con tarjeta real: el saldo sube una vez y el
  cobro tiene «Ver factura».
- [ ] Admin: Partners (columna Cobro), un partner → **Facturas**, Panel.
- [ ] Auditoría del partner: las acciones nuevas se leen en frases.

## Si algo va mal

| Síntoma | Causa y salida |
|---|---|
| Consola: «sin acceso» al entrar | La consola nueva habla con la API vieja. Paso 2 saltado: esperar a que `deploy-prod` termine, o volver a desplegar la consola anterior en Vercel |
| Facturación: «Stripe no aceptó la petición: …» | El mensaje es el de Stripe. Ajustar la cuenta (métodos de pago, datos) según lo que diga |
| Un pago de saldo no sube el saldo | Mirar en el log `metering.billing_event_ignored`. El webhook debe estar suscrito a `checkout.session.completed` |
| Un cobro se queda en «Falta confirmar» | El cron lo liquida solo en ≤5 min si Stripe ya lo cobró (`partner_charges.refreshed`) |
| La migración falla | `deploy-prod` no rueda ningún servicio: producción sigue con la versión anterior. Restaurar no hace falta; corregir y volver a lanzar |
