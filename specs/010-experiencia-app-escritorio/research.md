# Fase 0 — Investigación técnica: la experiencia de la aplicación de escritorio

**Spec**: [spec.md](./spec.md) · **Fecha**: 2026-09-17

La investigación de producto (estándares, referencias, librerías, auditoría) ya
está hecha y vive en la KB y en la evaluación:
`/Users/lmatos/Work/Auphere/nexus/research/2026-09-17-experiencia-app-escritorio/`
y `.specify/assessments/experiencia-app-escritorio/`. **Este documento no la
repite**: resuelve las incógnitas técnicas que quedaban para poder diseñar, y
cierra las cuatro condiciones de entrada al plan.

---

## D1 · ¿Funciona el arrastre de la ventana con la consola pintada encima del panel?

**Condición 1 de la decisión. Resuelta con un spike ejecutado, no con lectura.**

- **Decisión**: sí. El armazón se monta con **una vista a pantalla completa**
  (la aplicación) que es la **única dueña de las regiones de arrastre**, y la
  vista de la consola colocada **solo** sobre el rectángulo de contenido.
- **Evidencia** (spike con Electron 44 del repo, ventana `BaseWindow` +
  dos `WebContentsView`, `titleBarStyle: 'hidden'`, franja de 52 px con
  `-webkit-app-region: drag`, consola superpuesta en el panel):

  | Prueba | Resultado |
  |---|---|
  | Arrastrar por la franja superior con la consola encima del panel | **La ventana se movió**: `{x:120,y:120}` → `{x:319,y:334}` |
  | Pulsar un botón dentro de la vista superpuesta | **Responde** (contador pasó a 1) |
  | Arrastrar dentro de la vista superpuesta | **La ventana NO se movió** (solo selección de texto) |
  | Cobertura del panel | La consola cubre el panel entero; el color testigo del fondo no asoma |

- **Por qué funciona pese a electron#43320**: ese fallo aparece cuando las
  regiones de arrastre de una vista quedan **debajo** de otra vista. En este
  diseño **no hay solape de regiones**: la franja de arrastre vive en los 52 px
  superiores, y la consola empieza justo debajo. La regla queda escrita como
  invariante del armazón: **ninguna vista puede solapar la franja superior**, y
  la vista de la aplicación no declara `drag` fuera de ella.
- **Alternativas consideradas**: (a) franja en su propia vista — es justo la
  configuración que dispara el fallo; (b) `titleBarStyle: 'hiddenInset'` sin
  franja propia — deja la altura del sistema y no permite integrar el sidebar;
  (c) plan B de la evaluación (mantener dos superficies) — **no hace falta**: el
  spike salió verde.
- **Riesgo residual**: vistas ocultas aportaban regiones de arrastre hasta
  electron#51200; se mitiga ocultando con visibilidad (no moviendo fuera de
  pantalla) y manteniendo Electron al día.

## D2 · ¿Cómo sabe la aplicación dónde está la consola, sin darle un canal?

- **Decisión**: el **proceso principal** observa la navegación de la vista de la
  consola y **empuja** a la aplicación la ruta actual; la aplicación **pide** al
  principal que muestre una ruta. La consola no gana `preload` ni canal alguno
  (002 R12.1 intacta).
- **Rationale**: es la única forma de una sola navegación sin tocar la frontera.
  Lo que viaja son rutas (`/usage`, `/billing`) y números (el rectángulo del
  panel) — ningún dato de sesión; `redact` sigue aplicándose.
- **Alternativas**: `postMessage` entre vistas (exigiría `preload` en la
  consola: prohibido); leer el título de la ventana (frágil); no marcar la
  sección activa (rompe R1.4).

## D3 · Modo embebido de la consola

- **Decisión**: la consola detecta la cáscara por su user-agent
  (`AuphereDesktop/x`, que ya se añade hoy) y, en ese modo, **no pinta su propio
  armazón** (barra lateral, cabecera, conmutador de idioma y tema); pinta solo el
  contenido de la página.
- **Rationale**: la decisión ya existe en el producto («la consola sabe que la
  carga la cáscara **solo** por esto», 002 R12.7/D9), y el user-agent es la única
  señal disponible sin abrir canal.
- **Riesgo**: el modo embebido sirve desde el servidor; un despliegue que lo
  rompa deja dos armazones. Se cubre con un test de la consola que afirme el
  modo embebido y con una comprobación visual en el humo de escritorio.
- **Alternativa**: una cabecera propia por petición — mismo efecto, más frágil.

## D4 · Absorber el puesto de trabajo (la barra de 44 px)

- **Decisión**: se retira la vista y su partición; sus capacidades (estado,
  emparejar, desemparejar, elegir directorio) pasan al contrato de la pantalla.
  El código de emparejamiento lo sigue **canjeando el proceso principal** con la
  sesión de la partición humana.
- **Rationale**: reduce superficie (una partición y un `preload` menos), elimina
  por construcción el fallo de las hojas invisibles y hace el puesto alcanzable
  con teclado.
- **Lo que se conserva del contrato viejo**: los **ocho estados** y sus
  transiciones (`bar-state.ts` es lógica pura con test) — se reusa el módulo, se
  jubila su pintura. Las prohibiciones de `no-own-auth` se trasladan a la vista
  de la aplicación: ningún formulario de credenciales, ninguna palabra de sesión
  en el `preload`.
- **Alternativa**: darle altura dinámica a la barra — mantiene dos sistemas
  visuales y el borde inferior para lo crítico (HIG lo desaconseja).

## D5 · Tokens: oscuro en tinta y foco que se ve

- **Decisión**: superficies oscuras derivadas de la tinta de marca con croma muy
  bajo en el matiz verde; el verde queda para primario, positivo, foco y datos.
  Token de foco propio con **≥3:1 en ambos temas**, que la aplicación **no
  sobrescribe**.
- **Datos que lo obligan** (medidos en la auditoría): foco `primary` sobre `bone`
  **2,09:1** (y 1,46:1 con la variante translúcida que hoy usan los controles);
  error sobre tarjeta oscura **1,24:1**; texto apagado sobre tarjeta oscura
  3,83:1; aviso sobre claro 2,97:1.
- **Alcance**: `packages/ui` es compartido → cambia también consola y panel de
  operador. Se acompaña de un **test de contraste de pares** que falla si un par
  declarado baja del umbral.
- **Alternativa**: corregir solo `--card` en oscuro — arregla un par y deja la
  superficie saturada que la evaluación descartó.

## D6 · Tipografía empaquetada y política de contenido

- **Decisión**: se empaquetan `@fontsource-variable/inter-tight` y
  `@fontsource-variable/jetbrains-mono` (OFL-1.1 la fuente, MIT el empaquetado) y
  la vista de la aplicación declara una política de contenido con
  `font-src 'self'`, como ya hace la del puesto.
- **Rationale**: hoy la aplicación cae a la fuente del sistema mientras la
  consola usa Inter Tight, en la misma ventana; y la vista de la aplicación no
  tiene política de contenido (hallazgo del anexo 02).
- **Alternativa**: Google Fonts en tiempo de ejecución — prohibido por la
  política y falla sin red.

## D7 · Avisos efímeros bajo política de contenido

- **Hecho verificado**: `sonner@2.0.8` (MIT) **exporta su hoja de estilos**
  (`./dist/styles.css` en sus `exports`), además de inyectarla en tiempo de
  ejecución; y el `Toaster` de `@nexus/ui` **depende de `next-themes`**, que en la
  aplicación no existe.
- **Decisión**: la aplicación usa un `Toaster` propio del paquete compartido que
  (a) recibe el tema por propiedad en vez de `next-themes` y (b) **importa la
  hoja de estilos**, sin depender de la inyección. **Condición 2 cerrada por
  diseño**; el plan incluye una tarea que **prueba** que no hay violación de la
  política con los avisos encendidos, y si la hubiera, la alternativa es el
  primitivo de aviso de Base UI (ya presente en la librería).
- **Recordatorio de la taxonomía**: los avisos efímeros son **solo** para
  confirmaciones no críticas; ningún error viaja por ahí (R5.2).

## D8 · Cómo se navega dentro de la aplicación

- **Decisión**: no entra un enrutador. Las secciones son un estado del armazón
  con una **ruta interna canónica** (`/hoy`, `/pendientes`,
  `/teammates/:id`, `/admin/:seccion`) usada por la lista lateral, el historial
  (atrás/adelante), la búsqueda de acciones y la restauración al reabrir.
- **Rationale**: son doce pantallas; un enrutador completo añade dependencia y
  no resuelve nada que el estado no resuelva. La ruta canónica es lo que sí hace
  falta, porque es lo que se restaura y lo que se marca.
- **Alternativa**: TanStack Router con historia en memoria — se reconsidera si
  aparecen vistas anidadas o enlaces entrantes (fuera de alcance por 002 R3.5).

## D9 · Dependencias nuevas, con su licencia

Solo entran piezas pequeñas. Cada una con el párrafo citado en el plan
(`Constitution Check` §VIII):

| Paquete | Para qué | Licencia |
|---|---|---|
| `@fontsource-variable/inter-tight` | tipografía de marca servida localmente | OFL-1.1 (fuente) · MIT (empaquetado) |
| `@fontsource-variable/jetbrains-mono` | monoespaciada | OFL-1.1 · MIT |
| `react-resizable-panels` | sidebar y paneles redimensionables | MIT |
| `@tanstack/react-virtual` | listas largas (roster, pendientes, actividad) | MIT |
| `use-stick-to-bottom` | scroll del hilo que no pelea con la persona | MIT |
| `electron-context-menu` | menús contextuales nativos de texto y enlaces | MIT |
| `@playwright/test` (desarrollo) | humo del binario empaquetado | Apache-2.0 |
| `@axe-core/playwright` (desarrollo) | revisión automática de accesibilidad | **MPL-2.0** — se declara: es herramienta de desarrollo, **no se distribuye** con el producto |

**Descartadas y por qué**: `cmdk` (estancado y arrastra Radix; la búsqueda de
acciones se construye sobre el primitivo que ya usa `@nexus/ui`),
`@virtuoso.dev/message-list` (comercial), `electron-window-state` (sin
publicación desde 2018; ya existe módulo propio), iconos y fuentes de Apple y de
Fluent (licencias restringidas), cualquier fichero de `cosscom/coss` fuera de
sus dos rutas MIT (**AGPL-3.0**), Aceternity (propietaria).

**`streamdown`** (Apache-2.0), evaluado para el markdown en streaming, **no entra
en esta spec**: el hilo ya pinta texto sin markdown y añadirlo es cambio de
comportamiento del turno, que esta spec declara fuera de alcance. Queda anotado
para cuando toque.

## D10 · Cómo se prueba todo esto

- **Unidad y componente** (`vitest` + Testing Library, ya en uso): módulos puros
  nuevos (derivado de «lo que te espera», estado del puesto, taxonomía de
  avisos, rutas canónicas) y cada estado de cada pantalla.
- **Contraste**: test que recorre los pares declarados de tokens en ambos temas y
  falla por debajo del umbral. Es la única forma de que R2.4 no se degrade.
- **Accesibilidad**: `@axe-core/playwright` sobre las pantallas de la aplicación.
- **Humo del binario** (`@playwright/test` con su soporte de Electron, marcado
  como experimental por el proyecto): que la ventana abre sin destello, que la
  franja arrastra, que la consola se pinta en el panel y que no hay violaciones
  de la política de contenido en consola.
- **Aislamiento**: el test de particiones pasa de cuatro a **tres** y sigue
  abortando el arranque si alguien las iguala.
- **Lo que ya existe y hay que actualizar, declarándolo**: los tests que fijan el
  comportamiento que esta spec cambia a propósito («cerrar sesión abre la
  consola», «el navegador se dice, no se apaga», las siete funciones del puesto)
  y los recorridos de evidencia de la spec 003, uno de los cuales ya está roto
  (busca un elemento que la pantalla de Cuenta dejó de pintar).

## Condiciones de entrada al plan: estado

| # | Condición | Estado |
|---|---|---|
| 1 | Spike de regiones de arrastre | **Cerrada, verde** (D1). Plan B no se usa |
| 2 | Avisos efímeros bajo política de contenido | **Cerrada por diseño** (D7), con tarea de verificación y alternativa escrita |
| 3 | Ver en pantalla el fallo de las hojas del puesto | **Sigue abierta**: la máquina de pruebas está en `reconectando` y esa acción solo existe en `conectada`. **No bloquea**: la decisión D2 elimina las hojas, y el diseño no depende de reproducir el fallo |
| 4 | Licencia citada de cada dependencia | **Cerrada** (D9) y repetida en el Constitution Check |
