# Prototipo «Consola de partners v2»: marco, Operar y Cuenta

Especificación para reconstruir **tal cual** en la consola Next.js una parte del
prototipo aprobado, y lo que le falta hoy a la consola para parecerse.

- **Fuente**: `~/Downloads/Consola de partners v2/index.html` (`MODE = 'prototipo'`),
  capturas `proto/{home,usage,audit,guide,teammate,team,billing,api,notifications}-{light,dark}.png`
  del scratchpad del recorrido. Los números de línea son del `index.html`.
- **Alcance**: el documento de propuesta (`docView`), el marco (menú lateral, barra
  superior, migas, menú de usuario, plegar, ⌘K, campana y Notificaciones, avisos),
  las pantallas de Operar (Panel, Consumo, Auditoría, Guía del partner), las de Cuenta
  (Teammate, Equipo, Facturación, API), las gráficas y las acciones de esas pantallas.
  Clientes, ficha del cliente, agente y canales quedan fuera.
- **Consola comparada**: el worktree `047-recorrido-ui-9dd3dd`, **leído el 28 oct 2026
  entre las 17:30 y las 18:00 con cambios sin commit en curso** (otra sesión está
  alineando a la vez `console-shell-v2.tsx`, `PageHeader`, `tokens.css` y las
  cabeceras de varias páginas). Lo que ya vi alineado en el árbol se marca «ya
  alineado»; lo demás es brecha. Solo cuenta el marco v2 (`ConsoleShellV2`).
- **Rutas**: el prototipo navega por estado (`S.screen`, hash `#usage`…). En la
  consola cada pantalla es una URL: Panel `/`, Consumo `/usage` (Alertas
  `/usage/alerts`), Auditoría `/audit`, Guía del partner `/knowledge`, Teammate
  `/workstation`, Equipo `/team`, Facturación `/billing`, API `/keys`,
  Notificaciones `/notifications`.
- Los datos del prototipo son de ejemplo (`ACC`, `AUDIT`, `GUIDE`, `seed()`); lo que
  importa es la forma, el texto y el comportamiento.

---

## 0. Las brechas que más se ven (todas las pantallas)

Ordenadas por impacto visible. El detalle, en la sección de cada pantalla.

| # | Brecha | Prototipo | Consola hoy | Dónde | Datos |
|---|---|---|---|---|---|
| 1 | **Guía del partner sin cabecera de página** | `pageHead` con título de 40 px, subtítulo y raya; dos tarjetas (subir con zona de soltar, añadir URL) y tarjeta «Documentos» | `<h1>` de 16 px (`text-base`) sin `PageHeader`; formulario con `<input type=file>` y botón «Subir e indexar» | `app/(console)/knowledge/page.tsx`, `components/agent-tools/knowledge-table.tsx` (compartido con el conocimiento del cliente: separar la variante de partner) | Existen (`listPlaybook`) |
| 2 | **Botones más pequeños y con otra esquina en toda la consola** | `.btn` 36 px de alto, radio 8 px, 14 px 500; `.btn.sm` 30 px | `Button` `h-8` (32 px) y `sm` `h-7` (28 px), `rounded-sm` (4 px). El buscador del marco mide 28 px con radio 4 | `packages/ui/src/components/button.tsx` (tamaños y radio), `shell/console-command-palette.tsx` | — |
| 3 | **Conmutadores segmentados sin vidrio** | `.segm`: píldora de vidrio (`--glass`, borde `--line`, sombra), botones de 32 px y 14 px, activo con `--tab-on` | `rounded-md bg-muted p-1` con botones `text-xs` (Auditoría, Gasto por día) o píldoras con borde (Notificaciones) o radios nativos (tipo de clave, techo de ejecución) | `app/(console)/audit/filters.tsx`, `components/money/spend-by-day.tsx`, `components/notifications/notifications-list.tsx`, `components/keys/keys-list.tsx`, `components/workstation/local-exec-ceiling.tsx`; mejor un `SegmentedControl` en `@nexus/ui` con las clases de `TabsList floating` | — |
| 4 | **Facturación sin tarjetas ni composición** | Rejilla de dos columnas (Saldo de tu cuenta · Tarjeta y cobro automático), cantidades rápidas 20/50/100/250, todo en tarjetas, dinero en la moneda de la cuenta | Secciones sueltas de `max-w-lg` con títulos de 18 px, sin cantidades rápidas, etiquetas «(US$)» e «Importe en dólares» fijas, estado del recibo **sin traducir** («paid», «issued») | `app/(console)/billing/page.tsx`, `components/billing/{buy-credit-form,card-section,billing-email-form}.tsx`, `i18n/lanes/membership.ts` | Moneda de la cuenta: existe (`usageSummary().currency`). Cobrar en EUR: comprobar el checkout (hoy `MIN_USD`) |
| 5 | **Cifras de las tarjetas del Panel a 44 px** | `.kpi .kv b` 28 px 600 | `text-3xl`, que en los tokens es 44 px | `components/home/partner-panel.tsx` (`text-3xl` → 28 px) | — |
| 6 | **Panel: falta la tendencia de conversaciones** | «↑ 27 % más que los 7 días anteriores» en verde (`--accent-ink`) o «↓ … menos …» en ámbar | «Últimos 7 días» | `app/(console)/page.tsx` (ya calcula `trendDelta`), `components/home/partner-panel.tsx`; textos `hu.home.kpi.delta.*` | **Existen**: `home.conversations_trend.previous` llega en la misma respuesta de `GET /console/home` que `panel` |
| 7 | **Auditoría: «N más como esta» duplicado** | Una fila hija bajo el grupo: «2 más como esta» | «2 más como esta1 más como esta» pegados en la celda: se juntan dos veces (API `more_like_this` y `foldRepeats` del cliente) | `app/(console)/audit/audit-table.tsx` (quedarse con uno; el de la API, 49.1) | Existen |
| 8 | **Equipo, API y Notificaciones: listas sueltas, no tarjetas** | Cada lista en una `.card` con cabecera (título 15 px + recuento), filas `.connected` de 14×18 px | `ul` con `ring` y `h2` de 18 px fuera de la lista | `components/team/team-lists.tsx`, `components/keys/keys-list.tsx`, `components/notifications/notifications-list.tsx` | — |
| 9 | **Acciones de fila en línea en vez de «⋯»** | Claves (Rotar, Revocar), máquinas (Renombrar, Archivar) y miembros van en `rowMenu` «⋯» | Claves y máquinas: botones en la fila | `components/keys/keys-list.tsx`, `components/workstation/machines-list.tsx` (usar `RowActions menu`) | — |
| 10 | **Panel: las conversaciones por día sin franjas ni «los 3 con más actividad»** | 7 días × 4 franjas (madrugada, mañana, tarde, noche) y el tooltip con los 3 clientes de ese día | 7 columnas de un día, sin top-3 ni la nota de las franjas | `components/home/panel-model.ts` (`conversationColumns`) | Top-3: **existe** (`conversations_trend.by_client[].series`). Franjas: **cambio de API** (`conversations_per_day` por franja) |

Desviaciones **decididas** que no son brechas (spec 047): la campana abre un panel
con los 5 últimos y «Ver todas» (R47.3) en vez de ir a la página; en móvil el menú
pasa a una fila que se desplaza y el perfil se queda en la barra (el prototipo lo
escondía); Consumo por bolsas y partidas (requisitos 45 y 46); la matriz de permisos
en Equipo (49.2); el filtro «Fechas» de Auditoría; el enlace de salto «Saltar al
contenido». Se citan en su pantalla.

---

## 1. La propuesta (`docView`, l. 1008–1180): reglas y decisiones

El documento explica por qué el prototipo es como es. En `MODE = 'prototipo'` no se
pinta, pero manda.

**Tesis**: «Un cliente es un negocio. Un agente es quien lo atiende.» El cliente
guarda su ficha y su saldo; el agente guarda lo que hace, por dónde atiende y con
qué herramientas. Cada acción va donde el partner la piensa, con menos pantallas.

**Reglas del modelo** (lista numerada `.rules`):
1. Crear un cliente nunca crea un agente. El alta termina en el cliente.
2. La ficha baja, nunca sube: los agentes heredan sedes, horarios y servicios; lo
   que se enseña a un agente queda en ese agente.
3. Canales e integraciones son del agente. Publicado y conectado son estados
   independientes (un agente puede publicarse sin canal).
4. El saldo es una bolsa del cliente; todos sus agentes consumen de ella. Un agente
   puede tener tope mensual, no saldo propio.

**Qué cambia, tarea por tarea**: crear cliente = modal de 3 campos (nombre, nicho,
información adicional) que aterriza en el cliente; editar = el mismo modal desde
«Editar» o el menú de la tabla; saldo y consumo en el Panel del cliente (saldo,
consumido frente a asignado, días que quedan, agentes que más gastan); crear agente
= 1 pantalla con borrador en vivo, 5 clics hasta la primera prueba, termina en
«Guardar y conectar un canal»; conectar canal desde el agente con el flujo nativo.

**Flujos** (resumen): alta en modal, no en panel lateral (se hace a menudo y merece
foco); nicho libre con sugerencias que completan sin restringir; web, @usuario o
enlaces de redes en «Información» se colocan solos en la ficha y la web se lee en
segundo plano; zona horaria y moneda se deducen. Cliente con tres pestañas (Panel ·
Negocio · Agentes) y «Nuevo agente» a su altura; el Panel sustituye al Resumen y
lo que falta en la ficha se dice en una línea con su botón. Negocio es
configuración progresiva y cada sección dice de dónde viene (escrito por ti o leído
de la web). Editar usa el modal del alta con «Más ajustes» (zona, moneda,
archivar). Constructor en dos columnas que valida sus preguntas y cambia la derecha
al playground con «Pruébalo»; playground con 20 pruebas, revisión automática y
arreglo en un clic. No hay «Publicar»: el agente queda listo pero mudo hasta tener
canal; la configuración vive en cada canal (audiencia, escalado), en página propia,
desde «Configuración» del ⋯ del canal (que también ofrece «Pasar a otro agente»,
pausar, desconectar); el agente nunca pide números. WhatsApp: Coexistencia
(recomendado) o Cloud API, ventana de Meta con velo y errores con nombre propio,
catálogo opcional al volver, o enlace para el dueño (uno a la vez, pendiente y
revocable). Integraciones en el agente y en contexto.

**Saldo y consumo (decisión)**: bolsa del cliente con tope opcional por agente; un
número que vigilar por cliente; la barra del Panel se reparte por agente;
proyección con los últimos 7 días; avisos al 80 % y al 100 %; el modal de asignar
ofrece cantidades rápidas, otra cantidad y cuánto quedará en la cuenta del partner,
con aviso al 20 %; quien no puede asignar ve «Pedir saldo», no un botón bloqueado;
en la lista de clientes los saldos se comparan por días restantes y porcentaje, no
por importe (cada cliente tiene su moneda).

**Crítica**: Nielsen 29/40 (falla en consistencia y eficiencia); P0 modelo invertido
y alta que pide lo que no hace falta; P1 el Resumen no informa y «Revisar borrador»
sobra; P2 no se puede editar el cliente. Se queda: el playground con «Por qué falló»
y «Arreglar», la herencia explicada, publicar en prueba. Detector: tarjetas
anidadas, etiquetas sin `for`, sin media queries, contraste 3,6:1, filas sin foco,
pestañas sin `role="tab"`.

**Tres decisiones antes de construir**: audiencia del agente al canal; tarjetas
«Próximamente» aunque la constitución (§V) pide no mostrar lo que no se usa; moneda
del saldo (hoy todo en USD).

**Sistema visual** (lo que aplica a este documento):
- Evoluciona `@nexus/ui`: mismos tokens (verde Auphere, neutros con matiz verde,
  Inter con `ss01` y `cv11`).
- Primario en verde profundo (≈6,8:1 con texto claro) en vez del verde claro
  (≈2,4:1).
- 12 px solo para metadatos; el resto 13–14 px. Números tabulares en saldos y
  tablas. Modo oscuro diseñado, no invertido.
- Sin tarjetas dentro de tarjetas; una sola señal de progreso por pantalla. (Dice
  también «sin etiquetas de grupo», pero eso va por las pestañas del cliente: el
  menú lateral del prototipo sí lleva «Operar» y «Cuenta», y Andrés lo confirmó.)
- Pestañas con `role="tab"`; modales con foco y Escape; responsivo de 390 px a
  escritorio.
- **Liquid Glass con medida**: solo en la capa que flota (barra de pestañas fija,
  barra de acción, avisos, menús); nunca en tarjetas ni formularios; con «reducir
  transparencia» pasa a sólido.

**Preguntas al PO** (con su propuesta): asignan propietario y admin, el resto «Pedir
saldo»; al 100 % del tope el agente pasa la conversación a la Bandeja; bolsa en la
moneda del cliente y comparación por días; el nicho alimenta las pruebas del sector;
un agente en prueba se comporta como uno publicado al agotarse la bolsa.

---

## 2. Tokens y piezas comunes del prototipo

### 2.1 Tokens (`:root`, l. 9–73) y su equivalente en `@nexus/ui`

| Prototipo (claro / oscuro) | Uso | `@nexus/ui` |
|---|---|---|
| `--bg` oklch(.971 .006 185.3) / (.185 .012 182) | fondo del marco y del menú lateral | `--background` / `--sidebar` (bone / `ink-surface`) ✓ |
| `--surface` blanco / (.225 .014 182) | lienzo y tarjetas | `--card` ✓ |
| `--surface-2` (.955 .008 182) / (.26 .014 182) | hover, pistas, pies de modal | `--muted` (`sand` / `ink-sunken`) ✓ |
| `--ink`, `--muted` (70 %), `--faint` (45 %) | texto | `--foreground`, `--muted-foreground` ✓; `faint` ≈ `fg-subtle` |
| `--line` (12 %), `--line-strong` (22 %) | bordes | `--border` ✓; `line-strong` ≈ `--input` (45 %, más fuerte por 1.4.11) |
| `--primary` (.47 .095 168) / (.76 .12 167) | botón primario, foco | `--primary` (`bangladesh-green` / `mountain-meadow`) ✓ |
| `--accent` (.727 .138 167.3), `--accent-ink`, `--accent-soft` (12 %) | positivo, enlace, fondo del activo | `status-positive`, `--color-primary-text`, `status-positive-bg`; **el activo del menú lateral usa `--sidebar-accent` = pistachio, no `accent-soft`** |
| `--warn`, `--warn-ink`, `--warn-soft` | aviso | `status-warning`, `-text`, `-bg` ✓ |
| `--danger`, `--danger-soft` | error, sensible | `status-danger`, `-bg` ✓ |
| `--info`, `--info-soft` | pendiente, en prueba | `status-info`, `-bg` ✓ |
| `--s1..--s4` | series del gasto | `series-1`, `series-2`, `accent-mid`, `muted-foreground/50` (aprox.) |
| `--glass`, `--glass-edge`, `--glass-shadow`, `--tab-on` | capa flotante | `--glass-bg`, `--glass-edge`, `--glass-shadow`, `--tab-on` ✓ (ya alineado, árbol sin commit) |
| `--scrim` | fondo de modal | `--color-scrim` ✓ |
| `--r-sm 8 / --r-md 12 / --r-lg 16` | controles / tarjetas, menús / lienzo, modales (18) | `rounded-md 8`, `rounded-lg 12`, `rounded-xl 16` ✓ (ya alineado); **`Button` sigue en `rounded-sm` 4 px** |
| `--font` Inter, 14 px, `ss01` `cv11` | todo | ✓ |

Foco global: `outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 6px`
en `a, button, input, select, textarea, [tabindex], summary` (`:focus-visible`).
Movimiento reducido: todas las animaciones y transiciones a `.01ms` (l. 806).
Transparencia reducida: `.glass` a `--surface` sin desenfoque (l. 96).

### 2.2 Piezas que se repiten

- **`pageHead(título, sub, acciones)`** (l. 2043) → `.ph`: flex, `align-items:flex-end`,
  `justify-content:space-between`, `gap:16px`, wrap, `padding-bottom:20px`,
  `border-bottom:1px solid var(--line)`. `h1` 40 px / 1.1 / −0.03em / 600. `.sub`
  16 px `--muted`, `margin-top:6px`. `.acts` flex gap 8. **Sin eyebrow.**
  Consola: `PageHeader size="display"` ya da 40 px desde `sm`, `pb-5`, sin eyebrow
  (ya alineado en Panel, Teammate, Equipo, Facturación, API, Notificaciones y
  Alertas; **faltan Consumo y Auditoría**, que a las 18:05 ya no llevan eyebrow
  pero siguen con el tamaño por defecto, 44 px desde `md`, y la Guía, que no usa
  `PageHeader`).
- **`.page`**: `max-width:1240px`, centrado, rejilla de una columna, `gap:20px`.
- **`.card`**: `--surface`, borde `--line`, radio 12. `.card-h` flex
  space-between, `padding:16px 18px 0`, `h3` 15 px 600. `.card-b` `padding:14px 18px 18px`.
- **`rowMenu(id, items)`** (l. 2044): botón `.btn.sm.icon.ghost` (30×30) con
  `ellipsis` 16, `aria-haspopup="menu"`, `aria-expanded`, `aria-label="Más opciones"`;
  al abrir, `.menu.glass` `role="menu"` absoluto a la derecha, `top: 100% + 4px`,
  `min-width:200px`, `padding:6px`, radio 12; ítems `role="menuitem"` 14 px,
  `padding:8px 10px`, radio 8, icono 15 a la izquierda; `.danger` en rojo; `hr`
  separa. Un solo menú abierto a la vez (`S.menu`); un clic fuera lo cierra.
- **Modal** (`modalView`, l. 1728): `.scrim` fijo (`--scrim`, `fade .2s`) +
  `.box` `role="dialog" aria-modal="true" aria-labelledby="modal-t"`, ancho
  `min(var(--mw), 100%)` (620 por defecto; 480 confirmaciones y formularios cortos;
  520 invitar; 540 claves; 560 ⌘K), radio 18, sombra `0 24px 60px`, entrada `pop
  .26s cubic-bezier(.16,1,.3,1)`. `header` `padding:22px 24px 10px`, `h2` 21 px,
  `p` 14 px `--muted` máx. 56ch, botón cerrar `x` (`aria-label="Cerrar"`).
  `.body` con scroll, `padding:10px 24px 22px`, `gap:18px`. `footer` `padding:14px 24px`,
  borde superior, fondo `--surface-2`, a la izquierda una nota `.meta` y a la
  derecha «Cancelar» (ghost) + la acción primaria. Escape cierra; el campo con
  `data-autofocus` recibe el foco. (El prototipo no atrapa el foco: la consola sí,
  con `Dialog`.) Consola: `Dialog` es `max-w-sm` (384 px) por defecto, radio 16,
  `p-4`: **pasarle el ancho del prototipo en cada uso y subir el relleno a 24**.
- **Confirmación** (`MODALS.confirm`, l. 2071): 480 px, título + texto, cuerpo
  vacío, pie «Cancelar» + CTA; si es destructiva, la CTA es primaria con fondo
  `--danger`.
- **`.badge`**: 22 px, píldora, 12 px 500, punto de 6 px o icono de 12; tonos
  `t-positive | t-warn | t-danger | t-info | t-muted`.
- **`.segm`** (l. 776): ver brecha 3. `role="group"` o `"radiogroup"`/`"tablist"`
  según el caso, botones con `aria-pressed` (o `aria-checked`/`aria-selected`).
- **`.empty`**: centrado, `padding:40px 20px`, icono en baldosa de 44 px radio 12
  `--surface-2`, `h3`, `p` `--muted` máx. 52ch.
- **`.callout`**: flex gap 12, `padding:14px 16px`, radio 12, `--surface-2`, 14 px;
  `b` en tinta y el resto `--muted`.
- **`.minibar`**: 120×6 (o `width:100%`), pista `--surface-2`, relleno `--s1`;
  `.warn` y `.danger` cambian el relleno.
- **`.check`** (casilla en tarjeta): flex gap 12, `padding:14px 16px`, borde, radio
  12; casilla de 18 px `accent-color: var(--primary)`; `b` 500 y `span` 13 px muted.
- **`.radio`** (opciones en tarjeta): botones `role="radio"` `aria-checked`,
  `padding:12px`, borde `--line-strong`, radio 8; marcado: borde `--primary` + 1 px
  interior; punto de 16 px.
- **`.amounts`**: rejilla de 4 (2 en ≤520 px), gap 8, botones de 48 px, radio 10,
  17 px 500 tabulares; pulsado con borde primario y `--accent-soft`.
- **`.bigin`**: caja de importe grande (radio 12, `padding:12px 16px`, etiqueta
  13 px, input 30 px 600, moneda 18 px muted).
- **`.code`**: monoespaciada 12,5 px, `--surface-2`, borde, radio 10, con
  «Copiar» (`copy-code` → aviso «Copiado.»).

---

## 3. El marco

### 3.1 Composición y medidas (CSS l. 224–300, `appView` l. 1185–1218)

- `.app`: rejilla `256px minmax(0,1fr)`; plegado `64px minmax(0,1fr)`; transición
  de columnas `.25s cubic-bezier(.16,1,.3,1)` (nada con movimiento reducido).
  Desde 901 px el marco mide la ventana (`height:100dvh; overflow:hidden`) y **solo
  `.main` hace scroll** (`overscroll-behavior:contain`, barra fina). La posición
  de scroll se conserva entre renders y vuelve arriba al cambiar de pantalla.
- `.side` (menú lateral): fondo `--bg`, `padding:14px 12px 16px`, columna con
  `gap:22px`: logo, «Operar», «Cuenta», y el usuario al pie (`margin-top:auto`).
- `.wrap`: columna, `padding:0 16px 16px 0` (el lienzo queda a 16 px del borde
  derecho e inferior).
- `.topbar`: 56 px, `padding-left:10px`, a la izquierda plegar + migas; a la
  derecha buscador + campana (`gap:8px`).
- `.main` (lienzo): `--surface`, borde `--line`, **radio 16**, `padding:40px 48px 60px`
  (`28px 24px 48px` en ≤1100; `20px 16px 48px` en ≤900).

Consola (`components/shell/console-shell-v2.tsx`, 18:00): menú de 256 px y
plegado de 64 (ya alineado), lienzo `rounded-xl` (ya alineado). Brechas: barra
superior `min-h-12` (48 px) en vez de 56; el lienzo queda a 8 px del borde
(`shell:mr-2 shell:mb-2`) en vez de 16; relleno `px-8 py-8` (32) en vez de
40/48/60; `max-w-(--width-content)` 1280 en vez de 1240; `gap-6` (24) en vez de 20.

### 3.2 Menú lateral

De arriba abajo:
1. **Logo** (`.logo`, 40 px de alto): marca de 28 px en `--accent` + palabra
   «Auphere» de 20 px en tinta + píldora **«Beta»** (12 px 600, `--warn-soft` /
   `--warn-ink`, anillo de 1 px, `title="La consola de partners está en beta"`).
2. **«Operar»** (etiqueta `.gl`: 11 px, mayúsculas, `letter-spacing:.08em`, 600,
   `--muted`, `padding:0 10px 6px`): Panel (`layout-dashboard`), Clientes
   (`building-2`), Consumo (`chart-column`), Auditoría (`scroll-text`), Guía del
   partner (`book-open`), Teammate (`laptop`).
3. **«Cuenta»**: Equipo (`users`), Facturación (`receipt`), API (`key-round`).
   Notificaciones no está en el menú: se llega por la campana.
4. **Usuario** (`.me`): avatar de 28 px radio 6 en `--accent-soft`/`--accent-ink`
   con «LU», nombre «Luis Matos» (500) y «Propietario» (`.meta`).

Entrada (`a`, l. 243): 36 px, `padding:0 10px`, `gap:10px`, radio 8, **15 px, peso
normal, tinta**, icono de 17; hover `--surface-2`; la actual
`aria-current="page"` con fondo `--accent-soft` y peso 500. Cada `a` lleva
`title` con su nombre. La sección activa sale de la pantalla (cliente y agente
marcan Clientes; Notificaciones no marca nada).

Consola: entradas a 15 px en tinta con hover gris (ya alineado); etiquetas de grupo
a 12 px con `tracking-wider` (prototipo 11 px, .08em); **el activo pinta
`--sidebar-accent` = pistachio (`#AACBC4`) con texto pine, más oscuro y gris que el
`--accent-soft` del prototipo** (verde claro al 12 %). Cambiar `--sidebar-accent`
claro a `status-positive-bg` (o un token `nav-active`) en `tokens.css` y el texto a
tinta. Icono 16 px (prototipo 17), `gap-3` (12; prototipo 10). Plegado, la consola
añade un tooltip con el nombre (mejor que el `title`).

### 3.3 Menú de usuario (l. 1199–1211)

`.me` es un botón `aria-haspopup="menu"`, `aria-expanded`, `aria-label` = el correo.
Abre `.umenu.glass` `role="menu"` encima (`bottom: 100% + 6px`), 240 px,
`padding:6px`, radio 12:
1. Cabecera: **«Luis Matos»** (14 px 500), `luis@ladrian.studio` (mono, 12 px
   muted), «Partner: Ladrian Studio».
2. `hr` · «Tema» (12 px muted) · tres `menuitemradio` con icono de 15: `sun`
   «Claro», `moon` «Oscuro», `monitor` «Sistema»; el marcado lleva `check` 14 a la
   derecha en `--accent-ink`.
3. `hr` · «Idioma» · `globe` «English».
4. `hr` · `arrow-right` **«Cerrar sesión»** en rojo.

Elegir tema lo aplica (atributo `data-theme`, `localStorage aup-theme`) y cierra el
menú. Escape o un clic fuera lo cierran.

Consola (`profile-menu.tsx`): misma estructura y textos, 256 px. Brechas menores:
los tres temas no llevan icono (sol, luna, monitor) y la marca es la de
`DropdownMenuRadioItem`, no un `check` a la derecha; «English» lleva `Languages` y
«Cerrar sesión» `LogOut` (prototipo `globe`, `arrow-right`); el avatar es redondo de
32 px en `bg-accent` (prototipo cuadrado de 28 px radio 6 en `accent-soft`).

### 3.4 Plegar el menú

Botón `.collapse` (32×32, radio 8, `--muted`, icono `panel-left` 17) a la izquierda
de las migas; `aria-label` y `title` «Plegar menú» / «Abrir menú»;
`aria-expanded`. Plegado: 64 px, `padding` lateral 10; se ocultan con opacidad
(`.2s`) los nombres, las etiquetas de grupo (alto 0), la palabra, «Beta» y el texto
del usuario; las entradas se centran. Se recuerda (`localStorage aup-nav`).

Consola: igual, con cookie (sin salto al cargar) y `aria-controls`. Alineado.

### 3.5 Migas (`crumbs`, l. 1228)

`nav.crumbs aria-label="Ruta"`, 13 px `--muted`, `gap:6px`, separador
`chevron-right` 13. Los anteriores son botones (hover tinta + `--surface-2`); el
último es `span.cur aria-current="page"` en tinta. Páginas de primer nivel: una
sola miga con el título (`PAGE_TITLES`: Panel, Consumo, Auditoría, Guía del
partner, Teammate, Equipo, Facturación, API, Notificaciones). Subpágina: «Consumo ›
Alertas de consumo», con «Consumo» pulsable (`nav`).

Consola (`shell-breadcrumbs.tsx`, `crumbs-v2.ts`): igual, a 14 px y la actual en
500. En ≤640 px quedan las dos últimas. Alineado salvo el tamaño.

### 3.6 Buscador ⌘K (l. 2177–2186, teclado l. 2456)

- Disparador `.ksearch` (botón, `aria-label="Buscar y navegar"`): 36 px, mín.
  260 px, `padding:0 6px 0 12px`, borde `--line`, radio 8, `--surface`, «Buscar…»
  en `--muted` y la tecla «⌘K» (`.kbd`: 12 px, borde, radio 5). Se oculta en
  ≤560 px.
- ⌘K o Ctrl+K abre el modal `palette` (560 px, título solo para lectores «Buscar y
  navegar»). Cuerpo: input de 44 px y 16 px, placeholder **«Cliente, agente,
  acción…»**, `aria-label="Buscar"`, enfocado.
- Resultados (`palRes`), se filtran al teclear sin repintar el modal:
  - **«Clientes»**: los no archivados cuyo nombre contiene el texto. Fila
    `.palrow` (`building-2` + nombre + nicho a la derecha en `.meta`) → abre el
    cliente. Con texto escrito, bajo cada cliente dos filas sangradas
    (`corner-down-right`, `--muted`): «{cliente} · Agentes» y «{cliente} ·
    Negocio».
  - **«Acciones»** (filtradas por texto): «Nuevo cliente» (va a Clientes y abre el
    alta), «Equipo», «Claves de API», «Notificaciones», «Consumo», «Auditoría»,
    con `arrow-right`.
  - Nada: «Sin resultados para «{q}».»
- Pie: «↑↓ navegar · ↵ abrir · Esc cerrar» (en el prototipo las flechas no hacen
  nada; en la consola sí).

Consola (`ConsoleCommandPaletteV2`): busca en la API clientes (por nombre o
nicho), agentes y pantallas, con grupos Clientes, Agentes, Pantallas, Acciones;
mismos textos. Brechas: el disparador es `Button outline sm` de 256×28 px con radio
4 (prototipo 260×36, radio 8); las subfilas van en orden Negocio, Agentes
(prototipo Agentes, Negocio).

### 3.7 Campana (l. 1214, 600–602)

Botón `.bell` de 36×36, radio 8, **con borde `--line`** y fondo `--surface`, icono
`bell` 17 `--muted` (tinta al pasar), `aria-label="Notificaciones"`. Recuento
`.bcnt` si hay sin leer: arriba a la derecha (−5 px), 18 px mín., `padding:0 5px`,
`--primary`/`--on-primary`, 11 px 600. En el prototipo lleva a la pantalla
Notificaciones (§13).

Consola (`notifications-bell.tsx`): `NotificationsBellMenu`, panel con los 5
últimos, «Marcar todo como leído» y «Ver todas» (decisión R47.3). Brechas de
forma: botón `ghost icon-sm` (28 px, sin borde) y recuento de 16 px en `font-mono`.

### 3.8 Avisos (`toastView`, `toast`, l. 1743–1748)

`.toast.glass role="status"` fijo abajo al centro (`bottom: safe-area + 84px`),
píldora (radio 999), `padding:10px 10px 10px 16px`, `gap:12px`, 14 px, máx.
`100% − 32px`; icono `circle-check` en `--accent-ink`, texto, botón de acción
opcional (`.btn.sm`, p. ej. «Deshacer», «Revisar», «Pruébalo», «Reanudar») y cerrar
(`.btn.sm.ghost.icon` `x` 14, `aria-label="Cerrar aviso"`). Entra con `rise .3s`
(sube 12 px y aparece). Uno a la vez; se va a los **6 s**.

Consola (`packages/ui/src/components/sonner.tsx`): vidrio, abajo al centro, 6 s, se
para con foco o ratón. Brechas menores: radio 16 en vez de píldora y el botón de
cerrar de sonner en la esquina en vez de a la derecha del texto.

### 3.9 Responsivo del marco

- ≤1100: lienzo `28px 24px 48px`.
- ≤900: una columna; el menú lateral pasa a una fila con wrap encima
  (`border-bottom`), sin etiquetas ni usuario; `.wrap` con `padding:0 12px 120px`;
  la barra superior sin relleno; lienzo `20px 16px 48px`.
- ≤560: migas en una línea sin wrap; sin buscador.

Consola: desde 901 px igual; hasta 900 px barra superior con marca, ⌘K como icono,
campana, perfil y un botón para mostrar u ocultar la fila de menú, que se desplaza
de lado (decidido; mejor que el prototipo, que perdía el tema en móvil).

### 3.10 Brechas del marco (por impacto)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Botones de 36 px radio 8 (sm 30) | 32/28 px radio 4 | `packages/ui/src/components/button.tsx` | — |
| Alto | Activo del menú en verde claro (`accent-soft`) | Pistachio + pine | `packages/ui/src/styles/tokens.css` (`--sidebar-accent` claro) | — |
| Medio | Barra de 56 px; lienzo a 16 px del borde; relleno 40/48/60; ancho 1240; separación 20 | 48 px; 8 px; 32; 1280; 24 | `components/shell/console-shell-v2.tsx`, `--width-content` | — |
| Medio | Buscador 36 px radio 8, mín. 260 | 28 px radio 4, 256 | `components/shell/console-command-palette.tsx` | — |
| Medio | Campana con borde, 36 px; recuento 18 px | ghost 28 px; 16 px mono | `components/shell/notifications-bell.tsx` | — |
| Bajo | Temas con icono y check a la derecha; avatar cuadrado 28 | sin iconos; avatar redondo 32 | `components/shell/profile-menu.tsx` | — |
| Bajo | Migas 13 px; etiquetas de grupo 11 px .08em | 14 px; 12 px | `shell-breadcrumbs.tsx`, `console-shell-v2.tsx` | — |
| Bajo | Aviso en píldora con cerrar a la derecha | radio 16, cerrar de sonner | `packages/ui/src/components/sonner.tsx` | — |

---

## 4. Gráficas (l. 2205–2256)

### 4.1 `waffleChart` — gráfica de cuadros

Entrada: `labels`, `series` (1 o 2, `{name, vals}`), `fmt`, `unit`, `rows` (12),
`top3(i)`, `legend`, `sub` (franjas: `[['Madrugada',.35],['Mañana',1.45],['Tarde',1.4],['Noche',.8]]`, pesos que
suman 4 y reparten el total del día), `noun`.

- **Rejilla**: cada punto es un grupo de `k` subcolumnas (1, o 4 con franjas) de
  celdas cuadradas apiladas de abajo arriba; las llenas reparten las series (s0
  abajo, `--accent`; s1 encima, `--accent` al 40 % sobre `--surface`); las vacías
  dibujan la pista (`--ink` al 6 %) hasta el máximo del eje. Toda columna con
  algo tiene al menos una celda.
- **Eje**: 5 marcas (4 pasos de `niceStep(pico × 1,04 / 4)`), 11 px `--muted`
  tabular, a la izquierda (34 px).
- **Tamaños** por container query: celda `min(20px, lo que quepa)` redondeada a
  px, separación 3 px (vertical como mucho 6); **densa** si `n × k > 60` (16
  filas, celda ≤10 px, separación 2, radio 2) y en ≤700 px con scroll lateral.
- **Etiquetas**: todas si `n ≤ 14`; si no, cada `ceil(n/7)` sin pisar el final, y
  siempre «Hoy» (tinta, 600).
- **Leyenda** (con 2 series): punto de 9 px radio 3 + nombre; a la derecha
  `.meta` «Cada columna es una franja del día: madrugada, mañana, tarde, noche» si
  hay franjas.
- **Interacción**: cada grupo es `tabindex=0` con `aria-label="{día}: {total}{unidad}"`.
  Al pasar o enfocar: línea discontinua vertical por el grupo (tinta al 35 %), las
  vacías del grupo al 10 %, las llenas de los demás grupos al 55 %; tooltip
  `role="tooltip"` a la derecha (a la izquierda en la segunda mitad; debajo en
  ≤700): día (12 px muted), total en 18 px 600 «141 conversaciones» o «6,40 €»,
  una fila por serie con su punto y valor, y la lista de los 3 primeros (nombre y
  valor). Transiciones `.15s`.

Consola: `BlockChart` de `@nexus/ui` (rejilla continua, `listbox` con una parada
de Tab y flechas, tabla para lectores, tooltip con Escape). Mejor en
accesibilidad; distinta en forma: columnas seguidas sin agrupar por día, sin
línea guía al pasar. Admite `top` por columna y `description` (la nota de franjas).
Las franjas necesitan datos por franja (§5, §6).

### 4.2 `barChart` — barras con media

Definida pero **no se usa en ninguna pantalla** del prototipo: no hace falta
construirla. (Barras con degradado de `--accent`, la de hoy más intensa, rejilla de
5 líneas, línea discontinua de la media con etiqueta «Media X», tooltip encima.)

### 4.3 `spark` — línea mínima

SVG `aria-hidden` de 120×28 (90×22 en los medidores), `polyline` en `--s1` de 1,6
con extremos redondos y un círculo de r 2,5 en el último punto. Consola: el
`Sparkline` local del Panel (112×40, `text-primary`, trazo 2, sin punto final).
Bajo: añadir el punto final y bajar a 120×28.

---

## 5. Panel (`SCREENS.home`, l. 2258–2302)

### Composición

`pageHead` + `.homegrid` + tarjeta «Necesita tu atención».

`.homegrid`: rejilla `minmax(0,1.15fr) repeat(3, minmax(0,1fr))`, dos filas,
`gap:16px`; «Gasto del mes» ocupa 2 filas en la columna 1; las tres cifras en la
fila 1 (columnas 2–4); «Conversaciones por día» en la fila 2, columnas 2–4. En
≤1100: 3 columnas, el gasto y la gráfica a todo el ancho. En ≤700: una columna.

### De arriba abajo

1. **Cabecera**: «Hola, Luis» · «Ladrian Studio · lunes 26 de octubre» · botón
   primario `plus` **«Nuevo cliente»** (va a Clientes y abre el alta).
2. **Gasto del mes** (`.card.spend`): cabecera «Gasto del mes» + botón ghost sm
   «Ver consumo →» (`arrow-right` 14; va a Consumo). Cifra de 36 px 600 (−0.03em)
   «83,00 €»; `.meta` «1–26 oct · todos tus clientes». Barra apilada de 12 px
   (`role="img" aria-label="Gasto por cliente"`, separadores de 1 px en
   `--surface`, `title` por tramo): los 3 clientes que más gastan (`--s1`, `--s2`,
   `--s3`), «Resto de clientes» (`--s4`) si hay más, y «Companion y pruebas»
   (`--line-strong`). Leyenda en lista (rejilla `10px 1fr auto auto`, gap 10, 14 px):
   cuadro de color, nombre con elipsis, «47 %» (`.meta`), importe 500.
3. **Conversaciones** (`.card.kpi`): «Conversaciones» (`.meta`), cifra 28 px
   «875» + `spark` a la derecha, y debajo «↑ 27 % más que los 7 días anteriores»
   (13 px, `--accent-ink`) o «↓ N % menos que los 7 días anteriores» (`--warn-ink`).
4. **Clientes atendiendo**: cifra = clientes con algún agente publicado con canal;
   «De 4 · 1 en alta» (en alta = sin agentes).
5. **Saldo disponible**: «240,00 €»; `minibar` a todo el ancho con el asignado
   sobre (disponible + asignado); «42,99 € asignado a clientes».
6. **Conversaciones por día** (`.chartcard`): «Conversaciones por día» + «Últimos 7
   días»; `waffleChart` de 7 días (Lun…Sáb, Hoy) × 4 franjas, 12 filas, series
   «Resueltas sin persona» y «Pasadas a una persona», tooltip con el total («141
   conversaciones»), las dos series y los 3 clientes con más conversaciones ese
   día.
7. **Necesita tu atención** (`.card`): cabecera «Necesita tu atención» +
   `.cnt-pill` (22 px, `--danger-soft`, texto `--danger`, 12 px) con el número;
   a la derecha `.meta` «1 de 4 clientes sin problemas.». Filas `.attn li` (flex,
   gap 12, `padding:12px 18px`, borde superior): punto de 9 px (rojo si grave,
   ámbar si aviso), cliente (500) y motivo (13 px muted), botón primario sm con el
   arreglo y `rowMenu` con `building-2` «Abrir ficha del cliente» y
   `messages-square` «Ver conversaciones». Orden por gravedad: 1 «Sin saldo, el
   agente no responde» → «Asignar saldo»; 2 «12 mensajes no se entregaron en 24
   horas» → «Ver conversaciones»; 3 «{agente} no tiene canal: no recibe mensajes» →
   «Conectar canal»; 4 «Queda menos del 20 % de su saldo» (ámbar) → «Asignar
   saldo». **Se ven 4**; si hay más, enlace pequeño «Ver N más» / «Ver menos»
   (`margin:0 18px 16px`).

### Estados

- Sin nada que arreglar: `card-b` con `circle-check` «Todos tus clientes están
  atendiendo.» en `--accent-ink`.
- Tendencia a la baja: flecha ↓ y `--warn-ink`.

### Acciones

| `data-act` | Qué hace |
|---|---|
| `nav` (`data-then="new-client"`) | Clientes + modal de alta |
| `nav` (`data-to="usage"`) | Consumo |
| `h-topup` | Abre el cliente en su Panel con el modal «Asignar saldo a {cliente}» |
| `h-open` | Abre el cliente en su Panel |
| `h-channel` | Abre el agente en su pestaña Canales |
| `att-more` | Alterna ver todas / las 4 primeras |
| `menu` / `open-client` | Menú ⋯ de la fila / abrir ficha |

**Modal «Asignar saldo a {cliente}»** (`topup`, l. 1648–1664): «Sale del saldo de
tu cuenta de partner. Sin saldo, sus agentes no responden.» · «Cantidad» con 4
rápidas (10, 20, 50, 100 en la moneda del cliente) · «Otra cantidad» (`.bigin`) ·
recibo `aria-live="polite"`: «Saldo actual de {cliente}», «Asignas ahora»
(«+ X» o «—»), «Sale de tu cuenta (1 € = 1,08 USD)» si cambia la moneda, «Nuevo
saldo de {cliente}» (22 px), «Te queda en tu cuenta de partner» («X de Y» o «Faltan
X» en rojo) · casilla «Avisarme cuando le quede menos del 20 %» / «Así lo recargas
antes de que deje de responder.» (marcada) · pie: enlace «Recargar mi cuenta» si
falta saldo, «Cancelar», «Asignar saldo» (deshabilitado sin importe o sin saldo) →
aviso «Asignados X a {cliente}. En tu cuenta quedan Y.». Consola:
`components/money/assign-dialog.tsx` tiene lo mismo (rápidas 10/20/50/100, recibo,
aviso al 20 %, «Recargar mi cuenta»). Equivalente.

### Frente a la consola (`app/(console)/page.tsx`, `components/home/partner-panel.tsx`)

Ya alineado: cabecera, composición en dos columnas, gasto con barra y leyenda,
tres cifras, gráfica de bloques y «Necesita tu atención» al final con «N de M
clientes sin problemas» y ⋯.

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Cifras de 28 px | `text-3xl` = 44 px | `partner-panel.tsx` | — |
| Alto | «↑ 27 % más que los 7 días anteriores» | «Últimos 7 días» | `page.tsx` (pasar `delta`), `partner-panel.tsx`; textos `hu.home.kpi.delta.*` | **Existen** en `home.conversations_trend` (misma respuesta) |
| Medio | Se ven 4 filas + «Ver N más» / «Ver menos» | Todas | `partner-panel.tsx` (`Attention`) | — |
| Medio | ⋯ con «Abrir ficha del cliente» y «Ver conversaciones» | ⋯ con «Abrir el cliente» | `partner-panel.tsx`, `i18n/lanes/partner-views.ts` | `href` del cliente existe; conversaciones: ruta del cliente |
| Medio | Tooltip con los 3 clientes con más conversaciones del día | Sin top-3 | `panel-model.ts` (`conversationColumns` → `top`) | **Existen** en `conversations_trend.by_client[].series` |
| Medio | 4 franjas por día + nota «Cada columna es una franja del día: madrugada, mañana, tarde, noche» | Un día por columna | `panel-model.ts`, `partner-panel.tsx` (`description`) | **Cambio de API**: `conversations_per_day` por franja |
| Bajo | «1–26 oct · todos tus clientes» | «Del 1 oct al 31 oct» (fin de mes, no hoy) | `panel-model.ts` (`monthPeriod`), texto `panel.v2.period.month` | `spend.until`: comprobar si es hoy o fin de mes |
| Bajo | Recuento en `--danger-soft` con texto rojo | `bg-status-danger/15`, texto normal | `partner-panel.tsx` | — |
| Bajo | Título de tarjeta 15 px; «Ver consumo →» como botón ghost sm | 16 px; enlace | `partner-panel.tsx` | — |

---

## 6. Consumo (`SCREENS.usage`, `usageAlerts`, l. 2304–2365)

### De arriba abajo

1. **Cabecera**: «Consumo» · «Tu saldo, lo que puede gastar cada cliente y lo que
   se gasta cada día.» · botón `bell` **«Alertas de consumo»** (subpágina) + primario
   `plus` **«Comprar saldo»** (modal).
2. **Tres cifras** (`.kpis3`, 3 columnas, gap 16; una en ≤800), tarjetas `.kpi`
   **sin icono**: «Saldo disponible» 240,00 € · «Incluido 40,00 € · comprado
   200,00 €»; «Asignado a clientes» 42,99 € + `minibar` · «240,00 € sin asignar»;
   «Gasto del mes» 79,60 € · «A este ritmo, 94,91 € a fin de mes» (mes / 26 × 31).
3. **Saldo por cliente** (`.card`): cabecera + botón sm `plus` «Asignar saldo a un
   cliente» solo si algún cliente no tiene saldo. Tabla `.list` (filas de 14 px de
   relleno, hover `--surface-2`): **Cliente** (nombre 500 + código de moneda «USD»
   en 13 px muted; pulsable → ficha) · **Tope** · **Gastado este mes** · **Le
   queda** (`minibar` de 120 px con lo que queda, ámbar ≥80 % gastado, + importe; o
   `badge` rojo `circle-alert` «Sin saldo») · ⋯ `pencil` «Cambiar tope»,
   `corner-down-right` «Mover saldo a otro cliente», `chart-column` «Ver su gasto»
   (filtra la gráfica y baja a ella), `hr`, `building-2` «Abrir ficha del
   cliente». Solo clientes con tope. Vacía: «Ningún cliente tiene tope todavía.».
4. **Gasto por día** (`.card#gasto`): cabecera con `.segm` `role="group"
   aria-label="Periodo"` «7 días · 30 días · 90 días» (30 por defecto) y select
   (etiqueta oculta «Cliente») «Todos los clientes» / cada cliente.
   `waffleChart` de una serie «Gasto», en €; franjas solo con 7 días; etiquetas
   «d/m» y «Hoy»; con «Todos los clientes», el tooltip lista los 3 que más gastan
   ese día.
5. **Detalle técnico** (`details.card.tech`, cerrado): resumen con «Detalle
   técnico: mensajes, uso del modelo y multimedia» + «Lo que mide la plataforma
   por dentro, por cliente y medidor. Para revisar con detalle o exportar.» y
   `chevron-down` que gira 180° al abrir. Dentro: select «Conversaciones reales /
   Pruebas del Playground» (`aria-label="Origen"`) + sm `upload` «Descargar CSV»;
   medidores en 2 columnas (una en ≤760) por grupo — Mensajes («Mensajes de
   canal», «Mensajes de canal del mes»), Multimedia («Multimedia · imagen»), Voz
   («Minutos de voz»), Uso del modelo («Tokens de entrada», «de salida», «de
   caché leídos», «de caché escritos») — cada fila nombre · `spark` 90×22 ·
   cifra; nota «3 registros del periodo aún sin valorar por Auphere. Las unidades
   ya cuentan.»; tabla Cliente · Medidor · Origen (`badge` «Canal» verde o
   «Pruebas» azul) · Cantidad · Facturable · Registros.

### Alertas de consumo (subpágina; migas «Consumo › Alertas de consumo»)

«Alertas de consumo» · «Fija un tope mensual de mensajes de canal para todos tus
clientes. Al 80 % y al 100 % avisamos por correo y en la consola. El servicio
nunca se corta por el tope.» Tarjeta de 620 px máx.: «Este mes» · «4.310 mensajes»
(20 px) «(72 % del tope)» + `minibar` (ámbar ≥80 %); «Tope mensual (mensajes de
canal)» (placeholder «Sin tope», «Vacío = sin tope.»); «Destinatarios del correo»
(textarea de 3 filas, «Uno por línea.»); casilla «Alertas activas» / «Avisamos al
80 % y al 100 % del tope.»; «Guardar» → «Alertas guardadas.».

### Modales y acciones

| `data-act` | Modal / efecto | Textos |
|---|---|---|
| `u-buy` → `u-buy-pick`, `u-buy-do` | «Comprar saldo», 480 px | «El saldo comprado no caduca mientras tu cuenta siga viva, y es lo que gastan los agentes de tus clientes.» · rápidas 20/50/100/250 · «Otro importe» · «Recibirás X de saldo. Se paga en la página segura del proveedor.» / «Entre 5 y 5.000, en números enteros.» · «Comprar» (deshabilitado fuera de rango) → «Pago confirmado. Se añadieron X a tu saldo.» |
| `u-assign` → `u-assign-go` | «Asignar saldo a un cliente» | «Sale del saldo de tu cuenta de partner.» · select «Cliente sin tope» · «Continuar» → modal `topup` (§5); sin elegir, aviso «Elige un cliente.» |
| `u-cap` → `u-cap-save` | «Tope de {cliente}» | «Lo que este cliente puede gastar. Si se acaba, su agente deja de responder.» · «Importe» · errores «Escribe un importe, como 25 o 25,50.» / «La suma de topes superaría tu saldo.» · «Guardar tope» → «Tope actualizado.» |
| `u-move` → `u-move-do` | «Mover saldo desde {cliente}» | «Baja un tope y sube el otro de una vez: o cambian los dos o no cambia ninguno.» · «Hacia» (solo misma moneda) · «Importe a mover» / «Puedes mover hasta X.» · errores «Elige un cliente.», «Escribe un importe mayor que cero, como 10 o 10,50.», «{c} solo tiene X disponibles.» · sin destino: «No hay otro cliente con la misma moneda (EUR).» · «Mover saldo» → «X movidos de {c} a {d}.» |
| `u-spend` | Filtra la gráfica a ese cliente y baja a `#gasto` | — |
| `u-days`, `change u-client` | Periodo y cliente de la gráfica | — |
| `u-alerts`, `al-save` | Subpágina de alertas / guardar | «Alertas guardadas.» |

### Frente a la consola (`app/(console)/usage/usage-v2.tsx`, `components/money/*`)

La consola sigue el modelo de bolsas y partidas (requisitos 45–46): «En bolsas de
clientes» en vez de «Asignado a clientes», columnas «Bolsa · Le dura · Relleno
mensual», filtro y sección «Partidas», «Pedir ampliación», «Repartir tu saldo en
bolsas». Eso es decidido. Lo que se puede acercar sin tocar el modelo:

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Cabecera de 40 px sin eyebrow | Sin eyebrow ya, pero `PageHeader` por defecto: 32 px en móvil y 44 px desde `md` (18:05) | `usage-v2.tsx` (`size="display"`) | — |
| Alto | Cifras sin icono: etiqueta 12 px muted, cifra 28 px, nota 13 px | `Metric` con baldosa de icono, etiqueta 14 px, cifra 32 px | `usage-v2.tsx` (una variante sin icono de `Metric` o la tarjeta `.kpi` del Panel) | — |
| Medio | «Le queda» con `minibar` de 120 px | Solo el importe de la bolsa y «Le dura» en texto | `components/money/usage-clients-table.tsx` | **Cambio de API**: `ClientUsage` no trae lo asignado (solo `bag` restante); la barra necesita el total del periodo |
| Medio | Moneda bajo el nombre del cliente («USD») | No | `usage-clients-table.tsx` | Existe (`bag.currency`) |
| Medio | ⋯ termina en «Abrir ficha del cliente» | No (el nombre es enlace) | `usage-clients-table.tsx` | Existe |
| Medio | Periodo en `.segm` de vidrio | `rounded-md bg-muted p-1` | `components/money/spend-by-day.tsx` | — |
| Medio | Tooltip con los 3 que más gastan el día | Sin top-3 | `spend-by-day.tsx` | **Cambio de API**: `UsageDaily` va por partida, no por cliente |
| Bajo | Franjas con 7 días | Días | `spend-by-day.tsx` | **Cambio de API** |
| Bajo | «Detalle técnico: mensajes, uso del modelo y multimedia» + chevron que gira | «Detalle técnico» + «›» | `components/money/usage-detail.tsx` | — |
| Bajo | Comprar con rápidas 20/50/100/250 y `.bigin` | `BuyDialog` | `app/(console)/usage/buy-dialog.tsx` | — |

---

## 7. Auditoría (`SCREENS.audit`, l. 2367–2412)

### De arriba abajo

1. **Cabecera**: «Auditoría» · «Quién hizo qué, sobre qué cliente y cuándo.» ·
   botón `upload` «Descargar CSV».
2. **Filtros** (`.toolbar`): tres selects de ancho automático con etiqueta oculta
   (Cliente, Persona, Categoría): «Todos los clientes», «Todas las personas»,
   «Todas las categorías»; `.segm` `role="group" aria-label="Periodo"` «Todo · 7
   días · 30 días · 90 días»; enlace pequeño **«Limpiar filtros»** si hay alguno.
3. **Tabla** en `.card` (sin borde propio), cabeceras en tipo normal (13 px
   muted, **no mayúsculas**): Fecha · Persona · Qué pasó · Cliente · Categoría · ⋯.
   - Fecha: «Hoy, 09:12», «Ayer, 20:32», «24 oct, 17:50» (tabular, sin corte).
   - Persona: avatar de 26 px radio 6 — iniciales en `--accent-soft` para personas;
     icono para Companion (`sparkles`), Auphere (`shield-check`), clave de API
     (`key-round`), máquina (`laptop`), Sistema (`bot`) — + nombre (monoespaciado
     para clave y máquina).
   - Qué pasó: la frase («cambió los ajustes del agente Recepción»).
   - Cliente: enlace al cliente o «—».
   - Categoría: `badge` gris con punto; si la acción es sensible, `badge` rojo con
     `circle-alert` dentro de un `span title="Acción sensible: no se puede
     deshacer"`.
   - ⋯: «Ver solo este cliente», «Ver solo esta persona», «Ver solo esta
     categoría», `hr`, «Abrir la ficha del cliente».
   - **Agrupación**: filas seguidas con la misma persona, acción, cliente y día se
     juntan; debajo, una fila hija (fondo `--surface-2`, 13 px, 6 columnas) con el
     enlace «N más como esta»; abierta, las filas hijas (sin ⋯) y «Ocultar».
4. **Pie** de la tarjeta (borde superior): «14 registros» + sm «Ver anteriores»
   (añade los anteriores) → al final «No hay actividad anterior.».

Estados: sin resultados con filtros «Nada coincide con estos filtros.»; sin nada
«Sin actividad registrada.». Acciones: `af-set` (de un select, del ⋯ o del
periodo; cierra el menú), `af-clear`, `au-toggle`, `au-more`, `change af`.

### Frente a la consola (`app/(console)/audit/{page,filters,audit-table}.tsx`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | «N más como esta» en una fila hija | Dos agrupaciones a la vez: «2 más como esta1 más como esta» en la celda | `audit-table.tsx` (quitar `foldRepeats` o `MoreLikeThis`) | Existen |
| Alto | Cabecera 40 px sin eyebrow | Sin eyebrow ya, pero tamaño por defecto (44 px desde `md`; 18:05) | `audit/page.tsx` (`size="display"`) | — |
| Medio | Cabeceras de columna 13 px en tipo normal | Mayúsculas 12 px con `tracking-eyebrow` | `audit-table.tsx` (`Head`) | — |
| Medio | Periodo en `.segm` de vidrio | `rounded-md bg-muted p-1`, `text-xs` | `audit/filters.tsx` | — |
| Medio | Sensible = la categoría en rojo con icono y `title` | `badge` aparte «sensible» junto a la frase + categoría roja si `critical` | `audit-table.tsx` | Existen (`sensitive`, `severity`) |
| Bajo | Avatar cuadrado de 26 px radio 6 | `Avatar` redondo; iconos en círculo | `audit-table.tsx` (`Who`) | — |
| Bajo | — | Filtro «Fechas» (desde/hasta) y origen «Desde la web» | — | Decidido; se queda |

---

## 8. Guía del partner (`SCREENS.guide`, l. 2414–2440)

### De arriba abajo

1. **Cabecera**: «Guía del partner» · «Lo que lee el Companion, el asistente de
   esta consola, para ayudarte con todos tus clientes. Ningún agente de WhatsApp la
   ve: no llega a la conversación con el cliente final.»
2. `.panel.two` (2 columnas, gap 16; una en ≤860):
   - **«Subir archivo»**: zona `.drop` (borde discontinuo de 1,5 px
     `--line-strong`, radio 12, `padding:18px`, centrada, `--muted`): `upload` 18 +
     «PDF, TXT, MD o HTML · máx. 10 MB» + sm **«Elegir archivo»**; campo «Título ·
     opcional». Elegir el archivo lo sube (sin otro botón).
   - **«Añadir URL»**: «URL pública» (placeholder «https://…», `inputmode=url`;
     error «Introduce una URL http(s) válida.»), «Título · opcional», primario
     **«Añadir e indexar»**.
3. **«Documentos»** (`.card`, recuento a la derecha): «Uso del presupuesto del
   prompt» · «84.300 de 120.000 caracteres · 70 %» + `minibar` a todo el ancho
   (ámbar ≥90 %). Tabla: **Título** (500 + tipo MIME o URL monoespaciada; si falló,
   el motivo en rojo 13 px, p. ej. «No se pudo extraer texto (documento vacío o
   escaneado sin OCR).») · **Tipo** («Archivo»/«URL») · **Estado** (`badge`
   «Indexado» verde `circle-check`, «Pendiente» azul `loader-circle`, «Fallido» rojo
   `circle-alert`) · **Tamaño** · **Fragmentos** («—» si 0) · **Indexado** («20 oct
   2026, 10:14» o «—») · iconos ghost `refresh-cw` «Reindexar» y `trash-2`
   «Eliminar» (`aria-label` y `title`).
4. Vacía: `book-open` «Tu guía está vacía» / «Sube las reglas y documentos comunes
   a todos tus clientes o añade una URL pública.»

Acciones: `g-upload` (««{t}» subido.», pendiente → indexado), `g-url` (««{t}»
añadido.»), `g-reindex` (««{t}» reindexado.»), `g-del` → confirmación «Eliminar
«{t}»» / «El Companion dejará de consultar este documento de inmediato. No se
puede deshacer.» / «Eliminar» en rojo → ««{t}» eliminado.».

### Frente a la consola (`app/(console)/knowledge/page.tsx`, `components/agent-tools/knowledge-table.tsx`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | `pageHead` de 40 px | `<h1 className="text-base">` (16 px) y `<p>` de 14 px, sin raya | `knowledge/page.tsx` → `PageHeader size="display"` | Existen |
| Alto | Zona de soltar con «Elegir archivo» que sube al elegir | `<input type=file>` + «Subir e indexar» | `knowledge-table.tsx` (formulario de subida; compartido con el cliente) | Existen |
| Medio | Medidor y tabla dentro de la tarjeta «Documentos» con recuento | Medidor suelto encima de una tabla con anillo | `knowledge-table.tsx` | Existen |
| Bajo | Descripción sin la última frase | Añade «El texto extraído no sale de aquí.» | `i18n` `playbook.description` | — |
| Bajo | Eliminar sin deshacer | Eliminar con «Deshacer» en el aviso | — | Mejor; se queda |

---

## 9. Teammate (`SCREENS.teammate`, l. 2048–2083)

### De arriba abajo

1. **Cabecera**: «Teammate» · «Tu puesto de trabajo: las máquinas, a qué clientes
   sirven y en qué directorio. Los ejecutables permitidos se gestionan en cada
   cliente.»
2. **«Tu puesto de trabajo»** (`.card`; se oculta si está todo hecho o se cierra):
   «2 de 4 pasos» (`.meta`) + ghost icono `x` «Cerrar por ahora»; `minibar` a todo
   el ancho; pasos (`.steplog`): hecho `circle-check` verde, pendiente
   `circle-dashed` + «· 1 pendiente» / «· 2 pendientes» — «Abre la aplicación de
   escritorio en esta máquina», «Elige a qué clientes sirve», «Declara el
   directorio de cada cliente en la aplicación de escritorio», «Ejecutables
   habilitados por Auphere»; nota «Los ejecutables los habilita Auphere por
   cliente. Si falta alguno, pídelo desde la página del cliente.»
3. **«Máquinas»** (`h2.sech` 18 px) y una tarjeta por máquina:
   - Cabecera: baldosa de 36 px radio 8 `laptop`, nombre (`h3`), «Nombre de
     sistema: luis-mbp.local · tuya» / «· de Andrés» (mono, `.meta`), `badge`
     «Conectada» (verde) / «Desconectada desde hace 3 días» / «Nunca se ha
     conectado» (gris `circle-dashed`); ⋯ `pencil` «Renombrar», `hr`, `archive`
     «Archivar» en rojo.
   - «Clientes a los que sirve» (14 px 500); lista: baldosa `building-2`, nombre
     500, carpeta en mono con `file-text` o `badge` ámbar «Pendiente de declarar
     desde la máquina»; ghost sm «Quitar». Sin clientes: «No sirve a ningún cliente
     todavía.»
   - Añadir: select «Elige un cliente» + `plus` «Añadir cliente», nota «Después,
     elige la carpeta de este cliente en la aplicación de escritorio: la consola
     no teclea rutas.»; si ya están todos, «Todos tus clientes ya están vinculados
     a esta máquina.»
   - Sin máquinas: `.card.empty` `laptop` «Ninguna máquina registrada» / «Abre la
     aplicación de escritorio en la máquina que quieras usar: se registra sola con
     tu sesión y aparecerá aquí.»
   - Enlace «Ver archivadas (1)» / «Ocultar archivadas» → «Portátil antiguo» ·
     «Archivada hace 2 meses · desemparejada desde la máquina».
4. **«Ejecución en las máquinas del equipo»**: «Hasta dónde puede llegar cada
   persona con su propia máquina. Los programas que un teammate puede ejecutar los
   sigue fijando la lista de cada cliente. Esto solo acota si se pregunta antes.»;
   `.segm role="radiogroup" aria-label="Techo de ejecución"` «Cada persona decide ·
   Preguntar siempre · Nadie ejecuta»; nota «Bajarlo tiene efecto en la siguiente
   petición. No revoca los permisos de comandos ya concedidos: esos se quitan en el
   puesto de trabajo del cliente, donde consta quién los dio.»

Acciones: `ws-hide`; `ws-exec` («Techo de ejecución guardado.»); `ws-rename` →
«Nombre de la máquina» (host en mono) / «Cómo se llama esta máquina» / «Guardar» →
«Máquina renombrada.»; `ws-archive` → «¿Archivar {máquina}?» / «La aplicación
dejará de latir en menos de un minuto y esta máquina no vuelve: al abrir la
aplicación otra vez, se registra una nueva. Lo ya ejecutado sigue en la auditoría:
esto archiva, no borra.» / «Archivar» rojo → «Máquina archivada.»; `ws-unlink` →
«¿Quitar {cliente} de esta máquina?» / «El teammate de este cliente dejará de tener
herramientas locales en esta máquina. Lo ya ejecutado sigue en la auditoría.» /
«Quitar» → «Cliente quitado de la máquina.»; `ws-link` («Elige un cliente.» /
«{cliente} vinculado. Falta el directorio: elígelo en la aplicación de
escritorio.»); `ws-toggle-arch`.

### Frente a la consola (`app/(console)/workstation/page.tsx`, `components/workstation/*`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Título «Teammate», subtítulo «Tu puesto de trabajo: las máquinas, …» | «Puesto de trabajo» / «Tus máquinas, …» | `i18n/lanes/workstation.ts` (`ws.title`, `ws.description`) | — |
| Medio | Renombrar y Archivar en ⋯ | Dos botones en la cabecera de la tarjeta | `machines-list.tsx` (`RowActions menu`) | — |
| Medio | Techo en `.segm` de vidrio | Grupo de botones | `local-exec-ceiling.tsx` | — |
| Bajo | Baldosa `laptop` de 36 px en la cabecera | Sin baldosa | `machines-list.tsx` | — |
| Bajo | «Pendiente de declarar…» en ámbar | En gris | `machine-clients.tsx` | — |

---

## 10. Equipo (`SCREENS.team`, l. 2086–2107)

### De arriba abajo

1. **Cabecera**: «Equipo» · «Quién puede entrar en la consola de tu partner y con
   qué rol.» · primario `user-plus` **«Invitar»**.
2. **«Miembros»** (`.card`, recuento a la derecha). Filas `.mrow` en rejilla
   `36px minmax(0,1fr) 120px 120px 140px 30px` (en ≤760 `36px 1fr auto`, sin rol
   ni fecha): avatar de 36 px radio 8 en `--accent-soft` con iniciales · nombre 500
   (+ «(tú)» en `.meta`) y correo mono · **rol** (13 px) · **estado** (`badge`
   «Activo» verde `circle-check` o «Suspendido» ámbar `pause`) · «Se unió hace 8
   meses» (`.meta`, a la derecha) · ⋯ (en tu fila, un hueco de 30 px): «Cambiar rol»
   (etiqueta) y los demás roles, `hr`, «Suspender»/«Reactivar», `user-x` «Quitar
   del equipo» en rojo. Orden: propietario primero.
3. **«Invitaciones pendientes»** (`.card`, recuento): baldosa `send`, correo mono
   500, «Facturación · Caduca 16 nov 2026», sm «Revocar». Vacía: «No hay
   invitaciones pendientes.»
4. **«Qué puede hacer cada rol»** (`.card`, `dl` de 160 px + resto): Propietario
   «Todo, incluida facturación, equipo y borrar clientes.»; Administrador «Todo
   salvo facturación.»; Constructor «Clientes, agentes, canales y playground. Sin
   equipo ni facturación.»; Analista «Solo lectura: consumo, metadatos de
   conversación y auditoría.»; Facturación «Facturación, plan y recibos. Nada
   operativo.»

**Invitar** (520 px): «Invitar a alguien» / «Recibirá un enlace que caduca a los 21
días. Elige un rol por su trabajo, no por permisos.» · «Correo» (placeholder
«nombre@empresa.com») · «Rol»: **opciones en tarjeta** (`.radio`) con nombre y
descripción de cada rol, Constructor por defecto · errores «Introduce un correo
válido.» / «Ese correo ya es miembro de este partner.» · «Invitar». Hecho:
«Invitación creada» / «Correo enviado a {correo}.» / «Enlace de aceptación
(compártelo si el correo no llega)» + caja `.code` con «Copiar» / «Cerrar».
Avisos: «Invitación creada», «Invitación revocada», «Equipo actualizado».
Quitar: «Quitar a {correo}» / «Perderá el acceso de inmediato. Puedes volver a
invitarle.» / «Quitar del equipo» en rojo.

### Frente a la consola (`app/(console)/team/page.tsx`, `components/team/*`)

Textos iguales. Brechas:

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Miembros e invitaciones en tarjetas con cabecera (15 px + recuento) | `h2` de 18 px y `ul` con anillo | `team-lists.tsx` | — |
| Medio | Columnas fijas: rol y luego estado | Flex: estado antes que rol; la fecha se oculta <768 | `team-lists.tsx` | — |
| Medio | Rol en tarjetas con descripción | `NativeSelect` + descripción debajo | `invite-dialog.tsx` | — |
| Bajo | Avatar 36 px radio 8; baldosa `send` en invitaciones | 32 px radio 4; sin baldosa | `team-lists.tsx` | — |
| Bajo | Propietario primero | Orden de la API (propietario al final) | `team-lists.tsx` (ordenar) | Existe (`role`) |
| Bajo | `dl` de roles | Matriz de permisos + `dl` | `roles-table.tsx` | Decidido (49.2) |

---

## 11. Facturación (`SCREENS.billing`, l. 2110–2151)

### De arriba abajo

1. **Cabecera**: «Facturación» · «Tu saldo, tus recibos y tus datos de
   facturación. La consola es gratis: pagas solo el consumo de tus clientes.»
2. `.panel` (rejilla `1.35fr 1fr`, gap 16; una columna en ≤980):
   - **«Saldo de tu cuenta»** (`.card.wallet`): «Disponible» + **240,00 €** (32 px);
     a la derecha, 13 px muted: «Es lo que gastan los agentes de tus clientes.» /
     «El saldo comprado no caduca mientras tu cuenta siga viva.»; campo «Comprar
     saldo»: `.amounts` 20 / 50 / 100 / 250 € (`aria-label="Importes rápidos"`) +
     fila con input «Otro importe» + primario «Comprar» (deshabilitado fuera de 5–5.000
     enteros); nota: «Entre 5 y 5.000, en números enteros.» / «Recibirás X de saldo.
     Se paga en la página segura del proveedor.» / error en rojo «El importe tiene
     que estar entre 5 y 5.000, en números enteros.»
   - **«Tarjeta y cobro automático»**: «Guarda una tarjeta en la página segura de
     Stripe: su número nunca pasa por Auphere.»; `.cardbox` con logo de Stripe 32 px,
     «VISA terminada en 4242» / «Caduca 08/2028», sm «Cambiar», sm ghost rojo
     «Quitar» (sin tarjeta: «No hay ninguna tarjeta guardada.» + sm primario «Añadir
     tarjeta»); `.radio role="radiogroup" aria-label="Cómo se cobra"`: «Manual» /
     «Compro saldo cuando lo necesito.»; «Recarga automática» / «Cuando el saldo baja
     de un mínimo.» (deshabilitada sin tarjeta; elegida, debajo y sangrado: «Cuando
     el saldo baje de» + «Recargar» y «La recarga mínima es de 5,00 €.»); «Pospago»
     (siempre deshabilitado) / «Pago lo consumido el día 1 de cada mes. Lo activa
     Auphere con una línea de crédito: escríbenos si lo necesitas.»; sin tarjeta,
     «Añade una tarjeta para elegir un cobro automático.»; sm primario «Guardar».
3. **«Correo de facturación»** (`.card`, sm «Añadir»/«Cambiar»): «No configurado.
   Los avisos van a luis@ladrian.studio.» (muted) o el correo; editando: input
   «facturas@tuempresa.com» + «Guardar» + ghost «Cancelar»; nota «Aquí llegan los
   recibos y los avisos de cobro. Déjalo vacío para usar el correo de contacto.»
4. **«Cobros a la tarjeta»** (`.card`, filas `.connected`): baldosa (`rotate-ccw`
   recarga, `receipt` consumo), «Recarga automática» / «Consumo de 2026-09», fecha,
   importe, `badge` («Pagado», «Emitido», «Falta confirmar», «Rechazado», «En
   curso») y sm primario «Confirmar el pago» o ghost «Ver factura».
5. **«Recibos»** (`.card`, tabla): Periodo · Estado (`badge` en español) · Total ·
   Vencimiento · ghost «Descargar» (`title="Descargar el recibo (HTML imprimible)"`).

Acciones: `buy-pick`, `buy-do` («Pago confirmado. Se añadieron X a tu saldo.»),
`card-add` («Tarjeta guardada en Stripe.»), `card-remove` → «Quitar la tarjeta» /
«Sin tarjeta, el cobro vuelve a ser manual: tendrás que comprar saldo a mano.» /
«Quitar tarjeta» rojo → «Tarjeta quitada.»; `charge-mode`; `charge-save` («Cobro
guardado.» / «La recarga mínima es de 5.»); `bill-mail`, `bill-mail-save` («Correo
de facturación guardado.» / «Escribe un correo válido.»), `bill-mail-cancel`.

### Frente a la consola (`app/(console)/billing/page.tsx`, `components/billing/*`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | Dos tarjetas lado a lado y todo en tarjetas | Secciones sueltas de `max-w-lg`, `h2` de 18 px; un bloque extra «Tu cuenta» (moneda + disponible) | `billing/page.tsx` | Existen |
| Alto | Estado del recibo en español | Texto crudo de la API («paid», «issued») | `billing/page.tsx` (traducir `r.status`) | Existe |
| Alto | Cifra «Disponible» de 32 px dentro de «Saldo de tu cuenta» | `dl` de 14 px | `billing/page.tsx` | Existe (`usageSummary().available`) |
| Medio | Rápidas 20/50/100/250 + «Otro importe» | Solo un input numérico de 128 px «Importe en dólares» | `components/billing/buy-credit-form.tsx`, `i18n/lanes/membership.ts` | Ver fila siguiente |
| Medio | Importes en la moneda de la cuenta («5,00 €») | «(US$)», «Importe en dólares», «US$5» fijos | `card-section.tsx`, `buy-credit-form.tsx`, `membership.ts` | Moneda: existe (`usageSummary().currency`). **Comprobar en la API** si el checkout y la recarga cobran en EUR (hoy `MIN_USD`) |
| Medio | Modos de cobro en tarjetas `.radio` con descripción | Radios nativos con una línea | `card-section.tsx` | Existen |
| Medio | Tarjeta con logo de Stripe, «Cambiar» y «Quitar» en sm | Icono `CreditCard`, botones de tamaño normal | `card-section.tsx` | Existe (`brand`) |
| Bajo | Correo de facturación en tarjeta con «Añadir»/«Cambiar» en la cabecera | Lista de descripción + formulario | `billing-email-form.tsx` | — |

---

## 12. API (`SCREENS.api`, l. 2154–2175)

### De arriba abajo

1. **Cabecera**: «Claves de API» · «Para integrar tu propio sistema con la API de
   partners. La clave se muestra una sola vez.» · primario `plus` **«Nueva clave»**.
2. **«Claves»** (`.card`, «3 activas» a la derecha). Filas `.connected`, las
   revocadas al final con opacidad .6: baldosa `key-round` de 36 px · prefijo mono
   500 «nx_live_7fK2…» y debajo «Aprovisionar clientes · Difusiones · Último uso:
   hace 2 horas» · `badge` «Producción» (verde) o «Pruebas» (azul) · `badge`
   «Revocada» (gris) o «En gracia hasta 27/10/2026 14:00» (ámbar `clock`) · ⋯
   `refresh-cw` «Rotar», `hr`, `ban` «Revocar» en rojo (las revocadas, sin ⋯).
3. **Nota** (`.callout` `info`): «**Las claves de un solo cliente** (envío de
   mensajes) se crean desde la ficha del cliente.»
4. Vacía: `key-round` «Todavía no hay claves» / «Crea una clave para aprovisionar
   clientes o enviar difusiones desde tu sistema.»

**Nueva clave** (540 px): «Nueva clave de API» / «Elige tipo y permisos.» · «Tipo»
en `.segm` (Pruebas por defecto · Producción) · «Permisos» en `.check`:
«Aprovisionar clientes» / «Crear y configurar clientes desde tu sistema.»,
«Difusiones» / «Enviar mensajes masivos con plantillas aprobadas.» · error «Marca
al menos un permiso.» · «Crear clave». Después: «Guarda esta clave ahora» / «No
volverá a mostrarse. Si la pierdes, rota la clave.» + `.code` con «Copiar» · «Ya la
guardé» → «Clave creada.». **Rotar**: «Rotar la clave {prefijo}» / «Se crea una
clave nueva y la actual sigue funcionando 24 h para que despliegues sin corte.» /
«Rotar» (no rojo) → la vieja en gracia y el modal con la nueva. **Revocar**:
«Revocar la clave {prefijo}» / «Deja de funcionar inmediatamente, sin periodo de
gracia.» / «Revocar» en rojo → «Clave revocada.».

### Frente a la consola (`app/(console)/keys/page.tsx`, `components/keys/keys-list.tsx`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Alto | «Nueva clave» en la cabecera | Botón suelto encima de la lista | `keys/page.tsx` (`actions`), `keys-list.tsx` | — |
| Alto | Lista en tarjeta «Claves» con «N activas» | `ul` con anillo | `keys-list.tsx` | Existe |
| Medio | Rotar y Revocar en ⋯ | «Rotar» y «Revocar» en la fila | `keys-list.tsx` | — |
| Medio | Fila: baldosa + prefijo y debajo permisos · último uso; insignias a la derecha | Todo en una línea flex | `keys-list.tsx` | Existen |
| Medio | Nota de las claves de un cliente bajo la lista | Dentro del modal de crear | `keys-list.tsx`, `keys.create.body` | — |
| Medio | Tipo en `.segm`; permisos en tarjetas con descripción | Radios y casillas nativos | `keys-list.tsx` | — |
| Bajo | Revocadas con opacidad .6 | Sin atenuar | `keys-list.tsx` | — |

---

## 13. Notificaciones (`SCREENS.notifications`, l. 2188–2202)

### De arriba abajo

1. **Cabecera**: «Notificaciones» · «Avisos de la plataforma sobre tus clientes, tu
   consumo y tu equipo.» · si hay sin leer, botón `check` «Marcar todas como leídas».
2. `.toolbar` con `.segm role="tablist"`: «Todas» · «Sin leer (3)».
3. `.card` con filas `.connected`: punto de 8 px `--primary`
   (`aria-label="Sin leer"`) o hueco · `badge` con icono («Info» azul `info`,
   «Aviso» ámbar `triangle-alert`, «Crítico» rojo `circle-alert`) · texto (500 si
   sin leer, 400 si leída) y «hace 2 horas» (`.meta`) · ghost sm «Ver cliente» si
   tiene cliente · sm «Marcar como leída» si sin leer. Las leídas con opacidad .75.
4. Vacía: `bell` «Sin notificaciones» (o «Todo leído.» en «Sin leer») / «Aquí
   aparecerán los avisos: consumo, clientes activados, equipo, canales.»

Acciones: `notes-tab`, `notes-all` («Todo leído.»), `note-read`, `open-client`.

### Frente a la consola (`app/(console)/notifications/page.tsx`, `components/notifications/notifications-list.tsx`)

| Impacto | Prototipo | Consola | Archivo | Datos |
|---|---|---|---|---|
| Medio | «Marcar todas como leídas» en la cabecera, solo si hay sin leer | En la barra de filtros, siempre (deshabilitado a 0) | `notifications/page.tsx`, `notifications-list.tsx` | Existe (`unread`) |
| Medio | Filtro en `.segm` de vidrio | Píldoras con borde | `notifications-list.tsx` | — |
| Medio | Fila: punto sin leer, «Ver cliente» como botón ghost, «Marcar como leída» con borde; leídas atenuadas | Fondo `primary/5` sin leer, «Abrir»/«Ver cliente» como enlace en la línea de la fecha (mono), «Marcar como leída» ghost | `notifications-list.tsx` | Existen |
| Medio | Lista en `.card` | `ul` con borde | `notifications-list.tsx` | — |
| Bajo | Hora relativa («hace 2 horas») | Fecha y hora absolutas en mono | `notifications-list.tsx` (`formatRelative`) | Existe |
| Bajo | — | «Cargar más», «Asignar saldo» en «Pedir saldo», pulso en las graves | — | Mejor; se queda |

---

## 14. Mapa de acciones del alcance (`data-act`)

| Acción | Dónde | Efecto |
|---|---|---|
| `nav` | menú, migas, botones | Cambia de pantalla, cierra menús y modal, vuelve arriba; `data-then="new-client"` abre el alta |
| `nav-toggle` | barra | Pliega o abre el menú y lo recuerda |
| `user-menu`, `set-theme` | pie del menú | Abre el menú de usuario; aplica el tema y lo cierra |
| `palette`, `pal-new`, `pal-client` | ⌘K | Abre el buscador; nuevo cliente; cliente en su pestaña |
| `open-client` | varias | Abre el cliente en su Panel |
| `menu` | ⋯ | Abre o cierra ese menú (uno a la vez) |
| `close`, `untoast` | modales, aviso | Cierra |
| `copy-code` | cajas de código | Copia y avisa «Copiado.» |
| `noop` | «Descargar CSV», «Ver factura», «Cambiar», «Abrir la ventana otra vez» | Sin efecto en el prototipo: en la consola, el real |
| Panel | `att-more`, `h-topup`, `h-open`, `h-channel`, `amt`, `save-topup` | §5 |
| Consumo | `u-alerts`, `al-save`, `u-buy*`, `u-days`, `u-spend`, `u-cap*`, `u-move*`, `u-assign*`; `change` `u-client` | §6 |
| Auditoría | `af-set`, `af-clear`, `au-toggle`, `au-more`; `change` `af` | §7 |
| Guía | `g-upload`, `g-url`, `g-reindex`, `g-del`, `g-del-do` | §8 |
| Teammate | `ws-hide`, `ws-exec`, `ws-rename*`, `ws-archive*`, `ws-unlink*`, `ws-link`, `ws-toggle-arch` | §9 |
| Equipo | `tm-invite`, `tm-pick-role`, `tm-invite-do`, `tm-revoke`, `tm-role`, `tm-suspend`, `tm-remove*` | §10 |
| Facturación | `buy-pick`, `buy-do`, `card-add`, `card-remove*`, `charge-mode`, `charge-save`, `bill-mail*` | §11 |
| API | `key-new`, `key-type`, `key-create`, `key-close`, `key-rotate*`, `key-revoke*` | §12 |
| Notificaciones | `notes-tab`, `notes-all`, `note-read` | §13 |

Teclado: ⌘K / Ctrl+K abre el buscador; Escape cierra, por orden, el menú de usuario,
el velo de Meta y el modal. Un clic fuera cierra el ⋯ abierto y el menú de usuario.
Tras cada acción se repinta todo salvo que la acción devuelva `false`.

**No copiar del prototipo**: las flechas del buscador no funcionan; los menús ⋯ no
mueven el foco ni se recorren con flechas; el modal no atrapa el foco; el estado
vive en memoria y en el hash. La consola ya hace bien las tres primeras con
`@nexus/ui`.

---

## 15. Cómo se hizo

- Lectura completa de `index.html` (CSS, `docView`, `appView`, `SCREENS`, `ACT`,
  `MODALS`, gráficas y manejadores de teclado) y de las capturas en claro y oscuro.
- Consola: código del árbol de trabajo (sin commit, en movimiento) y, a 1440×1000,
  medidas con `getComputedStyle` en `http://localhost:3110` de Panel, Consumo,
  Auditoría, Guía, Teammate y Equipo antes de que la otra sesión ocupase el
  navegador (p. ej. barra 48 px, buscador 28 px radio 4, cifras del Panel 44 px,
  `h1` de Auditoría y Teammate 44 px, Equipo ya a 40 px).
- Datos: tipos de `apps/console/src/lib/backend/{home-usage,money-types}.ts` y, para
  la tendencia, `apps/api/src/nexus_api/api/console/{home,schemas_home_usage}.py`
  (la respuesta de `/console/home` trae `conversations_trend` junto a `panel`).
