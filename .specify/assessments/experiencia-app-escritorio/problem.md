# Problem Definition: la experiencia de la aplicación de escritorio

- **Slug**: experiencia-app-escritorio · **Fecha**: 2026-09-17
- **Entrada**: [`intake.md`](./intake.md) · [`research.md`](./research.md)

## Problem Statement

La aplicación de escritorio es la superficie donde el partner **opera el día a
día** con sus teammates (decisión de la evaluación `teammates-en-la-app`). Hoy
funciona por dentro y falla en todo lo que la persona ve y recorre:

1. **No es una aplicación, son tres pegadas.** Consola web, pantalla de operar y
   barra se apilan bajo la barra de título del sistema, con dos tipografías,
   dos sistemas de feedback, dos vocabularios («agentes» / «teammates»,
   «Companion» / teammate) y un cambio entre ellas escondido en el menú (⌘1/⌘2).
2. **Los recorridos básicos no se completan.** Entrar con Google no vuelve;
   emparejar la máquina depende de una hoja que no se ve; sin red al arrancar la
   app se queda colgada; pagar termina en un 404; un hilo que falla se pinta
   vacío (5 P0 verificados en código).
3. **La pantalla explica en vez de llevar.** Cada tope de plan, de consumo o de
   emparejamiento termina en una frase («cambia de plan, en Cuenta»,
   «escríbenos», «se empareja desde la consola») sin un botón que lleve al sitio
   exacto — lo contrario de §V («la ausencia se diseña») y de lo que hacen todas
   las referencias.
4. **Los estados y los avisos no tienen sistema.** Siete mecanismos de feedback
   sin taxonomía, tres contadores de pendientes con tres reglas, siete sitios
   donde una acción falla sin decirlo, y contraste y foco por debajo de WCAG 2.2
   AA en los tokens base.
5. **No hay armazón de escritorio.** Sin barra de título integrada, sin sidebar,
   sin menús completos ni atajos estándar, sin ⌘K, y cerrar la ventana cierra la
   app entera (y con ella los avisos de aprobaciones).

El resultado es que el partner que instala la app **no llega solo al primer
valor**, y el que llega no confía en lo que ve.

## Affected Users & Stakeholders

| Quién | Qué le duele hoy | Qué necesita |
|---|---|---|
| **Persona del partner que opera** (rol con `teammates:use`) | No sabe dónde está (consola o equipo), qué espera de ella ni cuánto le queda; aprueba a ciegas desde Pendientes | Una navegación, pendientes con contexto, consumo visible antes del tope, avisos fiables en segundo plano |
| **Owner / billing del partner** | Contratar o comprar saldo desde la app sale al navegador sin aviso y acaba en 404; Cuenta no dice qué plan tiene | Del tope al plan exacto en un paso, y vuelta a lo que hacía |
| **Owner / admin / builder que pone en marcha** | Emparejar = pedir código en consola (⌘2) + teclear en una hoja invisible; tres instrucciones distintas | Un recorrido guiado de primer arranque con los pasos y su estado |
| **Persona recién invitada o registrada** | Entrar con Google no vuelve; sin partner, bucle `/no-access` | Entrar desde la app y una salida clara si no tiene acceso |
| **Quien usa teclado o lector de pantalla** | La barra no se alcanza; foco 2,09:1; landmarks duplicados | WCAG 2.2 AA real |
| **Equipo de Auphere** (soporte, ventas) | Cada partner nuevo necesita acompañamiento para completar el alta; la app no «vende» el plan | Onboarding autoservicio y paywall que convierte sin dark patterns |

## Goals

1. **G1 — Una aplicación, un armazón.** Barra de título integrada, una sola
   navegación que alcanza tanto operar como administrar, menús y atajos de
   escritorio completos, y cerrar la ventana no detiene los avisos.
2. **G2 — Un sistema visual de escritorio sobre `@nexus/ui`.** Densidad, tipografía
   empaquetada, iconografía, tokens con contraste AA en ambos temas y una sola
   voz entre consola embebida y pantalla local.
3. **G3 — Estados honestos en cada pantalla y en cada turno del agente.** Los siete
   de §V más los propios del agente (enviando, pensando, herramienta, aprobación,
   detenido), con `sin conexión` distinto de `sin sesión`.
4. **G4 — Feedback estandarizado.** Una taxonomía (en línea · banner · toast ·
   diálogo · notificación del sistema · badge · bandeja) con reglas y una sola
   fuente para cada contador.
5. **G5 — Del primer arranque al primer valor sin ayuda.** Entrar (navegador y
   vuelta), emparejar, crear o abrir un teammate y ver su primera respuesta, con
   una checklist de activación visible y permisos pedidos en contexto.
6. **G6 — Llevar a la acción, no explicarla.** Todo tope o ausencia termina en una
   acción con destino exacto (plan, saldo, emparejar, pedir a un rol) y, cuando
   la acción sale al navegador, la app lo dice, espera y vuelve.

## Non-Goals

- **Windows.** El armazón y los tokens se preparan para no cerrarle la puerta,
  pero la build de Windows y su barra de título quedan fuera (`win: null` hoy).
- **Reimplementar pantallas de la consola** en la app (003 R12.6 sigue en pie): la
  consola se integra, no se reescribe.
- **Checkout dentro de la ventana.** Stripe sigue en el navegador del sistema
  (política de ventanas); lo que se diseña es el traspaso y la vuelta.
- **Esquema `auphere://` y enlaces profundos entrantes** (002 R3.5): abrirían
  superficie nueva (§II) sin necesidad para estos objetivos.
- **Nuevas capacidades del agente** (navegador del agente, VM, subagentes): se
  diseñan sus estados si ya existen, no se construyen.
- **Rediseño de la consola web fuera de la ventana**, salvo lo que la integración
  exija (modo embebido) y los tokens compartidos.
- **La página de éxito del checkout** (`/billing/gracias`): defecto de la 005, va
  por el flujo de bugs (tarea aparte ya abierta).
- **Tours guiados** y cambios de precios o planes.

## Success Metrics

| Métrica | Hoy | Objetivo | Cómo se mide |
|---|---|---|---|
| Persona nueva: de app instalada a primera respuesta de un teammate, sin ayuda | No se completa (P0-1, P0-2) | **≤10 min**, saliendo de la app solo para entrar y, si aplica, pagar | Recorrido cronometrado con cuenta nueva (quickstart) |
| Estados sin salida (vacío, error, bloqueado, tope, sin sesión, sin conexión) que no ofrecen ninguna acción | ≥12 (anexo 04 §2–§3) | **0** | Inventario de estados por pantalla, revisado en `/speckit-analyze` y test por estado |
| Acciones que fallan o salen de la app sin decirlo | 7 | **0** | Inventario de feedback + tests |
| Superficies que cuentan «pendientes» con reglas distintas | 3 | **1 derivado** usado por sidebar, Dock y bandeja | Test de un solo derivado |
| Violaciones axe *serious/critical* por pantalla | Sin medir; foco 2,09:1, pares a 1,24:1 | **0**; foco y todo texto **≥3:1 / ≥4,5:1 en ambos temas** | `@axe-core/playwright` + test de contraste de tokens |
| Destello blanco al arrancar / tiempo a primera pintura útil | Ventana blanca; esqueletos hasta cargar la consola remota | **Sin destello**; armazón pintado **<1 s** sin depender de la red | Humo E2E empaquetado |
| Tipografías distintas en la misma ventana | 2 (SF Pro + Inter Tight) | **1 familia** de marca + mono | Test de `font-family` computado |
| Recorridos de tope que llevan a la acción con destino exacto | 0 de 5 | **5 de 5** | Test por caso (sin plan, plan lleno, pool sin saldo, pago fallido, versión no admitida) |

## Cost of Inaction

- **La app no se puede autoservir**: cada alta nueva necesita a alguien de Auphere
  al lado (entrar con Google y emparejar no se completan solos). Con el registro
  autónomo de la 006 ya en producción, eso anula su propósito.
- **Monetización bloqueada por fricción**: el único camino a pagar desde la app
  termina en 404 y ninguna pantalla lleva al plan.
- **Confianza**: una pantalla que dice «vacío» cuando falló, «cerrar sesión» que
  no cierra, o un contador distinto en cada sitio erosiona justo lo que §IV y §V
  protegen — que la persona sepa qué aprueba y qué está pasando.
- **Deuda que crece**: cada spec nueva (VM, navegador del agente) añadiría
  pantallas a un armazón que no existe, multiplicando el rediseño posterior.

## Open Questions

Las cuatro decisiones de `concept.md` (armazón, barra, modo oscuro, corte) son de
Luis; el resto de decisiones transversales se proponen con recomendación.
