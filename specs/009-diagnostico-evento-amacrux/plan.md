# Implementation Plan: Diagnóstico IA de Amacrux para el evento (QR)

**Branch**: `DEMO-AMACRUX-EVENT` (spec dir `009-diagnostico-evento-amacrux`) | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-diagnostico-evento-amacrux/spec.md`

## Summary

Web pública mobile-first para un evento: wizard de 12 preguntas en 6 pantallas,
motor de recomendaciones **determinista y local** (catálogo de 24 oportunidades,
8 categorías), segmentación en 5 dimensiones y puntuación 0–100 interna,
resultado con 3 oportunidades explicadas, y captura de lead opcional entregada
por correo desde el servidor (Resend) con modo demostración local. Se construye
como aplicación Next.js aislada en `apps/amacrux-event` con su propio workspace
pnpm, sin dependencia de `@nexus/ui` ni de la API de Nexus.

## Technical Context

**Language/Version**: TypeScript 5.9 (strict, `noUncheckedIndexedAccess`), Node 22 · **Runtime**: Next.js 16.2 App Router, React 19.2

**Primary Dependencies**: `next`, `react`, `react-dom`, `zod` 3.25, `react-hook-form` 7 + `@hookform/resolvers`, `resend` 6, `tailwindcss` 4 + `@tailwindcss/postcss`. Fuentes vía `next/font/google` (Outfit, Inter). Dev: `vitest` 4, `@vitejs/plugin-react`, `jsdom`, `@testing-library/{react,jest-dom,user-event}`, `eslint` 9 + `eslint-config-next`, `typescript`, `@types/*`

**Storage**: ninguno en servidor. `sessionStorage` (respuestas y paso, sin PII) con esquema Zod versionado; el lead solo en memoria hasta el envío

**Testing**: Vitest + Testing Library (jsdom) para dominio y UI; pruebas del Route Handler llamando a la función `POST` con `Request` reales; verificación manual E2E con el navegador integrado (360/768/1280, dark mode) y `curl`

**Target Platform**: navegadores móviles y de escritorio modernos (2 últimos años); despliegue en Vercel (Root Directory `apps/amacrux-event`), un proyecto por entorno

**Project Type**: web app (frontend estático + un Route Handler)

**Performance Goals**: bienvenida < 3 s en 4G (LCP), JS inicial < 120 kB gz, resultado calculado en < 50 ms en el dispositivo, procesamiento visual 1,2–2 s

**Constraints**: sin secretos en cliente; sin llamadas de red hasta el envío del lead; sin PII en URLs/analítica/logs; sin CORS (mismo origen); accesible AA; `prefers-reduced-motion`; funciona con `sessionStorage` bloqueado

**Scale/Scope**: cientos de visitantes en 1–2 días; 14 pantallas/estados; ~24 oportunidades; 12 preguntas; 1 endpoint

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants | ☑ N/A | No hay tenant, RLS ni herramientas: la app no toca la plataforma Nexus ni su base de datos. Prueba: `grep -r "NEXUS_\|api.auphere" apps/amacrux-event/src` vacío (tarea de verificación) |
| II | Corte por superficie de confianza | ☑ | Superficie declarada en la spec: **ninguna de agente**; web pública + correo saliente. No se abre superficie nueva |
| III | Lo leído es dato, nunca instrucción | ☑ | No hay modelo de IA en runtime. Todo dato de entrada se valida con Zod en servidor (`/api/leads`) y en cliente; el motor solo lee enums cerrados |
| IV | Acción `mutates` con aprobación durable | ☑ N/A | La única mutación es el envío de un correo iniciado por la propia persona con consentimiento explícito; idempotente por `idempotencyKey` |
| V | Estados honestos; la ausencia se diseña | ☑ | Estados `normal · cargando · vacío · error` en wizard, resultado y formulario; modo demostración honesto; sin botones apagados por capacidad ausente (compartir/analítica) |
| VI | Por API, nunca navegando la consola | ☑ N/A | No hay agente ni consola implicados |
| VII | Test primero; el test es el criterio | ☑ | Tests de dominio (scoring, segmentación, motor, validación), de UI (navegación, persistencia, duplicados, errores) y del endpoint, escritos en rojo antes de cada implementación (tasks.md) |
| VIII | Licencias leídas | ☑ | Todas MIT/Apache-2.0/OFL, ver tabla abajo. Ninguna AGPL ni "Apache modificada" |
| IX | La KB es dueña del porqué | ☑ | `[[Auphere/partnerships/amacrux-diagnostico-evento/amacrux-diagnostico-evento]]` en `/Users/matos/workspace/kb/` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía tocada (no hay tenant ni datos en Nexus). Se sustituye por una prueba de **no acoplamiento**: la app no importa nada de `apps/api`, `packages/ui` ni usa variables `NEXUS_*` | `T008` (script `check-no-env-leaks.mjs` + grep en `pnpm check`) |
| **Licencias** | Dependencias nuevas (todas en el workspace propio, no en el lockfile raíz): ver tabla | `T007` (`docs/DECISIONS.md` §Licencias) |
| **Medidor** | Nada: sin modelo, sin reloj de máquina, sin herramienta de pago. El correo vía Resend es coste del partner y se documenta en `CONFIG.md` | — (se documenta, no hay medidor que conectar) |

#### Licencias de las dependencias nuevas (§VIII)

| Paquete | Licencia | Párrafo que permite el uso como servicio |
|---|---|---|
| next, react, react-dom, zod, react-hook-form, @hookform/resolvers, resend, tailwindcss, @tailwindcss/postcss, vitest, @vitejs/plugin-react, jsdom, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, eslint, eslint-config-next, @types/node, @types/react, @types/react-dom | MIT | "Permission is hereby granted, free of charge, to any person obtaining a copy of this software […] to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies" |
| typescript | Apache-2.0 | §2 "grant […] a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute" |
| Fuentes Outfit e Inter (Google Fonts, vía `next/font`) | SIL OFL 1.1 | "The OFL allows the licensed fonts to be used, studied, modified and redistributed freely as long as they are not sold by themselves" |

**Complejidad que hay que justificar:** ninguna añadida sobre la spec. La
interfaz `RecommendationProvider` y `LeadRepository` las pide la spec
(Req. 5.9 y 9.6).

## Project Structure

### Documentation (this feature)

```text
specs/009-diagnostico-evento-amacrux/
├── spec.md              # Especificación (EARS)
├── plan.md              # Este fichero
├── research.md          # Fase 0: decisiones y alternativas
├── data-model.md        # Fase 1: entidades, enums, validación, transiciones
├── quickstart.md        # Fase 1: cómo arrancar y validar de punta a punta
├── contracts/
│   ├── leads-api.md     # POST /api/leads, GET /api/health
│   ├── analytics-events.md
│   └── result-schema.md # Forma del resultado y del catálogo
├── checklists/requirements.md
└── tasks.md             # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/amacrux-event/
├── package.json                 # name "amacrux-event"; dev/build/start/lint/typecheck/test/check
├── pnpm-workspace.yaml          # workspace propio: packages: ["."]
├── pnpm-lock.yaml
├── .npmrc                       # auto-install-peers, strict-peer-dependencies=false
├── next.config.ts               # cabeceras de seguridad, reactStrictMode, poweredByHeader=false
├── tsconfig.json                # copiado de apps/console (strict, noUncheckedIndexedAccess)
├── postcss.config.mjs           # @tailwindcss/postcss
├── eslint.config.mjs            # next core-web-vitals + typescript (sin plugin nexus-ui)
├── vitest.config.ts / vitest.setup.ts
├── vercel.json
├── .env.example
├── README.md
├── scripts/check-no-env-leaks.mjs
├── public/brand/                # wordmark-{navy,turquoise,white}.png, isotipo-hex-*.png, mark-*.png
├── docs/                        # INSTALL, CONFIG, DECISIONS, TODO-COMERCIAL, EVENT-GUIDE, PUBLISH-CHECKLIST
└── src/
    ├── app/
    │   ├── layout.tsx           # fuentes, metadata/OG, theme-color, skip link, footer
    │   ├── page.tsx             # bienvenida
    │   ├── eventos/[slug]/page.tsx
    │   ├── diagnostico/page.tsx # wizard (client)
    │   ├── privacidad/page.tsx
    │   ├── not-found.tsx · error.tsx · opengraph-image.tsx · icon.png · apple-icon.png
    │   └── api/leads/route.ts · api/health/route.ts
    ├── domain/                  # lógica pura, sin React
    │   ├── types.ts · enums.ts · questions.ts · opportunities.ts
    │   ├── segmentation.ts · scoring.ts · engine.ts · copy.ts · validation.ts
    │   └── __tests__/
    ├── lib/
    │   ├── storage.ts · analytics.ts · env.ts · share.ts · idempotency.ts
    │   ├── leads/repository.ts · leads/email.ts · recommendation-provider.ts
    │   └── __tests__/
    ├── components/
    │   ├── layout/ (AppShell, Header, Footer, SkipLink)
    │   ├── ui/ (Button, OptionCard, OptionGrid, LevelScale, ProgressBar, Badge, Callout, Skeleton, Toast, Dialog, TextField, Checkbox, BrandMark)
    │   ├── wizard/ (Wizard, wizard-reducer.ts, StepQuestion, StepNav, ProcessingScreen)
    │   ├── result/ (ResultView, ResultSummary, OpportunityLevel, RecommendationCard, NextSteps, Warnings, ResultCta, ShareResult)
    │   ├── lead/ (LeadForm, LeadSkip, LeadConfirmation)
    │   ├── welcome/ (Hero, WhatYouGet, TrustNote)
    │   └── __tests__/
    └── styles/ (globals.css, tokens.css)
```

**Structure Decision**: aplicación web única y aislada en `apps/amacrux-event`
con workspace pnpm propio (patrón `apps/admin`), sin entrar en el
`pnpm-workspace.yaml` raíz ni en su lockfile. Dominio en `src/domain` sin React
para que scoring, segmentación y motor se prueben como funciones puras.

## Complexity Tracking

Sin violaciones que justificar.
