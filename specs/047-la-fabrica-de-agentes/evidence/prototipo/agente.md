# Prototipo aprobado · pantalla del agente — especificación para rehacerla tal cual

Fuente: `~/Downloads/Consola de partners v2/index.html` (un solo HTML: CSS arriba, una
IIFE con el estado `S`, `render()`, las funciones de pantalla y el mapa `ACT` de
`data-act`; iconos lucide con `ic(nombre, tamaño)`). Capturas en claro y oscuro:
`agent-build`, `agent-perf`, `agent-channels`, `agent-integrations`, `new-agent`
(tapada por el modal «Nuevo cliente») y `client-agents`.

Comparado con la consola del worktree `047-recorrido-ui` el 2026-10-28 por la tarde
(`agent-builder.tsx` ya reestructurado en cuatro pestañas, tabla compacta y barra de
vidrio). Rutas de la consola relativas a `apps/console/src/`.

Reglas que mandan sobre el prototipo:

- **El constructor no se nombra nunca en la interfaz.** El prototipo lo hace en dos
  sitios que no hay que copiar: la pestaña «Construir y probar» (usar siempre
  «Configurar y probar») y el `aria-label` «Preguntas del constructor» (usar
  «Preguntas pendientes»). La voz en primera persona del borrador («Me faltan 2
  datos», «Validé…», «Leo la ficha…») no lo nombra, pero sí le da voz: ver decisión D3.
- «Integraciones» del prototipo es «Conectores» en la consola (decisión 1 de
  `feedback-prototipo.md`, regla de palabras `words.test.ts`).
- Lo que el prototipo simula (botones «Simular que el cliente terminó», la fila
  «Prototipo · simular lo que devuelve Meta», la ventana de Meta pintada dentro del
  modal) no se copia: en la consola son las piezas reales.

---

## 0. Piezas comunes

### 0.1 Tokens del prototipo → tokens de la consola

| Prototipo | Claro | Oscuro | Consola |
|---|---|---|---|
| `--bg` | oklch(0.971 0.006 185.3) | oklch(0.185 0.012 182) | `--background` |
| `--surface` | blanco | oklch(0.225 0.014 182) | `--card` |
| `--surface-2` | oklch(0.955 0.008 182) | oklch(0.26 0.014 182) | `--muted` (fondo) |
| `--ink` | oklch(0.161 0.033 115.3) | oklch(0.95 0.01 170) | `--foreground` |
| `--muted` (texto) | ink / 0.7 | ink / 0.72 | `--muted-foreground` |
| `--faint` | ink / 0.45 | ink / 0.48 | `text-muted-foreground/60` |
| `--line` / `--line-strong` | ink / 0.12 · 0.22 | blanco / 0.1 · 0.2 | `--border` / `--input` |
| `--primary` | oklch(0.47 0.095 168) | oklch(0.76 0.12 167) | `--primary` |
| `--accent-soft` / `--accent-ink` | accent / 0.12 · oklch(0.442 0.086 170.4) | accent / 0.16 · oklch(0.82 0.1 167) | tono `positive` de `StatusBadge` |
| `--warn-soft` / `--warn-ink` | | | tono `warn` |
| `--danger-soft` / `--danger` | | | tono `danger` / `--destructive` |
| `--info-soft` / `--info` | | | tono `info` |
| `--glass`, `--glass-edge`, `--glass-shadow`, `--tab-on` | | | ya existen: `--glass-bg`, `--glass-edge`, `--glass-shadow`, `--tab-on` (`packages/ui/src/styles/tokens.css`) |
| `--chat-bg` | oklch(0.93 0.02 150) | oklch(0.21 0.02 160) | **no existe** |
| `--bubble-out` | oklch(0.9 0.07 150) | oklch(0.36 0.06 155) | **no existe** |
| `--r-sm` / `--r-md` / `--r-lg` | 8 / 12 / 16 px | | `rounded-md` (8) / `rounded-lg` (12) / `rounded-xl` (16) |

Tipografía: Inter 14 px, interlineado 1.5, `font-feature-settings: "ss01","cv11"`;
títulos con `letter-spacing:-0.02em` y peso 600. Números con `tabular-nums`.

Las tarjetas del prototipo (`.card`) tienen radio **12 px** (`--r-md`); en la consola
la pantalla del agente usa `rounded-md` (8 px). Es una diferencia visible en toda la
pantalla (tabla de bloques, pruebas, chat, listas): pasar a `rounded-lg`.

### 0.2 Controles

- `.btn`: 36 px de alto, `padding:0 14px`, radio 8, borde `--line-strong`, fondo
  `--surface`, 14 px/500, `gap:8px`, `:active` baja 1 px, transición 0.15 s.
  `.primary` fondo `--primary` y texto `--on-primary`; `.ghost` sin borde ni fondo;
  `.sm` 30 px, `padding:0 10px`, 13 px; `.icon` cuadrado (36 o 30); `[disabled]`
  opacidad 0.45. Dentro de la barra flotante, todos los botones son píldora
  (`border-radius:999px`).
- `.chip`: 28 px, `padding:0 10px`, píldora, borde `--line-strong`, 13 px;
  `aria-pressed="true"` → fondo `--accent-soft`, borde accent 55 %.
- `.badge`: 22 px, `padding:0 8px`, píldora, 12 px/500; con icono lucide de 12 px o
  con punto de 6 px. Tonos `t-positive`, `t-warn`, `t-danger`, `t-info`, `t-muted`.
- `.link`: botón como enlace, color `--accent-ink`, 500, subrayado con offset 3 px.
- `.glass`: fondo `--glass`, `backdrop-filter: blur(22px) saturate(170%)`, sombra
  `--glass-shadow` + `inset 0 1px 0 --glass-edge`, borde `--line`. Con
  `prefers-reduced-transparency: reduce` pasa a `--surface` sólido.
- `.toast` (vidrio): fijo, centrado, `bottom: safe-area + 84px`, píldora,
  `padding:10px 10px 10px 16px`, 14 px; icono `circle-check` en `--accent-ink`,
  texto, botón de acción opcional (`btn sm`) y cerrar (`btn sm ghost icon`,
  `aria-label="Cerrar aviso"`). `role="status"`. Se va solo a los 6 s. Entra con
  `rise` 0.3 s `cubic-bezier(.16,1,.3,1)` (sube 12 px y aparece).
- Movimiento: `spin` 1 s lineal infinito (icono `loader-circle`); barra de pruebas
  `transition: width .1s linear`; modal `pop` 0.26 s (de `translateY(10px)
  scale(.985)` y opacidad 0); velo `fade` 0.2 s. Con `prefers-reduced-motion:
  reduce`, toda animación y transición dura 0.01 ms.

### 0.3 Estados del agente (insignia `stBadge`)

| `status` | Texto | Tono | Icono |
|---|---|---|---|
| `draft` | Borrador | `t-muted` | `pencil` |
| `ready` | Listo · sin canal | `t-info` | `circle-check` |
| `testing` | En prueba | `t-info` | `flask-conical` |
| `live` | Publicado | `t-positive` | `circle-check` |
| `paused` | Pausado | `t-warn` | `pause` |

Consola (`life-model.ts` + `clients.v2.agent.*` en `i18n/lanes/business.ts`):
«Atendiendo», «En prueba», «Listo · sin canal», «Borrador», «Archivado», «Pausado ·
{a mano|sin saldo|su tope|cliente en pausa|cliente archivado}», con punto y sin icono
(`StatusBadge` solo tiene `dot`). Ver decisión D1.

### 0.4 Modal base (`modalView`)

Velo `.scrim` (`--scrim`, `fade` 0.2 s; clic cierra). Caja `.modal .box`: ancho
`min(var(--mw,620px),100%)`, radio 18, borde `--line`, sombra
`0 24px 60px oklch(0 0 0/.28), 0 2px 6px oklch(0 0 0/.12)`, animación `pop`.
`header` `padding:22px 24px 10px`, `h2` 21 px con `id="modal-t"`, `p` 14 px muted
(máx. 56ch); botón cerrar `btn ghost icon` `aria-label="Cerrar"`. `.body`
`padding:10px 24px 22px`, `gap:18px`, con scroll. `footer` `padding:14px 24px`,
borde superior, fondo `--surface-2`, radio inferior 18; a la izquierda una nota, a la
derecha `.r` con los botones. `role="dialog" aria-modal="true"
aria-labelledby="modal-t"`. Escape cierra (primero el velo de Meta, luego el modal).

---

## 1. Cliente › pestaña «Agentes» (`agentsTab`)

Captura `client-agents-*`. La cabecera del cliente (nombre 40 px, nicho · «Atiende
desde…») y la fila de pestañas de vidrio «Panel · Negocio · Agentes 3» llevan a la
derecha **un solo** botón `primary` «+ Nuevo agente». La pestaña no tiene título ni
párrafo propios: empieza directamente con las tarjetas.

**Rejilla** `.agrid`: `repeat(auto-fill, minmax(280px,1fr))`, `gap:12px`,
`margin-top:16px` (tres columnas a 1240 px).

**Tarjeta** `article.card.acard`: `role="link"`, `tabindex="0"`,
`aria-label="Abrir {nombre}"`, `data-act="open-agent"`; Enter la abre. `padding:16px`,
`gap:10px`; hover: borde `--line-strong` y sombra `0 2px 10px oklch(0 0 0/.06)`.

1. `.top` (flex, `space-between`, alineado arriba): `h3` 15 px con el nombre; a la
   derecha la insignia de estado (0.3).
2. `p` 13 px muted, **dos líneas como mucho** (`-webkit-line-clamp:2`): para qué es
   el agente (`purpose`) o «Sin descripción todavía.».
3. `.foot` (flex, `space-between`, 13 px muted, `padding-top:10px`, borde superior):
   - Con canales: el logo de cada canal (24 px; Chat web es un cuadrado `--ink` con
     `message-circle`) + la etiqueta del primero («+56 9 9191 9125») y « +N» si hay
     más.
   - Sin canal: insignia `t-muted` con `phone` 12 px «Sin canal».
   - A la derecha, lo gastado: «31,20 USD» (`tabular-nums`).

**Vacío** (`card empty`): icono `bot` 22 px en un cuadrado de 44 px radio 12 fondo
`--surface-2`; `h3` «Este cliente aún no tiene agentes»; `p` «Un agente atiende un
proyecto o servicio del negocio por un canal. Un cliente puede tener varios:
Recepción para citas, Ventas para presupuestos, Cobros para pagos.»; botón `primary`
«+ Nuevo agente».

**Al abrir una tarjeta** (`open-agent`): pantalla del agente en la pestaña que le toca:
`draft` → «Configurar y probar», `ready` → «Canales», el resto → «Rendimiento». Sube
arriba del todo.

---

## 2. Pantalla del agente: el marco (`agentScreen`)

### 2.1 Migas

`Clientes › {cliente} › {agente}` (13 px muted, la última en `--ink` con
`aria-current="page"`). Mientras el agente nuevo está en la fase «describir», la
última es «Nuevo agente». Dentro de la configuración de un canal:
`Clientes › {cliente} › {agente} › Canal {etiqueta}` (el agente vuelve a Canales).

### 2.2 Cabecera `.ph`

Flex, `align-items:flex-end`, `space-between`, `gap:16px`, `padding-bottom:20px`,
borde inferior `--line`.

- Izquierda: `h1` 40 px / 1.1 / `-0.03em`: el nombre del agente; «Nuevo agente» en la
  fase «describir». Debajo (`margin-top:6px`, 16 px muted, `gap:8px`): insignia de
  estado · «de {cliente}».
- Derecha (`.acts`): `live` o `testing` → botón «Pausar» (icono `pause` 15);
  `paused` → «Reanudar» (icono `play` 15); `draft` y `ready` → nada. No hay menú ⋯.

### 2.3 Pestañas (vidrio)

`.tabsbar.glass`: pegajosa (`top: safe-area + 8px`, `z-index:20`), píldora,
`padding:5px`, ancho `max-content`, scroll horizontal si no cabe.
`role="tablist" aria-label="Secciones del agente"`. Cada pestaña: `role="tab"`,
`aria-selected`, 32 px de alto, `padding:0 14px`, píldora, 14 px muted; la elegida
con fondo `--tab-on`, `--ink`, 500 y sombra `0 1px 3px oklch(0 0 0/.1)`. El número
(`.cnt`) 12 px muted `tabular-nums`. Debajo, `role="tabpanel"` con
`margin-top:16px`. Entre cabecera y pestañas, el `gap` de la página: 20 px.

| Pestaña | Cuándo sale | Texto |
|---|---|---|
| `perf` | `status !== 'draft'` o el agente ya se guardó (`saved`) | Rendimiento |
| `build` | siempre | «Configurar y probar» (el prototipo dice «Construir y probar» antes del primer guardado: **no copiar**) |
| `channels` | siempre | «Canales» + número de canales (también 0) |
| `integrations` | siempre | «Integraciones» → en la consola «Conectores» |

Cambiar de pestaña (`atab`) cierra la configuración de canal abierta y el panel de
«Añadir otro canal».

---

## 3. Nuevo agente (`startAgent`, fase `describe` → `building` → `ready`)

«Nuevo agente» abre **la misma pantalla del agente**, no otra página: título «Nuevo
agente», insignia «Borrador» · «de {cliente}», pestañas «Configurar y probar ·
Canales 0 · Conectores» (sin Rendimiento), la rejilla de dos columnas (4.1) y la barra
flotante (4.5).

> En el prototipo el agente nace al pulsar «Nuevo agente». En la consola nace con el
> primer borrador (requisito 17.2); se mantiene: la pantalla se pinta igual sin agente
> hasta que el trabajo termina.

### 3.1 Fase «describir»

Columna izquierda: `section.card.card-b` (`padding:14px 18px 18px`, `gap:18px`,
`aria-label="Describe el agente"`):

1. Campo «Nombre»: `input` 38 px, `placeholder="Recepción"`, `maxlength="40"`, con
   foco al entrar.
2. Campo «¿Qué tiene que hacer?»: `textarea` 5 filas,
   `placeholder="Como se lo explicarías a alguien nuevo: qué resuelve, cómo habla y
   cuándo pasa la conversación a una persona."`.
3. Debajo del textarea, fila de chips (`aria-label="Ejemplos"`): «Empieza con un
   ejemplo:» (12 px muted) + cuatro chips: «Recepción y citas», «Ventas», «Soporte»,
   «Cobros». Pulsar uno **sustituye** la descripción por su texto (con el nombre del
   cliente dentro) y, si el nombre está vacío, pone «Recepción» (para «Recepción y
   citas») o la etiqueta del chip:
   - Recepción y citas: «Atiende el WhatsApp de {cliente}: da citas, las cambia o
     cancela y responde precios y horarios. Tono cercano y breve, de tú. Si alguien se
     queja o pide hablar con una persona, avisa a Marta.»
   - Ventas: «Responde dudas de producto de {cliente}, explica precios y prepara
     presupuestos para pedidos grandes. Tono cercano, de tú. Si el pedido supera 300 €,
     avisa a Marta.»
   - Soporte: «Resuelve dudas de clientes de {cliente} sobre pedidos y horarios, y pasa
     a una persona si hay una queja. Tono amable, de usted.»
   - Cobros: «Recuerda pagos pendientes a clientes de {cliente} y envía el enlace de
     pago. Tono formal, de usted. Si alguien discute el importe, avisa a Marta.»

Sin contadores de caracteres y sin «Otras formas de empezar» (plantilla, en blanco).

Columna derecha (panel deshabilitado): `card` con opacidad 0.75; `.pane-h`
(`padding:10px 12px`, borde inferior): «Probar el agente» (icono `flask-conical` 15,
14 px/500) + insignia «Aún no» (`t-muted`, con punto). Cuerpo `empty`
(`padding:28px 20px`): icono `circle-play` 20 en un cuadrado de 44 px; «Disponible en
cuanto generes el borrador y le pongas sus parámetros.»; nota 12 px «Chat simulado con
agenda y hora de prueba. Nada llega a clientes reales.».

Barra flotante: ver 4.5. «Generar borrador» está deshabilitado hasta que haya nombre y
una descripción de **más de 20 caracteres**; el texto de la barra y el estado del
botón cambian al escribir, sin repintar la pantalla.

### 3.2 Fase «preparando el borrador» (`runBuild`)

Al pulsar «Generar borrador»: el nombre y la descripción pasan al agente, la cabecera
deja de decir «Nuevo agente» y enseña el nombre.

Columna izquierda: una tarjeta con `ul.steplog` (`gap:8px`, 14 px):

1. «Leo la ficha de {cliente} como datos, nunca como permisos»
2. «Propongo instrucciones y habilidades»
3. «Escribo 8 pruebas del caso y sumo 12 del sector»
4. «Valido qué preguntas hacen falta de verdad»

Cada paso: hecho → `circle-check` en `--accent-ink`; en curso → `loader-circle`
girando; pendiente → `circle-dashed` y texto `--faint`. Ritmo del prototipo: 700 ms
hasta el primer avance y 650 ms por paso.

Columna derecha: el panel deshabilitado con «Preparando el borrador…».
Barra: spinner + «Preparando el borrador…», sin botones.

Al terminar: fase `ready`, se calculan las preguntas y aviso «Borrador de «{nombre}»
listo. Me faltan {n} datos.» (sin la segunda frase si no hay preguntas).

Correspondencia con la consola (`builder-new.tsx`): paso 1 = `progress.step ===
"reading"`; paso 2 = llegan los bloques `identity`…`rules`; paso 3 = llega `tests`
(su `count` son las del caso; las del sector, `DraftTests.sector`); paso 4 = llega
`questions` (con `count` y `discarded`). Los números del paso 3 salen de ahí, no
fijos.

### 3.3 Fase «listo»: las preguntas

Encima de la tabla de bloques (4.2), mientras haya preguntas:
`section` (`gap:10px`, `aria-label` «Preguntas pendientes»):

- Fila de título (flex, `baseline`, `space-between`): `h3` 16 px «Me faltan {n}
  dato(s)» o «Todo respondido»; a la derecha, nota 12 px «No están en la ficha ni en
  la web».
- `.validated` (13 px muted, `padding:10px 12px`, radio 8, fondo `--surface-2`, icono
  `list-checks` 16): «Validé 6 preguntas posibles y descarté 4 porque la ficha ya las
  responde: horario, sedes, precios y duración de los servicios.» En la consola, con
  los datos del trabajo: total = preguntas + `discarded.count`; los motivos =
  `discarded.reasons`.
- Cada pregunta sin responder, `.q` (`role="group"`, `aria-labelledby` a su texto):
  borde `--warn` al 45 %, radio 12, `padding:14px 16px`, `gap:10px`:
  - texto en 14 px/500;
  - `.why`: icono `info` 14 + el porqué (13 px muted);
  - chips con las opciones (`aria-pressed` en la elegida);
  - si la opción pide un valor: campo con etiqueta, `input` y botón `primary`
    «Guardar» en la misma fila; el error debajo en `--danger` 13 px.
  - Elegir una opción que no pide valor la da por respondida al momento.
- Respondida, `.q.done` (borde `--line`): `circle-check` + el resumen de la respuesta
  y, a la derecha, enlace «Cambiar» (la vuelve a abrir sin elección).
- Al responder la última: aviso «Todo respondido. Ya puedes probarlo.» con botón
  «Pruébalo» (lleva el foco al chat y lanza las pruebas si no corrieron).

Preguntas del prototipo (de ejemplo; en la consola vienen del trabajo):

| id | Pregunta | Porqué | Opciones | Resumen |
|---|---|---|---|---|
| `hand` | «Cuando pase a una persona, ¿qué hago además de dejarla en la Bandeja?» | Si la descripción nombra a alguien: «Mencionas a {Marta}. No hace falta su número aquí: los contactos y avisos se configuran en el canal conectado.»; si no: «No mencionas a nadie. Los contactos y avisos se configuran en el canal conectado, no en el agente.» | «Avisar a {Marta\|el equipo} por el canal», «Avisar al equipo por correo», «Nada más: solo la Bandeja» | «Avisa a {Marta} por el canal conectado (su número o usuario se define en el canal)» / «Avisa al equipo por correo (los contactos, en el canal)» / «Deja la conversación en la Bandeja sin avisar» |
| `price` | «««{servicio}» no tiene precio en la web. ¿Qué respondo si lo preguntan?» | «Es el único servicio de la ficha sin precio; el resto ya lo sé.» o «Es el más pedido de los {n} servicios sin precio; los demás los puedes completar en la ficha.» | «Decir el precio» (pide «Precio de {servicio} ({moneda})», `placeholder="12"`; error «Escribe solo el número, por ejemplo 12 o 12,50.»), «Que lo consulten en el local» | «{servicio}: {12} {€} (se guarda en la ficha del negocio)» / «{servicio}: dirá que lo consulten en el local» |

Consola hoy (`builder-new.tsx`, `builder-questions.tsx`): las preguntas salen en la
columna derecha de la página «Nuevo agente», como formulario con radios, «Guardar
respuestas» / «Seguir sin responder», y al guardar se va al agente. Ver hueco H7.

---

## 4. «Configurar y probar» (`builderTab`)

Captura `agent-build-*`.

### 4.1 Rejilla

`.builder`: `grid-template-columns: minmax(0,1fr) minmax(360px,440px)`, `gap:20px`,
`align-items:start`. Por debajo de **1060 px**, una columna.
`.bleft`: `grid`, `gap:16px`. `.bright` (`<aside aria-label="Borrador y pruebas">`):
**pegajosa** con `top:120px`, `gap:10px`; por debajo de 1060 px deja de pegarse.
Las tarjetas de la derecha llevan `overflow:hidden`.

Contenido de la izquierda por fase: «describir» → 3.1; «preparando» → la lista de
pasos; «listo» → preguntas pendientes (3.3) + la tabla de bloques (4.2). Nada más:
ni conocimiento, ni pruebas en lista, ni revisión, ni historial, ni avanzado.

Contenido de la derecha: fase no lista → panel deshabilitado (3.1); lista → tarjeta
de pruebas + tarjeta del chat (5).

Debajo de la rejilla, fuera de ella y a todo el ancho, la barra flotante (4.5).

### 4.2 La tabla de bloques (`section.card.spec`, `aria-label` «Parámetros del agente»)

Cada fila `.blk`: `grid-template-columns: 170px minmax(0,1fr) auto`,
`gap:8px 16px`, `padding:14px 18px`, borde inferior `--line` (la última sin borde),
`align-items:start`. Por debajo de 640 px, una sola columna. Título `h4` 14 px/500.
Valor `.val` (`grid`, `gap:6px`), texto 14 px; nota 12 px muted. Lápiz:
`btn ghost sm icon` con `pencil` 14, `aria-label="Editar {título en minúsculas}"`.

| Fila | Valor (lectura) | Nota | Lápiz |
|---|---|---|---|
| Qué hace | La descripción del agente («Toma pedidos de ramos y arreglos, confirma las entregas del día y responde precios y zonas de reparto.») | — | sí |
| Cómo habla | «{Tono}, {de tú}. Saluda: «¡Hola! Soy el asistente de {cliente}».» (por defecto «Cercano, de tú…») | — | sí |
| Qué sabe | «{5} servicios · {1} sede · horario (de la ficha)» (se omite lo que falte) | «Hereda la ficha del negocio. Lo que le enseñes aquí solo lo sabe este agente.» | sí |
| Qué puede hacer | Una fila `.skill` por habilidad (4.4); sin habilidades: «Sin habilidades: solo responde preguntas.» (muted) | — | **no** (tercera columna vacía) |
| Cuándo pasa a una persona | «Si piden hablar con una persona o tras 2 intentos sin resolver.» o lo deducido («Quejas o si piden hablar con una persona: avisa a Marta») | «A quién avisa y por dónde se configura en cada canal.» | sí |

### 4.3 Edición en línea (`spec-edit` → `spec-save` / `spec-cancel`)

Solo una fila abierta a la vez. La fila abierta (`.blk.editing`) conserva el título
en la primera columna; en la segunda, `textarea` de 3 filas con el valor actual
(`aria-label` = el título, con foco) y debajo «Guardar» (`btn sm primary`) y
«Cancelar» (`btn sm ghost`); la tercera columna, vacía. Guardar vacío no hace nada.

Al guardar: el valor queda en el borrador; si el agente ya estaba guardado, pasa a
«con cambios»; **las pruebas quedan sin ejecutar** (contador a cero); aviso
«Guardado en el borrador. Vuelve a pasar las pruebas cuando quieras.».

En la consola cada fila abre su editor estructurado (`block-editor.tsx`), que es más
rico que un textarea y se mantiene; lo que cambia es qué bloques caen en cada fila
(sección 12).

### 4.4 «Qué puede hacer»

Cada habilidad `.skill`: flex, `space-between`, `gap:8px`, envuelve. Izquierda, el
nombre («Tomar pedidos», «Responder precios de Servicios»). Derecha, según su
conector:

- No necesita conector → nada.
- Conector conectado → insignia `t-positive` con `circle-check` «{WooCommerce} ·
  conectado».
- Conector sin conectar → `btn sm` con `plug` 14 «Conectar {AgendaPro}». En el
  prototipo conecta al momento (aviso «{AgendaPro} conectado para {agente}.»). En la
  consola abre el diálogo de conectar de la pestaña Conectores (pide el permiso), sin
  salir de la pantalla.

### 4.5 La barra flotante (`.actionbar.glass`)

`role="region"`, `aria-label` «Acciones del agente» (el prototipo dice «Acciones del
borrador»). Pegajosa abajo (`bottom: safe-area + 16px`, `z-index:25`), píldora,
`padding:8px 8px 8px 16px`, `margin-top:8px`, flex `space-between`, `gap:12px`.
**A la izquierda el estado** (`.st-txt`, 13 px muted, iconos de 14 px en línea, `gap:8px`);
**a la derecha los botones** (`margin-left:auto`, `gap:8px`, píldora). Por debajo de
560 px: radio 18, `padding:10px`, y los botones ocupan el ancho, repartidos.

Se evalúa en este orden (el primero que se cumple):

| # | Situación | Texto a la izquierda | Botones |
|---|---|---|---|
| 1 | Fase «describir» | «Listo para generar el borrador» si hay nombre y descripción de más de 20 caracteres; si no, «Nombre y una descripción de al menos una frase» | `primary` «Generar borrador» (icono `wand-sparkles` 15), deshabilitado hasta cumplirse |
| 2 | Fase «preparando» | spinner + «Preparando el borrador…» | — |
| 3 | Hay preguntas sin responder y las pruebas no han terminado | «{n} pregunta(s) pendiente(s) · puedes probar igualmente» | — (el panel de prueba ya está a la vista; el prototipo solo enseña «Pruébalo» si no lo estuviera) |
| 4 | Pruebas terminadas con un fallo | `triangle-alert` + «1 de 20 pruebas falla · tiene arreglo en un clic» | «Guardar igualmente» (secundario) |
| 5 | Pruebas en marcha | «Ejecutando pruebas…» | — |
| 6 | Pruebas terminadas, todas pasan | `circle-check` + «20 de 20 pruebas pasan» y « · guardado» si ya se guardó | Sin canal: `primary` «Guardar y conectar un canal →» (`arrow-right` 15). Con canal y cambios sin guardar: `primary` «Guardar cambios». Con canal y sin cambios: nada |
| 7 | Resto (borrador completo, pruebas sin ejecutar) | «Borrador completo» | `primary` «Ejecutar pruebas» (icono `play` 15) |

`save-agent`: el agente queda guardado; un borrador pasa a «Listo · sin canal».
Con canal → aviso «{nombre} guardado. Ya responde con la versión nueva.». Sin canal →
pestaña Canales arriba del todo y aviso «{nombre} guardado. Siguiente: conectar un
canal.».

---

## 5. Panel derecho: pruebas y chat (`rightPane`)

### 5.1 Tarjeta de pruebas (`.card` > `.tests`)

Cabecera `.hd` (`padding:12px 14px`, flex `space-between`):

- Izquierda: «Pruebas · {estado}» (14 px/500) con estado = «20 sin ejecutar», «{n} de
  20» (en marcha), «20 de 20 pasan» o «19 de 20 pasan»; debajo, nota «Agenda y hora
  simuladas · sin efectos reales».
- Derecha: `btn sm` con `play` 13: «Ejecutar todas» (`primary`) si no han corrido;
  «Repetir» (secundario) si ya corrieron. Deshabilitado mientras corren.

Barra de progreso `.pbar2` (6 px, píldora, fondo `--surface-2`, relleno `--accent`,
`margin:0 14px 10px`, `transition: width .1s linear`): visible en marcha y al
terminar. En el prototipo avanza una prueba cada 70 ms y el texto de la cabecera se
actualiza sin repintar.

**Fallo** (`.fail`, `role="alert"`; `margin:0 14px 14px`, `padding:12px`, radio 8,
fondo `--danger-soft`, 13 px, `gap:8px`):

- Título 14 px/500: «Falla «Reservar una cita para mañana»» (o «Hacer un pedido para
  hoy», «Pagar una señal», «Usar {conector}»).
- «El agente responde «tu cita queda reservada», pero {AgendaPro} no está conectado:
  la cita no existe en la agenda. Se comprueba el resultado, no lo que dice.» (los
  otros casos: «tu pedido está registrado» / «el pedido no existe en la tienda»; «te
  envío el enlace de pago» / «ningún enlace de pago se genera»).
- Botones: `btn sm primary` `plug` 13 «Conectar {AgendaPro}» y `btn sm` «Tomar la
  solicitud y avisar al equipo». Cualquiera de los dos marca el arreglo y **vuelve a
  ejecutar las 20 pruebas** solo.

**Todo bien** (`.okbox`: `margin:0 14px 14px`, `padding:10px 12px`, radio 8, fondo
`--accent-soft`, 13 px, icono `circle-check`): «Arreglado. Volví a pasar las 20
pruebas.» si venía de un arreglo; si no, «Todas pasan.». (El prototipo enseña
«Arreglado…» también a los agentes de ejemplo: es un artefacto, no copiar.)

**Comprobaciones** (`ul.checks`, `aria-label="Revisión automática"`, `padding:0 14px
14px`, `gap:8px`, 13 px, icono de 14 px por fila). Solo cuando las pruebas terminaron:

1. Conectores: `circle-check` «Cada habilidad tiene su integración» → en la consola
   «Cada habilidad tiene su conector»; o `triangle-alert` «{Reservar, mover y cancelar
   citas} necesita {AgendaPro}»; o, si se eligió tomar la solicitud, `info` «{AgendaPro}
   sin conectar: tomará solicitudes y avisará al equipo.» + enlace «Conectar».
2. `circle-check` «Ningún dato contradice la ficha del negocio».
3. Precios: `circle-check` «Todos los servicios tienen precio», o `triangle-alert` «{1
   servicio sin precio | n servicios sin precio}: dirá que lo consulten.» + enlace
   «Añadir precio». El enlace abre en el sitio `.pricefix` (borde, radio 10,
   `padding:10px`): una fila por servicio sin precio (`grid 1fr 130px`: nombre como
   etiqueta + `input` 32 px `inputmode="decimal"` `placeholder="0,00"` + moneda), y
   «Guardar precios» (`btn sm primary`) + «Cancelar» (`btn sm ghost`), con la nota
   «Se guardan en la ficha del negocio: los usan todos sus agentes.». Avisos:
   «Precio guardado en la ficha. El agente ya lo usa.», «{n} precios guardados en la
   ficha. El agente ya los usa.», «Escribe al menos un precio.».

En la consola estas tres filas son las comprobaciones de la revisión (`ReviewCheck`:
`skills_integrations`, `contradictions`, `services`), con sus arreglos (`ReviewFix`).

### 5.2 Tarjeta del chat de prueba

- `.pane-h`: «Chat de prueba · así lo verá su cliente» (13 px/500) y, a la derecha,
  nota con `clock` 13 y la hora simulada («Mar 11:20»).
- `.chat` (`aria-live="polite"`): **300 px de alto fijo**, scroll, fondo `--chat-bg`
  (verde WhatsApp suave), `padding:14px`, columna con `gap:8px`. Baja solo al último
  mensaje en cada repintado.
  - Mensaje del agente `.msg`: máx. 82 %, `padding:8px 10px`, radio 10, 14 px / 1.4,
    fondo `--surface`, sombra `0 1px 1px oklch(0 0 0/.06)`, a la izquierda.
  - Mensaje del cliente `.msg.out`: a la derecha, fondo `--bubble-out`.
  - Nota del sistema `.msg.sys`: centrada, máx. 94 %, borde discontinuo
    `--line-strong`, 12 px muted, sin sombra; icono `zap` 13 + «Lo que habría hecho:
    {Consultar huecos en AgendaPro (simulado)}».
  - Vacío: nota del sistema con `info` 13: «Escribe como lo haría un cliente. Prueba
    «¿cuánto cuesta?», «quiero reservar» o «quiero hablar con alguien».».
- `.composer` (`form`, flex, `gap:8px`, `padding:10px`, borde superior): etiqueta
  oculta «Mensaje de prueba»; `input` de una línea `placeholder="Escribe como un
  cliente"` (sin autocompletar, con foco) y botón `primary icon` `send` 15
  `aria-label="Enviar"`. Enviar añade el mensaje del cliente al momento; la respuesta
  llega a los 450 ms.

No hay selector de versión, ni «Empezar una conversación», ni panel de hora/agenda
simuladas, ni «¿Por qué dijo esto?». La conversación empieza al escribir.

---

## 6. Rendimiento (`perfTab`)

Captura `agent-perf-*`. Rejilla `.panel`: `minmax(0,1.35fr) minmax(0,1fr)`, `gap:16px`,
`align-items:start`; una columna por debajo de 980 px.

**Izquierda**, tarjeta «Últimos 30 días» (`card-h` `padding:16px 18px 0`, `h3` 15 px;
`card-b` `padding:14px 18px 18px`), `.stats` en tres columnas (`gap:12px`): cifra 20 px/600
`tabular-nums` y etiqueta 13 px muted:

1. «412» — «Conversaciones»
2. «89 %» (o «—» sin conversaciones) — «Resueltas sin persona»
3. «31,20 USD» — «Consumido de la bolsa» y, si tiene tope, « · tope 15,00 USD»

**Derecha**, tarjeta «Sugerencias de esta semana»: lista `.srcs` (filas `padding:10px 0`,
borde inferior): icono `lightbulb` 15 en cuadrado de 32 px radio 8 `--surface-2`;
título 14 px/500 y subtítulo 12 px muted; botón `btn sm` «Ver».

- «12 clientes preguntaron si hay estacionamiento» — «Propuesta: una respuesta para
  todo el negocio»
- «9 conversaciones pasaron a una persona por zonas lejanas» — «Faltan tarifas fuera
  de la zona habitual»

Nada más: sin selector de periodo, sin gráfica, sin tabla de conversaciones.

---

## 7. Canales (`channelsTab`)

Captura `agent-channels-*` (agente con un canal).

### 7.1 Sin canales: el asistente

1. Si el agente no se ha guardado: `.alert.info` con `info` 16: «Puedes conectar el
   canal ya. Hasta que guardes el agente no responderá a nadie.».
2. Si hay un enlace enviado al dueño: la tarjeta de 7.3.
3. `.chwiz.card`: `grid-template-columns: 240px minmax(0,1fr)`; por debajo de 900 px,
   una columna con el borde arriba.

**Pasos** (`ol.chsteps`, `aria-label="Pasos"`, `padding:22px 20px`, `gap:18px`). Cada
paso `grid 30px 1fr`, `gap:12px`: círculo de 30 px (`--surface-2`, 13 px muted,
número) + título 15 px/500 (`margin-top:5px`) + texto 14 px muted. Paso actual: círculo
`--accent-soft` con número `--accent-ink` 600 y título `--accent-ink`; hecho: círculo
`--accent-soft` con `check` 13.

1. «Elegir canal» — «Por dónde escribirán los clientes de este negocio.»
2. «Conectar» — «Autoriza la cuenta del proveedor y crea el canal.»
3. «Configurar el canal» — «A quién responde, excepciones y a quién escala.»
4. «¡Listo!» — «El agente ya responde por aquí.»

Paso actual: 2 mientras el modal de conectar está abierto; 4 si todos los canales
están configurados; si no, 1.

**Principal** (`.chmain`, `padding:22px 24px 24px`, borde izquierdo): `h2` 20 px «Elige
un canal»; `p` muted (`margin-top:4px`) «Los de Meta van primero. Un agente puede
tener varios números del mismo canal. Los marcados «Próximamente» todavía no se
pueden conectar.».

Rejilla `.chgrid`: `repeat(auto-fill, minmax(230px,1fr))`, `gap:14px`,
`margin-top:18px`, filas de la misma altura. Tarjeta `.chcard` (`min-height:232px`,
`padding:22px`, `gap:10px`): conectable = `button` con `aria-label="Conectar {canal}"`
y hover con borde y sombra `0 2px 12px oklch(0 0 0/.07)`; no conectable = `div`
`aria-disabled="true"`, fondo `--surface-2`, sin hover.

- Arriba: logo del canal (xl) y, a la derecha, nota «Meta» en los de Meta.
- Título 17 px/500 + insignia («Próximamente» `t-muted`, «Pendiente» `t-warn`).
- Descripción 14 px muted; nota 13 px si la hay.
- Si ya tiene números de ese canal: insignia `t-positive` «{n} conectado(s)».
- En las conectables, abajo (`margin-top:auto`): «Conectar →» o «Conectar otro número
  →» (14 px/500 `--accent-ink`, `arrow-right` 14).

| Canal | Insignia | Descripción | Nota | Meta |
|---|---|---|---|---|
| WhatsApp | — | «Atiende a los clientes en su número de WhatsApp Business, por la API de Meta.» | «Coexistencia o Cloud API. El negocio puede seguir usando su app.» | sí |
| Messenger | Próximamente | «Mensajes de la página de Facebook del negocio.» | — | sí |
| Instagram | Próximamente | «Mensajes directos y respuestas a comentarios de Instagram.» | (el prototipo dice «Diseñado (ADR-030)…»: texto interno, **no copiar**) | sí |
| Threads | Próximamente | «Conversaciones de la cuenta de Threads del negocio.» | — | sí |
| TikTok | Pendiente | «Responde los mensajes directos de la cuenta de empresa de TikTok.» | «Pendiente de la aprobación de TikTok.» | — |
| Telegram | Próximamente | «Un bot de Telegram que atiende con el agente del cliente.» | — | — |
| X | Próximamente | «Mensajes directos de la cuenta de X del negocio.» | — | — |

Pulsar WhatsApp abre el modal de 10.1. Si ya hay un enlace pendiente: aviso «Ya hay un
enlace pendiente para este canal. Revócalo para empezar otra conexión.» y no abre.

### 7.2 Con canales: la lista

Tarjeta con `ul.connected`. Cada fila: flex, `gap:12px`, `padding:14px 18px`, borde
inferior, envuelve.

1. Logo del canal (md, 32 px).
2. Bloque que crece: etiqueta en 14 px/500 («+56 9 9191 9125») + nota « · Coexistencia»
   o « · Cloud API»; debajo, nota 12 px: «{WhatsApp} · responde {a quién}[ · escala a
   {Carla, …}]», con «a quién» = «sin configurar: todavía no responde» / «solo a {n}
   número(s) de prueba» / «a todos[ salvo {n} excepción(es)]».
3. Insignia: agente en pausa → «En pausa» (`t-warn`, `pause`); sin configurar → «Sin
   configurar» (`t-muted`, `circle-dashed`); solo equipo → «En prueba» (`t-info`,
   `flask-conical`); todos → «Activo» (`t-positive`, `circle-check`). (El prototipo no
   refleja la pausa de un solo canal: la consola sí, con su estado visible.)
4. ⋯ (`btn sm icon ghost`, `ellipsis` 16, `aria-haspopup="menu"`, `aria-expanded`,
   `aria-label="Más opciones de {etiqueta}"`) → menú de vidrio (`role="menu"`, radio
   12, `padding:6px`, mín. 200 px; filas 14 px `padding:8px 10px` radio 8):
   «Configuración» (`sliders-horizontal`); «Pasar a otro agente» (`corner-down-right`,
   solo si hay otro agente que no sea borrador); «Pausar este canal» / «Reanudar este
   canal»; separador; «Desconectar» (rojo, `trash-2`).

Debajo de la tarjeta: `btn` «+ Añadir otro canal», que despliega el asistente de 7.1
debajo de la lista.

### 7.3 Enlace pendiente

Tarjeta flex (`gap:12px`): logo md; «Enlace enviado al cliente · WhatsApp» (500) y
nota «Caduca en 7 días. Cuando el cliente termine en Meta, el canal aparece aquí y te
avisamos.»; botones `btn sm` «Copiar de nuevo» (`copy` 13) y `btn sm ghost danger`
«Revocar». (El tercero, «Simular que el cliente terminó», es solo del prototipo.)
Avisos: «Enlace copiado.», «Enlace revocado. Ya no sirve para conectar.».

> En la consola el enlace no se puede volver a enseñar (31.7): «Copiar de nuevo» no
> existe; queda «Revocar» y «Crear otro enlace», como hoy en `owner-link-panel.tsx`.

---

## 8. Configuración de un canal (`channelConfigPage`)

Se abre dentro de la pestaña Canales (la cabecera del agente y las pestañas siguen
arriba), al conectar un canal o desde ⋯ › «Configuración». Sube arriba del todo.

### 8.1 Rejilla

`.cfgpage`: `grid-template-columns: 200px minmax(0,1fr)`, `gap:24px`. Por debajo de
860 px, una columna y el índice pasa a fila que envuelve.

**Índice** (`nav.cfgnav`, `aria-label="Secciones de la configuración"`, pegajoso a
76 px): botones de 34 px, `padding:0 10px`, radio 8, 14 px, que llevan a cada sección
con desplazamiento suave: «A quién responde», «Excepciones» (solo con «A todos»),
«Escalado a personas». Debajo, nota 12 px: «Todo esto es del canal. Si el agente
atiende en otro canal, allí tiene su propia configuración.».

**Cuerpo** (`gap:16px`):

1. `.cfghead` (flex, `gap:14px`): logo del canal (lg) + `h2` 20 px con la etiqueta
   («+56 9 9191 9125») + `p` muted «WhatsApp · Coexistencia · canal de {agente}».
2. Tarjeta «A quién responde» (`id="cfg-aud"`):
   - Grupo de radios (`role="radiogroup"`, `aria-label="A quién responde"`), cada
     opción un botón `role="radio"` (`padding:12px`, borde `--line-strong`, radio 8;
     elegida con borde y anillo `--primary`; círculo de 16 px):
     - «Solo mi equipo» — «Responde a los números de prueba. A los demás no les
       contesta ni les marca el mensaje como leído.» («usuarios» en canales sin número)
     - «A todos» — «Responde a cualquier persona que escriba por este canal, salvo las
       excepciones.»
   - Con «Solo mi equipo»: campo «Números de prueba» con chips (cada uno con «×»,
     `aria-label="Quitar {número}"`; vacío: «Ninguno todavía.»), y debajo `input`
     (`placeholder="+34 600 00 00 00"`, `inputmode="tel"`, máx. 460 px) + `btn` «+
     Añadir». Enter o coma añaden. Pista: «Añade todos los que necesites. Pulsa Enter o
     coma para añadir.». Un número con menos de 9 cifras: aviso «Escribe el número con
     prefijo, por ejemplo +34 600 00 00 00.».
3. Tarjeta «Excepciones» (`id="cfg-excl"`), **solo con «A todos»**: pista «Números a
   los que el agente nunca responde: familia, proveedores, el propio equipo. Sus
   mensajes quedan en Conversaciones sin respuesta automática.» + los mismos chips.
4. Tarjeta «Escalado a personas» (`id="cfg-esc"`):
   - Pista: «Cuando el agente pasa la conversación ({lo de «Cuándo pasa a una persona»}),
     deja la conversación en la Bandeja y avisa a estas personas.».
   - Una fila por persona `.escrow`: `grid 1.2fr .9fr 1.2fr auto`, `gap:8px`,
     `align-items:end`, `padding-bottom:12px`, borde inferior discontinuo; por debajo
     de 700 px, una columna. «Persona» (`placeholder="Marta · dueña"`); «Avisar por»
     (WhatsApp / Correo / Solo la Bandeja); tercer campo «Número»
     (`+34 600 00 00 00`), «Correo» (`marta@negocio.com`) o «Destino» («Bandeja del
     cliente», deshabilitado); papelera `btn icon ghost` (`aria-label="Quitar a
     {nombre|esta persona}"`, deshabilitada si es la única). El error de la fila,
     debajo, a todo el ancho.
   - `btn sm` «+ Añadir otra persona».
   - Casilla `.check` (marcada por defecto): «Incluir un resumen en el aviso» —
     «Nombre del cliente, qué pedía y por qué se escaló.».
5. Comprobaciones (`ul.checks`, 15 px de icono):
   - `circle-check` «20 de 20 pruebas pasan» o `triangle-alert` «Las pruebas no están
     al día. Se recomienda probar antes de abrirlo a todos.».
   - `circle-check` «Bolsa de {cliente}: quedan {60,00 USD}» o `triangle-alert`
     «{cliente} no tiene saldo: no responderá a nadie hasta que se asigne.» + enlace
     «Asignar saldo» (abre el modal de saldo).
6. Barra flotante de vidrio (`aria-label="Guardar configuración"`, la misma de 4.5):
   - Canal ya configurado: «Los cambios se aplican al guardar.» · «Cancelar» ·
     `primary` «Guardar».
   - Canal recién conectado: «El canal aún no responde: guarda para activarlo.» ·
     «Decidir luego» · `primary` «Activar solo para mi equipo» o «Activar para todos»
     según la opción elegida.

Al guardar se valida cada persona: correo inválido → «Ese correo no parece válido.»;
número corto → «Escribe el número con prefijo, por ejemplo +34 600 00 00 00.»; con
nombre y sin destino → «Falta {el correo|el número} de {Marta}.». «Solo mi equipo» sin
números → aviso «Añade al menos un número o usuario de prueba.». Bien: vuelve a la
lista, el estado del agente pasa a «Publicado» si algún canal responde a todos, «En
prueba» si alguno solo al equipo, «Listo · sin canal» si ninguno; aviso «{agente}
responde por {etiqueta} solo a tu equipo.» o «… a todos.».

---

## 9. Integraciones → Conectores (`integrationsTab`)

Captura `agent-integrations-*`. `grid`, `gap:14px`:

1. `p` muted: «Lo que este agente usa para actuar. Se autoriza una vez por cliente y
   cada agente activa solo lo que necesita.»
2. `.toolbar` (flex, `space-between`, envuelve, `gap:12px`):
   - Buscador (máx. 360 px): icono `search` 15 dentro del campo, etiqueta oculta
     «Buscar conector», `placeholder="Buscar conector"`. Filtra al escribir sin perder
     el foco ni la posición del cursor.
   - Filtro segmentado de vidrio `.segm` (`role="group"`, `aria-label="Categoría"`,
     píldora, `padding:4px`; botones 32 px, `aria-pressed`): «Todos {11}»,
     «Conectados {1}», «Agenda», «Pagos», «Tienda», «CRM», «Datos».
3. Una sola tarjeta con `ul.connected` (filas como 7.2). Orden: primero los que pide
   una habilidad, luego los conectados. Cada fila:
   - Logo `.blogo` 40 px, radio 9, anillo 1 px; marcas con su logo (Stripe, Google
     Calendar, WooCommerce, HubSpot, AgendaPro) y el resto un cuadrado de color con la
     inicial (Calendly #006BFF, Mercado Pago #009EE3, Shopify #96BF48, Zoho CRM
     #E42527, Google Sheets #34A853, Notion #111111, otros #64748B).
   - Nombre (500) + insignia de categoría `t-muted` (20 px de alto, 11 px).
   - Nota: «{descripción}[ · lo necesita una habilidad de este agente][ · {cómo se
     autoriza} si no está conectado]».
   - Derecha: conectado → insignia «Conectado» (`t-positive`, `circle-check`) +
     `btn sm ghost` «Quitar»; sin conectar → `btn sm` «Conectar», `primary` si lo pide
     una habilidad.
   - Sin resultados: «Ningún conector coincide con «{texto}».».

Catálogo del prototipo (nombre · descripción · cómo se autoriza · categoría):
AgendaPro · Reservas en la agenda del negocio · Autoriza con la cuenta de AgendaPro del
negocio · Agenda; Google Calendar · Citas en un calendario de Google · Inicia sesión con
Google y elige el calendario · Agenda; Calendly · Reservas con enlaces de Calendly ·
Autoriza con la cuenta de Calendly · Agenda; Stripe · Enlaces de pago y señales ·
Conecta con Stripe Connect; el dinero va al negocio · Pagos; Mercado Pago · Cobros en
Latinoamérica · Autoriza con la cuenta de Mercado Pago del negocio · Pagos; WooCommerce
· Pedidos de la tienda online · Clave de API de WooCommerce con permiso de lectura y
escritura · Tienda; Shopify · Pedidos y catálogo de Shopify · Instala la app de Auphere
en la tienda · Tienda; HubSpot · Contactos e incidencias · Autoriza con la cuenta de
HubSpot del negocio · CRM; Zoho CRM · Contactos y oportunidades · Autoriza con la
cuenta de Zoho · CRM; Google Sheets · Registrar solicitudes en una hoja · Inicia sesión
con Google y elige la hoja · Datos; Notion · Leer páginas y bases de datos · Autoriza
el espacio de Notion · Datos. (En la consola el catálogo y sus textos vienen de la API.)

«Conectar» en el prototipo conecta al momento («{Stripe} conectado para {agente}.»);
«Quitar», también, sin aviso. En la consola se mantienen el diálogo de permiso y la
confirmación al quitar (35.3, 35.7).

---

## 10. Modales y velo de estas pantallas

### 10.1 Conectar WhatsApp (`connect`, `k=whatsapp`, ancho 560)

**Paso «método»** (por defecto Coexistencia):

- `h2` «Conectar WhatsApp»; `p` «Elige cómo se conecta el número de {cliente}. Al
  continuar se abre la ventana de Meta en una pestaña nueva.».
- `.methods` (`role="radiogroup"`, `aria-label="Modo de conexión"`, `gap:10px`); cada
  opción `.method` (`role="radio"`, `padding:14px`, radio 12, borde `--line-strong`;
  elegida con borde y anillo `--primary`):
  - «Coexistencia» + insignia «Recomendado» (`t-positive`) — «Mantener la app WhatsApp
    Business. El equipo sigue respondiendo desde el móvil y el agente atiende a la
    vez.»
  - «Cloud API» — «Número nuevo o migrado. Si el número está en la app WhatsApp
    Business, deja de funcionar allí.»
- `.callout` (fondo `--surface-2`, radio 12, icono `link` 16): «**¿No tienes la cuenta
  de Meta del negocio?** Comparte un enlace y el dueño conecta desde su dispositivo.» +
  enlace «Compartir un enlace» (paso «enlace»).
- Pie: nota `external-link` 13 «Se abre una pestaña nueva» · «Cancelar» (ghost) ·
  `primary` «Conectar» → cierra el modal y abre el velo de 10.2 (y la ventana real de
  Meta).

**Paso «enlace»**: `h2` «Enlace para el cliente»; `p` «El dueño lo abre en su móvil u
ordenador y hace la conexión con su propia cuenta de Meta. Solo hay un enlace activo a
la vez y caduca en 7 días.». Cuerpo: segmentado «Coexistencia | Cloud API»
(`aria-label="Modo del enlace"`); `.code` (monoespaciada 12.5 px, fondo `--surface-2`,
radio 10) con la URL + `btn sm` «Copiar» (aviso «Copiado.»); pista «Mientras el
cliente no termine, el canal aparece como pendiente. Puedes revocar el enlace cuando
quieras.». Pie: «← Atrás» (ghost) · `primary` «Listo, ya lo compartí» → aviso «Enlace
marcado como enviado. Te avisamos cuando {cliente} termine.» y aparece la tarjeta de
7.3.

**Paso «conectado»** (vuelve de Meta): `h2` «WhatsApp conectado»; `p` «{+34 655 10 20
30} · {Coexistencia}. Ahora puedes vincular su catálogo de productos; es opcional.».
Radios (`aria-label="Catálogo de Commerce"`) con los catálogos de la cuenta, cada uno
«De la cuenta de Commerce de {cliente}». Pie: «Ahora no» (ghost) · `primary` «Vincular
catálogo». Los dos añaden el canal sin configurar, abren su configuración (8) y avisan
«WhatsApp conectado[ con su catálogo]. Configura el canal para que empiece a
responder.».

### 10.2 Velo de Meta (`veilView`)

Capa a pantalla completa (`z-index:85`), fondo `color-mix(--accent 22%, --scrim)` con
`blur(6px)`, caja de 480 px, radio 18, `padding:28px`, centrada. Escape la cierra.

- Esperando: logo de WhatsApp (xl); `h2` «Continúa en la ventana de Meta»; `p` «Se
  abrió una pestaña nueva de Facebook. Inicia sesión con la cuenta que administra
  {cliente}, elige la cuenta de WhatsApp Business y {escanea el código desde la app
  WhatsApp Business | confirma el número con el código}. Al terminar, vuelve aquí.».
  Botones: «Abrir la ventana otra vez» (`external-link`) y «Cancelar» (ghost).
- Número en uso: icono `circle-alert` 26 en rojo; «Ese número ya está conectado en otra
  cuenta»; «El número sigue vinculado a otro proveedor o a otra cuenta de WhatsApp
  Business. Desvincúlalo allí o usa otro número, y vuelve a intentarlo.»; «Cerrar» ·
  `primary` «Intentar de nuevo».
- Ventana cerrada: «Se cerró la ventana de Meta»; «No se conectó nada. Puedes volver a
  intentarlo cuando quieras.»; los mismos botones.

### 10.3 Pasar el canal a otro agente (`move`, ancho 520)

`h2` «¿Qué agente atiende {etiqueta}?»; `p` «El cambio aplica desde el siguiente
mensaje. Las conversaciones abiertas conservan su historial.». Radios
(`aria-label="Agente"`) con cada agente que no es borrador: nombre + para qué es. Pie:
«Cancelar» · `primary` «Pasar a este agente» (deshabilitado sin elección). Aviso:
«{etiqueta} lo atiende ahora {agente}, desde el siguiente mensaje. Las conversaciones
abiertas conservan su historial.».

### 10.4 Otros canales (no alcanzables en el prototipo: sus tarjetas son «Próximamente»)

- Instagram / Messenger: `callout` con el requisito («Necesitas una cuenta profesional
  de Instagram vinculada a una página de Facebook.» / «Necesitas ser administrador de
  la página de Facebook del negocio.») + «En la ventana de Meta eliges la página y das
  permiso para leer y responder mensajes. Auphere nunca publica por el negocio.»; los
  pasos de Meta pintados son simulación.
- Telegram: pasos con @BotFather y `/newbot`, campo «Token del bot»
  (`placeholder="123456789:AAH…"`), error «Ese token no tiene el formato de BotFather
  (números, dos puntos y una clave larga).», `primary` «Conectar bot».
- Chat web: «Web donde aparece el chat» + fragmento `<script>` con «Copiar» + pista «El
  chat solo funciona en {dominio} y sus subdominios. En cuanto cargue la página una
  vez, lo detectamos.», `primary` «Ya lo pegué».

### 10.5 Pausar y reanudar

En el prototipo no hay modal: «Pausar» pausa al momento con el aviso «Pausado. Sus
conversaciones pasan a la Bandeja.» y botón «Reanudar» en el aviso; «Reanudar» vuelve
al estado anterior y quita el aviso. En la consola se mantiene la confirmación cuando
hay conversaciones abiertas («¿Pausar {nombre}?», 28.x).

---

## 11. Acciones (`data-act`) de estas pantallas

| Acción | Qué cambia | Qué aparece / aviso | Navega |
|---|---|---|---|
| `new-agent` | crea el agente borrador en fase «describir» | 3.1 | pantalla del agente, «Configurar y probar», arriba |
| `open-agent` | elige la pestaña por estado | — | `draft`→build, `ready`→channels, resto→perf |
| `atab` | cambia de pestaña; cierra config de canal y «añadir canal» | — | — |
| `example` | descripción = texto del ejemplo; nombre si vacío | — | — |
| `build` | fase «preparando»; pasos cada 650 ms | al terminar: «Borrador de «{n}» listo. Me faltan {k} datos.» | — |
| `q-pick` | elige opción; sin valor que pedir → respondida | campo de valor si lo pide | — |
| `q-ok` | valida y responde; precio → a la ficha | error en línea; última: «Todo respondido. Ya puedes probarlo.» + «Pruébalo» | — |
| `q-reset` | vuelve a abrir la pregunta | — | — |
| `try` | panel de prueba a la vista; lanza las pruebas si no corrieron (250 ms) | — | pestaña build |
| `run-tests` | 20 pruebas, una cada 70 ms; falla si una habilidad pide un conector sin conectar y no se eligió la alternativa | barra y cabecera en vivo | — |
| `fix` (`connect` / `request`) | conecta el conector o marca «tomar la solicitud»; vuelve a ejecutar | «Arreglado. Volví a pasar las 20 pruebas.» | — |
| `integrate` | conecta el conector al agente | «{X} conectado para {agente}.» | — |
| `unintegrate` | lo quita | — | — |
| `spec-edit` / `spec-cancel` / `spec-save` | abre / cierra / guarda una fila; guardar deja las pruebas sin ejecutar y marca cambios | «Guardado en el borrador. Vuelve a pasar las pruebas cuando quieras.» | — |
| `price-edit` / `price-cancel` / `price-save` | precios de la ficha en línea | ver 5.1 | — |
| `save-agent` | guarda; borrador → «Listo · sin canal» | con canal: «{n} guardado. Ya responde con la versión nueva.»; sin canal: «{n} guardado. Siguiente: conectar un canal.» | sin canal: pestaña Canales, arriba |
| `pause` / `resume` | estado pausado / el anterior | «Pausado. Sus conversaciones pasan a la Bandeja.» + «Reanudar» | — |
| `connect` | abre el modal del canal (o avisa si hay enlace pendiente) | 10.1 | — |
| `cmethod`, `cstage` | método y paso del modal | — | — |
| `meta-launch` | cierra el modal, abre el velo | 10.2 | — |
| `veil-close`, `veil-err` | cierra / error del velo | 10.2 | — |
| `finish-connect` | añade el canal sin configurar y abre su configuración | «WhatsApp conectado[ con su catálogo]. Configura el canal para que empiece a responder.» | config del canal, arriba |
| `send-link` / `copy-link` / `cancel-link` | enlace del dueño | ver 7.3 y 10.1 | — |
| `add-ch` | despliega el asistente bajo la lista | 7.1 | — |
| `menu` | abre / cierra el ⋯ de una fila (clic fuera cierra) | — | — |
| `chconfig` | abre la configuración del canal con lo guardado (o un número de prueba de ejemplo y una persona vacía) | 8 | config, arriba |
| `cfg-go` | desplaza a la sección | — | — |
| `pmode` | «Solo mi equipo» / «A todos» | muestra u oculta Excepciones | — |
| `chip-add` / `chip-del` | añade / quita un número (Enter o coma también) | aviso si el número es corto | — |
| `esc-add` / `esc-del` | añade / quita persona | — | — |
| `do-chconfig` | valida y guarda; recalcula el estado del agente | «{agente} responde por {etiqueta} solo a tu equipo.» / «… a todos.» | vuelve a la lista |
| `cfg-cancel` | sale sin guardar | — | vuelve a la lista |
| `ch-move` / `pick-move` / `do-move` | modal 10.3 | aviso de 10.3 | — |
| `ch-pause` | pausa / reanuda el canal | «Canal en pausa. Sus conversaciones pasan a la Bandeja.» / «Canal reanudado.» | — |
| `disconnect` | quita el canal (sin confirmar en el prototipo; la consola confirma) | «Canal desconectado.» | — |
| `int-cat` | filtro de categoría | — | — |

Código muerto del prototipo (no copiar): `draftPanel` (no se usa), `do-audience` y
`undo-aud` (no hay modal «audience»), `meta-num`, `meta-wait`, `cwho`, `svc`, `right`.

---

## 12. Los 9 bloques del AgentSpec en las 5 filas

El prototipo tiene cinco filas; el AgentSpec tiene `identity`, `voice`,
`instructions`, `procedures`, `services`, `skills`, `escalation`, `rules` y
`ai_disclosure` (más `reception`, `model_policy`, `memory`, `team_access`,
`test_suite` y el conocimiento propio del agente). Propuesta exacta:

| Fila | Bloques | Lectura | Lápiz |
|---|---|---|---|
| **Qué hace** | `identity` (`description`, `goal`) + `instructions` + `rules` | La descripción en 14 px; si hay objetivo, «Objetivo: {goal}» en muted; debajo, nota 12 px «{n} instrucciones · {n} reglas» con un `details` «Ver instrucciones y reglas» que despliega las secciones (título + cuerpo recortado a 3 líneas) y las reglas | Un solo editor con tres partes: descripción (y objetivo), instrucciones por secciones, reglas. Guarda los tres bloques en una sola escritura del AgentSpec. El nombre no se edita aquí (⋯ › Renombrar) |
| **Cómo habla** | `voice` (`tone`, `register`, `greeting`, `languages`) + `ai_disclosure` | Una frase: «{Tono}, {de tú\|de usted\|de vos}. Saluda: «{saludo}».»; nota «Idiomas: español, inglés» si hay más de uno; nota «Aviso de IA: {lo dice en su primer mensaje\|lo dice si le preguntan\|no lo dice}», o insignia `warn` «Aviso de IA sin decidir» (impide guardar, condición de la puerta) | Un editor con tono, trato, saludo, idiomas y el aviso de IA |
| **Qué sabe** | `services` (`mode`, `service_ids`, `faqs`) + conocimiento propio del agente + resumen de la ficha | «{5} servicios · {1} sede · horario (de la ficha)» (o «{3} de {5} servicios»); notas «{n} preguntas frecuentes propias», «{n} fuentes propias»; la nota fija «Hereda la ficha del negocio. Lo que le enseñes aquí solo lo sabe este agente.» | Abre en el sitio: servicios (todos o una lista), preguntas frecuentes y el panel de Conocimiento con «Enseñar» |
| **Qué puede hacer** | `skills` + `connection_requests` (+ `tools`) + `procedures` | Una línea por habilidad con «{X} · conectado» o «Conectar {X}» (4.4); «Apagada» si está apagada; «Mientras tanto: {fallback}» en muted. Debajo, los procedimientos como «Para {título}: {cuándo}» | Sin lápiz en el prototipo. Propuesta: el lápiz abre los procedimientos; las habilidades se encienden desde Conectores |
| **Cuándo pasa a una persona** | `escalation` (`triggers`, `failed_attempts`, `message`) | Los motivos en una frase o lista corta; «Mensaje: {…}» en muted; nota fija «A quién avisa y por dónde se configura en cada canal.» | El editor de escalado de hoy |

Fuera de la tabla:

- **Pruebas** → tarjeta de la derecha (5.1). La lista completa (por tipo, «No aplica»,
  «Añadir una prueba», «Por qué falló») se abre desde esa tarjeta en una hoja lateral
  o un `details` «Ver las 20 pruebas».
- **Revisión** → las comprobaciones de la tarjeta de pruebas (5.1), con sus arreglos.
- **Recepción**, **tope mensual**, **calidad del modelo** (`model_policy`) e
  **historial** → un `details` «Más ajustes» cerrado debajo de la tabla, o en el ⋯ de
  la cabecera («Historial»). `memory`, `team_access` y `test_suite` no se enseñan.
- **Copiloto** y **propuestas** → no están en el prototipo: decisión D2.

Las filas «Cómo habla» y «Qué hace» juntan bloques que hoy se guardan por separado:
como el guardado ya escribe el AgentSpec entero con la revisión (`withBlock` +
`saveAgentSpec`), basta con aplicar varios `withBlock` antes de guardar. `services` y
`skills` no son editables hoy (`EDITABLE` en `builder-model.ts`): hacerlos editables
es solo de consola mientras el validador acepte el AgentSpec entero.

---

## 13. Huecos frente a la consola, por impacto visible

Cada hueco: qué hace el prototipo, qué hace la consola, qué tocar y si los datos ya
existen.

### H1. «Configurar y probar» no es la pantalla del prototipo (el más visible)

- **Prototipo**: izquierda, solo la tabla de cinco filas (y las preguntas pendientes);
  derecha, pegajosa, la tarjeta de pruebas y el chat. Nada más.
- **Consola**: la tabla tiene **nueve** filas (`AGENT_BLOCKS`, con «Instrucciones»,
  «Procedimientos», «Reglas» y «Aviso de IA» como filas propias); debajo, seis
  secciones con título y tarjeta (Conocimiento, Recepción, Pruebas, Revisión,
  Historial, Avanzado); a la derecha, Probador, Copiloto y Propuestas; la columna
  derecha mide `26rem` desde `lg` (1024 px), no es pegajosa y las tarjetas tienen
  radio 8.
- **Tocar**: `components/builder/agent-builder.tsx` (rejilla `minmax(0,1fr)
  minmax(360px,440px)`, `gap` 20, una columna por debajo de 1060 px, `aside` pegajoso
  a 120 px; filas y secciones según 12), `builder-model.ts` (las cinco filas y qué
  bloques lleva cada una), `block-view.tsx` (lectura combinada), `block-editor.tsx`
  (editores combinados), `agent-knowledge.tsx` (dentro de «Qué sabe»),
  `reception-section.tsx` / `agent-history.tsx` / `agent-model-quality.tsx` /
  `money/agent-cap` (a «Más ajustes»).
- **Datos**: existen. Para «{n} sedes · horario (de la ficha)» hay que leer además la
  ficha del negocio (`BusinessRecord`) en `[agentId]/page.tsx`; no hace falta API nueva.

### H2. El panel derecho: pruebas compactas y chat como el del cliente

- **Prototipo**: tarjeta «Pruebas · 20 de 20 pasan» con «Ejecutar todas»/«Repetir»,
  barra de progreso, el fallo con «Conectar {X}» / «Tomar la solicitud y avisar al
  equipo» que vuelve a ejecutar solo, «Todas pasan.» y tres comprobaciones con
  «Añadir precio» en línea. Chat de 300 px con fondo verde WhatsApp, burbujas del
  cliente en `--bubble-out`, nota «Lo que habría hecho: …», hora en la cabecera y un
  `input` con botón de icono. La conversación empieza al escribir.
- **Consola**: `TestList` es la lista completa en la columna izquierda; la revisión es
  otra sección; el Probador pide elegir versión y «Empezar una conversación», enseña
  el panel de hora y agenda simuladas, burbujas del cliente en `--primary`, un
  `textarea` de dos filas con «Enviar» en texto, «¿Por qué dijo esto?» y «Nueva
  conversación».
- **Tocar**: nuevo `components/builder/tests-box.tsx` (resumen de `TestSuite.summary`
  + comprobaciones de `AgentReview.checks` + arreglos de `ReviewFix`), `test-list.tsx`
  (en hoja lateral desde «Ver las pruebas»), `review-panel.tsx` (sin sección propia),
  `agent-playground.tsx` (modo compacto: abre la sesión del borrador al primer envío,
  hora en la cabecera, agenda y versión detrás de un ⋯), `packages/ui/src/styles/tokens.css`
  (`--chat-bg`, `--bubble-out` en claro y oscuro).
- **Datos**: existen salvo dos cosas. **API**: el trabajo de pruebas no da cuántas
  van (`QualityJob.progress` solo tiene `step`): para «{n} de 20» y la barra hace
  falta `progress.done/total` (si no, barra indeterminada). Ligar una prueba fallida
  a su conector («Conectar {X}» dentro del fallo) pide un campo estructurado en
  `AgentTest` (p. ej. `cause.integration`); sin él, el fallo se arma con el hallazgo
  `skills_integrations` de la revisión.

### H3. La barra flotante dice otra cosa

- **Prototipo**: estado a la izquierda según la tabla de 4.5 («20 de 20 pruebas
  pasan · guardado», «1 de 20 pruebas falla · tiene arreglo en un clic», «Borrador
  completo», «2 preguntas pendientes · puedes probar igualmente») y los botones
  píldora a la derecha («Ejecutar pruebas», «Guardar y conectar un canal →»,
  «Guardar cambios», «Guardar igualmente»). Sin nada que guardar, no hay botón.
- **Consola**: `PublishBar` pone el botón a la izquierda y el texto fijo «Guardar
  ejecuta las pruebas y la revisión. Solo llega a clientes si las pasa.»; sin
  borrador, «No hay cambios sin guardar.»; la puerta bloqueada sale como aviso grande
  dentro de la barra.
- **Tocar**: `publish-bar.tsx` (orden y textos por situación, botones
  `rounded-full`, «Ejecutar pruebas» cuando las pruebas están sin ejecutar, la puerta
  bloqueada en un `Sheet` desde «Ver por qué»), `agent-builder.tsx`,
  `i18n/lanes/builder-quality.ts`.
- **Datos**: existen (`PublishPreview.action/has_draft/has_channels/gate`,
  `TestSuite.summary`, `DraftTests.stale`).

### H4. Canales: falta elegir y conectar el canal desde el agente

- **Prototipo**: sin canales, el asistente de cuatro pasos y la rejilla de tarjetas
  (WhatsApp conectable, el resto «Próximamente»/«Pendiente»); el modal «Conectar
  WhatsApp» con Coexistencia (recomendado) / Cloud API y «Compartir un enlace»; el
  velo «Continúa en la ventana de Meta» con sus errores; el paso del catálogo; y al
  terminar, la configuración del canal. Con canales: una tarjeta con filas (logo,
  método, «responde a todos salvo 2 excepciones · escala a Carla», insignia, ⋯) y
  «Añadir otro canal».
- **Consola**: la pestaña solo lista los números en dos columnas con un icono
  genérico, el número como enlace a otra página y el panel del enlace del dueño
  siempre abierto; no hay forma de conectar un número desde el agente.
  «Guardar y conectar un canal» lleva a la página vieja del cliente
  (`/clients/{ref}/channels`, `channelsHref`).
- **Tocar**: `agent-channels.tsx` (asistente + lista en una tarjeta), nuevo
  `channel-picker.tsx` y diálogo `connect-whatsapp-dialog.tsx` que reutilicen el alta
  insertada de `app/(console)/clients/[ref]/channels/page.tsx` (`metaSignupConfig`,
  `connectChoice`) y el velo; `owner-link-panel.tsx` (pasa a ser el paso «Compartir
  un enlace» del diálogo y la tarjeta de enlace pendiente); `quality-model.ts`
  (`channelsHref` → `#agente-canales` del agente); `i18n/lanes/builder-channels.ts`.
- **Datos**: existen el alta de Meta, el enlace del dueño y los catálogos
  (`listCatalogs` / `setCatalog` en `lib/backend/channels.ts`). La meta de cada fila
  sale de `pages[canal].config` (ya se leen en `[agentId]/page.tsx`). **API pequeña**:
  `AgentChannel` no trae el método (Coexistencia / Cloud API); está en `ChannelDetail.mode`
  del API viejo: añadir `mode` a `GET …/agents/{id}/channels` o leerlo de allí.

### H5. La configuración del canal es otra página con otra forma

- **Prototipo**: dentro de la pestaña Canales (cabecera y pestañas del agente
  arriba), índice a la izquierda de 200 px, cabecera con el logo y «WhatsApp ·
  Coexistencia · canal de {agente}», dos modos, «Excepciones» solo con «A todos»,
  escalado en filas de una línea, comprobaciones de pruebas y bolsa, y la barra de
  vidrio con «Activar solo para mi equipo» / «Activar para todos» / «Decidir luego».
- **Consola**: ruta propia `agents/[agentId]/channels/[channelId]` con `h1` «Canal
  {número}», índice en píldoras horizontales, tres modos (incluido «Sin
  configurar»), Excepciones siempre visibles con «Solo cuentan cuando responde «A
  todos».», personas en `fieldset`, «Mensaje de espera», «Comprobaciones» e
  «Historial», y una barra opaca «Tienes cambios sin guardar.» / «Guardar» /
  «Descartar».
- **Tocar**: `channel-page.tsx`, `[channelId]/page.tsx` (pintarla dentro del marco del
  agente con la pestaña Canales activa, o como vista de la pestaña con
  `?canal=`), `channel-model.ts`, `i18n/lanes/builder-channels.ts`. «Mensaje de
  espera» e «Historial» pueden ir en un `details` «Más ajustes» (no están en el
  prototipo).
- **Datos**: existen (`ChannelPage.config`, `checks`, `triggers`, `undo_until`); las
  pruebas, de `BuilderDraft.tests`.

### H6. Las tarjetas de la pestaña Agentes no dicen qué hace cada agente

- **Prototipo**: nombre + insignia arriba; para qué es (dos líneas); pie con el logo y
  el número del canal («+1» si hay más) o «Sin canal», y lo gastado («31,20 USD»). Sin
  título ni párrafo; un solo «Nuevo agente», en la fila de pestañas.
- **Consola**: `h2` «Agentes» + párrafo + un **segundo** «Nuevo agente» (el de la
  cabecera ya está); tarjeta con nombre, «Por defecto», insignia, «Con cambios sin
  publicar», «{n} canales» y chevron.
- **Tocar**: `agent-cards.tsx`, `app/(console)/clients/[ref]/agents/page.tsx`,
  `components/clients/v2/client-header-v2.tsx` (dejar solo ese botón).
- **Datos**: **API**: `ClientAgent` (`lib/backend.ts`) no trae la descripción
  (`identity.description`), lo gastado del mes ni el tipo de cada canal
  (`channels: {id, display}`). Añadir `description`, `month_spent` (dinero de la bolsa)
  y `channels[].type` a `GET /console/clients/{ref}/agents`.

### H7. «Nuevo agente» es otra página, no la pantalla del agente

- **Prototipo**: la misma pantalla (título «Nuevo agente», «Borrador · de {cliente}»,
  pestañas, dos columnas, barra «Generar borrador»); cuatro chips de ejemplo que
  rellenan la descripción y el nombre; al generar, los cuatro pasos con spinner; al
  terminar, sin salir, las preguntas encima de la tabla (chips, respuesta una a una,
  «Cambiar»), la tabla de cinco filas y el panel de pruebas y chat.
- **Consola**: `/agents/new` con «La descripción» y «El borrador» lado a lado,
  contadores, ejemplos como botones de texto largo, «Otras formas de empezar»
  (plantilla y en blanco), los bloques que llegan con borde izquierdo, y las
  preguntas como formulario de radios que al guardar lleva al agente.
- **Tocar**: `builder-new.tsx` (pintar el marco del agente: cabecera, pestañas
  deshabilitadas, describir a la izquierda, panel «Aún no» a la derecha, barra
  flotante), `builder-questions.tsx` (chips, guardado por pregunta, resumen y
  «Cambiar»), `new/page.tsx`; al terminar el trabajo, cargar `getBuilderDraft` y
  pintar `AgentBuilder` sin navegar, con las preguntas del trabajo encima.
  «Plantilla» y «En blanco» pasan a un enlace discreto bajo los ejemplos (decisión D4).
- **Datos**: la mayoría existen (pasos, bloques, preguntas y descartadas del trabajo).
  **API**: los ejemplos son solo texto (`DraftOptions.examples: string[]`); para los
  chips hace falta `{label, text, name}`. Responder una a una exige que
  `POST /console/jobs/{id}/answers` acepte varias llamadas sobre el mismo trabajo
  (comprobar). Si las preguntas deben seguir ahí al recargar o volver otro día,
  hace falta leerlas desde el agente (p. ej. `open_questions` en
  `GET …/agents/{id}/draft`).

### H8. La cabecera del agente lleva más cosas y esconde «Pausar»

- **Prototipo**: título 40 px, insignia con icono · «de {cliente}», y a la derecha un
  botón visible «Pausar» o «Reanudar». Nada más.
- **Consola**: ⋯ con Renombrar / Pausar / Reanudar / Por defecto / Archivar; junto al
  estado, «Por defecto», la insignia de Recepción, «Borrador vN», la línea «{n}
  pruebas · {n} sin ejecutar»; y un aviso «En pausa: …» debajo; título 36 px.
- **Tocar**: `agent-builder.tsx` (botón «Pausar»/«Reanudar» a la vista junto al ⋯, que
  se queda para Renombrar, Por defecto y Archivar; quitar `TestsLine` y «Borrador vN»
  de la cabecera, que ya cuenta la barra; `h1` a 40 px), `agent-menu.tsx`.
- **Datos**: existen (`AgentHeader.allowed`, `visible_state`).

### H9. Rendimiento con otra composición

- **Prototipo**: dos columnas: «Últimos 30 días» con tres cifras (conversaciones,
  «89 %» resueltas sin persona, consumido de la bolsa « · tope …») y «Sugerencias de
  esta semana» con filas de bombilla y «Ver». La pestaña no existe hasta guardar el
  agente.
- **Consola**: periodo 7/30/90, cuatro cifras, gráfica, tabla de conversaciones y
  «Mejoras» debajo en otra tarjeta; la pestaña sale aunque el agente nunca se haya
  guardado, y abre por defecto si hay versión activa.
- **Tocar**: `agent-performance.tsx`, `agent-improvements.tsx` (filas compactas;
  aceptar o descartar dentro de «Ver»), `agent-builder.tsx` (rejilla 1.35fr / 1fr;
  pestaña solo con `active_number != null`; abrir en Canales si el estado visible es
  `ready_no_channel`). La gráfica y la tabla pueden ir debajo, a todo el ancho
  (decisión D5).
- **Datos**: existen (`AgentPerformance`, `Improvements`, tope en `AgentHeader`).

### H10. Conectores con otra forma

- **Prototipo**: una tarjeta con filas divididas; buscador con icono y sin etiqueta
  visible; filtro segmentado de vidrio con números («Todos 11», «Conectados 1» y las
  categorías); logo de 40 px; categoría como insignia junto al nombre; nota
  «{descripción} · lo necesita una habilidad de este agente · {cómo se autoriza}»;
  «Conectado» + «Quitar», o «Conectar» (`primary` si lo pide una habilidad).
- **Consola**: tarjetas separadas, etiqueta «Buscar un conector» encima, categoría en
  un `select`, «Se ven {n} de {m}», insignia «Lo pide una habilidad», selector de
  permiso en cada fila conectada y ⋯ por fila.
- **Tocar**: `agent-connectors.tsx`, `connector-parts.tsx`, `connector-model.ts`
  (recuentos por categoría y «Conectados»). El permiso puede quedarse dentro del ⋯ /
  «Ajustes» en vez de a la vista.
- **Datos**: existen (`AgentConnector.category/needed/connection/activation/auth_kind`).

### H11. «Qué puede hacer» lleva fuera de la pantalla

- **Prototipo**: cada habilidad en una línea con «{X} · conectado» o «Conectar {X}»,
  que conecta en el sitio.
- **Consola**: cada habilidad en su caja con borde; solo dice lo que falta; «Conectar
  {X}» es un enlace a la página de conectores del cliente (`connectHref` →
  `/clients/{ref}/integrations`).
- **Tocar**: `block-view.tsx` (`SkillsValue`/`SkillRow`: línea sin caja, insignia de
  conectado, el botón abre el `ConnectDialog` de `agent-connectors.tsx`).
- **Datos**: existen (conectado = la integración de la habilidad no está en
  `connection_requests`, o `AgentConnector.activation`).

### H12. Textos y forma del estado

- «Publicado» (prototipo) frente a «Atendiendo» (consola); «Pausado» frente a
  «Pausado · a mano»; insignias con icono (`circle-check`, `flask-conical`, `pause`,
  `pencil`) frente a punto. Ver D1. Tocar: `i18n/lanes/business.ts`
  (`clients.v2.agent.*`), `packages/ui/src/components/status-badge.tsx` (prop `icon`).

### H13. Detalles visuales sueltos

- Radio 12 en tarjetas de esta pantalla (`rounded-lg`), no 8.
- Fila de la tabla: `padding:14px 18px`, título 170 px (la consola: 12/16–20 px y
  10.5rem).
- Avisos (`sonner`) como píldora de vidrio abajo a 84 px, con icono y «Deshacer»
  dentro.
- Barra flotante: botones píldora; en móvil, botones a todo el ancho.

---

## 14. Decisiones para Andrés

- **D1. Nombre del estado publicado.** «Publicado» (prototipo) o «Atendiendo» (spec
  25.5, ya en toda la consola). Y si la pausa dice el motivo en la insignia.
- **D2. Copiloto y propuestas.** No están en el prototipo. ¿Fuera de la pantalla, en
  un ⋯ / hoja lateral, o se quedan a la derecha debajo del chat?
- **D3. La voz del borrador.** El prototipo habla en primera persona («Me faltan 2
  datos», «Validé 6 preguntas…», «Leo la ficha…», «Arreglado. Volví a pasar las 20
  pruebas.»). No nombra al constructor, pero le da voz propia. ¿Se copia o se dice en
  impersonal («Faltan 2 datos», «Se validaron…»)?
- **D4. Plantilla y en blanco.** El prototipo no las tiene; la spec sí (17.8, 17.9).
  ¿Enlace discreto bajo los ejemplos, o solo cuando el borrador no se puede escribir?
- **D5. Rendimiento.** ¿Se quitan la gráfica y la tabla de conversaciones, o van
  debajo de las dos tarjetas?
- **D6. «Mensaje de espera» e «Historial» del canal.** No están en el prototipo:
  ¿«Más ajustes» plegado o fuera?
- **D7. «Qué puede hacer» sin lápiz.** ¿Los procedimientos se editan desde esa fila o
  van a «Más ajustes»?
