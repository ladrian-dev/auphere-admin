# El panel de operador (`apps/admin`)

Spec viva del panel interno de Auphere. Se actualiza en el mismo commit que cambia lo
que describe. Origen: [spec 031](../specs/031-el-panel-se-ordena/spec.md).

## Qué es

El panel con el que el equipo de Auphere opera la plataforma: partners, clientes,
altas, tickets, conectores, canales propios, Playground QA y estado de la instancia.
Solo lo usan operadores; la identidad vive en la API (`/admin/auth/*`, ADR-034) y el
panel no tiene base de datos.

## Sistema de diseño

Desde la spec 031 el panel usa **`@nexus/ui`** como la consola de partners:

- Instala desde el workspace raíz (un solo `pnpm-lock.yaml`).
- `src/app/globals.css` solo importa `@nexus/ui/tokens.css`. No hay tokens propios.
- Tipografía Inter (`--font-inter`), tema claro/oscuro/sistema desde el menú del usuario.
- Lint `@nexus/ui/eslint` con `--max-warnings 0`: sin colores crudos, sin la paleta de
  Tailwind, espaciado en múltiplos de 4 px y radios `none | sm | md | full`.
- **Vercel**: el proyecto del panel necesita Root Directory `apps/admin` con «Include
  source files outside of the Root Directory» activado, como la consola.

## Navegación

Ordenada como el super admin de Chatwoot (`src/components/shell/nav.ts`):

| Grupo | Vistas |
|---|---|
| — | Panel (`/`) |
| Gestionar | Partners · Clientes (`/tenants`) · Altas · Tickets (con contador de abiertos) |
| Plataforma | Canales (`/channels`) · Conectores (`/connectors`) · Números de Auphere (`/auphere/channels`) · Playground QA (`/qa`) |
| Instancia | Estado (`/status`) |

⌘K abre una paleta que busca vistas, partners, clientes y tickets abiertos.

## Panel (`/`)

Lee `GET /admin/overview`: partners y clientes activos, saldo disponible total de los
partners (cada uno leído con su GUC), tickets abiertos, altas pendientes y clientes sin
tope. «Necesita tu atención» enlaza cada caso. Una sección ilegible se nombra en
`unreadable` y la pantalla se pinta parcial.

## Ficha de partner (`/partners/{id}`)

Cabecera con estado, consola, clientes, personas, saldo y alta. Pestañas:

| Pestaña | Contenido |
|---|---|
| Resumen | Nombre, correo de contacto y de facturación (editables y auditados); qué tiene encendido |
| Clientes | Uso de 30 días por cliente y mapeos `external_client_ref` → cliente, enlazados |
| Equipo | Personas (`GET /admin/partners/{id}/members`) e invitaciones pendientes |
| Módulos | Consola encendida y qué secciones y servicios tiene (spec 032): rejilla Operar · Cuenta · Asistente; el Companion se enciende aquí |
| Dinero | Saldo recargado, pool semanal y asignado en US$; recarga en dólares con confirmación e idempotencia; «¿cuadra el libro?»; movimientos con tipo (spec 033); recibos |
| Configuración | Límites, modelos, claves API e impersonación |
| Conocimiento · Auditoría | Sin cambios |

Las rutas antiguas (`keys`, `tenants`, `usage`, `wallet`, `receipts`, `limits`,
`models`) redirigen a la pestaña que las contiene.

## Ficha de cliente (`/tenants/{id}`)

La cabecera enlaza al partner (o dice «Cliente directo de Auphere»). La pestaña Agente
se divide en Prompt y herramientas · Runtime · Versiones · Evals (`?section=`).

## Canales y Conectores (spec 035)

Separados como las Bandejas y las Integraciones de Chatwoot.

- **Canales del cliente** (`/tenants/{id}/channels`): una fila por canal con
  «Configurar». «Añadir canal» abre un asistente de cuatro pasos: Elegir canal ·
  Conectar · Asignar agente · ¡Listo!. La ficha del canal tiene Ajustes (papel del número
  y si el agente responde), Agente, Plantillas (solo WhatsApp) y Salud (estado, envío de
  prueba, pausar o desconectar la conexión).
- **Catálogo de canales** (`GET /admin/channel-catalog`): WhatsApp, TikTok, Instagram,
  Telegram, X y Threads con su disponibilidad. Lo que no es `available` ni `beta` se
  enseña y no se puede iniciar (constitución §V 1.1.0, solo en este panel).
- **Conectores del cliente** (`/tenants/{id}/connectors`): rejilla con buscador, categoría
  y estado; sin WhatsApp ni TikTok, que son canales. La ficha de cada conector tiene sus
  acciones y el editor de permisos por herramienta: por defecto, siempre, pide
  aprobación o bloqueada.
- **Vistas globales**: `/channels` lista los canales de todos los clientes
  (`GET /admin/channels`) y `/connectors` el catálogo con cuántos clientes usan cada uno
  (`GET /admin/connectors-installs`). Las dos leen cliente a cliente con su GUC.

## Estado (`/status`)

`GET /admin/instance`: entorno, revisión de Alembic, commit de la imagen de la API
(`NEXUS_GIT_SHA`, lo pasan los workflows de despliegue) y si Postgres y Redis responden.

## Módulos por partner (spec 032)

`GET/PUT /admin/partners/{id}/access` con `X-Operator-Id`. Catálogo: `panel, clients,
usage, audit, knowledge, workstation, team, billing, keys, companion`. Con la consola
encendida hace falta al menos una sección del menú. El módulo `companion` escribe
`companion_enabled` en la misma transacción. La consola filtra menú, buscador, rutas y
burbuja; una sección sin módulo redirige al primer módulo del partner.

## Dinero (spec 033)

Todo en US$. La recarga (`POST /admin/partners/{id}/wallet/purchased`) lleva
`amount_cents`, la clave de idempotencia que genera el formulario y el operador; saldo,
asiento y auditoría van en una transacción. `GET …/wallet/reconcile` compara el saldo
recargado con el libro.
