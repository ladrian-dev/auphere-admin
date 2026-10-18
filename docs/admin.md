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
| Plataforma | Conectores · Canales de Auphere · Playground QA (`/qa`) |
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
| Dinero | Saldo, libro y recibos |
| Configuración | Límites, modelos, claves API e impersonación |
| Conocimiento · Auditoría | Sin cambios |

Las rutas antiguas (`keys`, `tenants`, `usage`, `wallet`, `receipts`, `limits`,
`models`) redirigen a la pestaña que las contiene.

## Ficha de cliente (`/tenants/{id}`)

La cabecera enlaza al partner (o dice «Cliente directo de Auphere»). La pestaña Agente
se divide en Prompt y herramientas · Runtime · Versiones · Evals (`?section=`).

## Estado (`/status`)

`GET /admin/instance`: entorno, revisión de Alembic, commit de la imagen de la API
(`NEXUS_GIT_SHA`, lo pasan los workflows de despliegue) y si Postgres y Redis responden.
