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
| Gestionar | Partners · Clientes (`/tenants`) · Consumo (`/usage`) · Altas · Tickets (con contador de abiertos) |
| Plataforma | Canales (`/channels`) · Conectores (`/connectors`) · Números de Auphere (`/auphere/channels`) · Playground QA (`/qa`) |
| Instancia | Estado (`/status`) |

⌘K abre una paleta que busca vistas, partners, clientes y tickets abiertos.

Las migas viven en la barra superior (`components/shell/crumbs.ts`) y dicen el recorrido
completo: «Clientes › Volumen 03 › Canales › WhatsApp». Las páginas no las repiten ni
ponen una etiqueta encima del título. El nombre de cada registro lo anuncia su página con
`<CrumbName>`.

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
| Dinero | Saldo recargado, pool semanal y asignado en US$; recarga en dólares con confirmación e idempotencia; «¿cuadra el libro?»; movimientos con tipo (spec 033); tarjeta, modo de cobro, cobros y la línea de crédito del pospago (spec 041); recibos |
| Configuración | Límites, modelos, claves API e impersonación |
| Conocimiento · Auditoría | Sin cambios |

Las rutas antiguas (`keys`, `tenants`, `usage`, `wallet`, `receipts`, `limits`,
`models`) redirigen a la pestaña que las contiene.

## Consumo (`/usage`, spec 038)

Lo que gastan todos los partners y sus clientes, por periodo (este mes, 7, 30 o 90 días).
Lee `GET /admin/usage`.

- **Cifras.** Hay cuatro:
  - gasto de los clientes, a precio de venta y del libro de cada partner;
  - coste interno, lo que el modelo le costó a Auphere, incluido el Playground;
  - margen;
  - mensajes, con las conversaciones y los clientes activos.
- **Gráfico.** Gasto por día.
- **Tablas.** Por partner (gasto, fuera de clientes, coste interno, mensajes, saldo disponible) y por cliente (gasto, coste interno, mensajes, conversaciones). Cada fila abre su ficha.
- **Clientes directos.** Los de Auphere no tienen saldo de partner: salen «Sin saldo» y solo cuentan su coste interno.

Consumo también enseña la **ganancia** (spec 039): venta, coste del modelo de esos mismos turnos (`usage_records`), ganancia, margen y «se cobra sobre el coste» frente a la tarifa fijada (2,2×). Las pruebas del Playground van aparte y solo restan de la ganancia neta.

## Conectar WhatsApp desde el dispositivo del dueño (spec 040)

En el paso «Conectar WhatsApp» del asistente, la primera opción es **enviar un enlace al dueño** del negocio.
- Lo abre en su teléfono o su computadora, donde ya tiene su cuenta de Meta, y conecta él mismo el número (coexistencia o Cloud API).
- El enlace sirve una vez, caduca a los 7 días y se puede anular desde Canales.
- La página del dueño vive en la consola. El enlace (`/connect/whatsapp/{token}`) pasa el token a una cookie httpOnly y redirige a `/connect/whatsapp`, así que el token no queda en la dirección, el historial ni el `Referer`.

## Lista de clientes (`/tenants`, spec 036)

- **Vistas en pestañas con contador.** Son Todos, Necesitan atención, Activos, En pausa y Archivados. «Todos» no incluye los archivados.
- **Necesita atención** el cliente con un canal con problemas, un conector por reconectar, sin canal, con el agente sin publicar o a medio montar. El motivo sale en palabras en la columna Estado.
- **Columnas.** Son Cliente (con su partner), Canal (logo y número), Agente, Actividad y Estado. La Mensualidad solo aparece si algún cliente tiene plan mensual.
- **Orden.** Por defecto va primero lo urgente; también se ordena por actividad o por nombre. Búsqueda, vista, orden y filtros viven en la dirección.
- **Datos.** Salen de `GET /admin/tenants-health`, que lee cada cliente con su GUC.

## Ficha de cliente (`/tenants/{id}`)

- **Cabecera.** Lleva nombre con su estado, una línea de contexto (partner, plan, mercado, zona), «Probar agente», Acciones y cuatro hechos enlazados: canal, agente, última conversación y esta semana.
- **Pestañas.** Son el mismo `NavTabs` que la ficha del cliente en la consola de Partners, con el rótulo de cada grupo (spec 037):
  - Observar: Resumen, Conversaciones, Playground, Auditoría, Aislamiento.
  - Configurar: Agente, Habilidades, Acceso, Facturación.
  - Conectar: Canales, Conectores, Canal del dueño.

  Canales lleva un punto si ningún canal atiende o alguno tiene problemas. La ficha del partner usa el mismo componente con Observar, Configurar y Cuenta.
- **Agente.** Como en la consola: «Nuevo borrador» a partir de la versión activa (solo el prompt) y una tarjeta por versión con «⋯» para publicar, revertir o ver el prompt. Debajo van las capacidades del runtime y las evaluaciones.
- **Habilidades.** El catálogo de la consola, con un interruptor por habilidad que guarda en el borrador. Se sirve en `GET/PUT /admin/tenants/{id}/capabilities`, con el mismo código que la consola y la auditoría firmada por el operador.
- **Playground.** El de `/qa/{cliente}/chat`, dentro de la ficha. «Probar agente» lleva aquí.
- **Resumen.** A dos columnas. A la izquierda va lo que falta para operar, solo lo pendiente y con lo hecho plegado; con todo hecho es una línea. Debajo, las conversaciones recientes. A la derecha, los datos del cliente y las pruebas del agente.
- **Conversaciones.** Nombra al contacto por su nombre o número y dice quién responde. El control es un botón «Tomar control» / «Devolver», que no aparece en las conversaciones resueltas.

Los logos de canales y conectores son las marcas de cada app (Simple Icons, CC0) sobre su
color, en `components/brand/brand-marks.ts`. Lo que no tiene marca usa la imagen del
catálogo o sus iniciales.

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
