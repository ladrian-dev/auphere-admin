# Implementation Plan: La conversación es el producto

**Branch**: `013-la-conversacion-es-el-producto` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-la-conversacion-es-el-producto/spec.md`

## Summary

Siete historias, y la investigación las abarata casi todas. El mensaje de la
persona **ya se guarda** —falta devolverlo—, y las varias conversaciones **ya
existen en la base de datos** —falta dejar de coger siempre la primera—. Lo caro
es una sola cosa: enseñar la salida de un comando sin guardarla, porque el
contrato congelado prohíbe llevarla por el stream y el único lector que hay hoy
la consume.

El Markdown entra con dependencia nueva, MIT y Apache-2.0, elegida porque
construye elementos de React en vez de HTML: el requisito de no ejecutar nada de
dentro del mensaje se cumple por construcción y no por sanear.

Detalle en [research.md](./research.md).

## Technical Context

**Language/Version**: TypeScript 5 (React 19) · Python 3.11

**Primary Dependencies**: nuevas — `react-markdown` 10.1.0 (MIT), `remark-gfm`
4.0.1 (MIT), `remend` 1.3.1 (Apache-2.0). Existentes: FastAPI, SQLAlchemy,
Redis, Electron 44, Next.js 16, `@nexus/ui`.

**Storage**: Postgres (`companion.threads`, `companion.messages`,
`companion.runs`, `local_executions`) — **sin migración**. Redis para lo efímero.

**Testing**: pytest (API) · vitest + Testing Library (escritorio y paquete
compartido) · Playwright (humo y a11y del escritorio)

**Target Platform**: aplicación de escritorio (macOS hoy) y consola web

**Project Type**: monorepo — API + paquete compartido de interfaz + dos clientes

**Performance Goals**: un mensaje de 50 000 caracteres no bloquea la ventana; el
texto en streaming se repinta sin parpadeo perceptible

**Constraints**: CSP estricta en Electron (sin recursos externos, sin `style` en
línea de terceros); la salida de un comando **no se persiste**;
`packages/companion-ui` lo comparten dos clientes

**Scale/Scope**: 7 requisitos, ~15 ficheros tocados, 3 paquetes

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants | ☑ | No toca ninguna de las 7. Todo lo nuevo se lee bajo `app.principal_id`, que es la RLS de la 0090, sin cambiarla. La ruta de la salida vive bajo el alcance de cliente que ya existe |
| II | Corte por superficie de confianza | ☑ | Superficie `0`, declarada en la spec. No se abre ninguna: todo se sirve con datos que la plataforma ya tiene |
| III | Lo leído es dato, nunca instrucción | ☑ | R3.4 lo pide en pantalla; R2.3 impide que un mensaje ejecute o cargue nada. El renderizador se elige **por esto** (research §5) |
| IV | Acción `mutates` con aprobación durable | ☑ | No añade ninguna acción consecuente. La tarjeta de aprobación no se toca: se le añade un hermano que enseña el resultado |
| V | Estados honestos; la ausencia se diseña | ☑ | R3.3 (decir que la salida no se conserva, en vez de un hueco), R6.2 (sin teammates no hay composer que no lleve a ningún sitio), R7.3 (vacío ≠ cargando) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | No hay agente implicado: esto es la pantalla |
| VII | Test primero | ☑ | Cada criterio EARS nace como test. Ver «Orden de entrega» |
| VIII | Licencias leídas enteras | ☑ | Tres dependencias nuevas, con licencia verificada en esta sesión y párrafo citado en research §5. Ninguna AGPL |
| IX | La KB es dueña del porqué | ☑ | `[[research/2026-09-19-auditoria-clase-mundial/_index]]` §5 y el informe 04, citados en el encabezado de la spec |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | **Ninguna de las 7.** Sí se apoya en la RLS por `principal_id` (0090) y no la modifica. Tres criterios lo afirman —R1.3, R7.2 y el alcance de la ruta de salida— y merecen test, aunque no sean garantía de las siete | `T` de contrato en `tests/isolation/` para R1.3 y R7.2 |
| **Licencias** | `react-markdown` 10.1.0 **MIT**, `remark-gfm` 4.0.1 **MIT**, `remend` 1.3.1 **Apache-2.0**. Párrafos en research §5 | `T` de alta de dependencias, con `THIRD-PARTY-LICENSES.md` actualizado |
| **Medidor** | **Nada nuevo.** La conversación no gasta; gasta el turno, y lo mide la 004 | — |

### La enmienda que este plan pide a la spec, antes de `/speckit-tasks`

**R3.2 no se puede implementar como está escrito.** Dice *«NO DEBE persistir la
salida en ningún sitio del que se pueda volver a leer»*; leído literal, prohíbe
también la clave efímera por la que la pantalla la recibe, y entonces R3.1 es
imposible.

Lo que §III pide, y lo que R3.3 y CE-005 miden, es que **no sea durable**.
Redacción propuesta:

> 2. El sistema NO DEBE persistir de forma durable la salida de un comando: no
>    entra en la auditoría ni en ninguna tabla, y deja de estar disponible al
>    cabo de **quince minutos** desde que la máquina contestó.

Quince minutos porque es el mismo reloj que ya caduca una aprobación (§IV), y
porque cubre leer el resultado de un build sin convertirse en un almacén.

**`/speckit-tasks` no debe arrancar hasta que esa frase esté en la spec.**

## Project Structure

### Documentation (this feature)

```text
specs/013-la-conversacion-es-el-producto/
├── spec.md
├── plan.md              # este fichero
├── research.md          # Fase 0 — las cinco preguntas
├── data-model.md        # Fase 1
├── quickstart.md        # Fase 1
├── contracts/
│   ├── el-hilo-recuerda.md
│   └── la-salida-en-vivo.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
packages/companion-ui/src/
├── components/
│   ├── markdown.tsx          # NUEVO — R2, el único sitio que pinta texto de un mensaje
│   ├── timeline.tsx          # R2 (usa markdown.tsx), R5 (copiar/reintentar)
│   ├── exec-card.tsx         # sin tocar: es la decisión, no el resultado
│   └── exec-result.tsx       # NUEVO — R3, el hermano que enseña lo que pasó
├── transport.ts              # R3: por dónde pide la pantalla la salida
└── types.ts                  # R1, R3

apps/api/src/nexus_api/
├── api/console/companion.py  # R1: el resumen de run lleva su prompt
├── api/console/workstation.py# R3: la ruta que sirve la salida efímera
└── services/local_dispatch.py# R3: publicar para dos lectores, no para uno

apps/desktop/src/
├── electron/app-surface.ts   # R4: dejar de coger siempre el primer hilo
├── app/routes/
│   ├── hoy.tsx               # R6: al abrir se puede escribir
│   └── thread.tsx            # R4: cambiar de conversación
└── app-ipc.ts                # R4, R7: canales nuevos

apps/console/                 # no se toca a mano: hereda el timeline
```

**Structure Decision**: lo que es «cómo se pinta un mensaje» vive en el paquete
compartido y aparece en los dos clientes a la vez —que es la regla de la 003 y es
deseable: la consola tiene hoy los mismos huecos—. Lo que es navegación de la
aplicación (varias conversaciones, pantalla de inicio, buscar) vive en
`apps/desktop`, porque la consola no tiene pantalla de teammates (003-R14.3).

**Consecuencia de verificación**: tocar `packages/companion-ui` obliga a
`./scripts/verify.sh js` **entero** —consola, panel, paquete compartido y el
`next build`—. Es justo lo que este repositorio olvida, y aquí el paquete
compartido está en medio de tres requisitos.

## Orden de entrega

Las tres P1 son independientes y **cada una se puede soltar sola**. El orden
recomendado va de menos a más riesgo, para que parar en cualquier punto deje algo
entregado:

| # | Requisito | Por qué aquí | Riesgo |
|---|---|---|---|
| 1 | **R1 — el hilo recuerda** | Un campo en una respuesta que ya existe. Sin esto, lo demás pule algo que no se puede leer | Bajo |
| 2 | **R2 — Markdown** | Dependencia nueva, pero acotada a un componente | Medio: el parpadeo de tablas a medias es de la implementación, no de la librería |
| 3 | **R3 — la salida en vivo** | Lo único que toca tres capas y roza un contrato congelado | **Alto** |
| 4 | R4 — varias conversaciones | Solo aplicación; la API ya sirve | Bajo |
| 5 | R6 — al abrir se escribe | Depende de R4 para saber a qué conversación llevar | Bajo |
| 6 | R5 — copiar, editar, reintentar | Encima del timeline ya renderizado | Bajo |
| 7 | R7 — buscar | P3. Solo tiene sentido tras R4 | Medio |

**Test primero en todos**, y el rojo se ve antes de implementar (§VII). Los
criterios que más fácil se «implementan» sin test son R3.2 y CE-005 —que algo
**no** esté— así que su test se escribe primero y se comprueba mirando la base de
datos, no confiando.

## Complexity Tracking

| Violación | Por qué hace falta | Alternativa más simple, y por qué se rechazó |
|---|---|---|
| **Tres dependencias donde podría haber una** | `react-markdown` no resuelve el streaming; `remend` sí, y son 4,3 kB sin dependencias | `streamdown` lo trae todo en uno y es Apache-2.0, pero son 144 kB y sus valores por defecto **traen `rehype-raw` y admiten imágenes de cualquier origen** — más permisivos que nuestra superficie de amenaza, que es texto de desconocidos por WhatsApp. Habría que apagar tres cosas para volver al punto de partida |
| **Una segunda clave en Redis para la salida** | El único lector de hoy hace `LPOP` y **consume**: la pantalla no puede leer lo mismo que el turno | Meter la muestra en `exec.completed` rompe una regla deliberada del contrato congelado —los eventos no llevan prosa— y se la rompe a todos los consumidores, no solo al que la necesita |
| **Un componente de resultado además de la tarjeta de aprobación** | La tarjeta existente dice «nunca la salida» y **tiene razón**: es la decisión, no el resultado | Cambiarla mezclaría decidir y ver, que son dos momentos distintos y con dos públicos distintos en el tiempo |
