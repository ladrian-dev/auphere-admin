# Idea Intake: la experiencia de la aplicación de escritorio — diseño, estados y recorridos

- **Slug**: experiencia-app-escritorio
- **Created**: 2026-09-17
- **Source**: pasted text (Luis, sesión del 2026-09-17, con una captura de Claude
  Desktop como referencia) · puntero al repositorio: `apps/desktop` (cáscara,
  pantalla de operar, barra), `packages/ui`, `packages/companion-ui`,
  `apps/console` (lo que la ventana embebe) · KB: `brand/brand-system.md`,
  `nexus/research/2026-09-17-experiencia-app-escritorio/` (anexos de esta evaluación)
- **Type**: improvement (experiencia y sistema visual de una superficie ya abierta)

## Idea (as captured)

> Estamos construyendo la app de escritorio de Auphere y no le hemos dado mucho
> énfasis al Diseño y UX. Esta sesión y nuevo Spec estará enfocado en eso. Mira en
> la imagen el diseño de Claude Desktop y está haciendo uso correcto de la barra
> superior, de sidebar, componentes, colores, estados (Empty, loading, thinking,
> etc). Un buen flujo de marketing y usabilidad (si no tienes una membresía te
> envía directo a la vista o página de membresías, no solo te dice que no puedes
> hacer sino que te envía directo a hacerlo), el flujo desde que descargas la app
> y pasas por todo ese proceso de onboarding está bien definido, las alertas y
> notificaciones están estandarizadas y bien usadas, los espacios, componentes,
> iconos, etc.
>
> Necesito que investiguemos a fondo las diferentes opciones que tenemos para
> implementar un diseño similar e incluso mejor, identificar si hay librerías de
> diseño de Electron o todo debe ser from scratch, los problemas de UX que tenemos
> que debemos arreglar, etc. Empieza con una investigación profunda de estándares
> de diseño, buenas prácticas y consejo, luego revisa lo que tenemos y las
> referencias que podríamos usar de software similares y luego continúas con el
> flujo SDD para empezar a implementarlo end to end correctamente.

## Restated

Las specs 001–009 construyeron una aplicación de escritorio **correcta por
dentro** —aislamiento, máquinas de estado puras, contención, firma y canal— pero
nadie la diseñó **como producto**. Tres superficies (la consola web embebida, la
pantalla de operar y la barra de 44 px) se apilan en una ventana con la barra de
título del sistema, cada una con su tipografía, su vocabulario y su forma de
avisar. Luis pide llevarla al nivel de las apps de escritorio de referencia
(Claude Desktop como ejemplo) en cinco ejes: **armazón** (barra superior, sidebar,
navegación), **sistema visual** (componentes, color, espaciado, iconos),
**estados** (vacío, cargando, pensando, error…), **feedback estandarizado**
(alertas, notificaciones) y **recorridos que llevan a la acción** (primer
arranque hasta primer valor; sin membresía → directo a contratar). Y quiere
saber, antes de construir, si hay librería de escritorio que adoptar o todo es
propio.

## Origin & Context

- **Raised by**: Luis, 2026-09-17.
- **Trigger**: usar la app instalada (v0.1.3) tras la cadena de la spec 008 y los
  fallos del 2026-09-15 (`docs/bugs-app-escritorio-2026-09-15.md`). La app
  funciona, pero se siente como una web dentro de una ventana.
- **Lo que ya decía el repo y encaja**: constitución §V («La pantalla no miente»:
  `normal · cargando · vacío · error · reconectando · parcial · bloqueado`, y
  «la ausencia se diseña»); regla del workspace (5 estados de Hurff, WCAG 2.2 AA,
  tokens como fuente única); `brand/brand-system.md` (suizo-modernista,
  editorial, radios 0/4/8/999, verdes Auphere); 003 R12.6 («la pantalla no
  reimplementa páginas de la consola»).
- **Lo que cambia**: la cáscara deja de ser «tres vistas que se turnan» y pasa a
  ser **una aplicación** con un armazón propio; el sistema de tokens gana una capa
  de densidad de escritorio; los topes de plan dejan de explicar y llevan a la
  acción.

## Estado verificado del código (2026-09-17)

| Hallazgo | Dónde |
|---|---|
| Ventana con barra de título del sistema, sin `titleBarStyle`, sin `backgroundColor`, tres `WebContentsView` apiladas | `apps/desktop/src/electron/main.ts:110-141` |
| Consola ↔ pantalla solo por menú Ver (⌘1/⌘2) y un «volver» en la barra | `main.ts:161-177`, `bar-state.ts:177-182` |
| La pantalla de operar no carga fuentes (cae a SF Pro) y no tiene CSP; la consola usa Inter Tight | `packages/ui/src/styles/tokens.css:92-97`, `apps/desktop/src/app/index.html` |
| **Entrar con Google desde la app no tiene disparador**: `signInWithBrowser()` sin llamador | `apps/desktop/src/app-runtime.ts:347-363` (grep sin usos) |
| **Las hojas de la barra caen fuera de sus 44 px** (`overflow:hidden`) | `apps/desktop/src/bar/bar.css:13-16,101-109`, `main.ts:68,77` |
| **Sin red al arrancar, `bootstrap()` aborta** en `loadURL` sin `try` | `main.ts:432-440` |
| **Tras pagar, Stripe vuelve a `/billing/gracias`, que no existe** | `apps/api/src/nexus_api/billing/checkout.py:41` (chip de tarea aparte) |
| Cerrar la ventana cierra la app, la bandeja y los avisos | `main.ts:553` |
| Los topes de plan y de consumo explican sin llevar a la acción | `apps/desktop/src/app/i18n.ts:33,73-86`, `packages/companion-ui/src/messages.ts:540-550` |

## First-Glance Unknowns

1. ¿Existe un kit de UI de escritorio para Electron que valga, o el estándar es
   un sistema propio sobre primitivas? → `research.md` §3.
2. ¿Qué armazón permite **una** navegación con la consola embebida sin darle a la
   consola un canal hacia la cáscara (002 R12.1)? → `concept.md`.
3. ¿La barra de 44 px sobrevive como superficie propia o se absorbe? → `concept.md`.
4. ¿El modo oscuro sigue en verde inmersivo o pasa a tinta con acento verde? →
   `concept.md` (contraste medido en `research.md` §4).
5. ¿Una spec o varias, y qué pasa con los P0 que son fallos de specs anteriores?
