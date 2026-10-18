# Especificación: el panel de Auphere se ordena

**Rama**: `031-el-panel-se-ordena` · **Creada**: 2026-10-18 · **Estado**: Aprobada para plan

**Entrada**: petición del owner del 2026-10-18 — «la consola de Partners cambió mucho y
el Super Admin se quedó atrás; actualizar la UI, mejorar las vistas, ordenar el sidebar
como el super admin de Chatwoot y ver desde el admin la información de partners y
clientes». Plan aprobado: `~/.claude/plans/necesitamos-trabajar-en-la-lazy-quail.md`.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. El panel de operador ya es una superficie abierta; no entra nada de fuera |
| **Garantías de aislamiento tocadas** | **Ninguna nueva.** Las lecturas nuevas (`/admin/overview`, miembros de un partner, cifras agregadas) van tras `require_admin_token`, que es la puerta de Auphere. Las que lean tablas con RLS forzada por partner fijan el GUC del partner del path (`apply_partner_to_session`), igual que hoy `partner_wallet.py` |
| **Nota de KB que la justifica** | `[[ADR-042-el-panel-de-auphere-se-ordena]]` · `[[audit-admin-2026-05-25-clase-mundial]]` (BL-2, consistencia) · `[[PLAN-ADMIN-INTERNO-2026-08-23]]` (F0: ficha de partner) |
| **Qué se mide** | Nada: no consume modelo, máquina ni herramienta de pago |

## Origen

Medido en el código el 2026-10-18 (`main` = `develop` = `28a5b562`):

1. **Dos sistemas de diseño.** La consola usa `@nexus/ui` (tokens OKLCH, modo oscuro,
   tablas, métricas, paleta de comandos). El panel tiene 22 copias propias de shadcn,
   tokens en hex y una escala de espaciado no lineal (`--spacing-1..9`) que hace que
   `h-7` mida 48 px: es la causa documentada de los controles desproporcionados. No
   hay `ThemeProvider`: el modo oscuro no se puede alcanzar.
2. **Navegación plana.** Seis entradas en un solo grupo «Operación», con nombres en
   inglés («Tenants», «Connectors», «Auphere channels»), sin inicio, sin buscador.
3. **Partners a medias.** El listado enseña nombre, estado, tope de difusión y fecha.
   La ficha no enseña ni deja editar el correo de facturación, no dice si la consola
   está encendida, cuántos clientes ni cuántas personas tiene, ni su saldo. La tabla
   de clientes del partner muestra un UUID truncado sin enlace.
4. **Clientes sin partner.** El listado de clientes no tiene columna de partner,
   búsqueda ni filtros; la ficha del cliente no dice de qué partner es salvo en
   Facturación y Acceso.
5. **La pestaña Agente es un scroll de 5–7 pantallas** con cuatro asuntos distintos
   (auditoría 2026-05-25, BL-2). La ruta `tenants/[id]/integrations` es una sombra que
   solo redirige.
6. **Copias obsoletas**: «Empresas SaaS que embeben el widget de WhatsApp» (el widget
   se retiró en `9827d156`).

La referencia de organización es el super admin de Chatwoot
(`/Users/matos/workspace/chatwoot`, `app/helpers/super_admin/navigation_helper.rb`,
`app/views/super_admin/accounts/show.html.erb`): un inicio, grupos «Gestionar» e
«Instancia», fichas con cabecera de hechos y pocas pestañas.

## Clarifications

### Session 2026-10-18

- Q: ¿Se migra el panel al design system de la consola o se retocan sus copias? → A: **Se migra a `@nexus/ui`** (owner).
- Q: ¿Qué ordena el sidebar? → A: **El modelo de Chatwoot** (owner): Panel arriba, grupos con nombre, todo en español.
- Q: ¿Roles de operador en esta spec? → A: **No.** Hoy quien es operador ve todo (decisión 7 de PLAN-ADMIN-INTERNO). Queda como spec futura.
- Q: ¿El tier de membresía se pinta en Partners? → A: **No mientras las membresías estén apagadas** (spec 034). La columna vuelve cuando vuelvan.
- Q: ¿La pestaña Módulos? → A: La añade la spec 032; esta deja la ficha preparada.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El operador se orienta en un vistazo (Prioridad: P1)

Al entrar, el operador aterriza en un **Panel** que dice cuántos partners y clientes
están activos, cuánto saldo tienen los partners en total, cuántos tickets y altas
esperan y qué clientes se han quedado sin tope, con un bloque «Necesita tu atención»
que enlaza a cada caso. El sidebar agrupa las vistas como en Chatwoot y todo está en
español.

**Por qué esta prioridad**: es lo primero que ve el equipo cada día y es lo que hoy no
existe: el panel abre directamente en una tabla.

**Prueba independiente**: con dos partners y tres clientes sembrados (uno sin tope),
entrar y comprobar cada cifra del Panel contra la base de datos y que cada fila de
atención lleva a su ficha.

**Escenarios de aceptación**:

1. **Dado** un operador con sesión, **cuando** abre `/`, **entonces** ve el Panel y
   no una redirección a la lista de clientes.
2. **Dado** el sidebar, **cuando** se lee, **entonces** muestra Panel; Gestionar
   (Partners, Clientes, Altas, Tickets); Plataforma (Conectores, Canales de Auphere,
   Playground QA); Instancia (Estado), en ese orden.
3. **Dado** un ticket abierto y un cliente con tope agotado, **cuando** abre el Panel,
   **entonces** «Necesita tu atención» los nombra y enlaza a su ficha.
4. **Dado** que no hay nada pendiente, **cuando** abre el Panel, **entonces** una
   línea tranquila lo dice; no hay bloque vacío.

---

### Historia 2 — Un solo aspecto con la consola, en claro y en oscuro (Prioridad: P1)

El panel se ve con los mismos tokens, controles, tablas, estados y tipografía que la
consola de Partners. El operador elige claro, oscuro o sistema desde su menú.

**Por qué esta prioridad**: dos sistemas de diseño divergen a cada cambio; los
controles de 48–96 px son el defecto visual más visible del panel.

**Prueba independiente**: recorrer todas las rutas a 390, 768 y 1440 px, en claro y en
oscuro, y comprobar que no hay controles de más de 36 px de alto salvo los que la
consola también tiene, ni colores fuera de los tokens (lint de `@nexus/ui`).

**Escenarios de aceptación**:

1. **Dado** cualquier pantalla, **cuando** se construye el panel, **entonces** el lint
   `@nexus/ui/eslint` pasa sin avisos.
2. **Dado** un operador, **cuando** cambia a oscuro en su menú, **entonces** todas las
   pantallas cambian y la elección persiste al volver.
3. **Dado** un botón por defecto, **cuando** se mide, **entonces** su alto es el de la
   consola (32 px).

---

### Historia 3 — La ficha de un partner cuenta todo lo que importa (Prioridad: P1)

La ficha del partner abre con una cabecera de hechos (estado, consola encendida o no,
creado, clientes, personas, saldo disponible) y pestañas ordenadas: **Resumen ·
Clientes · Equipo · Dinero · Configuración · Conocimiento · Auditoría**. En Resumen se
editan nombre, correo de contacto y correo de facturación. Clientes enlaza cada fila a
la ficha del cliente y suma sus cifras de uso. Equipo enseña las personas del partner
con su rol, estado y último acceso, y las invitaciones pendientes.

**Por qué esta prioridad**: el owner lo pidió explícitamente («ver desde la consola de
super admin la información de nuestros partners y clientes»).

**Prueba independiente**: sembrar un partner con dos clientes y tres personas (una
invitada), abrir la ficha y comprobar cada hecho y cada enlace.

**Escenarios de aceptación**:

1. **Dado** un partner, **cuando** el operador cambia su correo de facturación,
   **entonces** se guarda, la auditoría lo registra con antes y después, y la ficha lo
   enseña.
2. **Dado** un partner con dos clientes, **cuando** abre Clientes, **entonces** cada
   fila lleva a `/tenants/{id}` y muestra mensajes, coste y estado del WhatsApp.
3. **Dado** un partner con una invitación pendiente, **cuando** abre Equipo,
   **entonces** la persona aparece como «Invitación pendiente».
4. **Dado** el listado de partners, **cuando** el operador busca por nombre o slug o
   filtra por estado, **entonces** la tabla se reduce sin recargar la página.

---

### Historia 4 — Un cliente siempre dice de quién es (Prioridad: P2)

El listado de clientes tiene columna de partner (enlazada), búsqueda por nombre o slug
y filtros por estado, partner y plan. La cabecera de la ficha del cliente nombra a su
partner. La pestaña Agente se divide en **Prompt · Runtime · Versiones · Evals**.

**Prueba independiente**: con clientes de dos partners, filtrar por uno y abrir una
ficha; entrar en Agente → Versiones directamente por URL.

**Escenarios de aceptación**:

1. **Dado** un cliente de un partner, **cuando** se abre su ficha, **entonces** la
   cabecera enlaza al partner.
2. **Dado** `?section=versions` en Agente, **cuando** se abre, **entonces** se ve solo
   el historial de versiones.
3. **Dado** `/tenants/{id}/integrations`, **cuando** se pide, **entonces** responde 404
   (la ruta sombra deja de existir; sus enlaces ya apuntan a Canales).

---

### Historia 5 — Buscar cualquier cosa sin navegar (Prioridad: P2)

⌘K abre una paleta que encuentra partners, clientes y tickets por nombre, slug o
referencia, y las vistas del sidebar.

**Escenarios de aceptación**:

1. **Dado** un cliente «Mouna», **cuando** el operador escribe «mou» en la paleta,
   **entonces** aparece y Enter abre su ficha.

---

### Historia 6 — Estado de la instancia (Prioridad: P3)

`/status` dice si la API responde, en qué entorno, qué versión de esquema tiene la base
de datos y qué commit está desplegado.

**Escenarios de aceptación**:

1. **Dado** la API caída, **cuando** se abre Estado, **entonces** la pantalla lo dice
   en estado de error, sin romper el resto del panel.

### Casos límite

- La API no responde: cada vista pinta su estado de error con reintento; el shell y el
  sidebar siguen.
- Un partner sin clientes ni personas: las pestañas enseñan su vacío con una frase,
  sin tabla vacía.
- Pantallas de 390 px: el sidebar pasa a hoja deslizante; las tablas se desplazan en
  horizontal dentro de su tarjeta, nunca la página.
- **Capacidades ausentes** (§V): sin membresías (spec 034) no se pinta columna de
  tier; sin la spec 032 no hay pestaña Módulos. Nada se pinta apagado.

## Requisitos *(obligatorio)*

### Requisito 1 — Un solo sistema de diseño

**Historia de usuario:** Como equipo de Auphere, quiero que el panel use `@nexus/ui`,
para que un cambio de diseño llegue a las dos consolas a la vez.

#### Criterios de aceptación

1. El panel DEBE importar tokens, primitivas y componentes de marca de `@nexus/ui` y NO DEBE contener copias locales de primitivas que el paquete exporta.
2. El panel DEBE pasar `@nexus/ui/eslint` (`recommended`) con cero avisos.
3. El panel DEBE ofrecer tema claro, oscuro y de sistema desde el menú del usuario, y WHEN el operador lo cambia THEN el sistema DEBE aplicarlo a todas las pantallas y recordarlo.
4. El panel DEBE usar la familia tipográfica de los tokens (Inter).
5. El panel DEBE instalarse desde el workspace raíz con un solo lockfile.

### Requisito 2 — Navegación ordenada

**Historia de usuario:** Como operador, quiero un sidebar agrupado y en español, para
encontrar cada vista sin pensar.

#### Criterios de aceptación

1. El sidebar DEBE declarar, en este orden: Panel; Gestionar (Partners, Clientes, Altas, Tickets); Plataforma (Conectores, Canales de Auphere, Playground QA); Instancia (Estado).
2. WHEN una ruta hija está abierta THEN el sistema DEBE marcar como activa su entrada del sidebar.
3. El sidebar DEBE poder plegarse a iconos (⌘B) y recordar su estado.
4. WHEN el operador pulsa ⌘K THEN el sistema DEBE abrir una paleta que busca vistas, partners, clientes y tickets.
5. Tickets DEBE mostrar el número de tickets abiertos junto a su entrada, y NO DEBE mostrar contador cuando es cero.

### Requisito 3 — Panel de inicio

#### Criterios de aceptación

1. WHEN el operador abre `/` THEN el sistema DEBE mostrar: partners activos, clientes activos y pausados, saldo disponible total de los partners en US$, tickets abiertos, altas pendientes y clientes sin tope.
2. IF hay tickets abiertos, altas pendientes o clientes sin tope THEN el sistema DEBE listarlos en «Necesita tu atención» con enlace a su ficha.
3. IF no hay nada pendiente THEN el sistema DEBE decirlo en una línea, sin bloque vacío.
4. IF una de las cifras no se puede leer THEN el sistema DEBE pintar esa tarjeta en error y las demás normales (estado `parcial`).

### Requisito 4 — Partners

#### Criterios de aceptación

1. El listado de partners DEBE mostrar nombre y slug, estado, consola encendida o no, clientes, personas, saldo disponible en US$ y fecha de alta.
2. WHEN el operador escribe en la búsqueda o elige un estado THEN el sistema DEBE filtrar la tabla.
3. La ficha DEBE abrir con una cabecera de hechos y las pestañas Resumen, Clientes, Equipo, Dinero, Configuración, Conocimiento y Auditoría.
4. WHEN el operador guarda nombre, correo de contacto o correo de facturación THEN el sistema DEBE persistirlos y escribir auditoría con antes y después.
5. La pestaña Clientes DEBE enlazar cada cliente a su ficha y mostrar sus cifras de uso de 30 días.
6. La pestaña Equipo DEBE listar las personas del partner con rol, estado y último acceso, y las invitaciones pendientes.
7. El sistema NO DEBE mostrar la copia retirada del widget de WhatsApp.
8. Las rutas antiguas de la ficha (`keys`, `tenants`, `limits`, `usage`, `wallet`, `models`, `receipts`) DEBEN redirigir a la pestaña nueva que las contiene.

### Requisito 5 — Clientes

#### Criterios de aceptación

1. El listado de clientes DEBE mostrar el partner de cada cliente, enlazado a su ficha.
2. WHEN el operador busca o filtra por estado, partner o plan THEN el sistema DEBE filtrar la tabla.
3. La cabecera de la ficha de un cliente con partner DEBE enlazar al partner.
4. La pestaña Agente DEBE dividirse en Prompt, Runtime, Versiones y Evals, seleccionables por `?section=`.
5. La ruta `tenants/[id]/integrations` NO DEBE existir.
6. Las pestañas de la ficha DEBEN nombrarse en español.

### Requisito 6 — Estado de la instancia

#### Criterios de aceptación

1. WHEN el operador abre `/status` THEN el sistema DEBE mostrar si la API responde, el entorno, la revisión de Alembic y el commit desplegado.
2. IF la API no responde THEN el sistema DEBE mostrar el estado de error en esa vista.

### Requisito 7 — Estados honestos

#### Criterios de aceptación

1. Toda vista que lee de la API DEBE pintar cargando, vacío y error con los componentes de `@nexus/ui`.
2. WHERE un dato no aplica (membresías apagadas, módulos aún no existen) EL sistema NO DEBE pintar ni columna ni control apagado.

### Entidades clave

- **Partner** (plataforma, sin RLS: lo lee la puerta de la consola antes de que exista
  ámbito). Gana en la respuesta del admin: `billing_email`, `console_enabled`,
  `companion_enabled`, `activated_at`, `clients_count`, `members_count`.
- **Persona del partner** (`partner_memberships`, `partner_invitations`): se leen
  por partner del path.
- **Resumen de instancia**: agregado de solo lectura; no persiste nada.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ninguna primitiva duplicada: `apps/admin/src/components/ui/` no existe.
- **CE-002**: lint de `@nexus/ui` con cero avisos en el panel.
- **CE-003**: desde el Panel se llega a cualquier partner, cliente o ticket pendiente en 1 clic, y a cualquier vista en ≤ 3.
- **CE-004**: las cifras del Panel coinciden con la base de datos en la prueba sembrada.
- **CE-005**: todas las rutas se ven sin desbordes a 390, 768 y 1440 px, en claro y oscuro.

## Fuera de alcance

- Roles de operador y permisos por rol en el panel — spec futura «Operadores».
- Ajustes de instancia editables — la configuración es de entorno.
- Importes en US$ exactos del saldo y la recarga — los fija la spec 033 (aquí se
  pinta lo que la API ya da, convertido con la misma función de la consola).
- Módulos por partner — spec 032.

## Supuestos

- El despliegue de Vercel del panel admite el workspace raíz (Root Directory
  `apps/admin` con «Include source files outside of the Root Directory»), igual que la
  consola.
- `develop` y `main` parten del mismo commit (`28a5b562`).
