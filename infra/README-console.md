# Despliegue de `apps/console` (consola de partners) — CP-33

**Decisión (2026-08-16): la consola se despliega en Vercel**, como
`apps/admin`, y habla con la API de AWS por HTTPS público. Es viable porque
desde ADR-032 la consola **no tiene base de datos**: la identidad (usuarios,
contraseñas, sesiones) vive en la API y el BFF solo guarda una cookie con un
token opaco. Su único secreto es la clave privada EdDSA con la que acuña
tokens de 60 s.

El `Dockerfile` de la consola se conserva por si algún día se lleva a
ECS/Fargate (ver "Alternativa" al final), pero no es el camino actual.

## Proyecto de Vercel

Igual que `infra/vercel/README.md` describe para el admin:

1. **Import Git repository** → el repo de Nexus.
2. **Root Directory**: `apps/console`. ← Crítico; sin esto Vercel construye
   la raíz del monorepo y falla.
3. Framework Next.js autodetectado; install/build/output los declara
   `apps/console/vercel.json` (incluye cabeceras anti-buffering para el SSE
   del playground y `maxDuration` de 300 s en esa función).
4. **Dominio**: `console.staging.auphere.com` para staging y
   `console.auphere.com` para producción (proyectos separados o entornos del
   mismo proyecto — el patrón del admin es un proyecto por entorno).

## Variables de entorno

| Variable | Valor | Notas |
|---|---|---|
| `NEXUS_BACKEND_URL` | `https://api.staging.auphere.com` | La API de AWS por HTTPS. Sin barra final. |
| `NEXUS_CONSOLE_JWT_PRIVATE_KEY` | clave privada Ed25519 (PEM, `\n` escapados) | Generar con `pnpm keys:generate`. **Una pareja por entorno.** |
| `NEXUS_CONSOLE_JWT_ISSUER` | `nexus-console` | Debe coincidir con la API. |
| `NEXUS_CONSOLE_JWT_AUDIENCE` | `nexus-api` | Idem. |
| `NEXUS_CONSOLE_ORIGIN` | `https://console.staging.auphere.com` | Origen propio (CSP/cookies). |
| `NEXUS_META_APP_ID`, `NEXUS_META_CONFIG_ID_WA_CLOUD_API`, `NEXUS_META_CONFIG_ID_WA_COEXISTENCE`, `NEXUS_META_GRAPH_API_VERSION` | de la app de Meta (los mismos valores que `meta_app_id` / `meta_config_id_*` de la API en ese entorno) | Opcionales: sin ellas Canales muestra la nota «el número lo conecta Auphere», sin botón (spec 016, R1.3). Con ellas, el botón real de Embedded Signup. |

**Meta, además de las variables**: el origen de la consola tiene que estar en
la app de Meta (`957213733862330`) → «Inicio de sesión con Facebook para
empresas → Configurar → Dominios permitidos para el SDK para JavaScript», o la
ventana de Embedded Signup se abre y Meta la rechaza. Añadidos el 2026-09-23:
`https://console.staging.auphere.com/` y `https://console.auphere.com/`. Los
identificadores de configuración están en «Configuraciones» de esa misma
sección (Cloud API `1976547999669619`, Coexistencia `27787800820807899`).

**Ojo con el ámbito en Vercel**: `console.staging.auphere.com` lo sirve el
entorno **Preview** (rama `develop`) del proyecto `auphere-console-staging`;
`Production` de ese proyecto es `auphere-console-staging.vercel.app` (rama
`main`). Una variable marcada solo «Production» no llega a staging. Las tres de
Meta estuvieron así desde el 19-ago hasta el 23-sep-2026, cuando se ampliaron a
«Production and Preview».

**No hay ninguna variable de Postgres.** Si ves `NEXUS_CONSOLE_DATABASE_URL`
en algún sitio, es de antes de ADR-032 y sobra.

## Lado API (AWS), antes de que la consola sirva de algo

1. **Secretos** (SSM/el mismo sitio que el resto):
   - `NEXUS_CONSOLE_ENABLED=true`
   - `NEXUS_CONSOLE_JWT_PUBLIC_KEY` — la pública de la pareja de Vercel. La
     API se niega a arrancar si la consola está encendida y falta.
   - `NEXUS_CONNECTOR_CONSENT_SECRET` — **obligatorio desde 2026-08-16**:
     firma los enlaces de consentimiento OAuth de conectores. Genera uno por
     entorno con `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
     Con el valor de desarrollo la API no arranca en prod.
2. **Migraciones**: `alembic upgrade head` (staging va por debajo; la cabeza
   es `0117_billing_events` desde la spec 005).
3. **CORS/ALB**: nada especial — la consola llama a la API desde el servidor
   (Server Components / Route Handlers), no desde el navegador.
4. **Alta del partner piloto**:
   ```bash
   uv run --project apps/api python apps/api/scripts/seed_console_memberships.py \
     --partner-slug facelad --owner-email owner@facelad.com --enable-console
   ```
   Imprime el enlace de invitación (`/invite/<token>`); quien lo abra pone su
   contraseña y entra. Para dev/piloto sin correo existe `--set-password`.

## Comprobación tras desplegar

- `GET https://console.staging.auphere.com/healthz` → 200.
- Login con el owner sembrado → portada con cifras reales.
- Si sale la pantalla "sin acceso": el partner no tiene `console_enabled` o
  la persona no tiene membership activo.
- Si todo da 401: la pública de la API no es la pareja de la privada de Vercel.

## Producción (corte AWS 2026-08-19)

Proyecto de Vercel **`auphere-console`** (rama de producción `main`, dominio
`console.auphere.com`). **Un proyecto por entorno**.

`prod.tfvars` ahora fija `https_enabled = true` y `extra_certificate_arns`
(webhooks.auphere.com). Un apply **sin** ese tfvars sigue planeando destruir
el listener HTTPS — no lo apliques así.

Antes de apply en `prod`: las claves de `app_secret_keys` (incluida
`NEXUS_CONSOLE_JWT_PUBLIC_KEY`) tienen que existir en `nexus/prod/app`.

La cabeza de Alembic en `develop` es `0117_billing_events`. Las seis últimas
(`0112`→`0117`) llegaron con las specs 003, 004 y 005 y **no se han ensayado
contra un dump de producción** (T016 de la spec 004): hazlo antes del apply en
`prod`. Secuencia completa en [`../docs/go-live-consola-y-teammates.md`](../docs/go-live-consola-y-teammates.md).

## Alternativa (ECS, no vigente)

Si más adelante se quiere la consola dentro de la VPC: `apps/console/Dockerfile`
ya construye la imagen standalone (puerto 3110, `HEALTHCHECK /healthz`, usuario
no root, build context = raíz). Haría falta ECR + task definition + servicio en
`infra/terraform/20-services` (hoy `for_each` sobre 5 servicios), regla de
listener en el ALB y SG con egreso solo hacia la API. Nada hacia Postgres.
