# Problem Definition: los teammates viven en la aplicación de escritorio

- **Slug**: teammates-en-la-app
- **Created**: 2026-09-10
- **Inputs used**: [`intake.md`](./intake.md) · [`research.md`](./research.md) ·
  respuestas de Luis del 2026-09-10 a las ocho preguntas del research §7

## Las ocho respuestas, traducidas

| # | Pregunta del research | Respuesta de Luis | Qué fija |
|---|---|---|---|
| 1 | ¿Dónde corre el hilo? | «Como lo hace Grok» | Grok Bot corre el loop en su nube y la máquina local es un ejecutor opcional bajo permiso (research §4.1). **El hilo corre en plataforma; la máquina ejecuta.** Es lo que la 001 ya construyó |
| 2 | ¿UI en la cáscara o web cargada? | «Es una app de escritorio hecha con Electron; debe seguir sus buenas prácticas» | **UI propia dentro de la app** (renderer con `preload` e IPC, sin credenciales en el renderer). Es lo que hacen Grok Bot y la app de Claude |
| 3 | ¿Móvil y web? | «La consola no tendrá teammates aún; cuando haya app móvil se conectará con la de escritorio» | **Solo la app** en esta fase. El móvil no entra; se deja la puerta (el hilo está en plataforma, así que podrá verlo) |
| 4 | ¿Aprobación con la app cerrada? | «Buenas prácticas de Claude, OpenAI, Grok; correo no» | **Estado honesto «esperándote»**: la tarea se pausa, la aprobación no caduca mientras la tarea viva, aviso del sistema operativo cuando la app está abierta, bandeja al volver. Sin correo |
| 5 | ¿La edición empaquetada? | «Si como lo hace Grok funciona y escala, usémoslo» | **Empaquetada y supervisada por la app** cuando haga falta. Y un hallazgo: **no hace falta para esta fase** (§Problem Statement) |
| 6 | ¿Crear teammate es operar? | «No sé a qué te refieres» | Reformulado: *¿un teammate nuevo se crea desde la app?* Como los teammates solo existen en la app, **se asume que sí**. A confirmar en `decision.md` |
| 7 | ¿Las aprobaciones del Companion web cuentan como Pendientes? | «Tampoco sé a qué te refieres» | Reformulado: *el Companion de la consola web hoy pide aprobaciones dentro de su chat; ¿la bandeja Pendientes de la app las muestra también?* **Se asume que no**: Pendientes muestra lo que los **teammates** esperan de la persona; el Companion web sigue como hoy. A confirmar |
| 8 | ¿Política de ejecución local? | «Como Grok Bot» | **Por persona: preguntar siempre / permitir siempre / nunca**, con techo del administrador desde la consola, **encima** de la lista blanca por cliente (que no se toca) |

## Problem Statement

El partner tiene hoy una aplicación que **entra, se empareja y ejecuta** (specs
001 y 002), pero no tiene dónde **operar**: la ventana muestra la consola, y la
consola es el sitio de administrar. El diseño v3 describe la pantalla de operar
—roster de teammates, hilo privado por persona, Pendientes, Cuenta, Crear
teammate— y la KB la había asignado a la consola web (`[[14-mvp-y-fases]]`
§2). Luis la reasigna a la app, y la consola **no tendrá teammates**.

El problema es construir esa pantalla **como app de escritorio** —no como web
dentro de una ventana— sobre lo que ya existe: el loop del Companion en
plataforma (hilo, eventos, aprobaciones durables, medidor), el puente y el
ejecutor local con lista blanca y contención (001, `apps/desktop/src/{executor,
containment, local-runner}.ts`), y la identidad de persona y de máquina (002).

**Un hallazgo del research que simplifica el problema**: con el hilo en
plataforma (respuesta 1), el ejecutor local que da acceso a los archivos **ya
está dentro de la app** —es TypeScript empaquetado con ella, no la edición—.
La edición (KiroCrew) sostiene el *loop local* y sus subagentes, que esta fase no
usa. Empaquetarla (respuesta 5) deja de ser condición de la beta y pasa a ser
la siguiente fase. — [research §5.5, `apps/desktop/src/local-runner.ts`]

## Affected Users & Stakeholders

- **La persona del partner que opera** (decisión 2). Necesita hablar con su
  equipo, encargar trabajo que sobreviva a cerrar la app, aprobar lo que espera,
  ver cuánto consumo queda, y dar acceso a carpetas concretas. Hoy no tiene
  nada de eso.
- **La persona que administra** (owner/admin). Sigue en la consola: membresías,
  clientes, canales, lista blanca de ejecutables, emparejamiento, y **nuevo**:
  el techo de la política de ejecución local del equipo.
- **Auphere como operador**. Gana una superficie más que mantener (app + consola)
  y hereda de 001 dos deudas que esta fase convierte en obligación: firma y
  actualización (001-T057) y la contención en Windows (001-T039/T043).
- **Auphere como responsable de seguridad**. La app abre un renderer con IPC.
  Cada canal IPC es superficie; la sesión de la persona y la credencial de
  máquina **no** pueden llegar al renderer, y el ambiente del agente sigue sin
  alcanzar la sesión (001-R15.3 / 002-R14).
- **El cliente final**. No participa, no tiene app, y lo que sus datos aportan
  al hilo de un teammate es dato, nunca instrucción (§III).

## Goals

- **G-1 · La app es la pantalla de operar.** Roster, hilo por teammate y por
  persona, Pendientes, Cuenta (uso) y Crear teammate, con la forma del diseño
  v3 (tres columnas) y el nivel del sistema de diseño (WCAG 2.2 AA, tokens,
  cinco estados de Hurff en cada componente).
- **G-2 · El hilo corre en plataforma, la máquina ejecuta.** El trabajo
  sobrevive a cerrar la app; lo que toca archivos pasa por el puente, el
  `workdir` del cliente, la lista blanca y la contención de 001. Un solo loop,
  un solo medidor.
- **G-3 · Roster por partner con oficio, modelo y política**, y hilo privado por
  persona (decisiones 7–11). Un teammate de finanzas no ve las herramientas de
  desarrollo — comprobado en el catálogo que recibe el modelo.
- **G-4 · Pendientes es honesto.** Lo que un teammate espera de la persona se ve
  en una bandeja con nivel (Crítico / Aviso / Informativo); con la app abierta
  avisa el sistema operativo; con la app cerrada la tarea espera («esperándote»)
  y no caduca sola. Aprobar en un sitio hace desaparecer la tarjeta en el otro.
- **G-5 · Política de ejecución local como Grok Bot.** Por persona:
  *preguntar siempre / permitir siempre / nunca*; techo del administrador desde
  la consola; por defecto *preguntar*; la regla más restrictiva gana; la
  tarjeta enseña el comando exacto. Encima de la lista blanca, nunca en su lugar.
- **G-6 · El consumo se ve en la app** con el mismo medidor que la consola y
  con el mismo número. Los teammates gastan el consumo de la membresía.
- **G-7 · Electron como se debe.** Renderer sin Node, `contextIsolation`,
  `preload` mínimo, IPC tipado y enumerado, credenciales solo en el proceso
  principal, bandeja del sistema, una sola instancia, ventana que recuerda su
  sitio, actualización firmada.
- **G-8 · Puerta abierta al móvil.** Nada de lo que se construya impide que
  otra pantalla pinte el mismo hilo o apruebe lo mismo; nada lo construye
  todavía.

## Non-Goals

- **Empaquetar la edición y el loop local del sustrato** (subagentes,
  `session-control`, `select_crew`, TaskRunner). Siguiente fase, con la receta
  de KiroCrew (`backend-dist` + CPython 3.12 *standalone* por arquitectura +
  `gateway-supervisor`) ya localizada en el research §3.1.
- **La VM (beta 5), el control del escritorio (3b, beta 6), el navegador
  embebido (beta 4), la app móvil (beta 3).**
- **Rutinas, voz, chat de grupo, agente↔agente** por el consumer secuencial
  (`[[14-mvp-y-fases]]` §2.4). El handoff del diseño se pinta como nota de hilo
  cuando exista `run_subagent`; no como chat de grupo.
- **Aviso por correo.** Descartado por Luis.
- **Teammates en la consola web, o rehacer la consola.** La consola administra.
- **Cambiar la lista blanca, la contención o el puente** de 001/002. Se usan.
- **Precio y facturación.** Solo lo que se *ve*.

## Success Metrics

- **M-1 · Instalación limpia → primera tarea con archivos**: en una máquina sin
  nada instalado, la persona instala la app, entra, se empareja, declara una
  carpeta y un teammate lee y escribe dentro de ella. **Cero instalaciones
  adicionales.** (Hoy: cierto solo hasta «declara una carpeta».)
- **M-2 · La tarea sobrevive a la app**: encargar, cerrar la app, volver, y la
  tarea siguió y terminó o está «esperándote». 100 % de las tareas.
- **M-3 · Una aprobación, una tarjeta**: aprobar en la app hace desaparecer la
  tarjeta en cualquier otra vista abierta sin recargar (< 2 s).
- **M-4 · Catálogo por teammate**: el teammate sin permiso **no recibe** la
  herramienta — se comprueba en el catálogo que ve el modelo, no en la UI. Test
  de aislamiento, no demo.
- **M-5 · Hilo privado**: dos personas del mismo partner con el mismo teammate;
  ninguna ve el hilo de la otra. Test de aislamiento.
- **M-6 · Un solo número de consumo** en app y consola. Exactamente un medidor.
- **M-7 · Cero credenciales en el renderer**: ningún canal IPC devuelve sesión,
  cookie ni token; test que enumera los canales y sus formas.
- **M-8 · Cualitativa**: una persona ajena al equipo abre la app y en cinco
  minutos ha encargado algo, ha aprobado algo y sabe cuánto le queda — sin que
  nadie le explique nada.

## Cost of Inaction

La app queda como «la consola en una ventana con una barra»: cuesta lo que
cuesta mantener Electron y no devuelve nada que el navegador no dé. El diseño
v3 sigue sin construirse y la promesa de `[[07-competencia]]` («termina la tarea
mientras te vas a por un café») la cumplen hoy Grok Bot, Cowork y Codex con el
mismo esqueleto (research §4.3). Y la deuda técnica de tener el Companion como
*drawer* en la consola crece cada semana que se le añade algo pensando que es
la pantalla de la beta 1.

## Open Questions

- [NEEDS CLARIFICATION: **confirmar la reformulación de la 6**: el teammate se
  crea desde la app (formulario primero; conversación después, decisión 7).]
- [NEEDS CLARIFICATION: **confirmar la reformulación de la 7**: Pendientes
  muestra solo lo de los teammates; el Companion de la consola web sigue
  aprobando dentro de su chat, como hoy.]
- [NEEDS CLARIFICATION: **el techo del administrador** (G-5): ¿en la página de
  equipo, en la de puesto de trabajo (`/workstation`), o por cliente?]
