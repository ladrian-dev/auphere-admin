# Implementation Plan: La máquina se registra con la sesión

**Branch**: `012-la-maquina-se-registra-con-la-sesion` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: `specs/012-la-maquina-se-registra-con-la-sesion/spec.md`, sostenida por
la evaluación `.specify/assessments/maquina-sin-emparejar/` (cerrada con `go` el
2026-09-22, seis decisiones D-1…D-6).

## Summary

Se retira el código de emparejamiento de ocho símbolos y la máquina queda
registrada al entrar. El cambio se apoya en un hecho verificado en el código: la
aplicación **ya tiene sesión de consola confirmada** antes de poder teclear ese
código, así que el segundo acto no prueba nada.

Antes de tocar eso, se construye lo que hoy falta y ya hace falta: **retirar
todo el acceso de una persona** —sus sesiones y sus máquinas, en una
transacción—, que es la pieza que la spec 011 usará cuando restablecer la
contraseña revoque máquinas (D-6), y que hoy no existe ni siquiera a mano.

Técnicamente son tres movimientos, ninguno exótico: una operación de revocación
en bloque sobre dos tablas del mismo Postgres; una ruta nueva en el BFF de la
consola que canjea sesión por credencial de máquina, copiando el camino que ya
usa `/api/desktop/redeem`; y una limpieza que borra una tabla, dos diálogos y un
canal de IPC.

> **Corrección del 2026-09-22, al implementar US1.** Este plan decía **una sola
> migración**. Son **dos**: miró que `revoked_at` y el motivo de revocación ya
> existían, y no miró que este repositorio siembra el **vocabulario de auditoría
> por migración**. Un acto nuevo sin su frase sale con el fallback crudo, y
> `principal.access_revoked` es justo el asiento que alguien leerá con prisa el
> día que pregunte quién echó a quién. Así que `0124_access_revoked_vocab`
> —aditiva, con US1— y la destructiva al final, con US6. Detalle en
> [data-model.md](./data-model.md).
>
> Y una segunda corrección, de sitio: la ruta de retirar el acceso **no va en
> `/console/workstation/*`** sino en `/console/team/*` con `team:manage`. El
> permiso de la primera es `workstation:pair`, que tiene el builder porque es
> «reclamar lo que es tuyo»; retirarle el acceso a otra persona es lo contrario.
> Detalle en [contracts/registrar-la-maquina.md](./contracts/registrar-la-maquina.md).

## Technical Context

**Language/Version**: Python 3.11 (API, `uv`) · TypeScript 5 (consola Next.js 16, escritorio Electron 44)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2 · Next.js App Router · Electron + React 19. **Ninguna dependencia nueva.**

**Storage**: PostgreSQL. Dos tablas implicadas, **ambas en la misma base**: `console_auth.principal_sessions` y `partner_devices` (esquema público). Verificado: mismo `Base`, mismo engine.

**Testing**: pytest (`tests/unit`, `tests/integration`, `tests/isolation`) · Vitest + Testing Library (escritorio y consola) · Playwright para humo y a11y

**Target Platform**: API en AWS `eu-south-2`; consola en Vercel; escritorio macOS (Windows fuera de alcance, spec 022)

**Project Type**: monorepo — servicio web + BFF + aplicación de escritorio

**Performance Goals**: ninguno nuevo. Retirar el acceso es una operación puntual sobre dos tablas con índice por persona (`ix_console_sessions_principal` existe).

**Constraints**: la credencial de máquina no cambia de forma ni de vida (JWT 12 h, generación, gracia de 60 s). El puente sigue siendo **solo saliente**: esta spec no abre ningún puerto ni enmienda `no-inbound.test.ts`.

**Scale/Scope**: decenas de máquinas por partner como mucho; el tope que introduce R4 es de cinco por persona.

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y vuelta a comprobar tras el diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Ninguna de las **ocho** se debilita. La credencial sigue sin nombrar tenant. `test_29_device_credential_scope.py` y `test_30_device_partner_scope.py` **siguen verdes sin tocarlos**; si hubiera que aflojar uno, el cambio está mal. Test nuevo: retirar el acceso de una persona no alcanza a otra (R1.5) |
| II | Corte por superficie; no se abre una nueva sin agotar la actual | ☑ | **Sustitución, no apertura**: el endpoint nuevo reemplaza a `POST /device/pair`, que hoy emite la misma credencial a partir de un código tecleado desde una app que ya tiene la misma sesión. La autoridad era la sesión antes y lo es ahora. Y se **cierra** un vector conocido (device-code phishing) |
| III | Lo leído es dato, nunca instrucción | ☑ | No se lee nada nuevo. Esta spec no toca la ejecución local |
| IV | Acción `mutates` con aprobación durable; la auditoría nombra a la persona | ☑ | Los tres hechos nuevos —retirar acceso, desemparejar, registrar— dejan asiento con actor. R1.6, R2.2, R3.6. Es donde esta spec **mejora** el estado actual: hoy solo hay asiento en un extremo |
| V | Estados honestos; la ausencia se diseña | ☑ | R2 existe **porque hoy la pantalla miente** («dejarán de poder leer y ejecutar aquí» cuando la credencial sigue viva). Y los casos límite obligan a decir qué **no** se puede parar: lo que la máquina ya está ejecutando |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | El registro va por una ruta del BFF llamada desde el proceso principal, no navegando |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Con dos cuidados especiales: **R1.2** (atomicidad) se prueba forzando el fallo a mitad, y **R6.1** afirma que algo *no existe*, así que se comprueba **buscando**, no confiando |
| VIII | Licencias leídas enteras; AGPL no | ☑ | **Ninguna dependencia nueva.** Esta spec resta código |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | Encabezado de la spec → `[[research/2026-09-19-auditoria-clase-mundial/_index]]` §5 fila 012 y §A del informe 06 |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **Ninguna se debilita.** Pero se abre una frontera nueva por la que viaja poder: una operación que revoca en bloque corriendo con rol dueño. Necesita test propio de que no se pasa de la persona nombrada | tarea en `tests/isolation/` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna.** El cambio retira código | — (no aplica, declarado) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada.** No hay modelo, ni reloj de máquina, ni herramienta de pago | — (no aplica, declarado) |

**Complejidad que hay que justificar:** ninguna. El plan no añade nada que la
spec no pidiera; la operación de revocación en bloque la pide R1 explícitamente
y su reutilización desde la 011 está escrita en D-6.

## Project Structure

### Documentation (this feature)

```text
specs/012-la-maquina-se-registra-con-la-sesion/
├── plan.md              # este fichero
├── research.md          # Fase 0 — las siete decisiones cerradas
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/           # Fase 1
├── checklists/
│   └── requirements.md  # calidad de la spec, en verde
└── tasks.md             # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/nexus_api/
├── services/
│   ├── console_identity.py        # + end_all_sessions (la tercera forma de cerrar, que faltaba)
│   └── principal_access.py        # NUEVO — «retirar todo el acceso»: la pieza que la 011 reutiliza
├── repositories/
│   └── local_workstation.py       # + contar activas (tope) · − repositorio de códigos
├── api/
│   ├── device_bridge.py           # − POST /device/pair
│   └── console/
│       ├── team.py                # + DELETE /members/{id}/access  (team:manage)
│       ├── workstation_partner.py # − emitir código · + registrar máquina
│       └── auth.py                # sin cambios (la 011 la tocará)
├── core/
│   ├── workstation_limits.py      # NUEVO — el umbral y el tope, en un solo sitio
│   ├── console_auth.py            # sin cambios: el permiso ya está declarado
│   └── pairing_codes.py           # − se retira entero
└── alembic/versions/
    ├── 0124_access_revoked_vocab.py        # NUEVA, aditiva, con US1
    └── 01XX_drop_device_pairing_codes.py   # NUEVA, destructiva, la última

apps/console/src/
├── app/api/desktop/
│   ├── redeem/route.ts            # sin cambios — es el patrón que se copia
│   └── register-machine/route.ts  # NUEVA — canjea sesión por credencial
├── app/(console)/workstation/
│   ├── actions.ts                 # − issuePairingCodeAction
│   └── page.tsx                   # ajuste de lo que se ofrece
├── components/workstation/
│   └── pairing-dialog.tsx         # − se retira entero
├── lib/backend.ts                 # − emitir código · + registrar
└── i18n/lanes/workstation.ts      # − claves del código

apps/desktop/src/
├── app-runtime.ts                 # registro por sesión · unpair() llama al servidor
├── electron/main.ts               # llamada a register-machine desde la partición humana
├── http-transport.ts              # + revocar al desemparejar
├── app-ipc.ts                     # − canal app:workstation.pair
├── workstation-state.ts           # − estado y acción de introducir código
└── app/routes/
    ├── pair-dialog.tsx            # − se retira entero
    └── pair-errors.ts             # − se retira entero
```

**Structure Decision**: monorepo existente, sin paquetes nuevos. La única pieza
que nace en sitio propio es `services/principal_access.py`, y nace ahí por una
razón concreta: **la va a llamar la spec 011**. Si viviera dentro de
`console_identity` quedaría atada a la identidad; si viviera en el repositorio de
máquinas quedaría atada al puesto de trabajo. Retirar el acceso de una persona no
es ninguna de las dos cosas: las cruza, y por eso tiene su propio módulo.

## Orden de entrega

El de la spec, y el plan no lo contradice. Cada tramo se suelta solo:

| # | Historia | Depende de | Por qué se puede soltar sola |
|---|---|---|---|
| 1 | **H1** · retirar todo el acceso | nada | Tiene valor **hoy**, con el código de emparejamiento puesto. Es la pieza que la 011 reutiliza |
| 2 | **H2** · desemparejar revoca | H1 (reutiliza la revocación de una máquina) | Arregla una pantalla que miente. No necesita el registro nuevo |
| 3 | **H3** · entrar deja la máquina lista | nada de H1/H2 técnicamente | Es el corazón. Se entrega con el código todavía presente: dos caminos abiertos un tiempo, que es incómodo y seguro |
| 4 | **H4** · tope de máquinas | H3 (antes de H3 el tope apenas se nota) | Repone el freno que H3 retira |
| 5 | **H5** · la carpeta al frente | H3 (el sitio lo ocupa la ceremonia hasta entonces) | Valor de producto por sí sola |
| 6 | **H6** · el código desaparece | H3 entregada y en uso | Limpieza. Va última a propósito: se retira cuando ya nadie lo usa |

**Comprobado explícitamente: H1 no depende de nada de H3.** Era el riesgo de que
el orden se contradijera, y no se contradice: H1 toca revocación y H3 toca
emisión.

## Verificación

`./scripts/verify.sh` entero antes de dar por cerrada cualquier historia. Este
cambio toca **los tres sitios que este repositorio olvida**:

- **`apps/console`** — BFF nuevo, permisos, retirada del diálogo → `next build`.
- **`apps/desktop`** — registro, desemparejar, retirada del diálogo y del canal
  IPC → su suite entera, que es la que más se mueve.
- **`apps/api`** — `mypy --strict` sobre servicio nuevo y repositorios.
- **El worker** no se toca, pero se corre igual: es lo que ha roto la tubería dos
  veces.

Y una regla operativa que ya costó una investigación en falso: **una sola
ejecución de pytest a la vez**; las suites comparten la base de desarrollo.

## Re-evaluación del Constitution Check tras el diseño

Las nueve filas siguen en verde. El diseño movió dos cosas respecto a la primera
pasada, y las dos **suben** el cumplimiento en vez de bajarlo:

- **§I.** El diseño destapó una frontera que la primera pasada no nombraba:
  retirar el acceso **corre con rol dueño**, igual que ya lo hace archivar las
  máquinas de quien pierde la pertenencia. Eso significa que **la RLS no la
  protege** y que lo único que impide alcanzar a otra persona es la condición de
  la propia consulta. No es una violación —es la forma correcta para una
  operación de plataforma— pero sí obliga a un test de aislamiento que la primera
  pasada no había pedido. Está en las puertas.
- **§VII.** Al escribir los contratos quedó claro que R1.2 no se prueba mirando
  el resultado feliz: hay que **forzar el fallo a mitad**. Y R6.1 afirma que algo
  no existe, que solo se comprueba buscando. Los dos tienen su tarea propia.

Nada de lo diseñado añade superficie, dependencias ni medición.

## Complexity Tracking

Sin violaciones que justificar.
