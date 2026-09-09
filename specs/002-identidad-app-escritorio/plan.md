# Implementation Plan: la identidad y el puesto de trabajo en la aplicación de escritorio

**Branch**: `002-identidad-app-escritorio` | **Date**: 2026-09-09 | **Spec**: [`spec.md`](./spec.md)

**Input**: Feature specification from `/specs/002-identidad-app-escritorio/spec.md`

## Summary

La persona entra en la consola dentro de la ventana —como hoy—, pide emparejar su
máquina, la consola le muestra **un código de un solo uso** y la única superficie
propia de la aplicación —**la barra del puesto**— lo canjea por una credencial de
dispositivo que vive cifrada con el llavero del sistema. A partir de ahí la
máquina **pertenece al partner y a la persona que la emparejó**, sirve a los
clientes que se elijan en la consola, declara el directorio de cada uno con el
selector nativo, renueva su credencial sola mientras late, se detiene al cerrar
sesión y se archiva —nunca se borra— desde la barra o desde la consola.

**El canal entre la consola y la cáscara es la persona.** No hay `preload` en la
vista de la consola, ni puente de contexto, ni esquema de URL. La barra es una
vista aparte, con su propia partición y su propio `preload` mínimo, y la consola
no la conoce.

**Una apuesta va al principio, no al final.** El Requisito 4 cambia el dueño de
`partner_devices` y enmienda el 001-R6.3; sus tests de aislamiento (`test_30`) y la
migración `0107` son las primeras tareas. Nada de pantalla se construye encima
hasta que estén en verde.

## Technical Context

**Language/Version**: Python **3.11** en `apps/api` (sin cambio) · TypeScript sobre
**Electron 44.3.0** en `apps/desktop` (`BaseWindow` + `WebContentsView` +
`safeStorage`, todo de serie) · Next.js 16 en `apps/console`

**Primary Dependencies**: **ninguna nueva.** `pyjwt` (HS256 de la credencial),
FastAPI, SQLAlchemy y Alembic ya están; en escritorio, todo lo que hace falta lo
trae Electron 44; en la consola, `@nexus/ui` y `lucide-react` ya están

**Storage**: Postgres con RLS forzada. Migración **`0107`**: `partner_devices`
cambia de dueño (tenant → partner), aparecen `device_client_links` y
`device_pairing_codes`. Redis para el límite de intentos del canje. En la máquina,
`safeStorage` de Electron para la credencial

**Testing**: `pytest` (`tests/isolation/` bloqueante — `test_30` nuevo, `test_28`
y `test_29` reescritos) · `vitest` en `apps/desktop` y `apps/console` · auditorías
`a11y-audit` y `responsive-audit` sobre la barra y `/workstation`

**Target Platform**: máquina del partner **macOS** (Windows sigue fuera hasta que
la contención esté portada) · plano de control en Linux

**Project Type**: aplicación de escritorio + servicio backend + consola web, los
tres ya existentes

**Constraints**: cero credencial de backend en disco (15.2) · el puente sigue
siendo saliente (6.1) · la credencial autoriza **cinco** operaciones y ninguna más
(R4.2) · un solo contador de consumo (R9) · la consola reconoce a la cáscara en
**un** sitio (R12.7)

**Scale/Scope**: un partner con varias personas y varios clientes; una máquina por
persona y por ordenador; decenas de máquinas por partner, no miles

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y vuelta a comprobar tras el diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ **de frente** | `partner_devices` pasa a RLS **por partner y por persona** (dos políticas, fail-closed sin GUC). Los vínculos máquina↔cliente van por tenant (`test_21` los cubre solos). El tenant de un trabajo o de un directorio sale de la firma del partner + `partner_tenants`, **nunca** del cuerpo: el dispositivo nombra un `client_ref` y la plataforma lo resuelve dentro de su partner. Tests: `test_30_device_partner_scope.py` (nuevo), `test_28` y `test_29` reescritos |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0` + tramo de `3a`, declarado en la spec. Se rechazaron con motivo el puente de contexto y el esquema de URL. La barra **no** es superficie nueva: es UI de la propia cáscara, en su partición, sin acceso a la consola |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | Nada de esta spec lee contenido externo. El código de emparejamiento y el nombre de máquina son entradas de la persona y se validan como tal. La vista de la consola sigue **sin `preload`**: una página no puede hablarle al proceso principal |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Emparejar, desemparejar y archivar no son acciones de agente: las hace una persona y quedan en `audit_log` con su `actor`. La renovación la firma la máquina y así se anota (R13.1). Ninguna aprobación durable se consume |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | La barra tiene **siete estados** nombrados (R12.2) y ninguno con tono de error; los ejecutables ausentes se **piden** («Pedirla»); sin máquina no hay control apagado. La lista de puesta en marcha se calcula desde la plataforma en cada visita (R6.2) |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | El agente no interviene. La cáscara lee la identidad de la persona por un endpoint del BFF con la cookie de la partición humana **desde el proceso principal**; el ambiente del agente no tiene esa partición ni ese proceso (D6) |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS tiene test nombrado en [`research.md`](./research.md) §Mapa de tests. La revocación —que hoy no funciona— nace como test en rojo en `test_30` |
| VIII | Licencias leídas enteras; AGPL no | ☑ | **Cero dependencias nuevas** en los tres paquetes (D12). Si una tarea quisiera añadir una, para y declara |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | La spec cita `[[14-mvp-y-fases]]` §3 y `[[10-decisiones]]` 2, 9 y §2.3 (cerrada hoy con enlace a esta carpeta). Falta el enlace de vuelta desde `[[14-mvp-y-fases]]` §3 — va como tarea |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **1** (RLS: la máquina cambia de dueño y se lee por persona) · **2** (whitelist: una máquina del partner ejecuta con la lista del cliente vinculado y no alcanza la de otro) · **6** (log: emparejar/renovar/desemparejar/archivar etiquetados por partner y persona) | `test_30_device_partner_scope.py` · `test_28` reescrito · `test_27` ampliado con los cinco actos de identidad |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna.** Electron 44 trae `BaseWindow`, `WebContentsView` y `safeStorage`; `pyjwt` ya firma la credencial | Tarea de verificación: `pnpm ls --depth 0` y `uv lock --check` sin cambios |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada.** Ninguno de los cinco actos consume modelo, reloj ni herramienta (R9.2). El consumo sigue en `/usage` | Tarea de no-regresión: test que afirma que emparejar/renovar/archivar no crean asiento en `usage_ledger` |

**Ninguna fila en rojo.**

## Constitution Check — vuelta a comprobar tras el diseño

Tres cosas cambiaron de promesa a sitio concreto, y una obligó a enmendar la spec:

- **§I** — la resolución de tenant desde `client_ref` dentro del partner (D4) es
  la misma forma que `/console/clients/{ref}`: el llamante nombra, la plataforma
  resuelve bajo RLS de partner. La política **por persona** en `partner_devices`
  usa dos políticas OR (dueña · gestor) con un GUC nuevo `app.workstation_manager`
  que solo fija la dependencia de consola cuando el rol tiene `workstation:write`.
  Es el patrón del Companion con una política más, no otro patrón — y va a
  Complexity Tracking porque es un GUC que no existía.
- **R4.2 de la spec: cuatro → cinco operaciones.** El diseño hizo visible que
  declarar el directorio desde la máquina (R7) **es** una operación del
  dispositivo. Esconderla dentro de otra habría sido mentir sobre lo que la
  credencial abre. La spec queda enmendada con el motivo escrito.
- **§VI / 15.3** — la cáscara lee «quién está dentro» por `GET /api/session/whoami`
  del BFF, con la cookie de la partición humana, **desde el proceso principal**
  (D6). Ni la página de la consola ni el ambiente del agente participan. El test
  `session-isolation` gana una afirmación: la vista de la consola no tiene
  `preload` y la partición de la barra no es ninguna de las otras dos.
- **§V** — el estado `hay que volver a emparejar` y `archivada desde la consola`
  necesitan que la plataforma **distinga** al rechazar: `403 device_archived` y
  `403 pairing_required` frente al `401` opaco de un token inválido. Decirle a
  quien tenía una credencial válida por qué dejó de valer no es una fuga: es §V.

## Project Structure

### Documentation (this feature)

```text
specs/002-identidad-app-escritorio/
├── plan.md              # este fichero
├── research.md          # Fase 0 — decisiones D1..D14 y mapa de tests
├── data-model.md        # Fase 1 — migración 0107
├── quickstart.md        # Fase 1 — recorrido de validación de punta a punta
├── contracts/
│   ├── pairing.md       # el código y su canje
│   ├── device-bridge-v2.md   # las cinco operaciones de la credencial
│   ├── console-workstation.md # la API de consola a nivel de partner
│   └── desktop-bar.md   # la barra: estados, preload mínimo, almacén
└── tasks.md             # lo produce /speckit-tasks
```

### Source Code (repository root)

```text
apps/
  api/
    alembic/versions/0107_device_owner_and_pairing.py   # partner_devices → partner; links; códigos
    src/nexus_api/
      db/models/local_workstation.py       # PartnerDevice (partner_id, generation, hostname), DeviceClientLink, DevicePairingCode
      repositories/local_workstation.py    # repos por partner+persona; links por tenant; códigos
      services/device_credential.py        # claims v2 {sub, pid, gen}; renovación; motivos de rechazo
      services/device_pairing.py           # NUEVO — emitir código, canjear, límite de intentos
      services/device_presence.py          # presencia por tenant a través de los vínculos
      api/device_bridge.py                 # pair · heartbeat · poll · result · renew · links
      api/console/workstation.py           # /console/workstation/* a nivel de partner; ejecutables siguen por cliente
      api/console/schemas_workstation.py
      core/console_auth.py                 # permiso nuevo workstation:pair; GUC app.workstation_manager
    scripts/enrol_device_dev.py            # SE BORRA — la evaluación lo prometió
    tests/isolation/test_30_device_partner_scope.py   # NUEVO
    tests/isolation/test_28_*, test_29_*               # reescritos
    tests/integration/test_device_pairing.py, test_device_renewal.py   # NUEVOS
  console/src/
    app/(console)/workstation/             # NUEVO — máquinas, emparejar, clientes por máquina
    app/api/session/whoami/route.ts        # NUEVO — identidad para la cáscara (cookie, mismo origen)
    components/workstation/                # pairing-dialog, machines-list, machine-clients, setup-card
    components/home/workstation-setup-card.tsx
    components/channels/                   # el único sitio que usa isDesktopShell()
    lib/shell.ts                           # isDesktopShell() por UA
    lib/backend/workstation.ts             # cliente de la API nueva
    lib/permissions.ts                     # workstation:pair
    components/shell/nav.ts                # /workstation
    i18n/lanes/workstation.ts
  desktop/src/
    electron/main.ts                       # BaseWindow + dos WebContentsView; sin AUPHERE_DEVICE_TOKEN
    electron/bar-preload.ts                # NUEVO — contextBridge mínimo, solo para la barra
    bar/                                   # NUEVO — HTML+TS de la barra, tokens de @nexus/ui
    credential-store.ts                    # NUEVO — safeStorage, por persona
    session-gate.ts                        # NUEVO — whoami → arrancar/parar/«otra persona»
    bar-state.ts                           # NUEVO — máquina de siete estados
    directory-declare.ts                   # NUEVO — selector nativo + cuatro validaciones
    http-transport.ts                      # pair · renew · links
    app-runtime.ts                         # ciclo de vida con la puerta de sesión
  desktop/tests/                           # uno por módulo nuevo; session-isolation ampliado
```

**Structure Decision**: no aparece ningún paquete nuevo. Lo que cambia de sitio es
**el nivel**: el puesto de trabajo pasa de colgar de cada cliente
(`/console/clients/{ref}/workstation`) a ser del partner (`/console/workstation`),
y los ejecutables —que sí son por cliente— se quedan donde estaban. En la cáscara,
la barra es un directorio propio (`src/bar/`) con su `preload`, separado del
`main.ts` para que la vista de la consola siga sin ninguno.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| GUC nuevo `app.workstation_manager` y dos políticas RLS en `partner_devices` | R5.2 exige que la persona vea las suyas y el gestor todas, y R5.4 exige que sea RLS y no un `WHERE` | Un `WHERE principal_id` en el repositorio — es exactamente lo que R5.4 prohíbe («no reimplementarlo de otra forma»). Correr el listado de gestor con el rol dueño, como hace el reaper del Companion — es saltarse la RLS para una lectura en nombre de una persona, y el precedente del Companion lo reserva a mantenimiento de plataforma |
| Un endpoint sin credencial en `/device` (`POST /device/pair`) | Antes de emparejar no hay credencial; el código **es** la credencial de un solo uso | Emparejar desde `/console` con la sesión de la persona — la página no puede entregar nada a la cáscara (R3.5). Emparejar por variable de entorno — es lo que se sustituye |
| Segunda `WebContentsView` con `preload` (la barra) | R12.1 exige una superficie propia, y una superficie propia necesita hablar con el proceso principal | Pintar la barra con HTML inyectado en la vista de la consola — mete un `preload` en la vista de la consola, que es lo que 15.3 y R3.5 prohíben. Una `BrowserWindow` aparte — dos ventanas para una cosa, y la persona la pierde detrás de la principal |
| Ventana de gracia de 60 s para la generación anterior al renovar | Un fallo de red justo después de que el servidor rote dejaría a la máquina con un token muerto y sin camino de vuelta salvo re-emparejar | Sin gracia — convierte un fallo de red en «hay que volver a emparejar», y R10 pide que una instalación dure |

## Riesgo de plan, dicho una vez

- **La enmienda del 001-R6.3 se hace primero.** `0107` + `test_30` + los repos por
  partner son las tareas 1-4. Si el cambio de dueño rompe más de lo previsto en
  `local_executions`, `local_argument_grants` o el catálogo por presencia, se para
  y se vuelve a `shape` — no se recorta.
- **La revocación rota (bug aparte, `task_e4dabc39`).** `require_device` de este
  plan carga la fila y comprueba `revoked_at`, lo que **subsume** el arreglo. Si el
  bug aterriza antes, se rebasa; si no, `test_30` lo cubre y el expediente se
  cierra por referencia. Lo que no se hace es arreglarlo dos veces de dos formas.
- **`BaseWindow` + `WebContentsView` no se ha usado aún en este repo.** La primera
  tarea de escritorio es un spike de una tarde con display: dos vistas, la de la
  consola sin `preload`, la de la barra con el suyo, y `session-isolation` en
  verde. Si Electron 44 no lo sostiene como se espera, el repliegue es una
  `BrowserWindow` hija anclada — feo, pero no toca ningún principio.
