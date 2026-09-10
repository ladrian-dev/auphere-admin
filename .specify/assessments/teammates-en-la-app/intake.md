# Idea Intake: los teammates viven en la aplicación de escritorio, no en la consola

- **Slug**: teammates-en-la-app
- **Created**: 2026-09-10
- **Source**: pasted text (Luis, en la sesión que cerró la spec 002) · puntero al
  repositorio: `apps/desktop` (la cáscara y la barra), `apps/console`
  (`components/companion/`, 44 archivos), `apps/edition` (la edición sobre
  KiroCrew) · KB: `[[14-mvp-y-fases]]` §2 (beta 1 «el equipo, dentro de la
  consola»), `[[10-decisiones]]` decisiones 4, 9 y 11, `[[00-revision-del-diseno-v3]]`
- **Type**: new-capability

## Idea (as captured)

> Los teammates no van en la consola; en el diseño dice web, pero para que un
> teammate trabaje correctamente debe tener acceso a los archivos que el partner
> le dé acceso en el computador, y luego agregaremos la VM y así… La consola debe
> ser para configurar, administrar, etc. Y la app es para operar en el día a día.

Dicho al ver la aplicación de escritorio recién emparejada (spec 002): dentro
de la ventana solo se ve la consola, y ni el roster ni los hilos del diseño v3
existen en ningún sitio todavía.

## Restated

El plan de la KB puso la beta 1 —roster de teammates, hilo privado por persona,
Pendientes— **dentro de la consola web**. Luis corrige el lugar: la superficie
donde se **opera** con los teammates es la aplicación de escritorio, porque el
trabajo de un teammate necesita los archivos de la máquina del partner (y después
la VM); la consola queda para **configurar y administrar**. La evaluación decide
qué implica ese cambio de lugar: qué se construye en la app, qué se queda en la
consola, y qué del plan de la beta 1 sigue valiendo tal cual.

## Origin & Context

- **Raised by**: Luis, 2026-09-10.
- **Trigger**: el cierre de la spec 002. Con la máquina emparejada, la app se ve
  como «solo la consola»; el diseño v3 (roster, hilo, Pendientes, Cuenta, Crear
  teammate) no está construido, y la KB lo tenía asignado a la consola.
- **Lo que ya decía la KB y encaja**: decisión 4 (*«¿Reemplaza la consola? No. La
  app es el día a día; la consola tiene más información, configuración y
  facturación»*) y decisión 2 (*«solo el partner usa la app»*). Esta idea no las
  contradice: las lleva a su consecuencia.
- **Lo que cambia**: `[[14-mvp-y-fases]]` §2 («Beta 1 — el equipo, dentro de la
  consola») y su frase *«la interfaz se hereda: los 44 archivos del Companion son
  la pantalla de la beta 1; lo que se añade es el roster en el lateral»*. Si el
  operar es en la app, la pantalla de los teammates es de la app.

## Estado verificado del código (2026-09-10)

| Hallazgo | Dónde |
|---|---|
| La app carga la consola en una vista **sin `preload`** y tiene una sola superficie propia, la barra (spec 002, R12.1, R3.5). Construir la UI de teammates en la app es abrir una superficie propia **grande** donde la 002 decidió abrir una mínima | `apps/desktop/src/electron/main.ts`, `contracts/desktop-bar.md` |
| Los 44 componentes del Companion —hilo, línea de tiempo, tarjeta de confirmación, medidores, composer— viven en la consola (Next.js) | `apps/console/src/components/companion/` |
| La edición sobre KiroCrew corre en la máquina y ya ejecuta con lista blanca, contención y aprobaciones (spec 001); su dashboard y navegador son **inalcanzables** a propósito (001-R13.1) | `apps/edition/`, `specs/001-puesto-trabajo-partner/` |
| La cola global de aprobaciones del gateway ya la contesta la app (001-T069) | `apps/desktop/src/approvals-client.ts` |
| Los hilos del Companion tienen RLS por persona (decisión 9), y las máquinas también desde la 002 | `alembic/versions/0090_companion.py`, `0107_device_owner_and_pairing.py` |
| La app no instala ni arranca la edición: asume un gateway en `localhost:5476` | `apps/desktop/src/electron/main.ts` |

## First-Glance Unknowns

- [NEEDS CLARIFICATION: **¿qué es «operar» en la app y qué es «administrar» en la
  consola?** La línea hay que escribirla: ¿el roster, los hilos y Pendientes en la
  app; clientes, canales, ejecutables, equipo, claves, facturación y consumo en la
  consola? ¿Crear un teammate es operar o administrar?]
- [NEEDS CLARIFICATION: **¿la UI de teammates se construye dentro de la cáscara
  (React en una vista propia) o es una web de la plataforma que la app carga?**
  Decide si se rompe R12.1 («una sola superficie propia») o se conserva cargando
  otra web con la misma disciplina que la consola. Y decide si los 44 componentes
  del Companion se reutilizan o se reescriben.]
- [NEEDS CLARIFICATION: **¿el hilo corre contra la plataforma o contra la edición
  local?** El teammate que toca archivos ejecuta en la máquina (edición); el hilo,
  las aprobaciones durables y el medidor viven en la plataforma. Qué proceso
  sostiene la conversación, y qué pasa cuando la máquina no está.]
- [NEEDS CLARIFICATION: **¿qué pasa con las betas 3 y 4 (móvil y navegador)?** El
  diseño prometía «el mismo hilo en web, escritorio y iPhone». Si el hilo es de la
  app, ¿el móvil ve el mismo hilo, o solo aprueba?]
- [NEEDS CLARIFICATION: **la edición no viene con la app.** ¿Se empaqueta e
  instala con ella (Python 3.12 + rueda del sustrato) o se instala aparte? Es
  condición para que «el teammate trabaje con los archivos del partner» sea cierto
  en una máquina que solo instaló la app.]
- [NEEDS CLARIFICATION: **qué del plan de la beta 1 sigue igual**: roster por
  partner, hilo privado por persona, tarea ≠ turno, loop largo, `run_subagent`,
  estados honestos, empuje de aprobación, tope por tarea (`[[14-mvp-y-fases]]`
  §2.2). Casi todo es plataforma y no depende del lugar de la pantalla; hay que
  decir cuál sí.]

## Restricciones heredadas que esta evaluación no reabre

- 001-R15.3 / 002-R14: la sesión de la persona no es alcanzable desde el ambiente
  del agente, y la consola no tiene canal con la cáscara.
- 001-R13.1: el dashboard y el navegador del sustrato siguen inalcanzables. Los
  teammates se muestran con **nuestra** pantalla, no con la de KiroCrew.
- Decisión 9: hilo privado por persona. Decisión 11: todos aprueban en el chat que
  están teniendo.
- §III: lo que un teammate lee en los archivos es dato, nunca instrucción.
- Un solo medidor.

## Lo que esta evaluación declara fuera desde el minuto uno

- La VM compartida (beta 5) y el control del escritorio (`3b`): se nombran como
  destino, no se diseñan aquí.
- Rehacer la consola: sigue siendo la de hoy, para configurar y administrar.
