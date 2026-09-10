# Concept Exploration: los teammates viven en la aplicación de escritorio

- **Slug**: teammates-en-la-app
- **Created**: 2026-09-10
- **Recommended option**: **Opción A — la app como cliente de la plataforma, y
  la máquina como ejecutor.** La decisión formal es de `decision.md`.
- **Etapas anteriores**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md)

## Los dos ejes, ya fijados por Luis

Las respuestas 1 y 2 cierran los dos ejes que separaban opciones en el research:
el hilo corre **en plataforma** (como la nube de Grok Bot) y la UI es **propia de
la app** (Electron bien hecho). Lo que queda por elegir es **cuánto sustrato se
mete en esta fase** y **cómo se estructura la app** para que el renderer nunca
tenga una credencial.

## Options

### Option A — La app como cliente de la plataforma; la máquina como ejecutor

- **Sketch**: una tercera vista en la ventana (`WebContentsView` con `preload`,
  partición propia `auphere-app`, sin Node, `contextIsolation`), que pinta el
  diseño v3 en React con `@nexus/ui`. El renderer no tiene credenciales: pide
  por IPC y el **proceso principal** llama al BFF de la consola con la sesión de
  la persona (`session.fromPartition('persist:auphere-console').fetch`, el mismo
  camino que hoy usa `consoleWhoami`) y reenvía el *stream* de eventos por
  `webContents.send`. La plataforma gana el eje **teammate**: tabla de roster por
  partner (oficio, modelo, política, lista de herramientas) y hilo del Companion
  con `teammate_id` + `principal_id`. Pendientes es la API de aprobaciones con
  nivel; Cuenta es `/companion/budget` con la misma cifra que la consola. La
  ejecución local sigue por el puente de 001 (`/device/poll` → `local-runner`),
  con la política *preguntar / siempre / nunca* por persona guardada en
  plataforma y el techo del administrador en la consola. La vista de la
  consola se conserva para operar clientes.
- **Appetite**: `large` — dos specs. Una de **plataforma + app** (roster, hilo por
  teammate, política local, Pendientes, Cuenta, Crear teammate, renderer e IPC)
  y otra de **empaquetado**: firma, actualización y Windows, que la 001 dejó y
  esta opción convierte en obligación (M-1). Ocho a diez semanas de trabajo real.
- **Trade-offs**:
  - (+) Un solo loop, un solo medidor, el móvil podrá pintar el mismo hilo (G-8).
  - (+) Reutiliza el 90 % de lo construido: Companion (44 archivos, portables
    salvo el *drawer*), aprobaciones durables, eventos con `seq`, puente,
    ejecutor con contención, identidad.
  - (+) Es literalmente el reparto de Grok Bot: coordinador (nuestro puente) +
    ejecutor local (nuestro `local-runner`) + UI; sin su nube porque nuestra
    «nube» es la plataforma.
  - (−) Segundo frontend. Se paga con un paquete compartido de componentes
    (`packages/companion-ui`, extraído de `apps/console/src/components/companion`)
    para que consola y app no diverjan; la barra ya enseñó que copiar tokens a
    mano se rompe.
  - (−) Cada canal IPC es superficie. Se paga con un contrato enumerado y un
    test que lo recorre (M-7), como `test_device_bridge_inbound` recorre el puente.
  - (−) El *stream* pasa por el proceso principal. Es un salto más; Grok Bot y
    la app de Claude hacen exactamente esto (el renderer no habla con la red
    con credenciales).
- **Rabbit holes**:
  - Reescribir el Companion en vez de portarlo. La forma cambia (tres columnas);
    los componentes no.
  - Querer los subagentes del sustrato «ya que estamos». Son la fase siguiente
    y exigen la edición empaquetada.
  - Hacer del techo del administrador un sistema de permisos. Es un enum de
    tres valores por partner que acota el enum de tres valores por persona.
  - Notificaciones nativas con acciones («Aprobar» desde el aviso). Primero
    el aviso que abre la app en la tarjeta; las acciones después.

### Option B — El hilo en la edición (el daemon de Grok Bot, invertido)

- **Sketch**: la app arranca y supervisa la edición (patrón `gateway-supervisor`),
  el hilo del teammate corre en el harness local con sus subagentes, `members.py`
  y `select_crew`; la plataforma recibe eventos y audita.
- **Appetite**: `large`, y con la edición empaquetada como condición de arranque.
- **Trade-offs**: (+) acceso a ficheros y subagentes nativos del sustrato;
  (−) el modelo se factura fuera del medidor salvo enrutar (research §5.3);
  (−) el hilo vive en la máquina: sin ella no hay hilo ni móvil; (−) contradice
  la respuesta 1 y el reparto que Grok Bot mismo eligió («nube primero, local
  opcional»).
- **Rabbit holes**: `--strict-mcp-config` sin verificar; techos de recursos
  fuera de Linux; procesos que sobreviven al turno (research de KiroCrew).

### Option C — Una web de la plataforma cargada en la app

- **Sketch**: la pantalla de teammates es otra ruta de la consola (o una web
  aparte) cargada en la partición de la persona; cero IPC nuevo.
- **Appetite**: `medium`.
- **Trade-offs**: (+) un solo frontend; (−) no es una app de escritorio: sin
  bandeja, sin avisos nativos, sin acceso al ejecutor local salvo por el puente,
  y la consola «no tendrá teammates» — tenerlos en una ruta suya oculta es
  tenerlos. Descartada por la respuesta 2.

### Option D — Seguir con la consola en la ventana

- **Appetite**: `zero`. Es el coste de inacción de `problem.md`.

## Decisiones transversales — no son opciones, hay que tomarlas igual

### T-1 · Dónde vive el roster
En plataforma, tabla por partner con RLS, y **el hilo del Companion gana
`teammate_id`**. La *crew* de KiroCrew queda como espejo para la fase de loop
local, no como fuente. Alternativa (roster en la máquina) rompe G-8 y M-5.

### T-2 · Qué hace una aprobación cuando nadie la ve
**La tarea se pausa y la aprobación espera.** Hoy §IV caduca las aprobaciones;
para las de teammates la caducidad se ata a la vida de la *tarea* (tope por
tarea de `[[14-mvp-y-fases]]` §2.2 fila 10), no a un reloj propio. El estado del
hilo es `esperándote`, honesto (§V), y Pendientes lo lista con su nivel. Al
abrir la app: aviso del sistema operativo si hay algo Crítico. Sin correo.

### T-3 · El Companion como paquete compartido
Extraer `components/companion/` a `packages/companion-ui` (React + tokens, sin
`next`), consumido por consola y app. Los dos archivos que importan `next`
(`companion-launcher`, `trial-panel`) se quedan en la consola. Alternativa
(copiar) es más rápida esta semana y más cara todas las demás.

### T-4 · La política local, tres capas y una regla
Lista blanca por cliente (consola, no se toca) → techo por partner (consola,
admin) → preferencia por persona (app: *preguntar / siempre / nunca*, por
defecto *preguntar*). **La más restrictiva gana**, como en Grok Bot. La tarjeta
enseña ejecutable, argumentos y directorio.

### T-5 · Firma, actualización y Windows entran
M-1 exige instalar en una máquina limpia. Eso convierte 001-T057 (firma) y
001-T039/T043 (contención Windows) en tareas de esta fase, no en deuda.

### T-6 · La edición, después, con la receta de KiroCrew
Cuando entre el loop local: `backend-dist/<arch>/` con CPython 3.12
*python-build-standalone*, `bundle-integrity` y `gateway-supervisor` (research
§3.1). Se anota aquí para que nadie lo decida otra vez.
