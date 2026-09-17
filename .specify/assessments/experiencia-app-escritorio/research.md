# Research: la experiencia de la aplicación de escritorio

- **Slug**: experiencia-app-escritorio · **Fecha**: 2026-09-17
- **Método**: cuatro investigaciones en paralelo más una observación en vivo de la
  app instalada. Los informes completos, con todas las URLs, viven en la KB —
  este documento es la síntesis y **cita, no copia**:

| Anexo (KB) | Qué contiene | Tamaño |
|---|---|---|
| `nexus/research/2026-09-17-experiencia-app-escritorio/01-estandares-de-diseno.md` | Apple HIG (incl. macOS 26/27), Fluent 2, Electron, estados, feedback, onboarding, paywall, densidad, accesibilidad, navegación. Top 25 reglas | ~7.200 palabras |
| `…/02-librerias-y-stack.md` | Kits de escritorio, cómo lo hacen las apps de referencia (bundles leídos en esta máquina), piezas sueltas, licencias citadas, matriz de decisión | ~5.200 |
| `…/03-referencias.md` | Teardown de Claude Desktop, ChatGPT/Codex, Cursor, Linear, Raycast, Superhuman, Notion, Slack, Granola, Devin, Manus, Lindy, Relevance | ~15.000 |
| `…/04-auditoria-del-codigo.md` | Mapa de la experiencia actual con `archivo:línea`, flujo de punta a punta, inventario de estados y feedback, sistema visual, accesibilidad, paywall, P0/P1/P2, restricciones y tests | ~9.000 |
| `…/05-observacion-en-vivo.md` | 20 observaciones de la app instalada (v0.1.3), sesión real | ~900 |

**Límite honesto**: las búsquedas web se agotaron a mitad de las cuatro
investigaciones; lo no verificado está marcado en cada anexo. Nada de lo que
sostiene una decisión de abajo depende de un dato marcado como no verificado.

---

## En una página

1. **No hay librería de escritorio que adoptar.** Los kits que imitan macOS o
   Windows están muertos (react-desktop 2019, Photon 2017) o son solo CSS; los
   kits completos vivos (Mantine, Chakra, HeroUI, Fluent, Blueprint) son web
   genérica con su propia identidad. **Las apps de referencia construyen su
   sistema propio sobre primitivas headless** — leído en los bundles instalados:
   Codex (Electron 40) = Radix + cmdk + Tailwind v4 + react-resizable-panels;
   Claude Desktop (Electron 44.2) = claude.ai en un `WebContentsView` + ventanas
   locales en React y Tailwind v4.3. `@nexus/ui` (Base UI 1.x + tokens OKLCH con
   nombres shadcn) **ya está en el camino correcto**. [02 §0, §3]
2. **La calidad «Claude/Linear/Raycast» no sale de una librería**: sale del
   armazón nativo (barra de título integrada, sidebar, menús completos, atajos),
   la densidad, la tipografía, el teclado, los estados y la velocidad percibida.
   Y el caso Claude enseña el contrapunto: su estética se admira, pero se le
   critica por no respetar convenciones de Mac. **La estética no compensa las
   convenciones que faltan.** [01 §3.6]
3. **Lo que tenemos es correcto por dentro y roto en las costuras.** La auditoría
   encuentra 5 P0, 14 P1 y 14 P2; los P0 son recorridos que no se pueden
   completar (entrar con Google, las hojas de la barra, arrancar sin red, pagar,
   abrir un hilo que falla). [04 §0, §8]
4. **Existe un estándar de facto 2026 para apps de agentes** (§2.2): sidebar con
   actividad/pendientes, ⌘K, aprobaciones «una vez / siempre / rechazar» con
   teclado, medidor de uso visible **antes** del tope con hora de reinicio,
   permisos del sistema pedidos en contexto, notificaciones solo en segundo
   plano, y en el tope **acciones concretas** (comprar, mejorar, esperar).
5. **Donde Auphere puede ser mejor** es exactamente donde su dominio es distinto
   (§2.3): el agente actúa en la máquina del partner, el pool es de equipo y las
   aprobaciones son objetos durables con persona responsable. Nadie diseña bien
   la «tarea pausada por saldo que se reanuda con un clic», ni estima el coste
   antes, ni une máquina + aprobaciones + consumo en una sola vista.

---

## 1. Estándares — lo que la plataforma y la disciplina piden

Resumen normativo; cada fila cita su fuente primaria en el anexo 01.

### 1.1 Armazón (macOS primero, Windows preparado)

| Regla | Cifra / especificación | Fuente |
|---|---|---|
| Barra de título integrada con el sidebar de borde a borde; semáforos dentro de la franja superior del sidebar | `titleBarStyle:'hidden'` + `trafficLightPosition`; macOS 27 vuelve a sidebars de borde a borde | HIG Windows/Sidebars; notas de macOS 27 |
| No imitar Liquid Glass con CSS ni usar APIs privadas | Electron sobrescribía `_cornerMask` → GPU de WindowServer en Tahoe (arreglado 36.9.2/37.6/38.2) | HIG Materials; PR electron#48376 |
| Título de la barra = el objeto (teammate/hilo), **nunca el nombre de la app**; <15 caracteres | — | HIG Toolbars |
| Sidebar: ≤2 niveles, ocultable (botón + Ver › Mostrar/Ocultar), **no oculto por defecto**, colapsa en ventana estrecha | Control por defecto 28×28 pt; la HIG ya no publica altura de fila (recomendación: 28 px, 32 con avatar; ancho 220–320) | HIG Sidebars/Accessibility |
| Nada crítico abajo del todo: la gente arrastra ventanas con el borde inferior fuera de pantalla | — | HIG Layout |
| **Una sola vista dueña de las regiones de arrastre**; las demás no solapan esa franja | issue electron#43320 (abierto): un `no-drag` en una vista superior **no** anula el `drag` de otra; PR #51200: vistas ocultas ya no aportan regiones | Electron Custom Title Bar |
| Arranque sin destello | `backgroundColor` siempre + `show:false`/`ready-to-show` | Electron BrowserWindow |
| Tema: una fuente de verdad | `nativeTheme.themeSource` cambia marcos nativos **y** `prefers-color-scheme` en todas las vistas | Electron nativeTheme |
| Windows: WCO con `titleBarOverlay`; Mica solo si toda la cadena es transparente | Barra 32 px (48 con búsqueda); radios 8/4/0 | Fluent 2 Title bar, Geometry |

### 1.2 Menús, atajos, ajustes

- **Menú completo con roles** (App, Edición, Ver con Mostrar/Ocultar sidebar,
  Ventana siempre, Ayuda siempre); **todo ítem de la toolbar existe como comando
  de menú**; los ítems se deshabilitan, no desaparecen. [HIG Menu bar]
- **Atajos estándar intactos** (⌘, ⌘W ⌘N ⌘Q ⌘M ⌘F ⌘Z, Esc/⌘.); ⌘[ / ⌘] historial;
  ⌘K es convención de apps (no del sistema) y debe ser **una sola** paleta con
  todas las acciones, atajos visibles y sinónimos. [HIG Keyboards; Superhuman]
- **Ajustes con ⌘,**, nunca un botón en la toolbar; restauran el último panel;
  la HIG **desaconseja** un selector de tema propio (Sistema por defecto). [HIG Settings, Dark Mode]
- **macOS: cerrar la última ventana no cierra la app**; `activate` la recrea. [HIG; Electron]

### 1.3 Estados y tiempos

| Umbral | Qué hacer | Fuente |
|---|---|---|
| <1 s | **Ningún** indicador (parpadea) | NN/g Response times |
| 1–10 s | Skeleton con dimensiones finales (página) o spinner (módulo), **con texto** | NN/g Skeleton screens (rev. 2026-09) |
| >10 s | Progreso + qué está pasando + tiempo transcurrido | NN/g Progress indicators |
| 400 ms | Umbral de Doherty para respuesta percibida | Laws of UX |
| Mutación que casi siempre sale | UI optimista (`useOptimistic`) con reintento en el propio elemento | React 19 |
| Sin red al arrancar | **Datos en caché + banner discreto**, no alerta | HIG Alerts |

Estados propios de un turno de agente (máquina de estados explícita):
`enviando → esperando primer token → pensando → streaming → herramienta pendiente
de aprobación → herramienta ejecutando → hecho | detenido | fallido`, más
`reconectando`, `sin conexión`, `tope`. **Detener (Esc) siempre visible** mientras
piensa, genera o ejecuta. Transcripción con `role="log"`, mensaje en curso con
`aria-busy`, y nunca una región viva por token. [01 §4.2]

### 1.4 Feedback — taxonomía única

| Mecanismo | Para | Persistencia |
|---|---|---|
| En línea (campo, tarjeta) | Error ligado a un control o a una tarjeta | Hasta resolverse |
| Banner de vista | Estado del sistema que afecta a la vista: sin conexión, tope cercano, pago fallido | Persistente; descartable solo si no es crítico |
| Toast | Confirmación **no crítica** de una acción del usuario, a lo sumo con «Deshacer» | Corta, pausa con hover/foco, consultable después |
| Diálogo / alerta | Decisión inmediata, crítica e irreversible (≤3 botones, verbo, sin «Error» como título) | Hasta decidir |
| Notificación del sistema | Evento con la app en **segundo plano**, sin datos sensibles, agrupada | Centro de notificaciones |
| Badge (Dock/sidebar) | **Número** de pendientes, siempre al día | Mientras existan |
| Bandeja / actividad | Historial de lo anunciado | Permanente |

Reglas duras: **ningún error de datos o de agente va en un toast** (Primer
desaconseja toasts por WCAG 2.2.1, 1.3.2, 2.1.1 y 4.1.3); una sola acción por
notificación (Carbon); no notificar si la app está al frente (HIG); mensajes de
estado sin mover el foco (WCAG 4.1.3). [01 §5]

### 1.5 Onboarding

- **Inicio de sesión en el navegador del sistema**, loopback + PKCE (RFC 8252 —
  ya construido en la 009), con **pantalla de espera** («Continúa en tu
  navegador · Abrir de nuevo · Copiar enlace · Cancelar») y la app recuperando el
  foco al volver. [01 §6]
- **Permisos en contexto**, cuando se usa la función, explicando el beneficio;
  tras una denegación, explicar qué no funciona y enlazar a Ajustes del sistema.
  Claude Desktop pide notificaciones **al ir a mostrar la primera**. [01 §6; 03 Claude §2]
- **Tutoriales impuestos no funcionan** (NN/g 2023); tours de >5 pasos pierden a
  más de la mitad (Chameleon 2025). **Checklist de activación de 4–5 pasos
  accionables** + ayuda contextual. Excepción documentada: Superhuman subió la
  finalización de 30 % a >98 % con onboarding **interactivo sobre datos de
  práctica**, no con diapositivas. [01 §6; 03 Superhuman]

### 1.6 Monetización

- **Nunca un control apagado sin explicación**; el bloqueo lleva al **plan mínimo
  que lo desbloquea** y **vuelve a la acción original** tras pagar. [HIG Feedback]
- **Medidor visible antes del tope** con hora de reinicio (Claude: Ajustes › Uso
  con barra por límite; banner encima del composer al acercarse). [01 §7; 03 Claude §3]
- Contraejemplo Cursor (jul-2025): opacidad del límite → reembolsos y disculpa
  pública. [01 §7]
- UE: Directiva 2023/2673 (aplicable desde 2026-06-19, consumidores) — baja tan
  fácil como el alta, sin prominencia desigual. Auphere es B2B y probablemente
  queda fuera; se adopta como buena práctica. [01 §7]

### 1.7 Densidad, tipografía, iconos, accesibilidad

- Texto de UI **13 px en macOS** (Body 13/16), 14 px en Windows; escala de 4 px;
  control por defecto 28 px; **objetivo mínimo 24×24** (WCAG 2.5.8 manda sobre el
  mínimo de Apple). [01 §8]
- **Iconos**: SF Symbols **no** (licencia limitada a SO de Apple, zona gris en
  Electron, prohibido en Windows); Lucide (ISC/MIT) a 16 px en filas/menús y
  20 px en barra, trazo visual constante. [01 §1.8, §8; 02 §4]
- **WCAG 2.2 AA vía WCAG2ICT** (W3C 2025-12): foco visible **≥3:1** y no tapado,
  teclado completo con salto entre paneles (F6), movimiento y transparencia
  reducidos, zoom 200 % (⌘+/⌘−/⌘0, macOS no tiene Dynamic Type). [01 §9]

---

## 2. Referencias — cómo lo hacen

Detalle con fuentes en el anexo 03. Aquí, lo que converge, lo que diferencia y lo
que se critica.

### 2.1 Tabla comparativa (selección)

| Dimensión | Claude Desktop | ChatGPT/Codex (app unificada, jul-2026) | Cursor 3 | Linear | Raycast 2 | Devin / Lindy |
|---|---|---|---|---|---|---|
| Stack | Electron 44; web en `WebContentsView` | Electron; Radix + Tailwind v4 | Electron (VS Code) | Electron; DS propio LCH | Nativo + React en WebView | Web + desktop local (Devin) |
| Navegación | Sidebar Recents + Projects + Customize; ⌘K busca todo; ⌘/ atajos; `claude://` | Selector de producto; sidebar; ⌘K, ⌘[ ⌘], ⌘B; pestañas; `codex://` | Agents Window; layouts; ⌘E | Sidebar personalizable, back/forward, pestañas con historial, Inbox Priority/Other | Action Panel ⌘K con atajo a la derecha de cada acción | Sidebar con sesiones, carpetas, tags, punto de no leído |
| Onboarding | Descargar → entrar (navegador) → primer valor; permisos al usar | 4 pasos; permisos al usar; **importar de Claude/Cursor** | Entrar (navegador) → carpeta → tarea pequeña | 7–8 pantallas: tema, ⌘K, invitar, primer issue | Onboarding nuevo o migración; permisos al usar | Welcome card; primera sesión sugerida |
| Aprobaciones | Una vez / Siempre / Denegar por sitio, sesión o herramienta; **retardo anti-Enter** | ⏎ aprueba, Esc rechaza; modos Ask / Auto / Full | Run once / Allow always / Skip; modos Auto-review / Allowlist | (SDK: estados `awaitingInput`) | Allow ↵ / Always ⌘↵ / Deny Esc; «Show Command» | **Editar el comando antes de aprobar** (Devin); lectura nunca pide aprobación (Lindy) |
| Uso y tope | Ajustes › Uso con barra por límite; banner «Approaching…resets»; anillo junto al modelo | Uso restante en sidebar; en el tope: **comprar créditos / usar reset / mejorar / esperar** | Notificación con activar on-demand o mejorar; facturación solo web | Créditos IA; avisos de saldo bajo | Píldora «No Credits Left» sobre el composer; `/usage` | Avisos escalonados (66 % → banner → bloqueo con «Request more»); **check-in por gasto anómalo** (Lindy) |
| Feedback | Notificación al terminar si no miras; pantallas de error con salida («Restart Claude») | **Activity** (no leídos, en curso, esperando respuesta) | Notificación + sonido al terminar; badge en bandeja | Inbox, badge Dock, **⌘Z deshace casi todo** | Toast con acciones; notificación con motivo (terminó / necesita confirmación / falló) | Chip working/blocked/done; `Reboot VM` como error accionable |

### 2.2 Patrones convergentes → estándar de facto que Auphere adopta

1. **Barra de título integrada + sidebar** con navegación principal, actividad o
   pendientes con contador, y cuenta/uso al pie.
2. **⌘K** como paleta única con acciones y atajos visibles; **⌘/** lista de atajos;
   ⌘[ ⌘] historial.
3. **Aprobación con tres salidas y teclado** (↵ una vez · ⌘↵ siempre · Esc
   rechazar), alcance explícito (qué, dónde), y **retardo anti-pulsación** al
   aparecer.
4. **Notificación del sistema solo en segundo plano**, con el motivo (terminó /
   necesita tu decisión / falló); clic lleva al objeto.
5. **Permisos del sistema pedidos al usar la función**, con su estado visible en
   Ajustes y enlace a Ajustes del sistema.
6. **Medidor visible antes del tope** con hora de reinicio; en el tope, **opciones
   concretas** (mejorar, comprar, esperar hasta X) — nunca solo un texto.
7. **Errores con salida** (reintentar, reconectar, volver a entrar, reiniciar) y
   **reintento automático** con estado visible.
8. **Enlaces profundos** propios que abren el objeto y **nunca ejecutan** sin
   confirmación.

### 2.3 Diferenciadores posibles para «incluso mejor»

| Diferenciador | Por qué encaja con Auphere | Quién se acerca |
|---|---|---|
| **Una vista «Hoy»** que une máquina, pendientes, consumo del equipo y actividad de los teammates | El partner opera un equipo, no un chat | Lindy Home («What I've been up to»), Activity de ChatGPT |
| **Pausa por saldo reanudable con un clic** desde el hilo, tras comprar | §IV y 004: la tarea es durable; nadie lo diseña bien | Nadie (Manus deja saldo negativo, Lindy no reanuda) |
| **Coste esperado visible antes** («gasta más / normal / poco» ya existe) y **aviso de gasto anómalo** | «Todo lo que gasta se mide»; es la queja nº 1 del sector | Lindy (check-in), Devin (Session Insights) |
| **Editar antes de aprobar** + «siempre en esta máquina para este cliente» | Las tres capas de política ya existen (001/003) | Devin Local |
| **Aprobación con persona responsable visible** | §IV: `decided_by` es de dominio | Nadie lo enseña |
| **Estados honestos como marca** (parcial acotado, bloqueado ≠ ocioso) | §V es constitucional | Nadie lo formaliza |

### 2.4 Anti-patrones documentados (qué no hacer)

- **Rediseños que rompen el modelo mental** y se revierten: ChatGPT (jul-2026, chat
  enterrado, corregido en una semana), Cursor (toggle Agent/Editor que aparece y
  desaparece, 3 layouts en meses), Slack (3 reorganizaciones en 3 años). → Cambiar
  **una vez**, con la navegación decidida antes de construir.
- **Medidores que se contradicen** (Codex: banner contra analítica; Cursor: «límite»
  al 70 %; Claude: banner sin porcentaje y botón «Upgrade» en el plan máximo). →
  **Un solo derivado** de uso para todas las superficies.
- **Contadores de no leídos atascados** (Cursor, Codex en Dock). → El badge sale del
  mismo derivado que la bandeja.
- **Esconder lo que hace el agente** aunque se pida detalle (Cursor 3.10). → Modos
  de detalle que se respetan.
- **Permisos que se reinician en cada actualización** (Claude). → Persistencia
  probada entre versiones.
- **Paywall antes de ver valor** (Superhuman 2023) y **opacidad de la unidad**
  (ACU de Devin, créditos de Manus). → Mostrar en unidades del partner (porcentaje
  y fecha, 004 R7).

### 2.5 Flujos de referencia (resumen; detalle en anexo 03)

- **(a) Primer arranque → primer valor**: abrir → una pantalla «Entrar» → navegador →
  vuelta con foco → (si falta) configurar lo imprescindible con su porqué →
  primer objeto útil ya presente (Granola: reunión de ejemplo; ChatGPT:
  sugerencias; Linear: workspace demo) → checklist de activación visible, no
  bloqueante.
- **(b) Sin membresía intenta usar la función**: la función **se ve** con su
  etiqueta de plan; al pulsarla, hoja con el plan mínimo, precio y «Mejorar» →
  checkout → vuelta a la acción. (Claude Code: «If clicking Code prompts you to
  upgrade…»; Raycast: píldora en el composer.)
- **(c) 80 % / 100 % del pool**: banner encima del composer con porcentaje y
  reinicio → en el tope, el turno en curso termina y el composer ofrece mejorar,
  comprar o esperar hasta la hora exacta.
- **(d) Aprobación con la app en segundo plano**: notificación «X necesita tu
  decisión» sin el comando en el texto → clic abre la tarjeta con foco →
  ↵/⌘↵/Esc; el badge baja al instante en Dock, sidebar y bandeja.
- **(e) Sesión caducada / máquina sin emparejar**: pantalla propia en la app
  («Tu sesión terminó · Entrar de nuevo») conservando el borrador; la máquina
  sin emparejar es un paso de la checklist con su acción, no un banner que
  explica.

---

## 3. Librerías y stack — decisión técnica

Detalle, versiones y licencias citadas en el anexo 02.

### 3.1 Matriz

| Camino | Coste relativo | Identidad | Consistencia con consola | Riesgo |
|---|---|---|---|---|
| **A. `@nexus/ui` + Base UI con capa de escritorio y armazón propio** | 1,0 | Propia | Máxima (un solo DS) | Carga propia de diseño y QA |
| B. Kit completo (Mantine / HeroUI / Fluent / Blueprint) | 2,5–3× | La del kit | Rota (dos DS) | Hoja de ruta ajena; Fluent con assets restringidos; HeroUI con licencia ambigua |
| C. A + registros copiados a demanda (shadcn Base, coss `apps/ui`, AI Elements) | 1,1× | Propia si se re-tokeniza | Alta | **coss es AGPL fuera de `apps/ui` y `apps/origin`**; Radix entra sin darse cuenta |

**Recomendación del anexo, que esta evaluación hace suya**: **A como arquitectura,
con las tácticas de C bajo control** — Base UI como única capa de primitivas
(lo copiado con Radix se porta o no entra), y solo piezas pequeñas y
especializadas.

### 3.2 Dependencias candidatas (licencia leída en el anexo 02 §8)

| Paquete | Para | Licencia |
|---|---|---|
| `@fontsource-variable/inter-tight`, `@fontsource-variable/jetbrains-mono` | Fuentes empaquetadas (CSP `font-src 'self'`) | OFL-1.1 / MIT |
| `react-resizable-panels` | Sidebar y paneles redimensionables | MIT |
| `@tanstack/react-virtual` | Roster, pendientes y actividad largos | MIT |
| `use-stick-to-bottom` | Scroll del hilo que no pelea con el usuario | MIT |
| `streamdown` (+ `@streamdown/code`) | Markdown en streaming seguro (`rehype-harden`) | Apache-2.0 |
| `electron-context-menu` | Menús contextuales nativos de texto/enlaces | MIT |
| `@playwright/test` (dev), `@axe-core/playwright` (dev) | Humo E2E del empaquetado y a11y | Apache-2.0 / **MPL-2.0** (dev, no distribuida) |

**No**: `cmdk` (estancado desde 2025-03, arrastra Radix; la palette propia pasa a
`Autocomplete` de Base UI), `@virtuoso.dev/message-list` (comercial),
`electron-window-state` (sin release desde 2018; ya hay `window-state.ts`),
Lost Pixel (archivado), SF Pro / SF Symbols / assets de Fluent (licencias),
Aceternity (propietaria y estética de marketing), cualquier fichero de
`cosscom/coss` fuera de `apps/ui` y `apps/origin` (AGPL-3.0).

### 3.3 Dos huecos técnicos que el rediseño cierra de paso

- **La vista de la pantalla de operar no tiene CSP** (solo la barra). [02 §1]
- **No se carga ninguna fuente** en la app: la pantalla y la barra van en SF Pro,
  la consola en Inter Tight, en la misma ventana. [02 §1; 04 §5.3; 05 obs. 8]

---

## 4. Lo que tenemos — auditoría y observación

Detalle con `archivo:línea` en los anexos 04 y 05.

### 4.1 Lo que está bien y hay que conservar

Máquinas de estado puras con test (`bar-state`, `app-state`, `update-policy`,
`notifications-policy`); aislamiento de particiones comprobado al arrancar;
IPC como lista cerrada con validación y `redact`; tarjetas de confirmación y
ejecución con teclado, cuenta atrás desde `expires_at` y frases distintas para
409/412; timeline con cinco estados, `role=log` y `assertive` solo para
aprobaciones; formulario de teammate que conserva lo escrito; política de
ejecución en tres capas con techo explicado; `Intl` en fechas y números;
`prefers-reduced-motion` respetado.

### 4.2 Problemas P0 — el recorrido básico no se completa

| # | Síntoma | Causa verificada |
|---|---|---|
| P0-1 | Entrar con Google desde la app no vuelve nunca | `signInWithBrowser()` sin llamador; el botón de la consola sale al navegador por `will-navigate` (`main.ts:196-201`) |
| P0-2 | «Introducir código» y «Directorios» no se ven | Hoja en segunda fila con `overflow:hidden` en una vista de 44 px (`bar.css:13-16,101-109`) |
| P0-3 | Sin red al arrancar: esqueletos para siempre; sin red a mitad: te echa al login | `loadURL` sin `try` aborta `bootstrap()` (`main.ts:434`); `session-gate.ts:50-53` convierte excepción en `anonymous` |
| P0-4 | Pagar sale al navegador sin aviso y acaba en 404 | `will-navigate` sin feedback; `/billing/gracias` inexistente (tarea aparte) |
| P0-5 | Un hilo que no abre se pinta «vacío» | `thread.tsx:75-82` sin rama de error; `useCompanion` nace en `ready` |

### 4.3 P1 más relevantes para el diseño

- **La persona no se entera de las actualizaciones** (el aviso nunca se emite;
  «Actualizar» abre el feed crudo).
- **El paywall explica y no lleva**: «cambia de plan, en Cuenta» y Cuenta no
  tiene plan; «escríbenos» sin enlace; banner y composer contradictorios en la
  pausa.
- **Tres contadores de pendientes con tres reglas** (pestaña, bandeja, Dock).
- **El hilo del teammate habla como el Companion** («Mensaje al Companion»,
  «tope mensual» cuando es semanal).
- **Foco y contraste bajo AA**: anillo `primary` sobre `bone` 2,09:1 (con `/50`,
  1,46:1); errores de formulario 2,97:1; en oscuro, error sobre `card`
  (bangladesh-green) **1,24:1** y `muted-foreground` sobre `card` 3,83:1.
- **La barra no se alcanza con teclado** (otra `WebContentsView`).
- **Cerrar la ventana cierra la app** (y la bandeja y los avisos).
- **Cómo emparejar se dice de tres formas** y con equipo vacío no hay camino clicable.
- **Pendientes aprueba a ciegas** (sin comando, diff ni antigüedad) y no dice
  cuándo falla.

### 4.4 Observación en vivo (v0.1.3) — lo que el código no enseña

Barra de título gris separada del contenido; pestañas Equipo/Pendientes/Cuenta
**sobre el roster que no cambian el roster**; **dos vacíos contradictorios** en el
primer arranque («Todavía no tienes teammates» + «Elige un teammate…»); panel
Entorno siempre visible con «Navegador: todavía no.»; barra inferior con
`Adrians-MacBook-Pro.local · reconectando` fijo mientras la consola dice
«Empareja esta máquina ✓»; radios nativos azules junto a toggles verdes; la
consola embebida es **otra app** (sidebar, iconos, ⌘K, avatar, checklists de
onboarding) y la pantalla de operar no tiene nada de eso; menú Ver mezcla
español e inglés.

### 4.5 Inventario de feedback hoy

Siete mecanismos sin taxonomía: `role=status` usado para errores y contenido
estático, `role=alert` en tono warning de bajo contraste, `alertdialog` en línea
sin atrapar foco, `window.confirm` nativo, banners `bg-muted` para gravedades
distintas, notificaciones sin icono y con resumen solo en español, y **siete
sitios donde una acción falla o sale de la app sin decirlo**. La consola usa
toasts (`sonner`); la pantalla de operar, ninguno.

---

## 5. Datos y restricciones que no se reabren

Del anexo 04 §9; cualquier opción de `concept.md` las respeta o las enmienda
explícitamente.

1. **Cuatro particiones separadas**; solo la humana persiste. La pantalla y la
   barra no ven cookies: lo que necesita sesión pasa por el proceso principal.
2. **La consola no tiene `preload`** (002 R12.1). Solo influye por navegación,
   cookies observadas o el user-agent `AuphereDesktop/x`.
3. **IPC de la pantalla = lista cerrada** (25 invocación + 8 empuje). Toda
   capacidad nueva es **enmienda** de `specs/003-*/contracts/desktop-app-ipc.md`.
4. **`redact` borra claves** que casan con
   `session|cookie|token|credential|authorization|secret|password` a cualquier
   profundidad — un campo `token_usage` desaparece en silencio.
5. **La barra tiene siete funciones exactas** y tests que prohíben `login`,
   `session`, `password` en su preload y en `src/bar/`.
6. **Sin autenticación propia** (002 R2.1/R2.5) y **sin esquema `auphere://`**
   (002 R3.5); un solo oyente permitido: el loopback de la 009.
7. **Google, Stripe y Meta no ocurren dentro de la ventana** (política de
   ventanas): se diseña el traspaso y la vuelta.
8. **003 R12.6**: la pantalla no reimplementa páginas de la consola; **004 R7**:
   sin cifra absoluta del pool; **005**: sin datos de tarjeta; **§IV**: acción
   consecuente con humano y auditoría; borrar no existe, se archiva.
9. **Updater**: nunca reinicia solo; no instala con trabajo vivo.
10. **~20 tests fijan copy y estructura** (lista en anexo 04 §9.2), más los
    recorridos de evidencia de `main.ts:476-668` (uno ya roto).

---

## 6. Evidencia en contra y riesgos

- **Riesgo de rediseño que se revierte** (ChatGPT, Cursor, Slack). Mitigación: la
  navegación y el armazón se deciden y validan **antes** de construir pantallas;
  se cambia una vez.
- **Electron criticado como «mala app de Mac»** (Gruber sobre Claude,
  2026-07). La estética no basta: menús, atajos, cierre de ventana, texto y
  foco son requisitos, no pulido.
- **Regiones de arrastre con vistas apiladas** (electron#43320 abierto). Un
  armazón con la consola **solapando** la franja superior se rompería; exige que
  una sola vista sea dueña de la franja.
- **La consola embebida es la mitad de la experiencia** y vive en otro despliegue
  (Next.js remoto). Cualquier armazón unificado toca `apps/console`
  (modo embebido por UA) y sus tests (`shell-detect.test.ts`).
- **Cambiar tokens de `@nexus/ui` toca también consola y admin**. Arreglar el
  contraste en oscuro (card = bangladesh-green) es un cambio visible en la web.
- **Tamaño**: cinco ejes × tres superficies es una spec grande; el riesgo es una
  `tasks.md` de >120 tareas imposible de verificar. Mitigación: historias
  priorizadas e independientes (plantilla de spec).
- **Tests que fijan comportamiento que queremos cambiar** («cerrar sesión abre la
  consola», «el navegador se dice, no se apaga», siete funciones de la barra).
  Cambiarlos es legítimo si la spec lo declara; hacerlo en silencio no.

---

## 7. Gaps & Open Questions — para `concept.md` y la decisión

1. **Armazón**: ¿una sola aplicación con la consola como panel de contenido, o dos
   superficies con mejor cambio entre ellas, o todo nativo con la consola en el
   navegador?
2. **Barra de 44 px**: ¿se absorbe en el armazón (estado de la máquina en el
   sidebar, emparejar como diálogo) o sobrevive?
3. **Dirección del modo oscuro**: ¿verde inmersivo (hoy) o tinta neutra cálida con
   el verde como acento?
4. **Corte**: ¿una spec con historias priorizadas o varias; y los P0 que son
   defectos de 005/009, dentro o por el flujo de bugs?
5. **No verificado y necesario antes de plan**: comportamiento real de
   `app-region` con la consola como panel lateral (spike de 1 h en el plan);
   bloqueo de `sonner` bajo CSP (`style-src 'self'`).
