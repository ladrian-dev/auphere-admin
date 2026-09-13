# Go-live: la consola y la app de teammates, en staging y en producción

Qué hay que hacer, en qué orden, para que un partner pueda entrar en la consola
y operar la app de escritorio en los dos entornos desplegados.

**El código está construido y verde.** 409 tareas de las specs 001-005, `ci` en
verde y `./scripts/verify.sh` completo en verde. Lo que falta no es código: es
configuración que no existe todavía en AWS, en Stripe y en Vercel.

> Este documento es la secuencia. El cambio de cuenta de Stripe tiene su propio
> runbook en
> [`specs/005-membresias-y-cobro/runbook-migracion-cuenta.md`](../specs/005-membresias-y-cobro/runbook-migracion-cuenta.md);
> el detalle de cómo se cobra está en [`billing.md`](billing.md); el despliegue
> de la consola, en [`../infra/README-console.md`](../infra/README-console.md).

---

## La regla que ordena todo lo demás

Una definición de tarea que pide una clave ausente del secreto **no arranca**:

```
ResourceInitializationError: ... did not contain json key NEXUS_BILLING_API_KEY
```

Y el `apply` que la introduce se lleva por delante los cinco servicios del
entorno. De ahí el orden, que no se negocia:

**secreto primero → Terraform después → despliegue al final.**

Las cuatro claves nuevas de la spec 005 están **comentadas** en
`app_secret_keys` de [`variables.tf`](../infra/terraform/20-services/variables.tf)
precisamente por esto. Descomentarlas es el paso 3, nunca el paso 1.

Para meterlas en un secreto que ya vive, usa `add_app_secret_keys.sh`:

| Script | Para qué | Cuidado |
|---|---|---|
| `populate_app_secret.sh` | primer llenado | **sobrescribe**: compone el JSON desde cero. El 2026-08-19 se llevó las 3 claves de la consola |
| `refresh_app_secret.sh` | rotación de Aurora | solo reescribe las 4 URLs de base de datos |
| `add_app_secret_keys.sh` | **añadir claves nuevas** | parte de lo que hay, nunca borra, aborta si la clave ya existe con otro valor |

---

## Lo que falta, exactamente

De los diez campos de configuración que `develop` estrena, seis traen default
seguro y no hay que aprovisionarlos (`llm_proxy_required`,
`teammate_run_max_seconds`, `local_exec_wait_seconds`, `teammate_task_ttl_days`,
`partner_default_client_allocation_tokens`) o ya están en el secreto
(`device_token_secret`). **Las cuatro que importan** —ya dentro de
`nexus/staging/app` desde el 2026-09-13; en `nexus/prod/app` siguen ausentes:

| Clave | staging | producción |
|---|---|---|
| `NEXUS_CONSOLE_BASE_URL` | `https://console.staging.auphere.com` | `https://console.auphere.com` |
| `NEXUS_BILLING_API_KEY` | `sk_test_…` | `sk_live_…` |
| `NEXUS_BILLING_PUBLIC_KEY` | `pk_test_…` | `pk_live_…` |
| `NEXUS_BILLING_WEBHOOK_SECRET` | `whsec_…` (del endpoint de test) | `whsec_…` (del endpoint live) |

Las tres de `BILLING` **van juntas o no van**: `billing_enabled` es todo o nada
([`config.py`](../apps/api/src/nexus_api/config.py)), así que con dos de tres el
cobro sigue apagado y el despliegue miente.

Modo test y modo live viven **dentro de la misma cuenta de Stripe** pero son
catálogos distintos: productos, precios, clientes y webhooks separados. Cruzar
las claves es el único error que `sync_billing_catalog.py` existe para impedir.

---

## Fase 0 · Antes de tocar nada

- [ ] **Tratamiento fiscal.** Bloquea el **primer cobro real**, no staging.
      IVA europeo con ventanilla única e IVA chileno para una membresía de 20 $
      vendible a cualquiera. Es asesoría, no ingeniería
      ([`billing.md` §Precondición](billing.md)).
- [ ] **La cuenta del proveedor está a nombre de una persona física.**
      Comprobado el 2026-09-13 contra la cuenta de test: `business_name`
      «Andres Matos», `business_type` `individual`, país `ES`. Facturar
      membresías como particular es parte del problema fiscal de arriba, no algo
      aparte — y el cambio a la cuenta de la empresa tiene su propio runbook
      ([`runbook-migracion-cuenta.md`](../specs/005-membresias-y-cobro/runbook-migracion-cuenta.md)).
      **Ese cambio va antes de crear el catálogo live, no después**: rehacerlo
      contra otra cuenta es un comando, pero mover suscripciones ya vivas no.
- [ ] **T016 de la spec 004.** Ejecutar `0115` contra un dump de producción y
      probar el `downgrade()`. Van seis migraciones nuevas (`0112`→`0117`) sin
      ese ensayo. **Bloquea producción, no staging.**

---

## Estado: desplegado en producción el 2026-09-13

**El go-live se completó.** `main` en `89d93ef`, las doce migraciones
(`0106`→`0117`) aplicadas, los cinco servicios `COMPLETED` y el cobro encendido
en los dos entornos. El `/health` respondió `ok` en las 21 comprobaciones
minuto a minuto durante el despliegue: **ningún cliente perdió servicio**.

Lo que queda abierto no es ingeniería:

- **El tratamiento fiscal.** Con `sk_live_` en producción, la distancia entre
  desplegado y cobrando de verdad es un clic de un partner. La cuenta del
  proveedor está a nombre de una persona física (`business_type: individual`,
  ES) y aloja además otro negocio, cuyas compras llegan a nuestro webhook y
  terminan en `failed` por huérfanas —correcto, pero genera ruido—.
- **La app de escritorio sin firmar** (T057): se instala en las máquinas del
  equipo, no se distribuye a un partner.

Lo demás, para no volver a preguntarlo:

| | Estado |
|---|---|
| `api.staging.auphere.com/health` | **200** |
| `console.staging.auphere.com/healthz` | **200** — el proyecto de Vercel ya existe |
| `console.auphere.com/healthz` | **200** |
| `nexus/staging/app` | 42 claves, **las cuatro de la spec 005 ya dentro** |
| `NEXUS_CONSOLE_ENABLED` (staging) | `true` |
| Clave de Stripe en staging | `sk_test_…`, modo correcto |
| Endpoint del webhook | `…/webhook/billing`, **8 eventos exactos**, `enabled` |
| Catálogo en modo test | Pro 20 $ · Team 60 $ · Business 150 $, activos con `tier_code` |
| Portal del proveedor | configurado y activo |
| `apply` en workspace staging | **hecho**: las cinco tareas piden 4/4 claves |
| Los cinco servicios ECS | `COMPLETED`, 1/1, logs sin errores |
| El cobro en staging | **encendido**: el webhook responde `invalid signature` y ya no `billing closed` |
| Crons del planificador | 27 arriba, `expire_credit_cron` y `wallet_renewal_cron` incluidos |

Queda por hacer en staging, y las dos cosas bloquean el paso a producción:

1. **Los price ids en `membership_tiers`** (paso 1.6). Sin ellos el checkout no
   encuentra el precio del nivel.
2. **Un aviso real de Stripe.** Que el webhook conteste `invalid signature`
   prueba que las tres claves llegan, pero **no** que
   `NEXUS_BILLING_WEBHOOK_SECRET` sea el mismo con el que firma Stripe: un
   secreto que no case da exactamente esa misma respuesta. Firmarse uno mismo el
   aviso no vale —verificaría con la propia clave que se usó para firmar—, así
   que la prueba tiene que originarse en Stripe: «Send test event» en el
   endpoint, o `stripe trigger checkout.session.completed`.

---

## Fase 1 · Staging: la API y el cobro

Staging arranca con `NEXUS_ENVIRONMENT=staging`
([`taskdefs.tf:50`](../infra/terraform/20-services/taskdefs.tf)), así que el
guard de secretos **avisa pero no bloquea**. Conviene poner las cuatro claves
igual: sin `CONSOLE_BASE_URL`, staging cobra en modo test y manda el acuse a un
`localhost` sin decir nada.

**1.1 · Crear el catálogo en modo test.** Con la clave de test en el shell y en
ningún otro sitio:

```bash
BILLING_API_KEY=sk_test_... uv run --project apps/api python scripts/sync_billing_catalog.py --env staging --dry-run
```

```bash
BILLING_API_KEY=sk_test_... uv run --project apps/api python scripts/sync_billing_catalog.py --env staging --apply
```

Crea productos, precios, el **endpoint de webhook**
(`https://api.staging.auphere.com/webhook/billing`) y la configuración del
portal. Es idempotente por `metadata.tier_code`, así que correrlo dos veces es
seguro. Al terminar imprime los **price ids**, el **webhook signing secret** y
una lista de ajustes manuales — los de suscripción, que Stripe no expone por
API. El secreto se imprime en tu terminal y en ningún otro sitio.

> **No crees el webhook a mano en el dashboard.** El asistente nuevo de Stripe
> («Review and finish», *Destination 1 of 2*) ofrece crear dos destinos —uno
> `snapshot` y uno `thin`— y ninguno de los dos sirve:
>
> - Pone la URL **sin la ruta**: `https://api.staging.auphere.com` en vez de
>   `…/webhook/billing`. Los eventos llegan a la raíz de la API y nunca ven el
>   handler.
> - Marca **sus** eventos, no los nuestros. El `snapshot` trae 14 (los de
>   `billing.meter.*` y `billing_portal.*`, que no manejamos) y de los ocho que
>   el código necesita solo incluye `invoice.upcoming`. Falta
>   `checkout.session.completed`, que es el que activa la suscripción cuando
>   alguien paga: sin él, el cobro entra y el partner no recibe su nivel.
> - El `thin` no lleva el objeto en el payload, y
>   [`provider.verify_signature`](../apps/api/src/nexus_api/billing/provider.py)
>   construye el evento completo y lee `data.object`.
>
> Los ocho eventos exactos los declara `WEBHOOK_EVENTS` en el script, y
> coinciden uno a uno con lo que despacha
> [`billing/events.py`](../apps/api/src/nexus_api/billing/events.py). Deja que
> el script cree el endpoint.
>
> Si ya creaste destinos a mano, bórralos antes de correr el script: dos
> destinos a la misma URL duplican cada aviso y el que no case con
> `NEXUS_BILLING_WEBHOOK_SECRET` falla la firma, devuelve `400` y Stripe
> reintenta hasta desactivarlo. Y cuando el script te dé el `whsec_` nuevo,
> reemplaza el viejo con `--force`:
>
> ```bash
> AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh --force staging NEXUS_BILLING_WEBHOOK_SECRET
> ```

**1.2 · Meter las cuatro claves en el secreto de staging.**

```bash
export NEXUS_CONSOLE_BASE_URL=https://console.staging.auphere.com
export NEXUS_BILLING_API_KEY=sk_test_...
export NEXUS_BILLING_PUBLIC_KEY=pk_test_...
export NEXUS_BILLING_WEBHOOK_SECRET=whsec_...
AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging \
  NEXUS_CONSOLE_BASE_URL NEXUS_BILLING_API_KEY \
  NEXUS_BILLING_PUBLIC_KEY NEXUS_BILLING_WEBHOOK_SECRET
```

No imprime valores: solo qué clave quedó añadida.

**1.3 · Descomentar las cuatro en Terraform.** En
[`variables.tf`](../infra/terraform/20-services/variables.tf), el bloque
«Membresías y cobro (spec 005)». Solo después de que 1.2 haya terminado bien.

**1.4 · Aplicar — con su `tfvars`, nunca sin él.**

```bash
terraform -chdir=infra/terraform/20-services workspace select staging
```

```bash
terraform -chdir=infra/terraform/20-services apply -var-file=staging.tfvars
```

`state_bucket` es la única variable sin default: sin el `-var-file` Terraform la
pide por consola y, si se deja vacía, los dos `terraform_remote_state` fallan
con «The value cannot be empty or all whitespace». Y lo que es peor, el plan
**sale mal en silencio**: sin `staging.tfvars` faltan también `https_enabled` y
`litellm_enabled`, así que el plan propone `https_enabled = true -> false`
—destruir el listener HTTPS— y borrar `litellm_secret_arn`.

**Si ves `https_enabled = true -> false` en un plan, no lo apliques.** Te falta
el `-var-file`. Lo mismo en producción con `prod.tfvars`, que además fija
`extra_certificate_arns` (webhooks.auphere.com).

**1.5 · Desplegar.** Push a `develop` dispara `deploy-staging`: espera a `ci` en
el mismo sha, construye, corre la task de migración (bloqueante: `0112`→`0117`)
y rueda los cinco servicios.

**1.6 · Escribir los price ids en la base de datos de staging.** Los `UPDATE`
que imprimió 1.1, contra la base de **ese** entorno. Los ids de test no sirven
en producción.

**1.7 · Comprobar.**

```bash
curl -s https://api.staging.auphere.com/health
```

- La consola responde `503 billing_unavailable` en las rutas de cobro → falta
  alguna de las tres claves de `BILLING`.
- El webhook responde `400` a una firma válida → el `whsec_` no es el del
  endpoint de **ese** modo.

---

## Fase 2 · Staging: la consola

Vive en **Vercel**, un proyecto por entorno, y habla con la API de AWS por HTTPS
público. No tiene base de datos (ADR-032): su único secreto es la clave privada
EdDSA con la que acuña tokens de 60 s.

**2.1 · Generar la pareja de claves — una por entorno.**

```bash
pnpm --filter console keys:generate
```

**2.2 · Proyecto de Vercel.** *Root Directory* `apps/console` (sin esto Vercel
construye la raíz del monorepo y falla). Dominio
`console.staging.auphere.com`. Variables:

| Variable | Valor |
|---|---|
| `NEXUS_BACKEND_URL` | `https://api.staging.auphere.com` (sin barra final) |
| `NEXUS_CONSOLE_JWT_PRIVATE_KEY` | la privada de 2.1, PEM con `\n` escapados |
| `NEXUS_CONSOLE_ORIGIN` | `https://console.staging.auphere.com` |
| `NEXUS_CONSOLE_JWT_ISSUER` | `nexus-console` |
| `NEXUS_CONSOLE_JWT_AUDIENCE` | `nexus-api` |

`NEXUS_META_APP_ID` y los `CONFIG_ID` son opcionales: sin ellos el botón de
Embedded Signup sale deshabilitado explicando por qué.

**2.3 · Lado API.** `NEXUS_CONSOLE_ENABLED` y `NEXUS_CONSOLE_JWT_PUBLIC_KEY` ya
están en `app_secret_keys`, así que el hueco existe — **comprueba los valores**:
`ENABLED` en `true` y la pública tiene que ser la pareja de la privada de 2.1.
Si no lo son, todo da 401. La API se niega a arrancar con la consola encendida y
la pública ausente.

**2.4 · Alta del partner piloto.**

```bash
uv run --project apps/api python apps/api/scripts/seed_console_memberships.py --partner-slug facelad --owner-email owner@facelad.com --enable-console
```

Imprime el enlace de invitación (`/invite/<token>`): quien lo abra pone su
contraseña y entra. Para piloto sin correo existe `--set-password`.

**2.5 · Comprobar.**

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://console.staging.auphere.com/healthz
```

Login con el owner sembrado → portada con cifras reales. Si sale «sin acceso»:
el partner no tiene `console_enabled` o la persona no tiene membership activo.

---

## Fase 3 · Staging: la app de teammates

**3.1 · Construir y empaquetar.**

```bash
pnpm --filter @nexus/desktop build && pnpm --filter @nexus/desktop package
```

**3.2 · Apuntarla a staging.** Los defaults van a producción
([`main.ts:59`](../apps/desktop/src/electron/main.ts)), así que para staging hay
que decírselo:

```bash
AUPHERE_API_URL=https://api.staging.auphere.com AUPHERE_CONSOLE_URL=https://console.staging.auphere.com
```

`AUPHERE_GATEWAY_URL` se queda en `http://localhost:5476`: el gateway corre en
la máquina del operador por diseño — la ejecución local es el punto de la spec
003.

**3.3 · Emparejar.** Desde la consola (*Workstation*) se genera un código
`XXXX-XXXX` con cuenta atrás; se teclea en la barra de la app. El token de
dispositivo lo firma `NEXUS_DEVICE_TOKEN_SECRET`, que ya está aprovisionado.

**3.4 · Límite conocido.** **La app no está firmada ni notarizada** (T057 de la
spec 001, bloqueada: en la máquina solo hay un certificado «Apple Development»,
que no sirve para distribuir, y los OV de Windows tienen plazo de entrega). Se
puede instalar en las máquinas del equipo salvando el aviso del sistema; **no se
puede distribuir a un partner** hasta que haya certificados. Para el piloto con
Facelad eso puede bastar; para vender, no.

---

## Fase 4 · Producción

Solo cuando staging esté verde de punta a punta, T016 esté hecha y la respuesta
fiscal esté encima de la mesa.

Misma secuencia que las fases 1-3, cambiando:

- `--env prod` y clave `sk_live_` en `sync_billing_catalog.py`. Pide escribir
  «prod» antes de aplicar.
- `NEXUS_CONSOLE_BASE_URL=https://console.auphere.com`.
- `add_app_secret_keys.sh prod`.
- Workspace `prod` en Terraform y `apply -var-file=prod.tfvars`: fija
  `https_enabled = true`, `state_bucket` y `extra_certificate_arns`
  (webhooks.auphere.com). Un apply **sin** ese tfvars planea destruir el
  listener HTTPS.
- Proyecto Vercel `auphere-console`, rama de producción `main`, dominio
  `console.auphere.com`. **Pareja de claves EdDSA propia**, distinta de staging.
- Merge a `main` dispara `deploy-prod` con la misma secuencia contra el
  workspace `prod`. Está protegido por revisores requeridos en el entorno
  `production` de GitHub.
- La app de teammates ya apunta a producción por defecto: no hay que exportar
  nada.

**Salud de producción: pega al ALB, no al hostname.** `api.auphere.com` va por
Cloudflare y hay redes que no alcanzan su borde — un timeout ahí no dice nada:

```bash
curl -s https://nexus-prod-317439020.eu-south-2.elb.amazonaws.com/health
```

---

## Si algo va mal

| Síntoma | Causa |
|---|---|
| El plan propone `https_enabled = true -> false` | Falta el `-var-file`. **No lo apliques**: destruye el listener HTTPS |
| `The value cannot be empty or all whitespace` en un `terraform_remote_state` | Terraform pidió `state_bucket` por consola y se dejó vacía. Es la única variable sin default: usa el `-var-file` |
| Los avisos de Stripe no llegan nunca al handler | El endpoint apunta a la raíz (`…auphere.com`) y no a `…/webhook/billing`. Lo hace el asistente del dashboard; deja que el script cree el endpoint |
| Se cobra pero el partner no recibe su nivel | El endpoint no está suscrito a `checkout.session.completed` |
| Las tasks no arrancan, `did not contain json key` | Terraform pide una clave que el secreto no tiene. Se saltó el orden: corre `add_app_secret_keys.sh` y vuelve a aplicar |
| La API no arranca en prod: «Refusing to boot… placeholder secrets» | Es el guard haciendo su trabajo. El mensaje nombra las claves que faltan |
| Rutas de cobro en `503 billing_unavailable` | Falta alguna de las tres de `BILLING`. Es todo o nada |
| El webhook devuelve `400` con firma buena | El `whsec_` es del otro modo (test vs live) |
| Toda la consola da 401 | La pública de la API no es la pareja de la privada de Vercel |
| Un partner paga y aterriza en `localhost` | Falta `NEXUS_CONSOLE_BASE_URL`. En prod ya no puede pasar: el guard lo impide. **En staging sí** |
| Faltan claves tras rotar Aurora | `refresh_app_secret.sh`, no `populate_` |
