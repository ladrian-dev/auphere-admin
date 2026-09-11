# T082 — Las cuatro auditorías de la pantalla de operar

**Alcance**: `apps/desktop/src/app/` (App.tsx, `routes/*.tsx`) y
`packages/companion-ui/src/components/`. Ejecutadas el 2026-09-11 en el orden
que manda el workspace: `ui-states-checklist` → `a11y-audit` →
`responsive-audit` → `design-tokens`.

**Cómo se ejecutaron, sin adornos**: como revisión estática del fuente más la
evidencia con display de US1–US5 (`evidence/US1/`, `US2/`, `US3/`, `US4/`,
`US5/`), que son capturas reales de la aplicación ejecutándose contra la API
local. **No** se pasó `axe-core` ni Lighthouse: la pantalla vive en una
`WebContentsView` de Electron, no en una URL que Playwright pueda abrir, y
montar ese andamio es trabajo propio — queda anotado abajo como lo que falta
para poder decir «verificado en vivo» en vez de «revisado».

---

## 1. `ui-states-checklist` — los cinco estados

| Componente | loading | empty | error | partial | ideal |
|---|---|---|---|---|---|
| `roster.tsx` | esqueletos con la forma final | «Todavía no tienes teammates» + CTA | mensaje + reintentar | `forbidden` con su frase | ✅ |
| `thread.tsx` | del paquete (`Timeline`) | vacío propio de la app | mensaje + reintentar | `parcial` y `reconectando` como banda | ✅ |
| `inbox.tsx` | esqueletos | «Nada te espera» explicando cuándo aparece algo | mensaje | `can_decide: false` dice por qué | ✅ |
| `new-teammate.tsx` | esqueletos, sin formulario a medias | sin modelos: no se finge un formulario | error con reintento; fallo de envío conserva lo escrito | — | ✅ |
| `teammate-settings.tsx` | — (el teammate ya está en memoria) | — | fallo de guardado sin fingir que guardó | archivado: solo lectura | ✅ |
| `account.tsx` | esqueletos | «ningún teammate ha gastado» | mensaje + reintentar | equipo ilegible sin tumbar la pantalla | ✅ |
| `env.tsx` | — | secciones que no se pintan vacías | — | sin datos de máquina, no se inventan | ✅ |
| `change-notes.tsx` | — | no pinta nada (ni el título) | — | — | ✅ |

Tres ausencias **deliberadas**, no olvidos:

- `teammate-settings` y `env` no tienen `loading` porque no esperan a nadie: el
  teammate viene del roster que ya está en memoria, y el panel de entorno pinta
  lo que sabe y calla lo que no.
- `change-notes` sin notas **no pinta el título**. Una franja «Cambios de este
  teammate» vacía diría que hubo alguno.

Verdicto: **SHIP** · 9/10. El punto que falta es el de arriba: cinco estados
revisados en el fuente y vistos en capturas, no recorridos uno a uno en vivo.

---

## 2. `a11y-audit` — WCAG 2.2 AA

Comprobado: nombre accesible de cada control, papel, estado anunciado, foco
visible, tamaño de objetivo, y que ningún estado se pinte como error.

**Dos hallazgos, los dos corregidos en este commit:**

- 🟡 **4.1.2 Nombre, papel, valor** — `roster.tsx`: el punto de «te contestó»
  era un `<span>` con `aria-label` y sin papel, que no se anuncia de forma
  fiable. Ahora lleva `role="img"`.
- 🟡 **2.4.3 Orden del foco** — `teammate-settings.tsx`: el panel de confirmar
  el archivado se anunciaba como `alertdialog` pero no recibía el foco, así que
  quien navega con teclado leía una pregunta sin saber dónde contestarla. Ahora
  el foco entra al abrirlo y Escape lo cierra.

Lo que ya estaba bien y se deja escrito para que no se pierda:

- el foco visible sale de los primitivos (`Button`, `Input` de `@nexus/ui`:
  `focus-visible:ring-3`), y los controles propios lo repiten explícitamente;
- los interruptores de permiso son `role="switch"` con `aria-checked` y nombre,
  no casillas: el lector dice «activado / desactivado»;
- el coste de cada modelo va **dentro del nombre accesible** de su opción, así
  que se oye al elegir y no queda como texto suelto al lado;
- ningún estado de espera es `alert`: tope, máquina ausente y reconexión son
  `role="status"`;
- objetivos ≥ 24 px en todo lo pulsable (el `+` del roster es 28);
- `prefers-color-scheme` se aplica en `App.tsx` y `prefers-reduced-motion` vive
  en los tokens de `@nexus/ui`.

Verdicto: **AA en revisión estática**, 0 🔴 · 8/10. Para subir de 8 hace falta
lo mismo que arriba: una pasada real con lector de pantalla y contraste medido
sobre el render, no sobre el nombre del token.

---

## 3. `responsive-audit`

La pantalla es de escritorio y la ventana **no baja de 900 × 600**
(`MIN_WINDOW`, `window-state.ts`), así que 360 y 414 px no son casos de esta
superficie: no existen. Lo que sí se comprobó:

- las tres columnas son `minmax(220px,280px) · minmax(0,1fr) · minmax(220px,300px)`;
  el `minmax(0,…)` del centro es lo que impide que un mensaje largo empuje el
  ancho y aparezca scroll horizontal;
- `min-w-0` en los hijos flexibles de todas las rutas (11 en Cuenta, 13 en el
  panel de entorno, 9 en el formulario), `truncate` con `title` en lo que se
  recorta, y `break-all` en lo que no se puede partir por espacios (rutas,
  nombres de máquina);
- `text-pretty` en párrafos y `text-balance` en títulos;
- texto largo: los nombres de teammate están acotados a 80 en la columna y en
  el formulario, y las rutas del panel de entorno se recortan con `title`.

Verdicto: **PASS** · 8/10, con el alcance acotado a lo que esta superficie
puede ser. Falta medir a 200 % de zoom, que es lo que subiría la nota.

---

## 4. `design-tokens`

Fuente única: `packages/ui/src/styles/tokens.css` (OKLCH, `@theme`), copiada a
la barra por `scripts/copy-tokens.mjs`.

- 🔴 hex/rgb/hsl inline: **ninguno**.
- 🔴 paletas por defecto (`slate`/`zinc`/`gray`): **ninguna**.
- `!important`, `z-index` altos: **ninguno**.
- `style={{…}}`: **uno**, y es geometría en tiempo de ejecución (el ancho del
  medidor de Cuenta, que sale del dato). Queda con su comentario explicando por
  qué no puede ser una clase. El otro que había —el desplazamiento del
  interruptor— pasó a `translate-x-5`, que sí está en la escala.
- 🟡 valores arbitrarios: `max-w-[85%]` en la burbuja del timeline. Es una
  proporción de la conversación, no una medida de la escala de espaciado; queda
  con su comentario.

Verdicto: **CLEAN** · 9/10.

---

## Lo que falta para decir «verificado en vivo»

Un arnés que abra la pantalla del renderer fuera de Electron —el mismo bundle
servido por Vite, con el puente IPC simulado— y le pase `axe-core` y una pasada
de zoom al 200 %. Es trabajo propio, no de esta spec, y sin él estas cuatro
auditorías son lo que dicen ser: revisión del fuente con capturas reales al
lado, no medición del render.
