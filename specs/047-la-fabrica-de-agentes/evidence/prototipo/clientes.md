# Clientes: el prototipo, pantalla a pantalla, y lo que le falta a la consola

Especificación para reconstruir «tal cual», en la consola Next.js (consola v2), la
parte de Clientes del prototipo aprobado «Consola de partners v2». Fecha: 2026-10-28.

- **Fuente**: `~/Downloads/Consola de partners v2/index.html` (vista «Prototipo»).
  Líneas citadas: CSS 109–806, dominio 849–972, lista 1232–1274, detalle
  1276–1406, modales 1628–1748, acciones 1750–1996, eventos 2442–2505.
- **Capturas** (claro y oscuro): `clients`, `client-panel`, `client-business`,
  `client-agents`, `new-client` en el scratchpad del recorrido (`proto/*.png`).
  Los datos son los de la semilla (sección 1.2).
- **Consola comparada**: worktree `047-recorrido-ui-9dd3dd`, con los cambios sin
  commit de hoy (cabecera del cliente y modal del alta ya alineados).
- **Comentarios de Andrés que mandan sobre el prototipo** (ver
  `../feedback-prototipo.md`): los placeholders del alta son generales, no de
  barbería (comentario 1), y nada de la interfaz nombra al constructor (4 y 8).
  Donde el prototipo dice «Barbería Cultor», vale lo que ya tiene la consola.

Convenciones: el texto entre «» es copia literal de la interfaz; `{x}` es un
valor. «→» se lee «al hacer clic». Los tokens son los del prototipo; la tabla 0.1
dice su equivalente en `@nexus/ui`.

---

## 0. Base visual común

### 0.1 Tokens del prototipo y su equivalente en `@nexus/ui`

| Prototipo | Uso | `@nexus/ui` (`packages/ui/src/styles/tokens.css`) |
|---|---|---|
| `--bg` | fondo de la app | `--background` |
| `--surface` | tarjetas, inputs, modal | `--card` |
| `--surface-2` | pistas de barras, hover de filas, pie del modal, iconos en baldosa | `--muted` |
| `--ink` | texto | `--foreground` |
| `--muted` (tinta al 70 %) | texto secundario | `--muted-foreground` |
| `--faint` (tinta al 45 %) | anillos vacíos, texto en espera | `--muted-foreground` con opacidad / `--input` |
| `--line` (12 %) | bordes de tarjeta y separadores | `--border` |
| `--line-strong` (22 %) | bordes de control | `--input` |
| `--primary` / `--on-primary` | botón primario | `--primary` / `--primary-foreground` |
| `--accent`, `--accent-ink`, `--accent-soft` | verde de estado positivo, nav activa | `--color-status-positive`, `--color-status-positive-text`, `--accent` |
| `--warn`, `--warn-ink`, `--warn-soft` | ámbar | `--color-status-warning`, `-text`, `-bg` |
| `--danger`, `--danger-soft` | rojo | `--color-status-danger`, `--destructive`, `-bg` |
| `--info`, `--info-soft` | azul verdoso | `--color-status-info`, `-text`, `-bg` |
| `--s1`…`--s4` | series de consumo por agente | `--color-series-1`, `--color-series-2`, `--color-accent-mid`, `--color-status-warning` (tono arena) |
| `--glass`, `--glass-edge`, `--glass-shadow`, `--tab-on` | capa flotante | `--glass-bg`, `--glass-edge`, `--glass-shadow`, `--tab-on` (ya existen, clase `glass`) |
| `--scrim` | fondo del modal | el overlay del `Dialog` |
| `--r-sm` 8 · `--r-md` 12 · `--r-lg` 16; modal 18 | radios | `rounded-md` = 8; tarjetas 12 (`rounded-xl`) |

Tipografía: Inter 14 px / 1,5, `font-feature-settings: "ss01","cv11"`. Títulos 600 y
`letter-spacing:-0.02em`. Cifras con `tabular-nums` (`.num`).

### 0.2 Piezas que se repiten

- **Botón** `.btn`: 36 px de alto, `0 14px`, radio 8, borde `--line-strong`, fondo
  `--surface`, 14 px/500, hueco 8 px con el icono (16 px). Hover `--surface-2`;
  `:active` baja 1 px. `primary`: fondo `--primary`, sin borde, texto `--on-primary`.
  `ghost`: sin borde ni fondo. `sm`: 30 px, `0 10px`, 13 px. `icon`: cuadrado 36
  (o 30 en `sm`). `danger`: texto `--danger`. Deshabilitado: opacidad 0,45 y
  `not-allowed`.
- **Insignia** `.badge`: 22 px, `0 8px`, píldora, 12 px/500, con un icono de 12 px o
  un punto de 6 px; tonos `t-positive` (fondo `--accent-soft`, texto
  `--accent-ink`), `t-warn`, `t-danger`, `t-info`, `t-muted` (fondo `--surface-2`,
  texto `--muted`). **El texto va tintado del tono**, no en tinta (la
  `StatusBadge` de la consola pinta tinta con punto: ver hueco 13).
- **Tarjeta** `.card`: fondo `--surface`, borde `--line`, radio 12. Cabecera
  `.card-h`: flex, `space-between`, hueco 12, relleno `16px 18px 0`, título h3 de
  15 px. Cuerpo `.card-b`: `14px 18px 18px`.
- **Campo** `.field`: grid con hueco 6; etiqueta 14 px/500 con `for`; «· opcional»
  en 400 y `--muted`. Input 38 px, `8px 10px`, radio 8, borde `--line-strong`; foco:
  contorno 2 px `--primary` hacia dentro. `textarea` mínimo 96 px, `resize:
  vertical`. Ayuda `.hint` 13 px `--muted`.
- **Select** `.select`: 38 px, flecha `chevron-down` dibujada a 12 px del borde
  derecho, `appearance:none`.
- **Menú** `.menu` (todos los «⋯»): absoluto, `right:0`, 4 px bajo el disparador,
  `z-index:30`, ancho mínimo 200, relleno 6, radio 12, **vidrio**. Ítems: 8×10 px,
  radio 8, 14 px, icono de 15 px a 10 px del texto; hover `--surface-2`; `hr` con
  borde `--line` y margen `4px 0`; `danger` en `--danger`. `role="menu"`, ítems
  `role="menuitem"`. Cualquier clic fuera lo cierra.
- **Interruptor** `.switch`: 38×22, mando de 16 px, encendido `--primary`,
  transición 0,2 s.
- **Enlace-botón** `.link`: sin fondo, `--accent-ink`, 500, subrayado a 3 px con el
  color al 40 %.

### 0.3 Estructura de página

`.main` (tarjeta grande, radio 16, `40px 48px 60px`; ≤1100 px `28px 24px 48px`;
≤900 px `20px 16px 48px`) → `.page` (máx. 1240 px, grid de una columna, **hueco
20 px** entre bloques). Cabecera de página `.ph`: flex `space-between`,
`align-items:flex-end`, hueco 16, `padding-bottom:20px` y borde inferior `--line`;
h1 40 px/1,1/−0,03em; subtítulo 16 px `--muted`, 6 px bajo el título.

---

## 1. Datos y reglas de dominio

### 1.1 Dinero

- `money(v, cur)`: `Intl.NumberFormat('es-ES', {minimumFractionDigits: 2,
  maximumFractionDigits: 2, useGrouping: 'always'})` + espacio + símbolo. EUR →
  «€», USD → «USD». Ejemplos: «17,70 USD», «9,75 €», «1.234,00 €».
- Cada cliente tiene su moneda (`cur`). El partner tiene la suya (EUR en la semilla,
  saldo 240 €). Cambio de ejemplo `RATE = {EUR: 1, USD: 1.08}`, solo para el modal
  de saldo. En la consola: `Money` / `formatMoney` y la moneda de la bolsa (spec 027:
  la consola habla en USD salvo bolsas en EUR).

### 1.2 Semilla (para fixtures y Storybook)

| id | Nombre | Nicho | Moneda · zona | Bolsa (asignado / gastado) | Agentes | Desde |
|---|---|---|---|---|---|---|
| c1 | Flor y Encanto | Floristería con entregas a domicilio | USD · America/Santiago | 60 / 42,30 (71 %) | Recepción (publicado, WhatsApp +56 9 9191 9125, WooCommerce, 31,20, 412 conv., 89 %, 31 a persona) · Ventas mayoristas (en prueba, WhatsApp +56 9 8812 4410, 8,90, 23 conv., 91 %, 2, tope 15) · Cobranza (pausado, WhatsApp +56 9 7720 1180, Stripe, 2,20, 37 conv., 70 %, 11) | «Atiende desde el 3 sep 2026» |
| c2 | ADSL System | Proveedor de internet y fibra para hogares | USD · America/Lima | 40 / 21,80 | Soporte (publicado, WhatsApp + Chat web, HubSpot, 15,40, 318) · Ventas (publicado, Instagram @adslsystem, 6,40, 96) | «Atiende desde el 12 ago 2026» |
| c3 | Clínica Dental Sonrisa | Clínica dental familiar | EUR · Europe/Madrid | 30 / 20,25 | Citas (publicado, WhatsApp, Google Calendar, 20,25, 214) · Recordatorios (listo, sin canal, 0) | «Atiende desde el 20 sep 2026» |
| c4 | Café Origen | Cafetería de especialidad con tostador propio | EUR · Europe/Madrid | 0 / 0 | ninguno | «Creado hoy» |

Ficha de c1: info «Floristería de barrio en Providencia. Entregamos en el día en
comunas del oriente. florencanto.cl · Instagram @florencanto»; web `florencanto.cl`;
redes Instagram `florencanto`, Facebook vacío; sede «Tienda Providencia · Av.
Italia 1420»; horario por bloques L–V 09:00–14:00 y 16:00–20:00, sábado
09:00–14:00, domingo cerrado; servicios «Ramo de temporada» 26,90, «Ramo de 12
rosas» 32,90, «Centro de mesa» 41,90, «Decoración de bodas» sin precio, «Arreglo de
condolencias» 41,90 (todos sin duración, para todos los agentes); fuentes
`florencanto.cl` («14 páginas leídas · hace 2 días», leído) y
`catalogo-bodas-2026.pdf` («18 páginas · subido por ti», leído). c3 tiene un
documento fallido: `tarifas-2026.pdf`, «Imagen escaneada sin texto». c2 y c4 tienen
el horario «leído de la web».

### 1.3 Estado de un agente (`STATUS`)

| Código | Texto | Tono | Icono | Punto en la lista |
|---|---|---|---|---|
| `draft` | «Borrador» | muted | `pencil` | anillo vacío 1,5 px `--faint` |
| `ready` | «Listo · sin canal» | info | `circle-check` | anillo vacío 1,5 px `--info` |
| `testing` | «En prueba» | info | `flask-conical` | relleno `--info` |
| `live` | «Publicado» | positive | `circle-check` | relleno `--accent` |
| `paused` | «Pausado» | warn | `pause` | relleno `--warn` |

### 1.4 Saldo de un cliente (`walletInfo`)

`left = max(0, asignado − gastado)`; `pct = round(gastado / asignado × 100)` (0 sin
asignar); `avail = 100 − pct` (0 sin asignar). El prototipo **no** muestra días
restantes (`days: null`), aunque la propuesta los pide (la consola sí los da: se
mantienen).

### 1.5 Qué necesita un cliente (`attention`), en este orden

1. Sin saldo asignado → «Sin saldo», `t-danger`, icono `circle-alert`.
2. Gastado ≥ 80 % → «Saldo bajo», `t-warn`, `triangle-alert`.
3. Agentes publicados o en prueba sin canal → «1 agente sin canal» / «{n} agentes
   sin canal», `t-info`, `phone`.
4. Sin agentes → «Sin agentes», `t-muted`, `circle-dashed`.
5. Si no → «Al día», `t-positive`, `circle-check`.

Archivado (manda sobre todo) → «Archivado», `t-muted`, `archive`. «Necesita
atención» = tonos warn, danger o info (los «Sin agentes» no cuentan).

### 1.6 Secciones de la ficha (`bizSections`) y sus marcas

| Sección | `ok` | `web` (leído, por revisar) | `todo` | `opt` |
|---|---|---|---|---|
| Datos básicos | siempre | — | — | — |
| Sedes | hay sedes | hay sedes y vienen de la web | sin sedes | — |
| Horarios | algún día abre | abre y viene de la web | ningún día abre | — |
| Servicios | hay servicios | hay y vienen de la web | sin servicios | — |
| Documentos y webs | hay fuentes | — | sin fuentes | — |
| Redes sociales | alguna red con valor | — | sin redes y sin web | sin redes pero con web |

Marca en el índice (`stIcon`), círculo de 16 px: `ok` fondo `--accent-soft` con
`check` 11 px en `--accent-ink`; `web` fondo `--info-soft` con `globe` 10 px en
`--info` y `title="Leído de la web, revísalo"`; `todo` anillo interior 1,5 px
`--faint`; `opt` el mismo anillo al 50 %.

### 1.7 Horarios

- Filas `[día, abre, cierra, turnosExtra[]]`. Modo `blocks`: «Lunes a viernes»,
  «Sábado», «Domingo». Modo `days`: los siete días.
- `shiftTxt`: «09:00 – 14:00 · 16:00 – 20:00» (raya con espacios, turnos unidos
  por « · »); si cierra a la misma hora o antes, añade « (día siguiente)».
- `hourGroups`: en modo días, junta días seguidos con los mismos turnos: «Lunes a
  jueves» (el segundo en minúscula). Nunca junta la fila «Lunes a viernes».
- `hoursSentence` («Así lo dirá el agente»): «Abrimos {grupo en minúsculas} de
  {abre} a {cierra}[ y de {abre} a {cierra}]…, {grupo}… y {último}.» + si hay días
  cerrados «{Días cerrados unidos por " y ", con mayúscula inicial} cerramos.».
  Nocturnos: «de 22:00 a 06:00 del día siguiente». Ejemplo de c1: «Abrimos lunes a
  viernes de 09:00 a 14:00 y de 16:00 a 20:00 y sábado de 09:00 a 14:00. Domingo
  cerramos.». En la consola la frase la devuelve la API (`Hours.label`): se usa esa.
- Pasar de bloques a días copia L–V en los cinco días; de días a bloques toma el
  lunes para L–V (el prototipo pierde datos sin avisar; la consola avisa con
  `ConfirmDialog`: se mantiene).

### 1.8 Lo que se detecta en «Información adicional»

`detectSources` saca: perfiles de `instagram.com/x`, `facebook.com/x`,
`tiktok.com/@x`, `linkedin.com/(company|in)/x`, `youtube.com/(@|c/)x`,
`(twitter|x).com/x`; dominios `.com .es .cl .pe .mx .co .ar .net .org .shop .store
.app .io` (sin `https://`, `www.` ni `/` final) como **web**; y `@usuario` suelto
(3–30) como **Instagram**. Al guardar (`applyDetected`): la primera web pasa a
`web` si no había y se añade a Documentos y webs como «Leyendo…»; cada red rellena
su fila si estaba vacía o se añade. En la consola esto lo hace la API
(`LinkDetection`), con chips editables: se mantiene.

---

## 2. Lista de clientes (`/clients`)

Captura `clients-light.png`. Orden vertical, con 20 px entre bloques.

### 2.1 Cabecera

- h1 «Clientes». Subtítulo: «Cada cliente es un negocio con sus propios agentes.
  Los que necesitan algo salen primero.»
- A la derecha, abajo: botón primario «Nuevo cliente» (sin icono) → modal 7.1.
- Sin antetítulo (eyebrow). Borde inferior `--line`, 20 px por debajo.

### 2.2 Barra de herramientas

Flex `space-between`, hueco 12, con salto de línea.

- **Buscador**: caja flexible, máx. 440 px, mín. 200 px. Icono `search` 15 px a
  10 px del borde izquierdo y 11 px del superior, en `--muted`; input con 32 px de
  relleno izquierdo, placeholder «Buscar por nombre o nicho». Etiqueta oculta
  «Buscar clientes» (`<label for="q" class="sr">`). **Filtra mientras se escribe**
  (nombre + nicho, sin distinguir mayúsculas), sin botón «Buscar»; conserva el foco
  y el cursor tras cada pulsación.
- **Filtro**: `<select>` nativo a la derecha, ancho automático y mínimo 240 px,
  etiqueta oculta «Filtrar clientes». Opciones con su cuenta entre paréntesis:
  «Todos ({n})» (no archivados), «Necesitan atención ({n})», «Activos ({n})» (no
  archivados que no necesitan atención), «Archivados ({n})». Al cambiar, se
  repinta y el foco vuelve al select.

### 2.3 Tabla

Caja `.tablewrap`: borde `--line`, radio 12, fondo `--surface`, `overflow:
visible` (para que se vean los menús). Por debajo de 760 px, `overflow-x: auto`.

Cabecera: «Cliente» (32 % del ancho) · «Estado» · «Agentes» · «Saldo» · columna
de acciones con «Acciones» solo para lectores de pantalla. `th` 13 px/500 `--muted`,
alineado a la izquierda; celdas con 14 px de relleno, borde inferior `--line` (la
última fila sin él) y alineación vertical al centro.

Orden: primero las que necesitan atención; dentro de cada grupo, el orden de la
lista (los recién creados, arriba). La consola deja el orden a la API (menos días
de saldo primero): se mantiene.

Cada fila (toda la fila es clicable: cursor de mano y hover `--surface-2` en
0,12 s → abre el Panel del cliente):

1. **Cliente**: botón `.rowlink` (grid, hueco 2): nombre 14 px/500 y debajo el nicho
   13 px `--muted`. Es el elemento con foco de teclado de la fila.
2. **Estado**: insignia de 1.5 (texto, tono e icono de 12 px).
3. **Agentes**: flex con hueco 8: puntos de 8 px (hueco 4) por agente, con el color
   de 1.3 y `title="{nombre}: {estado}"`; texto 13 px `--muted`: «{n} agente(s)»
   + « · {n} en prueba» + « · {n} pausado(s)» + « · {n} borrador(es)» cuando hay;
   sin agentes, «Ninguno». (El prototipo no pone plural a «pausado» ni
   «borrador»: en la consola, con plural.) Los «listo · sin canal» no suman texto.
4. **Saldo**: grid con hueco 6: minibarra de 120×6 px, píldora, pista
   `--surface-2`, relleno **del porcentaje gastado** en `--s1`; `warn` si ≥ 80 %,
   `danger` (y al 100 %) si no tiene saldo asignado. Debajo, 13 px `--muted`
   tabular: «Quedan {left} de {asignado}» o «Sin saldo asignado».
5. **Acciones**: alineado a la derecha, botón `sm icon ghost` de 30 px con
   `ellipsis` 16, `aria-haspopup="menu"`, `aria-expanded`, `aria-label="Acciones de
   {nombre}"` → menú:
   - «Editar cliente» (`pencil`) → modal 7.1 en edición, sin salir de la lista.
   - «Asignar saldo» (`wallet`) → modal 7.2, sin salir de la lista.
   - separador
   - «Archivar» (`archive`) → 7.4, o en un archivado «Restaurar»
     (`archive-restore`).
   - «Eliminar…» (`trash-2`, rojo) → modal 7.3.

Datos de la semilla: Café Origen («Sin saldo», barra roja llena, «Sin saldo
asignado», «Ninguno») sale primero; luego Flor y Encanto («Al día», «3 agentes · 1
en prueba · 1 pausado», «Quedan 17,70 USD de 60,00 USD»), ADSL System y Clínica
Dental Sonrisa («Quedan 9,75 € de 30,00 €»).

### 2.4 Vacíos y pie

- Sin resultados: una fila de 5 columnas con `.empty` (centrado, 40×20 px de
  relleno) y el texto `--muted`: «Ningún cliente coincide con «{q}».» o, sin
  búsqueda, «Nada por aquí.».
- Pie, 12 px `--muted`: «Cada cliente tiene su moneda; el saldo se compara por
  porcentaje disponible.»

---

## 3. Detalle del cliente: marco (cabecera y pestañas)

Ya alineado en la consola (`client-header-v2.tsx`). Lo que define el prototipo:

- h1 con el nombre; debajo, «{nicho} · {desde}» (16 px `--muted`; el «desde» en
  14 px): «Atiende desde el {d mmm aaaa}» o, si aún no atiende, **«Creado hoy»**.
- Sin insignia de estado ni «⋯» en la cabecera (editar está en Negocio › Datos
  básicos; archivar y eliminar, en la lista y en «Más ajustes»).
- Fila `.tabsrow`: a la izquierda la barra de pestañas de vidrio (pegajosa, 8 px
  bajo el borde superior, `z-index:20`, relleno 5, píldora): «Panel», «Negocio»,
  «Agentes {n}» (cuenta 12 px `--muted`); botones de 32 px, `0 14px`, píldora,
  14 px `--muted`; la activa con fondo `--tab-on`, tinta, 500 y sombra `0 1px 3px`.
  A la derecha, botón primario «+ Nuevo agente» (`plus` 16) → constructor.
- Cambiar de pestaña cierra cualquier edición abierta de Negocio (`S.edit = null`).
- Migas de la barra superior: «Clientes › {nombre}».

---

## 4. Pestaña Panel

Captura `client-panel-light.png`. Grid `.panel` con 16 px arriba: columnas
`minmax(0,1.35fr) minmax(0,1fr)`, hueco 16, `align-items:start`; ≤980 px una
columna. Columna izquierda (grid, hueco 16): tarjeta de lectura (si hay), «Saldo»,
«Este mes». Columna derecha: «Agentes que más consumen».

### 4.1 Tarjeta de lectura (solo mientras se lee la web)

`.card .card-b .reading`: flex, hueco 10, 13 px `--muted`; icono `loader-circle`
16 girando (1 s lineal): «Leyendo {web o @usuario} para completar la ficha: sedes,
horario y servicios…». Al terminar (2,8 s en el prototipo) desaparece y sale el
aviso «Leímos {web}: horario, 1 sede y {n} servicios. Revísalos en Negocio.» con el
botón «Revisar» → pestaña Negocio. Consola: `ClientReadCard` (ya existe, mismo
texto).

### 4.2 Saldo

- Cabecera: h3 «Saldo» y, a la derecha, botón `sm` «+ Asignar saldo» (`plus` 14)
  → modal 7.2. (Quien no puede asignar: «Pedir saldo», según la propuesta.)
- Cuerpo, fila flex `space-between` alineada abajo, con salto de línea, hueco 16:
  - Izquierda: «Quedan» (12 px `--muted`) y el importe en 32 px/600/−0,02em/1,1
    tabular: «17,70 USD».
  - Derecha (13 px, alineado a la derecha): «Consumido **{gastado}** de
    {asignado} · {pct} %» (el gastado en 500; « · {pct} %» solo con saldo
    asignado) y debajo, `--muted`: «{avail} % disponible · bolsa compartida por sus
    agentes» o, sin asignar, «Bolsa compartida por sus agentes».
- Barra apilada 16 px por debajo: 12 px de alto, píldora, pista `--surface-2`.
  Un segmento por agente con gasto > 0, ordenados de más a menos, **ancho =
  gastado del agente / asignado** (lo que queda vacío es lo disponible), colores
  `--s1`…`--s4` en ese orden, separados por una sombra de 1 px `--surface`,
  `title` con el nombre. `role="img"`, `aria-label="Consumo por agente sobre el
  saldo asignado"`. Sin saldo asignado, la pista vacía.
- Leyenda (solo con saldo asignado), 10 px por debajo: flex con salto, hueco
  6×16, 13 px `--muted`; cuadrado de 8 px (radio 2) + nombre por agente, y al final
  «Disponible» con el cuadrado en `--surface-2` y borde interior 1 px
  `--line-strong`.
- Aviso, 14 px por debajo (`.alert`: flex, hueco 10, `10px 12px`, radio 8, 13 px):
  - Sin saldo asignado, rojo (`--danger-soft`, `circle-alert` en `--danger`):
    «**Sin saldo asignado.** Sus agentes pueden crearse y probarse, pero no
    responderán a clientes reales.»
  - Gastado ≥ 80 %, ámbar (`triangle-alert` en `--warn-ink`): «**Queda menos del
    20 % del saldo.** Al llegar a cero, las conversaciones pasan a la Bandeja en
    lugar de quedarse sin respuesta.»
- Sin saldo asignado (Café Origen) el bloque se pinta igual: «Quedan 0,00 €»,
  «Consumido 0,00 € de 0,00 €», «Bolsa compartida por sus agentes», pista vacía y
  el aviso rojo.

### 4.3 Este mes

Cabecera: h3 «Este mes» y, a la derecha, «1–25 oct» (12 px `--muted`; del día 1 a
hoy). Cuerpo `.stats`: tres columnas iguales, hueco 12; cifra 20 px/600 tabular y
etiqueta 13 px `--muted`:

- «{n}» «Conversaciones» (separador de miles es-ES).
- «{n} %» «Resueltas sin persona» (media ponderada por conversaciones; «—» sin
  conversaciones).
- «{n}» «Pasadas a una persona».

### 4.4 Agentes que más consumen

- Cabecera: h3 «Agentes que más consumen» y el enlace-botón «Ver todos» (13 px) →
  pestaña Agentes.
- Lista ordenada `.rank` con los 4 que más gastan (incluye los de gasto 0). Cada
  ítem: grid `1fr auto`, hueco 4×12, `10px 0`, borde inferior `--line` (el último
  sin él):
  - Nombre como botón (500, subrayado al pasar) → abre el agente; al lado su
    insignia de estado (1.3).
  - A la derecha, el gasto (500, tabular).
  - Barra de 6 px a todo el ancho, pista `--surface-2`, ancho = gasto / gasto del
    primero, color de la serie de su puesto.
  - Línea 12 px `--muted`: «{n} conversaciones» + « · {gasto/conv} por
    conversación» (si hay conversaciones) + « · tope {tope} ({pct} %)» (si tiene
    tope).
- Sin agentes: `.empty` con 16 px arriba y abajo: «Aún no tiene agentes. Un agente
  atiende un servicio del negocio por un canal; por ejemplo, citas por WhatsApp.» y
  botón secundario «+ Crear el primer agente» → constructor.

### 4.5 Lo que el prototipo calcula y no pinta

`panelTab` calcula la primera sección pendiente de la ficha («{Sección}: falta. Sin
horario, los agentes no saben cuándo abrís.», «…: leído de {web}. Revísalo para
que los agentes no repitan un dato equivocado.») pero no la muestra. La propuesta
sí la pide («el Panel lo dice en una sola línea con su botón»): la línea que ya
pinta la consola (`panel-missing`) se queda.

---

## 5. Pestaña Agentes

Captura `client-agents-light.png`. Sin título ni texto de introducción: las
tarjetas empiezan 16 px bajo la barra de pestañas («Nuevo agente» ya está en ella).

- Grid `.agrid`: `repeat(auto-fill, minmax(280px, 1fr))`, hueco 12.
- Tarjeta `.acard` (artículo con `role="link"`, `tabindex="0"`, `aria-label="Abrir
  {nombre}"`; Intro la abre): grid, hueco 10, relleno 16. Hover: borde
  `--line-strong` y sombra `0 2px 10px` al 6 % (0,15 s).
  1. Arriba, `space-between`: h3 15 px con el nombre y su insignia de estado.
  2. Propósito 13 px `--muted`, **dos líneas como máximo** (`line-clamp: 2`); sin
     propósito, «Sin descripción todavía.».
  3. Pie con borde superior `--line` y 10 px de relleno, 13 px `--muted`,
     `space-between`: a la izquierda los logos de sus canales (24 px, hueco 4) y la
     etiqueta del primero («+56 9 9191 9125», «@adslsystem», «adslsystem.pe») con
     « +{n}» si hay más; sin canales, insignia `t-muted` «Sin canal» con `phone`
     12. A la derecha, su gasto del mes, tabular.
- Abre: borrador → «Construir y probar»; listo sin canal → «Canales»; el resto →
  «Rendimiento».
- Vacío: tarjeta `.empty` (centrada, 40×20 px): baldosa de 44 px (radio 12,
  `--surface-2`) con `bot` 22; h3 «Este cliente aún no tiene agentes»; «Un agente
  atiende un proyecto o servicio del negocio por un canal. Un cliente puede tener
  varios: Recepción para citas, Ventas para presupuestos, Cobros para pagos.»;
  botón primario «+ Nuevo agente».

---

## 6. Pestaña Negocio

Captura `client-business-light.png` (y el texto completo de la página en
`proto/texts.json`, clave `client-business`).

### 6.1 Composición

- Grid `.biz` 16 px bajo las pestañas: `200px minmax(0,1fr)`, hueco 24,
  `align-items:start`. ≤860 px una columna y el índice deja de ser pegajoso.
- **Índice** (`<nav aria-label="Secciones de la ficha">`, pegajoso a 132 px del
  borde, grid con hueco 2): un botón por sección, 34 px, `0 10px`, radio 8, 14 px,
  `space-between`: el nombre y su marca (1.6). Hover `--surface-2`. → desplaza
  suave hasta la sección (`scroll-margin-top: 140px`). Orden: «Datos básicos»,
  «Sedes», «Horarios», «Servicios», «Documentos y webs», «Redes sociales». Debajo,
  12 px `--muted` con 10 px de relleno: «Lo heredan todos sus agentes. Los cambios
  se aplican al momento y vuelven a pasar sus pruebas.» (ver decisión D6).
- **Secciones**: grid con hueco 14; cada una es una tarjeta con `id="sec-{id}"`.
- **Cabecera de sección** (`head`): a la izquierda (flex, hueco 10) el h3 de 15 px
  y, si la sección es `web`, la insignia `t-info` con `globe` «Leído de la web ·
  revísalo»; si es `todo`, la insignia `t-muted` con punto «Falta». Las
  completas y las opcionales no llevan insignia. A la derecha (flex, hueco 8): si
  es `web`, botón `sm` «✓ Es correcto» (`check` 14) → la marca pasa a «escrito por
  ti» y el aviso «Confirmado. Ya no aparece como pendiente de revisar.»; después,
  la acción propia de la sección.
- **Una sola edición abierta a la vez** (`S.edit`): empezar otra, o cambiar de
  pestaña, cierra la anterior sin guardar.
- Por defecto **todas las secciones están en modo lectura**; los formularios solo
  aparecen tras «Editar» o «Añadir…».

### 6.2 Datos básicos

- Acción de cabecera: `sm` «✎ Editar» (`pencil` 14) → **el modal del cliente en
  edición** (7.1), el mismo del alta.
- Cuerpo: lista de definición `.dl`, grid `160px minmax(0,1fr)`, hueco 10×16; `dt`
  en `--muted`. ≤560 px una columna (hueco 2, 10 px bajo cada `dd`).
  - «Nombre» · {nombre}
  - «Nicho» · {nicho}
  - «Información adicional» · {info} o «Sin información» (`--muted`)
  - «Web» · {web} o «Sin web» (`--muted`)
  - «Zona horaria» · «{zona} · {moneda}» (p. ej. «America/Santiago · USD»)
- Siempre `ok` en el índice.

### 6.3 Sedes

- Acción de cabecera: `sm` «+ Añadir sede» → abre la fila de alta (abajo).
- Lectura: lista `.srcs`; cada sede: flex, hueco 12, `10px 0`, borde inferior
  `--line`; baldosa de 32 px (radio 8, `--surface-2`) con `map-pin` 15; nombre
  (500) y dirección (12 px `--muted`) en columna; a la derecha, botón `sm icon
  ghost` `trash-2` 14 con `aria-label="Quitar sede"`, al 60 % de opacidad (100 % al
  pasar por la fila) → se quita al momento y avisa «Sede quitada.» (sin deshacer).
- Vacío: «Sin sedes. Si atiende solo online, déjalo vacío.» (`--muted`).
- Alta (bajo la lista, 12 px): grid `1fr 1.4fr auto`, hueco 8, alineado abajo:
  «Nombre» (placeholder «Centro», foco automático), «Dirección» («Calle y
  número») y botón primario «Añadir». Sin nombre no hace nada. Guardar: añade, marca
  la sección como «escrita por ti» y avisa «Sede añadida.». (El prototipo no pone
  «Cancelar»; en la consola, con «Cancelar», como Servicios.)

### 6.4 Horarios

**Lectura** (acción de cabecera `sm` «✎ Editar»):

- Con horario: `.dl` con un `dt` por grupo (1.7) y en `dd` (tabular) el texto de
  turnos o «Cerrado» (`--muted`). Debajo, 12 px por debajo y 12 px `--muted`:
  «Mismo horario para {su sede | las {n} sedes}. Así lo dirá el agente:
  «{frase}»».
- Sin horario: «Sin horario, el agente responderá «no lo sé» cuando pregunten
  cuándo abrís.» (`--muted`).

**Edición** (la cabecera pierde «Editar»; grid con hueco 12):

1. Fila con hueco 12: control segmentado de vidrio (`.segm`, `role="group"`,
   `aria-label="Modo de horario"`, botones `aria-pressed`): «Por bloques» · «Día
   por día»; al lado, 12 px `--muted`: «Lunes a viernes comparten horario.» o «Cada
   día con su horario. Deja vacío el día que cierra.».
2. Una fila `.hrow` por día o bloque: grid `150px minmax(0,1fr)`, hueco 10, `8px 0`,
   borde inferior `--line` (≤640 px una columna). Etiqueta del día (`for` al primer
   campo, 8 px de relleno arriba). Turnos en grid con hueco 8; cada turno, flex con
   hueco 6 y salto de línea:
   - Primer turno: `input type=time` (112 px) «a» `input type=time` (con
     `aria-label="{día} cierre"`); si cierra a la misma hora o antes, insignia
     `t-info` «Nocturno · cierra al día siguiente»; si el día abre, botón `sm
     ghost` «Cerrado» (vacía el día y sus turnos); si no, el texto «Cerrado» (12 px
     `--muted`).
   - Turnos extra: los mismos dos campos (`aria-label="{día} turno {n} apertura"`
     y «… cierre»), la insignia nocturna si toca y botón `sm icon ghost` `x` 14
     «Quitar turno».
   - Si el día abre: enlace-botón 13 px «+ Añadir turno» (`plus` 13), alineado a la
     izquierda.
3. Ayuda: «Usa turnos para horarios partidos (09:00–14:00 y 17:00–21:00) o
   nocturnos (22:00–06:00): si el cierre es anterior a la apertura, termina al día
   siguiente.»
4. Botones `sm`: primario «Guardar horario» y `ghost` «Cancelar».

Guardar: descarta turnos extra incompletos, cierra los días sin apertura o sin
cierre, guarda el modo, marca «escrito por ti» y avisa «Horario guardado. Volví a
pasar las pruebas de sus agentes.» (ver D6).

### 6.5 Servicios

- Acción de cabecera: `sm` «+ Añadir servicio» → fila de alta.
- Tabla (en `.tablewrap`, sin recorte para que salga el menú): «Servicio» ·
  «Duración» · «Precio» · «Lo usan» · acciones (oculto: «Acciones»). Celdas al
  centro; duración y precio sin salto de línea y tabulares.
  - Duración: «{n} min» o «—» (`--muted`).
  - Precio: `money()`; 0 → «Gratis»; sin precio → «Sin precio» en `--warn-ink`.
  - Lo usan (13 px `--muted`): si es para todos, los nombres de los agentes que
    atienden «todos los servicios» separados por coma («—» si ninguno), o «Todos
    los agentes que crees» si el cliente aún no tiene agentes; si es para algunos,
    sus nombres.
  - «⋯» (`aria-label="Acciones de {servicio}"`) → «✎ Editar», «⧉ Duplicar»
    (`copy`), separador, «🗑 Eliminar» (rojo).
- Editar (la fila se sustituye por un formulario a 5 columnas, grid `1.6fr .7fr
  .7fr 1.4fr auto`, hueco 8, alineado abajo): «Servicio» (foco), «Minutos»
  (`inputmode=numeric`), «Precio» (`inputmode=decimal`), «Lo usan» (select: «Todos
  los agentes» / «Solo {agente}» por cada uno), primario «Guardar» y `ghost`
  «Cancelar». Guardar: nombre vacío deja el anterior; minutos no numéricos →
  sin duración; precio vacío → «Sin precio», no numérico → el anterior. Aviso
  «Servicio guardado. Los agentes ya lo usan.».
- Duplicar: inserta «{nombre} (copia)» justo debajo y lo abre en edición.
- Eliminar: lo quita y avisa ««{nombre}» eliminado.» con «Deshacer» (vuelve a su
  sitio).
- Añadir (bajo la tabla, `.svcadd`: `1.5fr .7fr .7fr 1.2fr auto`; ≤860 px dos
  columnas con el nombre a todo el ancho): «Servicio» (foco), «Minutos», «Precio
  ({€|USD})», «Lo usan» y «Añadir» + «Cancelar». Sin nombre no hace nada. Aviso:
  «Servicio añadido. Ya lo conocen los agentes que atienden todos los servicios.» o
  «Servicio añadido. Solo lo usa {agente}.».
- Vacío: «Sin servicios. Añádelos o sube una carta o catálogo en Documentos.»
- Pie de la tarjeta: interruptor encendido (`role="switch"`, `aria-label="Conectar
  servicios nuevos"`, sin efecto en el prototipo) + 13 px: «Los servicios nuevos
  llegan solos a los agentes que atienden «todos los servicios».» (ver D7).

### 6.6 Documentos y webs

Sin acción de cabecera. Cuerpo en grid con hueco 14:

1. 13 px `--muted`: «Lo que leemos para responder: carta, catálogo, tarifas,
   preguntas frecuentes. Si una fuente ya no vale, quítala y los agentes dejan de
   usarla al momento.»
2. Fila `.srcrow` (grid `1fr auto auto`, hueco 8, alineado abajo; ≤640 px una
   columna): campo «Pegar una página web» (placeholder
   «https://negocio.com/carta», `inputmode=url`), botón «🔗 Leer página» (`link`
   14) y botón «⤒ Subir archivo» (`upload` 14). Error en 13 px `--danger`: «Eso no
   parece una dirección web. Ejemplo: negocio.com/carta» o «Esa página ya está en
   la lista.». Acepta la dirección sin `https://`.
3. Zona de arrastre `.drop`: borde discontinuo 1,5 px `--line-strong`, radio 12,
   relleno 18, centrada, `--muted`: `upload` 18 + «O arrastra aquí PDF, Word o
   fotos de la carta».
4. Lista `.srcs`: baldosa de 32 px con `globe` (web) o `file-text` (archivo); nombre
   (500) y detalle (12 px `--muted`: «14 páginas leídas · hace 2 días», «18 páginas
   · subido por ti», «Imagen escaneada sin texto», «Leyendo…», «Subiendo…»);
   insignia «Leído» (`t-positive`, `circle-check`), «Leyendo» (`t-info`,
   `loader-circle`) o «No se pudo leer» (`t-danger`, `circle-alert`); botón `trash-2`
   «Quitar {nombre}» (`title="Quitar"`, al 60 %) → aviso ««{nombre}» quitado. Los
   agentes dejan de usarlo.» con «Deshacer».
5. Si alguna falló: «Un archivo escaneado sin texto no se puede leer. Súbelo como
   PDF con texto o copia los precios en Servicios.» (13 px `--muted`).

Leer página: añade la fuente «Leyendo…», vacía el campo, si el cliente no tenía web
la toma, avisa «Leyendo {dirección}…» y al terminar queda «1 página leída · hoy».
Subir archivo: avisa «Subiendo el archivo…» y al terminar «Leído «{archivo}». No
cambia los servicios que ya tenías.» (o, sin servicios, «… Encontré servicios con
precio: revísalos.»).

### 6.7 Redes sociales

Sin acción de cabecera. Cuerpo `.social` (grid, hueco 10):

1. Sin web: aviso `info` (`info` 16): «Este negocio no tiene web. Sus redes son la
   mejor fuente: leemos la biografía, las publicaciones fijadas y los
   destacados.». Con web, 13 px `--muted`: «Opcional si ya hay web. Sirven para
   responder sobre novedades y promociones. Si pegas un enlace en «Información
   adicional», aparece aquí solo.».
2. Una fila por red (Instagram y Facebook siempre, primero): grupo `.prefix` (borde
   `--line-strong`, radio 8, foco del grupo con contorno 2 px `--primary`): a la
   izquierda, 38 px de alto, `0 10px`, borde derecho `--line`, 13 px `--muted`: el
   logo de 24 px y el nombre («Instagram»); el input sin borde (placeholder
   «usuario» en Instagram y Facebook, «enlace o usuario» en las demás; etiqueta
   oculta con el nombre de la red). Las añadidas llevan al final un botón `x`
   «Quitar {red}». Se guarda al escribir (sin botón).
3. «+ Añadir otra red social» (`sm`) → fila `.socialadd` (grid `160px 1fr auto`,
   hueco 8; ≤640 px una columna): select «Red» con las que faltan (Instagram,
   Facebook, TikTok, LinkedIn, YouTube, X, Threads), «Enlace del perfil»
   (placeholder «https://www.tiktok.com/@negocio», foco), primario «Añadir» y
   `ghost` «Cancelar». Del enlace saca la red y el usuario; si no reconoce la red,
   guarda el texto sin protocolo en la elegida. Aviso «{Red} añadido.».

---

## 7. Modales y capas

### 7.0 Marco común

- Velo `.scrim` fijo (`z-index:70`, `--scrim`, aparece en 0,2 s); clic en él
  cierra.
- Caja (`z-index:71`, centrada, 16 px de margen y las zonas seguras):
  `width: min(var(--mw, 620px), 100%)`, alto máximo 100 %, columna flex, fondo
  `--surface`, borde `--line`, radio 18, sombra `0 24px 60px` al 28 % + `0 2px 6px`
  al 12 %; entra con `translateY(10px) scale(.985)` → 0 y opacidad en 0,26 s
  `cubic-bezier(.16,1,.3,1)`.
- `role="dialog"`, `aria-modal="true"`, `aria-labelledby="modal-t"`. Escape
  cierra. El primer campo marcado recibe el foco.
- Cabecera (`22px 24px 10px`): h2 21 px y párrafo 14 px `--muted` (máx. 56ch); a
  la derecha botón `ghost icon` `x` «Cerrar».
- Cuerpo (`10px 24px 22px`, grid con hueco 18, con su propio scroll).
- Pie (`14px 24px`, borde superior `--line`, fondo `--surface-2`, radios
  inferiores 18): a la izquierda un texto o botón; a la derecha (`.r`, hueco 8)
  «Cancelar» (`ghost`) y la acción primaria.

### 7.1 Nuevo cliente / Editar cliente

Captura `new-client-light.png`. 620 px. **Ya alineado hoy** en la consola salvo lo
que dice el hueco 11. Contenido:

- Título «Nuevo cliente» / «Editar cliente». Texto: «Con esto basta. Sedes,
  horarios y servicios los completas después en su ficha, o los leemos de su web.»
  / «Los cambios se aplican al momento a todos sus agentes.».
- «Nombre del negocio» (máx. 60, foco). «Nicho» (máx. 80) + chips de sugerencia
  fijos «Barbería», «Clínica dental», «Restaurante vegano», «Floristería»,
  «Inmobiliaria» (28 px, píldora; clic → reemplaza el nicho; la consola los saca
  de la API y los añade: se mantiene) + ayuda «Escríbelo como lo dirías:
  «restaurantes veganos», «clínica de fisioterapia deportiva». Lo usamos para las
  pruebas del sector.». «Información adicional · opcional» (textarea de 4 filas).
  (Placeholders: los generales de la consola, comentario 1.)
- Línea de detección `.detect` (13 px `--muted`, `sparkles` 14), siempre visible:
  sin nada, «Si pegas su web o su @ de Instagram, leemos sedes, horarios y
  servicios por ti.»; con algo, «Irá a la ficha:» + chips no clicables con el icono
  (`globe` o logo) y el valor («florencanto.cl», «@florencanto»), `title`
  «Documentos y webs» o «Redes sociales · {red}». Se actualiza al escribir.
- `<details>` «Más ajustes» (borde superior `--line`, 14 px arriba; `chevron-right`
  14 que gira 90° al abrir) con el resumen « · {zona} · {moneda}» en 12 px
  `--muted` y 400. Dentro, dos columnas (≤520 px una): «Zona horaria» y «Moneda de
  cobro» («Euro (€)», «Dólar (USD)»). **Solo en edición**, debajo: «Archivar
  cliente» (`archive`) y «Eliminar…» (`danger`, `trash-2`) + ayuda «Archivar pausa
  todos sus agentes y se puede deshacer. Eliminar borra el cliente y sus
  agentes.».
- Pie: a la izquierda «Nombre y nicho son obligatorios» o, si ya están,
  «⌘ ↵ para guardar» (con `kbd`); a la derecha «Cancelar» y «Crear cliente» /
  «Guardar cambios» (deshabilitado hasta tener nombre y nicho). ⌘/Ctrl + Intro
  guarda.
- Crear → aterriza en el Panel del cliente nuevo, aviso «{nombre} creado.» y, si
  había web o @, la tarjeta de lectura (4.1). Guardar → aviso «Guardado. Añadí a la
  ficha: {lo nuevo}.» o «Cambios guardados. Sus agentes ya los usan.».

### 7.2 Asignar saldo

620 px. Desde el Panel («Asignar saldo») o desde el «⋯» de la lista.

- Título «Asignar saldo a {nombre}». Texto: «Sale del saldo de tu cuenta de
  partner. Sin saldo, sus agentes no responden.».
- «Cantidad»: cuatro botones (`.amounts`, 4 columnas, hueco 8; ≤520 px dos), 48 px,
  radio 10, 17 px/500 tabular: 10, 20, 50 y 100 en la moneda del cliente; el
  elegido con borde e interior `--primary` y fondo `--accent-soft`
  (`aria-pressed`).
- «Otra cantidad» (`.bigin`: borde, radio 12, `12px 16px`; input sin borde de
  30 px/600 con la moneda detrás en 18 px `--muted`; placeholder «0,00»; foco).
  Escribir desmarca los botones.
- Recibo `<dl>` (borde, radio 12, `aria-live="polite"`): «Saldo actual de
  {nombre}» · {saldo}; «Asignas ahora» · «+ {importe}» o «—»; si la moneda del
  cliente no es la del partner, fila pequeña «Sale de tu cuenta (1 € = 1,08 USD)» ·
  «− {importe en EUR}»; total «Nuevo saldo de {nombre}» (22 px/600); fila pequeña
  «Te queda en tu cuenta de partner» · «{queda} de {saldo}» o, si no llega,
  «Faltan {importe}» en `--danger`.
- Casilla (marcada por defecto): «**Avisarme cuando le quede menos del 20 %**» /
  «Así lo recargas antes de que deje de responder.».
- Pie: si no llega, enlace «Recargar mi cuenta» a la izquierda; «Cancelar» y
  «Asignar saldo» (deshabilitado sin importe o si no llega).
- Guardar → aviso «Asignados {importe} a {nombre}. En tu cuenta quedan {saldo}.».

### 7.3 Eliminar cliente

520 px. Desde «Eliminar…» de la lista o de «Más ajustes».

- Título «Eliminar {nombre}». Texto: «Se borran sus {n} agente(s), sus canales y su
  ficha. No se puede deshacer. Si solo quieres dejar de atenderlo, archívalo.».
- Campo «Escribe **{nombre}** para confirmar» (foco, sin autocompletar). Intro
  confirma.
- Pie: a la izquierda «Mejor archivar» (`archive`) → archiva (7.4); a la derecha
  «Cancelar» y «Eliminar» (primario con fondo `--danger`), habilitado solo cuando
  el texto coincide (sin espacios a los lados ni mayúsculas).
- Eliminar → si estabas dentro del cliente, vuelves a la lista; aviso «{nombre}
  eliminado.».

### 7.4 Archivar y restaurar (sin modal)

- Archivar: el cliente pasa a archivado, sus agentes publicados o en prueba pasan a
  pausado (recordando su estado), y aviso «{nombre} archivado. Sus agentes quedan en
  pausa.» con «Deshacer». (Desde «Más ajustes» el prototipo deja el modal abierto:
  en la consola, cerrarlo.)
- Restaurar (o «Deshacer»): vuelve a activo y cada agente a su estado. Si era el
  último archivado y el filtro era «Archivados», el filtro vuelve a «Todos».

### 7.5 Aviso (toast)

Fijo, centrado, 84 px sobre el borde inferior (más la zona segura), `z-index:90`,
**vidrio**, píldora, flex con hueco 12, `10px 10px 10px 16px`, 14 px, ancho máximo
`100% − 32px`; entra subiendo 12 px en 0,3 s. Icono `circle-check` en
`--accent-ink`, el texto, la acción opcional (`btn sm`) y un `x` «Cerrar aviso».
`role="status"`. Se va a los 6 s; uno nuevo sustituye al anterior.

### 7.6 Velo de Meta (`veilView`)

Solo para conectar WhatsApp desde un agente (fuera de esta pantalla): capa fija
`z-index:85` con `color-mix(--accent 22 %, --scrim)` y desenfoque 6 px; caja de
480 px, radio 18, 28 px de relleno, centrada. Escape la cierra. Ya existe en la
consola (`channels`).

---

## 8. Acciones (`data-act`) de estas pantallas

| Acción | Dónde | Efecto | Aviso |
|---|---|---|---|
| `new-client` | Lista | Modal 7.1 vacío | — |
| `open-client` | Fila / nombre | Panel del cliente; cierra menús | — |
| `menu` | «⋯» | Abre o cierra ese menú (uno a la vez) | — |
| `m-edit` | «⋯» › Editar cliente | Modal 7.1 en edición | — |
| `m-topup` / `topup` | «⋯» / Panel | Modal 7.2 (importe vacío, aviso marcado) | — |
| `m-archive` | «⋯» / Más ajustes / Mejor archivar | 7.4 | «{nombre} archivado. Sus agentes quedan en pausa.» + Deshacer |
| `m-restore` | «⋯» / Deshacer | 7.4 | — |
| `m-delete` → `do-delete` | «⋯» / Más ajustes | Modal 7.3 → borra | «{nombre} eliminado.» |
| `niche` | chips del nicho | Pone el nicho | — |
| `toggle-more` | «Más ajustes» | Abre o cierra | — |
| `save-client` | Modal 7.1 | Crea o guarda (ver 7.1) | ver 7.1 |
| `ctab` | Pestañas, «Ver todos» | Cambia de pestaña y cierra la edición | — |
| `new-agent` / `open-agent` | Cabecera, Panel, Agentes | Constructor / agente | — |
| `go-biz` | Aviso «Revisar» | Pestaña Negocio | — |
| `biz-go` | Índice | Desplaza a la sección | — |
| `edit-client` | Datos básicos › Editar | Modal 7.1 en edición | — |
| `confirm-sec` | «Es correcto» | Sección a «escrita por ti» | «Confirmado. Ya no aparece como pendiente de revisar.» |
| `add-sede` / `save-edit[sedes]` / `del-sede` | Sedes | Alta / guardar / quitar | «Sede añadida.» / «Sede quitada.» |
| `start-edit[hours]`, `hours-mode`, `hours-close`, `shift-add`, `shift-del`, `save-edit[hours]`, `cancel-edit` | Horarios | 6.4 | «Horario guardado. Volví a pasar las pruebas de sus agentes.» |
| `add-service`, `save-edit[services]`, `svc-edit`, `svc-save`, `svc-dup`, `svc-del`, `undo-svc` | Servicios | 6.5 | ver 6.5 |
| `add-url`, `add-file`, `del-source`, `undo-source` | Documentos y webs | 6.6 | ver 6.6 |
| `start-edit[social]`, `save-edit[social]`, `del-social`, entrada `data-social` | Redes | 6.7 | «{Red} añadido.» |
| `amt`, `save-topup` | Modal 7.2 | Elige importe / asigna | ver 7.2 |
| `close`, `untoast` | Modal / aviso | Cierra | — |

Teclado: Escape cierra (menú de usuario, velo, modal, por ese orden); ⌘/Ctrl +
Intro guarda el modal del cliente; Intro en el campo de 7.3 elimina; Intro sobre
una tarjeta de agente la abre.

---

## 9. Transversal: responsive, accesibilidad y movimiento

- **Responsive**: tabla de clientes con scroll horizontal propio ≤760 px; Panel en
  una columna ≤980; Negocio en una columna ≤860 (índice no pegajoso); `.dl` ≤560 y
  `.hrow`, `.srcrow`, `.socialadd` ≤640 en una columna; alta de servicio en dos
  columnas ≤860; modal de saldo en dos columnas de importes ≤520. La página nunca
  hace scroll horizontal.
- **Accesibilidad**: etiquetas con `for` en todos los campos (las de buscador y
  filtro, ocultas); filas clicables con un botón real dentro; menús con
  `aria-haspopup`, `aria-expanded` y nombre «Acciones de {x}»; pestañas
  `role="tablist"`/`tab` con `aria-selected` (la consola usa enlaces con
  `aria-current`: vale, cada pestaña es una URL); barra apilada `role="img"` con
  etiqueta; modal con foco inicial, Escape y título asociado; recibo con
  `aria-live`; aviso `role="status"`; foco visible: contorno 2 px `--primary` a
  2 px.
- **Movimiento**: hover de filas 0,12 s; tarjetas 0,15 s; botones bajan 1 px al
  pulsar; modal 0,26 s; velo del modal 0,2 s; aviso 0,3 s; spinner 1 s lineal; el
  interruptor 0,2 s. Con `prefers-reduced-motion: reduce`, todo a 0,01 ms. El
  vidrio pasa a sólido con `prefers-reduced-transparency`.

---

## 10. Huecos con la consola, de más a menos visibles

### H1. Negocio no tiene «Documentos y webs» ni «Redes sociales»

- **Prototipo**: seis secciones; las dos últimas, 6.6 y 6.7, con su marca en el
  índice.
- **Consola**: `BusinessSectionsView` pinta Datos básicos, Sedes, Horario, Fechas
  especiales y Servicios. Los componentes `BusinessSources` y `BusinessLinks`
  existen, con textos e i18n, pero **no se montan en ninguna página**.
- **Cambiar**: `app/(console)/clients/[ref]/business/page.tsx` (pedir también
  `listSources` y `getBusiness`); `components/business/sections/business-sections.tsx`
  (dos entradas en `ORDER` y en el índice); `components/business/sources/business-sources.tsx`
  y `business-links.tsx` (envolverlos en `SectionFrame`, título «Redes sociales»,
  textos del prototipo, zona de arrastre, el grupo `.prefix` con logo, aceptar
  direcciones sin `https://` anteponiéndolo, el aviso «Este negocio no tiene
  web…»); `i18n/lanes/business.ts`.
- **Datos**: existen. `GET /business/sources` y sus acciones (subir ≤10 MB, URL,
  volver a leer, quitar y recuperar 10 min); `PUT /business/links` con `If-Match`.
  El estado de ambas secciones y las redes guardadas llegan en `GET /business`
  (`BusinessRecord.sections[]` y `spec`): comprobar que `spec.links` trae
  `LinkItem[]` y tomar la revisión de `sections.find(s => s.section === "links")`;
  si no, hace falta `GET /business/links`. Solo falta en la API el número de
  páginas leídas («14 páginas leídas»): `Source` no lo trae (opcional; mientras, la
  consola dice «Leído {cuándo}» y el tamaño).

### H2. Las secciones son formularios siempre abiertos

- **Prototipo**: lectura por defecto (`dl` y listas) y «Editar» / «Añadir…» en la
  cabecera de cada sección; una edición a la vez; Datos básicos se edita en el
  **modal del cliente**.
- **Consola**: quien puede escribir ve Datos básicos como siete inputs (con «País
  (ISO, dos letras)»), un textarea y «Guardar datos básicos»; Horario con el editor
  siempre abierto y su «Guardar horario»; cada sección lleva además un párrafo de
  introducción.
- **Cambiar**: `section-frame.tsx` (hueco para las acciones de la cabecera, quitar
  la intro por defecto); `basics-section.tsx` (`dl` de 6.2 + «Editar» que abre
  `ClientModal` en edición, como `client-menu.tsx › openEdit/editBody`; mejor
  extraer un `useClientEdit`); `hours-section.tsx` y `shift-editor.tsx` (lectura con
  grupos y frase; edición con el segmentado de vidrio, «a», botón «Cerrado»,
  «+ Añadir turno» como enlace, «Guardar horario» + «Cancelar»); `locations-section.tsx`;
  `services-section.tsx`; un estado `editing` compartido en `business-sections.tsx`.
- **Datos**: ninguno nuevo.

### H3. Índice y cabeceras: marcas, «Leído de la web · revísalo» y «Es correcto»

- **Prototipo**: en el índice, un círculo de 16 px por sección (1.6); en la
  cabecera, solo «Leído de la web · revísalo» (info, `globe`) con el botón «Es
  correcto», o «Falta»; nada si está completa.
- **Consola**: una `StatusBadge` con texto en el índice y en cada sección
  («Completa», «Leída · revísala», «Pendiente», «Opcional»); en móvil el estado del
  índice es solo para lectores de pantalla; ningún «Es correcto» (el componente
  `ProvenanceLabel` existe y no se usa).
- **Cambiar**: `business-sections.tsx` (índice con iconos y `title`),
  `section-frame.tsx` (`SectionStateBadge` → solo `read_pending` y `pending`, con
  los textos del prototipo; botón «Es correcto» con `confirmSectionAction`),
  `provenance-model.ts` si se quiere decir «de un documento» o «de sus redes» en
  vez de «de la web».
- **Datos**: existen (`state` en cada sección; `POST /sections/{s}/confirm`;
  `BusinessRecord.provenance`). Mapa: `complete`→`ok`, `read_pending`→`web`,
  `pending`→`todo`, `optional`→`opt`.

### H4. El Panel tiene otra composición

- **Prototipo** (4): dos columnas 1,35 : 1; «Asignar saldo» `sm` en la cabecera de
  «Saldo»; «Quedan» + 32 px y a la derecha consumido y disponible; barra apilada
  **contra lo asignado** con «Disponible»; «Este mes» con tres cifras y el periodo a
  la derecha; a la derecha, la lista de los 4 que más consumen con barra, estado y
  «Ver todos».
- **Consola**: «Saldo» y «Este mes» lado a lado y debajo una tabla de cinco
  columnas a todo el ancho (con el editor de tope por agente); la barra reparte el
  100 % entre agentes (`share_pct`), así que siempre llena y sin «Disponible»; el
  botón de saldo abajo; insignia de atención en la cabecera de Saldo; sin saldo
  asignado solo «Este cliente aún no tiene bolsa asignada.»; «Este mes» con cuatro
  cifras (añade «Consumo del mes»).
- **Cambiar**: `components/clients/v2/client-panel.tsx` (rejilla, cabecera con
  `BalanceButton size="sm" variant="outline"`, barra con ancho
  `spent / bag.assigned`, leyenda con «Disponible», lista `.rank`, estado vacío con
  el aviso rojo), `i18n/lanes/business.ts` (`panel.*`). El tope por agente puede
  quedarse como enlace en la línea «· tope {x} ({pct} %)».
- **Datos**: existen (`spend_by_agent[].spent`, `bag.assigned`,
  `top_agents[].visible_state | conversations | spend_per_conversation | cap`).
  Comprobar que `spend_by_agent` mide el mismo periodo que `bag.spent`; si no, la
  barra contra lo asignado necesita el gasto por agente desde la asignación (API).

### H5. Las tarjetas de agente no dicen qué hace, por dónde ni cuánto gasta

- **Prototipo** (5): propósito en dos líneas, logo y número del canal (+N), gasto
  del mes; sin título ni intro en la pestaña.
- **Consola** (`AgentCards`): h2 «Agentes», intro y un segundo «Nuevo agente»
  (repite el de la cabecera); tarjeta con nombre, «Por defecto», estado, «Con
  cambios sin publicar», «{n} canales» y un chevron.
- **Cambiar**: `components/builder/agent-cards.tsx` (quitar la cabecera en v2;
  tarjeta del prototipo; el estado vacío con su texto), `lib/backend.ts`
  (`ClientAgent`), `i18n/lanes/builder.ts`.
- **Datos**: **falta en la API**. `AgentOut` (`apps/api/src/nexus_api/api/console/agents_list.py`)
  no trae propósito, tipo de canal ni gasto, aunque el contrato (§4, `GET
  /agents`) los promete. Añadir `purpose` (la descripción de la versión),
  `channels[].provider` y `spent: Money` del mes. Mientras, el gasto puede salir de
  `getClientPanel().spend_by_agent`.

### H6. La lista de clientes

- **Prototipo** (2): subtítulo «Cada cliente es un negocio…»; buscador con lupa que
  filtra al escribir; filtro en `<select>` «Todos (4)»; fila entera clicable;
  «Al día»; agentes «3 agentes · 1 en prueba · 1 pausado»; columna «Saldo» con
  minibarra y «Sin saldo asignado»; menú «Editar cliente», «Asignar saldo», —,
  «Archivar», «Eliminar…» con iconos; archivar sin confirmar y con «Deshacer»; pie
  «Cada cliente tiene su moneda…».
- **Consola** (`ClientsListV2`): antetítulo y «Primero los que necesitan algo y,
  dentro de cada grupo, los que tienen menos días de saldo.»; formulario con botón
  «Buscar»; filtros en píldoras «Todos · 4»; solo el nombre es enlace; «Todo en
  orden»; «{n} de {total} atendiendo»; columna «Bolsa» sin barra, con «{n} días ·
  {pct} % libre» y «Sin bolsa asignada»; menú sin iconos, con «Nuevo agente» y el
  separador solo antes de «Eliminar»; archivar con `ConfirmDialog`.
- **Cambiar**: `app/(console)/clients/page.tsx` (cabecera),
  `components/clients/v2/clients-list-v2.tsx` (buscador con `router.replace` y
  espera de ~250 ms, `NativeSelect` de filtro, `onClick` en la fila manteniendo el
  enlace, minibarra, texto de agentes, pie), `client-v2-model.ts` (textos),
  `client-menu.tsx` (iconos, «Editar cliente», «Eliminar…», separador),
  `i18n/lanes/business.ts` (`clients.v2.*`).
- **Datos**: existen (`bag.pct_spent`, `agents_summary.testing | paused | draft`).
  Los días y el «% libre» de la consola se pueden dejar en el `title` de la barra.

### H7. Servicios: edición en la fila y «Eliminar» con deshacer

- **Prototipo** (6.5): «+ Añadir servicio» en la cabecera; edición y alta en la
  propia fila; «Sin precio» en ámbar; menú Editar / Duplicar / Eliminar; eliminar
  con «Deshacer»; «Todos los agentes que crees»; interruptor con la línea de
  servicios nuevos.
- **Consola**: diálogo para crear y editar (con descripción, «Se reserva»,
  duración en pasos de 5 y precio con radios); menú Editar / Quién lo ofrece /
  Duplicar / Archivar; «Añadir servicio» al pie; «Ningún agente lo ofrece todavía».
- **Cambiar**: `services-section.tsx`, `services-model.ts`, i18n.
- **Datos**: la vista no pide nada. «Deshacer» tras eliminar: no hay `POST
  /services/{id}/restore`; se puede con `GET /history?section=services` + `POST
  /history/{id}/undo` (existen) o añadiendo el restaurar (API). Ver D3.

### H8. Sedes con otro aspecto

- **Prototipo** (6.3): lista con baldosa `map-pin`, nombre y dirección y una
  papelera; «+ Añadir sede» en la cabecera; alta en una fila de tres columnas.
- **Consola**: cajas con borde, teléfono y «Horario propio / Horario del negocio»,
  lápiz y archivar; «Añadir sede» al pie; formulario con teléfono; «Ver las
  archivadas».
- **Cambiar**: `locations-section.tsx`. **Datos**: ninguno (quitar = archivar).

### H9. Eliminar y archivar

- **Prototipo**: 7.3 con «Mejor archivar», el número de agentes y «Eliminar» en
  rojo; «Archivar cliente» y «Eliminar…» dentro de «Más ajustes» al editar.
- **Consola**: `ConfirmDialog` con «Se borra para siempre, con sus agentes y sus
  conversaciones…», «Escribe «{nombre}»», «Eliminar para siempre»; sin «Mejor
  archivar»; el modal de edición no tiene archivar ni eliminar. La API exige
  archivar antes de eliminar (`archive_first`).
- **Cambiar**: `client-menu.tsx`, `client-modal.tsx` (`MoreSettings` en modo
  edición), `packages/ui/src/components/confirm-dialog.tsx` (una acción secundaria
  a la izquierda) o un diálogo propio. **Datos**: ninguno.

### H10. «Creado hoy» en la cabecera

- **Prototipo**: sin atender aún, «Creado hoy» (o la fecha) en lugar de «Atiende
  desde…».
- **Consola**: no dice nada.
- **Cambiar**: `client-header-v2.tsx` y `clients/[ref]/layout.tsx` (pasar
  `legacy.created_at`). **Datos**: existen (`ClientSummary.created_at`).

### H11. Restos del modal del cliente (ya alineado)

- «Nombre del negocio» frente a «Nombre»; texto de cabecera del alta y de la
  edición; la línea de detección con `sparkles` siempre visible frente a la ayuda
  del campo; «Moneda de cobro» frente a «Moneda»; pie «⌘ ↵ para guardar» y el
  atajo (no existe en la consola); el contador «{n} de 2000» no está en el
  prototipo. Archivo: `client-modal.tsx`, `i18n/lanes/business.ts`.

### H12. Restos del modal de saldo

- «Sale del saldo de tu cuenta de partner. Sin saldo, sus agentes no responden.»
  frente a «Sale de tu cuenta y queda en su bolsa…»; «Cantidad» frente a
  «Cuánto»; «Asignas ahora», «Nuevo saldo de {nombre}», «Te queda en tu cuenta de
  partner»; la ayuda de la casilla. Archivos: `components/money/assign-dialog.tsx`,
  `i18n/lanes/money.ts`.

### H13. Insignias (afecta a todas las pantallas)

- **Prototipo**: texto del color del tono e icono de 12 px.
- **Consola**: `StatusBadge` con texto en tinta y punto.
- **Cambiar**: `packages/ui/src/components/status-badge.tsx` (decisión del sistema de
  diseño: contraste del texto tintado sobre el fondo suave). Ver D5.

---

## 11. Lo que la consola tiene y el prototipo no (se mantiene salvo que se decida)

- **Fechas especiales** (sección propia): el prototipo no la tiene. Propuesta:
  dentro de la tarjeta de Horarios, para que el índice siga con seis entradas.
- Horario por sede, hasta 6 turnos, aviso de pérdida al pasar a bloques.
- Servicios reservables con duración, descripción y «Quién lo ofrece».
- Días de saldo restantes y «% libre»; bolsa «Sin límite (lo cubre Auphere)»;
  relleno mensual; «Pedir saldo».
- Más motivos de atención (canal con problemas, conector por reconectar, tope) y la
  línea «{Sección}: falta» del Panel.
- Paginación de la lista; cliente en pausa con su insignia y «⋯» en la cabecera.

---

## 12. Decisiones abiertas

- **D1. «Saldo» o «Bolsa»** en la lista y el Panel. El prototipo dice «Saldo» y
  «Sin saldo asignado»; la consola, «Bolsa» y «Sin bolsa asignada».
- **D2. Vocabulario del estado**: «Publicado» y «Al día» (prototipo) frente a
  «Atendiendo» y «Todo en orden» (consola, requisito 25.5: el mismo texto en toda
  la consola).
- **D3. Eliminar servicio**: el prototipo elimina con «Deshacer»; la consola
  archiva (las reservas pasadas conservan el nombre). Propuesta: la palabra
  «Eliminar» y el «Deshacer» del prototipo, archivando por debajo.
- **D4. Archivar sin confirmar**: el prototipo archiva al momento con «Deshacer»;
  la consola pide confirmación. Archivar se deshace: propuesta, sin confirmación.
- **D5. Insignias tintadas** (H13): cambio del sistema de diseño, no de la pantalla.
- **D6. «Vuelven a pasar sus pruebas» / «Volví a pasar las pruebas de sus
  agentes»**: solo si la API las vuelve a pasar al guardar la ficha. Si no, el
  texto honesto de la consola: «Guardado. Los agentes lo usan desde el siguiente
  mensaje.».
- **D7. El interruptor de Servicios** no hace nada en el prototipo. Sin un ajuste
  en la API, solo la frase.
- **D8. Redes**: el prototipo guarda al escribir; la API pide revisión
  (`If-Match`). Propuesta: guardar al salir del campo, sin botón, y avisar con el
  412.
- **D9. País, moneda de los precios y «Solo UE»** no existen en el prototipo. Hoy
  solo se editan en Datos básicos; si Datos básicos pasa a lectura con el modal,
  hay que decidir dónde se cambian (¿«Más ajustes» en edición?).
