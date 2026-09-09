# Implementation Plan: el puesto de trabajo del teammate en la máquina del partner

**Branch**: `001-puesto-trabajo-partner` | **Date**: 2026-09-09 | **Spec**: [`spec.md`](./spec.md)

**Input**: Feature specification from `/specs/001-puesto-trabajo-partner/spec.md`

## Summary

El teammate pasa de proponer a **hacer**: ejecuta en la máquina del partner, dentro
de un directorio declarado, con una lista blanca de ejecutables que solo se cambia
desde la consola, contención de escrituras probada contra seis ataques en macOS y
Windows, y presencia de dispositivo que retira las herramientas del catálogo cuando
la máquina no está.

El puesto de trabajo **no se construye: se compone**. Una edición Auphere sobre
KiroCrew `0.7.0` fijado a `37933a5` (Apache-2.0), por su entry point
`kirocrew.plugins`, con el núcleo a **0 archivos modificados**. Nexus sigue siendo
plano de control: las herramientas `console.*` llegan por un servidor MCP de la
edición y las aprobaciones que tocan a un cliente final siguen siendo las durables
que ya existen en `companion.actions`.

**Dos apuestas van al principio, no al final.** `T001` verifica que el catálogo se
puede contener; `T002`, que la app de escritorio puede contestar la aprobación de
subagentes. Ninguna está verificada, y de ellas dependen los Requisitos 5 y 11.

## Technical Context

**Language/Version**: Python **3.12** para la edición (lo exige el sustrato) ·
Python **3.11** en `apps/api`, que **no se toca** · Node/Electron para la cáscara de
escritorio

**Primary Dependencies**: KiroCrew `0.7.0` @`37933a5` (Apache-2.0, rueda construida
por nosotros — no hay pública) · `@agentclientprotocol/claude-agent-acp` `0.75.1`
(Apache-2.0) · CLI `claude`

**Storage**: Postgres con RLS para lista blanca, presencia de dispositivo,
aprobaciones y auditoría (Alembic en `apps/api/alembic/versions/`, última `0105`) ·
el data home del sustrato vive en la máquina del partner, redirigido por tres
variables

**Testing**: `pytest` · `apps/api/tests/isolation/` (bloqueante en CI; 50 ficheros
hoy) · suite de contención de escrituras portada, seis ataques × dos sistemas

**Target Platform**: máquina del partner **macOS y Windows** · plano de control en
Linux (AWS `eu-south-2`)

**Project Type**: aplicación de escritorio + servicio backend ya existente

**Constraints**: sin techos de recursos del sistema operativo fuera de Linux — los
pone el producto (Requisito 12) · el puente es **saliente**, nada entra hacia la
máquina del partner · navegador y ejecución local **no** conviven en esta beta

**Scale/Scope**: un dispositivo por persona del partner; concurrencia de sesiones
acotada por la máquina, no por nosotros

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y vuelta a comprobar tras el diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La lista blanca de ejecutables y la presencia de dispositivo son filas por tenant con RLS; los repos las toman del contexto de petición. Tests: `tests/isolation/test_26_*`, `test_28_*`. Extiende el contrato que ya fija `test_2_tool_whitelist_contract.py` |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie **`3a`** declarada en la spec. Se abre por su **mitad barata** —ficheros y terminal, con precedente en ambos sistemas—; la cara (`3b`, controlar el escritorio) queda fuera. La `0` está agotada: esto es justo lo que no se puede hacer por API |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ **con condición** | El sustrato **trae** navegador y `computer_use`. Esta beta enciende solo ejecución local, así que no se pagan las guardas de las dos — **pero no basta con no listarlos**: `T00A` comprueba que no son alcanzables. La salida de un comando se trata como dato (Requisito 8 la registra; ningún requisito la deja gobernar el turno) |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Se reutiliza `companion.actions` (`state_hash`, `decided_at`, `decided_by`, UPSERT idempotente). El gate del sustrato se queda solo para lo que ocurre dentro de la máquina (Requisito 7.2) |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Requisitos 4.3, 4.4, 11.3 y 11.4. **Con una guarda propia**: la evaluación observó que su `spawn list` informó `✅` de un subagente rechazado, así que nuestra pantalla **no** puede reflejar su estado sin contrastarlo |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | Servidor MCP de la edición sobre las herramientas `console.*`. El agente no navega nuestra consola en ningún caso |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS nace como test. Los doce ataques de contención (seis × dos sistemas) son tests, no una declaración |
| VIII | Licencias leídas enteras; AGPL no | ☑ | Dos dependencias nuevas, ambas **Apache-2.0**, con su párrafo citado en [`research.md`](./research.md) §D10. `NOTICE` conservado (§4.d); marcas **no** usadas (§6) |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | La spec cita `[[15-kirocrew-y-alternativas]]` y `[[14-mvp-y-fases]]` §3. **Falta el enlace de vuelta**: la KB debe apuntar a `specs/001-puesto-trabajo-partner/` — va como tarea |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **2** (whitelist de herramientas, de frente) · **6** (log y traza etiquetados por tenant) · **1** (RLS sobre lista blanca y dispositivos) | `test_26_local_tool_catalog_exhaustive.py` · `test_27_local_execution_audit_tenant_tagged.py` · `test_28_local_allowlist_device_rls.py`. El nº 25 queda reservado a la VM de la beta 5 |
| **Licencias** — ¿qué dependencia nueva entra? | KiroCrew `0.7.0`@`37933a5` **Apache-2.0** · `@agentclientprotocol/claude-agent-acp` `0.75.1` **Apache-2.0**. Párrafos citados en `research.md` §D10 | Tarea de licencias + `NOTICE` |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Modelo**, al medidor que ya existe. **Reloj de máquina: no** — la máquina es del partner (Requisito 10.2) | Tarea de medición |

**Ninguna fila en rojo.** La única con condición es §III, y su condición es una
comprobación, no una excepción.

## Constitution Check — vuelta a comprobar tras el diseño

Ninguna fila cambia de color. Lo que cambia es que dos condiciones dejan de ser
promesas y tienen sitio concreto:

- **§III** — la condición «el navegador y `computer_use` no son alcanzables» ya no
  es una intención: es una comprobación con tarea propia, y el contrato del
  catálogo ([`contracts/console-mcp.md`](./contracts/console-mcp.md)) la hace
  fail-closed — si no se puede garantizar, la sesión no se abre.
- **§V** — la guarda contra heredar un estado mentiroso del sustrato queda escrita
  en la guía de validación: en la Puerta 2 se comprueba **también el rechazo**, no
  solo el camino feliz.
- **§I** — el diseño no introdujo ninguna tabla sin `tenant_id`, y ninguna acepta
  el tenant del llamante. `test_21`, que exige RLS en toda tabla con tenant, cubre
  las cuatro nuevas sin cambios.

El diseño **no** añadió ninguna dependencia más allá de las dos ya declaradas en
§D10, así que la puerta de licencias sigue igual.

## Constitution Check — tercera comprobación (Requisito 15, la cáscara)

El Requisito 15 llegó tarde y toca dos principios, así que se vuelve a comprobar
en vez de darse por cubierto.

| # | Principio | ¿Cumple? | Por qué |
|---|---|---|---|
| **VI** | Por API, nunca por navegador, y nunca contra nosotros mismos | ☑ **con la condición 15.3** | §VI prohíbe que un agente navegue nuestra consola porque eso mete una sesión autenticada en su ambiente. La cáscara tiene esa sesión **en la misma máquina** que el agente. Lo que las separa es 15.3: el agente llega a `console.*` por su propio servidor MCP y con **su propia identidad**, y la sesión de la persona no es alcanzable desde su ambiente. Sin ese criterio, esta fase violaría §VI de frente |
| **I** | Aislamiento; la whitelist es por tenant, sin globales | ☑ | La cáscara no añade catálogo: sigue sirviéndose del de la edición, con sus tres reglas. Envolver la consola no crea una vía nueva hacia herramientas |
| Restricciones adicionales | La consola nunca guarda una credencial de backend | ☑ | 15.2 lo extiende a la cáscara. Envolver la consola no puede relajar lo que la consola cumple — y una app de escritorio es justo donde la tentación de «guardar el token para no pedirlo cada vez» es mayor |
| **V** | Estados honestos | ☑ | 15.4 le da sitio al `reconectando`, que hasta ahora existía en `OutboundBridge` sin pantalla donde vivir |

**Nada nuevo en licencias ni en medidor**: Electron y `electron-updater` entran en
la fase, y su licencia se declara con su tarea antes de instalarlos (§VIII).

## Project Structure

### Documentation (this feature)

```text
specs/001-puesto-trabajo-partner/
├── plan.md              # este fichero
├── research.md          # Fase 0 — decisiones D1..D12
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/           # Fase 1
└── tasks.md             # lo produce /speckit-tasks, no este comando
```

### Source Code (repository root)

```text
apps/
  api/                       # plano de control — Python 3.11, NO se toca la versión
    alembic/versions/        # 0106+ : dispositivos, lista blanca, auditoría local
    src/nexus_api/
      db/models/             # entidades nuevas (ver data-model.md)
      repositories/          # tenant del contexto, nunca del llamante
      api/console/           # gestión de la lista blanca y los dispositivos
    tests/isolation/         # test_26, test_27, test_28
  desktop/                   # NUEVO — cáscara de escritorio y puente saliente
  edition/                   # NUEVO — la edición Auphere (Python >=3.12)
    src/auphere_edition/
      edition.py             # build_enterprise_context, el entry point del seam
      mcp_console.py         # servidor MCP sobre las herramientas console.*
      wrapper/               # el envoltorio de CLAUDE_CODE_EXECUTABLE (T001)
    tests/
```

**Structure Decision**: el plano de control se queda donde está y **no cambia de
versión de Python**. Lo nuevo son dos paquetes independientes —`apps/edition` y
`apps/desktop`— porque la edición exige Python ≥3.12 y viaja con la aplicación de
escritorio, no con la API. Esa separación es también lo que mantiene la promesa de
D2: la edición se puede reconstruir sobre un commit nuevo del sustrato sin tocar
nada de `apps/api`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Construimos y publicamos nosotros la rueda del sustrato desde un commit fijado | No existe rueda pública: PyPI da 404 y los releases solo publican bundles de escritorio | Depender de una rueda publicada — no existe. Vendorizar el código en nuestro repo — es un fork disfrazado y pierde el seguimiento aguas arriba, que es la única razón de usar el seam |
| Dos paquetes nuevos (`edition`, `desktop`) en vez de uno | La edición exige Python ≥3.12 y el plano de control está en 3.11; y la cáscara es Node | Un solo paquete obligaría a subir la versión de Python de `apps/api` por una razón ajena a `apps/api` |
| Techos de recursos implementados por nosotros (Requisito 12) | Fuera de Linux no hay cgroups, y el destino es macOS y Windows | Confiar en el sistema operativo — el propio arranque del sustrato avisa de que ahí no hay contención |

## Riesgo de plan, dicho una vez

Dos requisitos descansan en capacidades **sin verificar**, y sus verificaciones son
las dos primeras tareas:

- **`T001` — Requisito 5**: ¿basta el envoltorio con `--strict-mcp-config` para que
  el catálogo salga solo con las herramientas de Crew? Si no, la edición tendría
  que intervenir el lanzamiento del harness, que es lo primero que obligaría a
  tocar el núcleo. Entonces se aplica el repliegue de la evaluación —opción C sobre
  B— y esta spec se replantea **antes** de construir encima.
- **`T002` — Requisito 11.1**: ¿puede la app de escritorio ser la superficie que
  contesta la aprobación de un subagente? Si no, el Requisito 11 se retira y la
  beta 2 entrega ejecución de un solo agente.

Ninguna tarea que dependa de 5 u 11 arranca antes de que su verificación esté en
verde.
