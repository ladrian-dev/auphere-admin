# Implementation Plan: la experiencia de la aplicación de escritorio

**Branch**: `010-experiencia-app-escritorio` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-experiencia-app-escritorio/spec.md`

## Summary

Convertir tres superficies apiladas en **una aplicación**: una vista a pantalla
completa que es dueña del armazón (franja superior con los controles del sistema
integrados + lista lateral única + panel de contenido), con la consola web
pintada **dentro del panel** en modo embebido y el puesto de trabajo **absorbido**
en el armazón. Sobre esa base: estados honestos (conexión, sesión, turno),
taxonomía de avisos con un solo contador, primer arranque que llega solo al
primer valor, y topes que terminan en una acción con destino exacto.

El enfoque técnico está fijado por la Fase 0 ([research.md](./research.md)): el
spike confirmó que **el arrastre funciona** con la consola superpuesta si una
sola vista posee la franja; la consola se integra por **modo embebido detectado
por user-agent**, sin ganar ningún canal; y el sistema visual crece dentro de
`@nexus/ui` con seis dependencias pequeñas de licencia permisiva, sin adoptar
ningún kit.

## Technical Context

**Language/Version**: TypeScript 5.7 `strict` + `noUncheckedIndexedAccess` · React 19 · Node 22 (proceso principal)

**Primary Dependencies**: Electron 44 · Vite 8 · Tailwind CSS v4 · `@nexus/ui` (Base UI 1.x, tokens OKLCH) · `@nexus/companion-ui` · `lucide-react` · `sonner` · `electron-updater`

**Storage**: preferencias locales de ventana (tamaño, posición, última sección, tema, ruido de avisos) en el fichero de datos de usuario ya existente, **sin credenciales**. Ningún dato de producto se guarda en la máquina.

**Testing**: `vitest` (unidad y componente, jsdom) · test de contraste de tokens · `@playwright/test` con su soporte de Electron (humo del binario) · `@axe-core/playwright` (accesibilidad) · `./scripts/verify.sh`

**Target Platform**: macOS 13+ (arm64 y x64). Windows queda fuera de esta spec.

**Project Type**: aplicación de escritorio (Electron) dentro de un monorepo, con paquetes de UI compartidos con la consola web.

**Performance Goals**: armazón visible **<1 s** desde la apertura y sin depender de la red · sin destello de color al arrancar · respuesta de navegación entre secciones por debajo del umbral en el que hace falta indicador.

**Constraints**: cuatro particiones pasan a **tres**, todas comprobadas al arrancar · la consola **sin `preload`** · canal de la pantalla como **lista cerrada validada** con redacción de credenciales · política de contenido en la vista de la aplicación (`font-src 'self'`) · Google y Stripe **fuera de la ventana** · sin cifra absoluta del pool · sin datos de tarjeta · el actualizador nunca reinicia solo.

**Scale/Scope**: ~12 pantallas de la aplicación + **las 10 secciones que la consola ya ofrece** (inicio, clientes, conocimiento, puesto, consumo, auditoría, notificaciones, equipo, claves, facturación), integradas con sus mismos permisos · 6 historias · 12 requisitos · 3 paquetes tocados (`apps/desktop`, `apps/console`, `packages/ui`) más el catálogo compartido de `packages/companion-ui`.

**Decisiones cerradas aquí, que la spec dejaba como supuesto**: el aviso de consumo cercano usa el **80 %**, que es el umbral que el producto ya aplica en los avisos de consumo de la consola («Umbrales: 80 % (aviso) y 100 % (tope alcanzado)»); y «esta versión ya no se admite» vive **solo** en el estado del puesto, no en el de actualización.

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y vuelta a comprobar tras el diseño (§ al final).*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ✅ | **Ninguna de las 7 garantías se toca**: esta spec no añade herramientas, no cambia el catálogo ni toca la RLS. Todo lo que la aplicación lee sigue entrando por el BFF con la sesión de la persona. Prueba: las suites de `tests/isolation/` siguen en verde sin cambios; el test de particiones de la cáscara pasa de cuatro a tres (`apps/desktop/tests/session-isolation.test.ts`) |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ✅ | Superficie declarada en la spec: `0` (API de la consola) + tramo abierto de `3a`. **Se retira** la partición `auphere-bar`. Sin esquema propio, sin oyente nuevo (el único permitido sigue siendo el de la entrada por navegador), sin credencial nueva |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ✅ | No cambia qué lee el agente ni cómo. La ruta que viaja del principal a la pantalla (`/usage`, `/billing`) es **dato de navegación de la propia consola**, se valida contra una lista de rutas conocidas y **no dispara ninguna acción**; pintar una sección nunca ejecuta nada |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ✅ | R10 refuerza el principio: la decisión se toma con lo necesario delante, con teclado, con protección contra pulsación accidental (R10.3) y con **atribución visible** (R10.7). No se crea ninguna vía de aprobación automática; el aviso del sistema **lleva** a la tarjeta, no decide |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ✅ | Es el núcleo de la spec: R3, R4 y R9.9. Prueba por estado en cada pantalla (tabla de `data-model.md` §5) y CE-002 («cero estados sin salida») |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ✅ | Este principio gobierna **al agente**, y el agente no cambia. La persona sí navega la consola —es su consola— y lo hace dentro de la ventana; ninguna automatización lee ni conduce esa vista |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ✅ | Cada criterio EARS nace como test (unidad, componente, contraste, accesibilidad o humo). `tasks.md` cita `_Requisitos: N.m_` por tarea y pone el test antes que la implementación |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ✅ | Seis dependencias nuevas de producto y dos de desarrollo, con su párrafo citado abajo. **Ninguna AGPL**; la única no-MIT/Apache es de desarrollo y se declara |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ✅ | La spec cita `[[2026-09-17-experiencia-app-escritorio]]`; la nota de KB enlaza de vuelta a esta carpeta y a la evaluación |

### Licencias de las dependencias nuevas (§VIII)

| Paquete | Licencia | Párrafo citado | Dónde |
|---|---|---|---|
| `@fontsource-variable/inter-tight` | OFL-1.1 (fuente) + MIT (empaquetado) | «This Font Software is licensed under the SIL Open Font License, Version 1.1.» | `apps/desktop` |
| `@fontsource-variable/jetbrains-mono` | OFL-1.1 + MIT | ídem | `apps/desktop` |
| `react-resizable-panels` | MIT | «Copyright (c) 2018 Brian Vaughn / Permission is hereby granted, free of charge, to any person obtaining a copy…» | `packages/ui` |
| `@tanstack/react-virtual` | MIT | «Copyright (c) 2021-present Tanner Linsley / Permission is hereby granted, free of charge…» | `packages/ui` |
| `use-stick-to-bottom` | MIT | «Copyright (c) 2024 - present StackBlitz / Permission is hereby granted, free of charge…» | `packages/companion-ui` |
| `electron-context-menu` | MIT | «Copyright (c) Sindre Sorhus … Permission is hereby granted, free of charge…» | `apps/desktop` (principal) |
| `@playwright/test` *(desarrollo)* | Apache-2.0 | «Apache License Version 2.0, January 2004» | `apps/desktop` |
| `@axe-core/playwright` *(desarrollo)* | **MPL-2.0** | «Mozilla Public License, version 2.0» | `apps/desktop` — **no se distribuye**: herramienta de desarrollo. Copyleft por fichero; no se modifican sus ficheros |

> Las citas vienen del archivo `LICENSE` de cada repositorio, leídas en el anexo
> `02-librerias-y-stack.md` de la KB. **Antes de instalar**, la tarea de
> dependencias vuelve a leer el `LICENSE` del paquete instalado y actualiza
> `apps/desktop/THIRD-PARTY-LICENSES.md`.

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **Ninguna de las siete.** Sí toca el aislamiento de superficies de la cáscara: cuatro particiones → tres, la consola sigue sin `preload`, el canal de la pantalla sigue siendo lista cerrada con validación y redacción | `T0xx` en `apps/desktop/tests/session-isolation.test.ts`, `app-ipc.test.ts`, `no-credentials-over-ipc.test.ts` y `no-own-auth.test.ts` (trasladado a la vista de la aplicación) |
| **Licencias** — ¿qué dependencia nueva entra? | Seis de producto + dos de desarrollo, tabla de arriba. **Ninguna AGPL** | `T0xx` «declarar licencias y actualizar `THIRD-PARTY-LICENSES.md`» |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada nuevo.** No consume modelo, reloj de máquina ni herramienta de pago. La aplicación **muestra** el medidor de la spec 004 (proporción y reinicio, sin cifra absoluta) | `T0xx` de la historia P5, que verifica R9.6 |

### Enmiendas de contrato que este plan ejecuta

| Contrato | Enmienda | Artefacto |
|---|---|---|
| `specs/002-identidad-app-escritorio/contracts/desktop-bar.md` | El puesto deja de ser superficie propia: se retiran la vista, la partición y el `preload` de siete funciones; los **ocho estados** y sus transiciones se conservan como lógica pura | [`contracts/workstation-en-el-armazon.md`](./contracts/workstation-en-el-armazon.md) |
| `specs/003-teammates-app-escritorio/contracts/desktop-app-ipc.md` | El canal de la pantalla gana los canales del puesto, los del armazón (mostrar sección, ruta actual, rectángulo del panel), los de entrada por navegador, los de actualización y los de puesta en marcha | [`contracts/desktop-app-ipc-v2.md`](./contracts/desktop-app-ipc-v2.md) |

## Project Structure

### Documentation (this feature)

```text
specs/010-experiencia-app-escritorio/
├── plan.md                                   # este archivo
├── research.md                               # Fase 0 (spike incluido)
├── data-model.md                             # Fase 1
├── quickstart.md                             # Fase 1
├── contracts/
│   ├── desktop-app-ipc-v2.md                 # canal de la pantalla, enmendado
│   ├── shell-armazon.md                      # ventana, vistas, franja, tema
│   ├── console-modo-embebido.md              # qué oculta la consola y cómo se detecta
│   ├── workstation-en-el-armazon.md          # el puesto, absorbido
│   └── feedback-taxonomia.md                 # qué mecanismo para qué caso
├── checklists/requirements.md
└── tasks.md                                  # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/desktop/
├── src/electron/
│   ├── main.ts                 # ventana, vistas, franja, menú, tema, ciclo de vida
│   ├── shell-layout.ts         # NUEVO: rectángulos de las vistas (puro, con test)
│   ├── app-surface.ts          # canales; absorbe los del puesto
│   ├── updater.ts              # cableado del aviso de versión nueva
│   └── adapters.ts             # avisos del sistema, badge, diálogos nativos
├── src/
│   ├── app-ipc.ts              # contrato de canales (enmendado)
│   ├── waiting.ts              # NUEVO: derivado único de «lo que te espera»
│   ├── workstation-state.ts    # ex bar-state.ts: estados del puesto (puro)
│   ├── setup-checklist.ts      # NUEVO: pasos de puesta en marcha (puro)
│   ├── sign-in-state.ts        # NUEVO: estados de la entrada por navegador
│   ├── handoff-state.ts        # NUEVO: traspaso al navegador y vuelta
│   └── app/
│       ├── shell/              # NUEVO: franja, lista lateral, panel, atajos, búsqueda
│       ├── routes/             # hoy · pendientes · teammate · cuenta · puesta en marcha
│       └── feedback/           # NUEVO: la API de avisos y sus mecanismos
└── tests/                      # unidad, contraste, accesibilidad, humo del binario

packages/ui/src/
├── styles/tokens.css           # tinta oscura, foco ≥3:1, densidad de escritorio
├── components/                 # sidebar, panel redimensionable, lista virtual, toaster sin next-themes
└── __tests__/contrast.test.ts  # NUEVO: pares declarados en ambos temas

packages/companion-ui/src/      # glosario por contexto (teammate, no «Companion»), scroll del hilo

apps/console/src/
├── app/(console)/layout.tsx    # modo embebido: sin armazón propio
├── lib/shell.ts · lib/shell-ua.ts   # detección por user-agent (ampliada, con test)
└── components/shell/nav.ts     # la navegación que la lista lateral de la app replica
```

**Structure Decision**: se conserva el monorepo tal cual. El armazón vive en
`apps/desktop`; todo lo reutilizable (tokens, primitivas, densidad, toaster) baja
a `packages/ui` para que consola y panel de operador hereden el mismo sistema; el
vocabulario del hilo se parametriza en `packages/companion-ui`. `apps/console`
solo recibe el modo embebido.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Dos enmiendas de contrato (002 y 003) | Una sola navegación exige que la pantalla sepa dónde está la consola; absorber el puesto exige mover sus capacidades | Mantener las tres superficies (plan B) deja en pie el problema que la spec existe para resolver; el spike demostró que no hace falta |
| Cambiar tokens compartidos (alcanza a consola y panel de operador) | El contraste actual incumple AA en pares medidos, y dos tipografías conviven en la misma ventana | Tokens solo para escritorio crearía dos sistemas de diseño divergentes, justo lo que `packages/ui` existe para evitar |
| Un humo del binario empaquetado con herramienta marcada como experimental | Los fallos que más han dolido (actualizador que no arrancaba, paquete que se tragaba su salida) **solo aparecen empaquetado y firmado** | Probar solo en desarrollo es lo que dejó pasar esos fallos |

## Post-diseño: Constitution Check revisitado

Tras la Fase 1 (contratos y modelo de datos), las nueve filas siguen en ✅. Tres
comprobaciones explícitas del diseño:

1. **§I/§II** — `contracts/desktop-app-ipc-v2.md` no introduce ningún canal que
   acepte `tenant_id`, ni credenciales, ni contenido de cliente final; la
   redacción de claves sensibles sigue aplicándose a todo lo que sale.
2. **§IV** — ningún canal nuevo aprueba nada: los de decisión siguen siendo los
   existentes, y el aviso del sistema solo **enfoca**.
3. **§V** — `data-model.md` §5 lista, pantalla por pantalla, qué estado se pinta
   en cada caso y cuál es su salida; sin esa tabla, «la ausencia se diseña» no
   sería comprobable.
