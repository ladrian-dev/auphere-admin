# Decision Gate: los teammates viven en la aplicación de escritorio

- **Slug**: teammates-en-la-app
- **Decided**: 2026-09-10
- **Verdict**: **go**
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: `0` (API de la consola, a través del BFF con
  la sesión de la persona) y `3a` (ejecutar en la máquina, por el puente de 001).
  **No se abre ninguna superficie nueva.** Se abre un renderer propio con IPC,
  que no es superficie de confianza del agente sino de la app.

## Scorecard

| Criterio | Nota | Evidencia |
|---|---|---|
| Demanda | 5/5 | Decisión de Luis; el diseño v3 entero describe esta pantalla; las cinco apps de referencia convergen en el mismo esqueleto (research §4.3) |
| Encaje con lo construido | 5/5 | Loop, eventos, aprobaciones, medidor, puente, ejecutor, identidad: todo se usa, nada se rehace. Se superan dos frases (001-R15.1 / 002-R12.1) |
| Riesgo de aislamiento | 3/5 | Nuevo renderer con IPC; la sesión y la credencial de máquina no pueden llegar a él (M-7). Ambiente del agente: sin cambios |
| Coste | 2/5 | `large`: dos specs, segundo frontend, firma y Windows entran |
| Reversibilidad | 4/5 | El roster y el hilo por teammate son plataforma; si la UI cambiara de forma, la plataforma sigue. El paquete compartido evita la divergencia |
| Licencias | 5/5 | Nada nuevo. KiroCrew (Apache-2.0) aporta patrones, no ficheros, y no entra en esta fase |
| Un solo medidor | 5/5 | El hilo en plataforma lo garantiza sin trabajo; la opción B lo rompía |

## Verdict & Rationale

**Go, con la Opción A.** La evidencia y las respuestas coinciden: el loop en
plataforma es lo que Grok Bot hace con su nube y lo que la 001 ya construyó; la
UI propia es lo que una app Electron debe ser; y el ejecutor local ya viaja
dentro de la app, así que la promesa «el teammate trabaja con los archivos del
partner» se cumple **sin** empaquetar la edición. La edición y su loop local
son la fase siguiente, con receta conocida.

### Las tres decisiones que esta puerta toma

1. **La beta 1 se construye en la app y la consola no tiene teammates.** Se
   enmienda `[[14-mvp-y-fases]]` §2 («dentro de la consola» → «dentro de la
   app») y se superan 001-R15.1 y 002-R12.1: la app tiene una segunda
   superficie propia, grande, y sigue sin duplicar pantallas de la consola.
2. **Las aprobaciones de teammates no caducan solas: la tarea espera.** Enmienda
   acotada de §IV para este tipo de aprobación (T-2). Todo lo demás de §IV
   (durable, idempotente, 409) se conserva.
3. **La política de ejecución local tiene tres capas y gana la más restrictiva**
   (T-4). La lista blanca por cliente no cambia de sitio ni de dueño.

### Supuestos que viajan a la spec para confirmarlos en `/speckit-clarify`

- Crear teammate se hace desde la app (formulario; conversación después).
- Pendientes lista solo lo de los teammates; el Companion web sigue como hoy.
- El techo del administrador vive en la página de equipo de la consola.

## If go — Handoff to `/speckit-specify`

- **Problema**: la app entra, se empareja y ejecuta, pero no tiene dónde operar;
  la pantalla del diseño v3 no existe y la consola no la tendrá.
- **Enfoque elegido**: **Opción A**. Renderer propio (React, `@nexus/ui`,
  `preload` mínimo, IPC enumerado) que pinta roster, hilo, Pendientes, Cuenta y
  Crear teammate; el proceso principal habla con el BFF con la sesión de la
  persona; el hilo corre en plataforma con el eje teammate; la máquina ejecuta
  por el puente de 001 bajo la política de tres capas.
- **En alcance** (spec 003 — *teammates en la aplicación*):
  - Plataforma: tabla de roster por partner (oficio, modelo, política, lista de
    herramientas) con RLS; hilo del Companion con `teammate_id` y
    `principal_id`; catálogo por teammate (M-4); nivel de aviso en la
    aprobación; política local por persona y techo por partner; caducidad
    atada a la tarea (T-2); `/companion/budget` como está.
  - App: tercera vista con `preload`; contrato IPC enumerado y probado (M-7);
    roster / hilo / Pendientes / Cuenta / Crear teammate con los cinco estados
    de Hurff y WCAG 2.2 AA; aviso del sistema operativo; bandeja e instancia
    única; la vista de la consola se conserva para clientes.
  - `packages/companion-ui` extraído del Companion (T-3).
  - Consola: techo del administrador; nada más.
  - Tests de aislamiento: M-4, M-5, M-7, y los de 001/002 en verde.
- **En alcance** (spec 004 — *instalable*): firma y notarización, actualización,
  contención en Windows (001-T039/T043/T057). Condición de M-1.
- **Fuera de alcance**: edición empaquetada y loop local (T-6, fase siguiente);
  VM, 3b, navegador, móvil; rutinas, voz, chat de grupo; correo; rehacer la
  consola; tocar lista blanca, contención o puente.
- **Métricas de éxito**: M-1 a M-8 de `problem.md`.
- **Preguntas que viajan abiertas a la spec**: los tres supuestos de arriba; el
  nombre y forma del `teammate_id` en los eventos de CONTRACT-V2 (¿v3 o
  enmienda?); si el *stream* por IPC reusa `since_seq` tal cual; cuánto del
  `jobList` del diseño es semilla y cuánto es libre.

## Advertencia de método que esta evaluación hereda

«Cobertura por cita no es cobertura por capacidad.» La spec 003 tiene que
declarar cada garantía de aislamiento que toca (renderer nuevo, hilo con dos
ejes, catálogo por teammate) con **su** test, y `tasks.md` es el único plan.

## Enlace de vuelta a la KB (§IX, obligatorio en las dos direcciones)

- `[[14-mvp-y-fases]]` §2: título y §2.2 «la interfaz se hereda» → enmendar:
  la beta 1 vive en la app; el material del Companion se comparte por paquete.
- `[[14-mvp-y-fases]]` §7 decisión 4: «en la beta 1 la app vive dentro de la
  consola» → «la consola vive dentro de la app, para administrar y para
  clientes; los teammates son de la app».
- `[[10-decisiones]]`: nueva decisión 13 (política local en tres capas, la más
  restrictiva gana) y 14 (aprobación de teammate espera a la tarea).
- `[[00-revision-del-diseno-v3]]` §5.1 («no hay pantalla de escritorio») →
  cerrar: la pantalla de escritorio **es** la del diseño.
- `specs/001-puesto-trabajo-partner/spec.md` R15.1 y
  `specs/002-identidad-app-escritorio/spec.md` R12.1: nota «superado por
  specs/003» en la misma línea.
