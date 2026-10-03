# Tasks: Diagnóstico IA de Amacrux para el evento (QR)

**Input**: Design documents from `/specs/009-diagnostico-evento-amacrux/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: obligatorios (constitución §VII). Cada bloque de tests se escribe y se ve en rojo antes de su implementación.

**Organization**: por historia de usuario. Rutas relativas a `apps/amacrux-event/` salvo indicación.

## Reglas de este repo *(constitución)*

- Cada tarea cita sus requisitos con `_Requisitos: N.m_`.
- Cada tarea entregada se anota con `Entregado: …`.
- Test primero (§VII). Aislamiento (§I): ninguna garantía tocada → se sustituye por la prueba de no acoplamiento (T013). Licencias (§VIII): T007. Medidor: nada que conectar (plan).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [x] T001 Crear el esqueleto de la app: `package.json` (name `amacrux-event`, scripts dev/build/start/lint/typecheck/test/check, deps del plan), `pnpm-workspace.yaml` (`packages: ["."]`), `.npmrc`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`, `eslint.config.mjs`, `vitest.config.ts`, `vitest.setup.ts`, `vercel.json`, `.env.example`, `README.md`, `src/app/layout.tsx` y `src/app/page.tsx` mínimos. _Requisitos: 15.3_
- [x] T002 `pnpm install` y `pnpm build` en verde con la app vacía. _Requisitos: 15.3_
- [x] T003 [P] Copiar la marca a `public/brand/` (`wordmark-navy.png`, `wordmark-turquoise.png`, `wordmark-white.png`, `wordmark-gray.png`, `isotipo-hex-turquoise.png`, `isotipo-hex-navy.png`, `isotipo-hex-white.png`, `mark-turquoise.png`, `mark-navy-hex.png`) y generar `src/app/icon.png` (512) y `src/app/apple-icon.png` (180) desde el isotipo hexagonal. _Requisitos: 12.3, 13.1_
- [x] T004 [P] Tokens y base de estilos: `src/styles/tokens.css` (paleta del manual, semánticos, radios, sombras, espaciado, tipografía, dark mode) y `src/styles/globals.css` (Tailwind 4, `@theme`, base accesible, `prefers-reduced-motion`); fuentes Outfit + Inter en `src/app/layout.tsx` vía `next/font/google`. _Requisitos: 13.1, 13.4, 13.5_

**Checkpoint**: la app arranca, compila y muestra la marca.

---

## Phase 2: Foundational

- [x] T005 Enums y tipos del dominio en `src/domain/enums.ts` y `src/domain/types.ts` (data-model.md). _Requisitos: 5.1, 6.1_
- [x] T006 Esquemas Zod en `src/domain/validation.ts`: `AnswersSchema`, `PartialAnswersSchema`, `LeadSchema`, `StoredSessionSchema`, `AnalyticsEventSchema` (strict), `CampaignSchema`. _Requisitos: 4.3, 8.3, 10.6, 11.1_
- [x] T007 [P] `docs/DECISIONS.md` con la tabla de licencias del plan (§VIII) y las decisiones D1–D12. _Requisitos: 15.2_
- [x] T008 [P] `scripts/check-no-env-leaks.mjs`: falla si en `src/` aparece `RESEND_API_KEY`, `LEADS_TO`, `LEADS_FROM`, `NEXUS_`, `sk_` fuera de `src/lib/env.ts` y `src/app/api/**`, o cualquier import de `apps/api`, `packages/ui`, `@nexus/*`; enlazar en `pnpm check`. _Requisitos: 9.2, 10.5_
- [x] T009 [P] `src/lib/env.ts` (público) y `src/lib/env.server.ts` (secretos, solo importable desde `src/app/api/**`; sustituye a `server-only`, que rompe Vitest — DECISIONS D13). _Requisitos: 9.3, 14.2_
- [x] T010 [P] Definición declarativa de preguntas en `src/domain/questions.ts` (12 preguntas, 6 pantallas, etiquetas, descripciones, máximos, agrupaciones visuales de fricciones, minutos estimados por pantalla). _Requisitos: 2.1, 2.5, 3.1_
- [x] T011 [P] Componentes base en `src/components/ui/`: `Button`, `OptionCard`, `OptionGrid` (fieldset/legend, radio/checkbox roles), `LevelScale`, `ProgressBar`, `Badge`, `Callout`, `Skeleton`, `Toast` (aria-live), `Dialog` (`<dialog>` nativo), `TextField`, `Checkbox`, `BrandMark`; y `src/components/layout/` (`AppShell`, `Header`, `Footer`, `SkipLink`). _Requisitos: 13.2, 13.3, 13.4_
- [x] T012 [P] `src/lib/analytics.ts` (`track`, adaptadores `noop|console|plausible`, cola previa a la carga) y `src/lib/storage.ts` (lectura/escritura segura con try/catch, versión, fallback en memoria). _Requisitos: 4.1, 4.5, 11.2, 11.3_

**Checkpoint**: dominio tipado, validación, tokens, componentes base y utilidades listas.

---

## Phase 2b: Las puertas de la constitución

- [x] T013 Test de no acoplamiento en `src/lib/__tests__/no-coupling.test.ts` (mismo criterio que T008 sobre el árbol `src/`) — sustituye al test de aislamiento porque no hay tenant. _Requisitos: 9.2, 10.5_
- T007 cubre la puerta de licencias. La puerta de medidor no aplica (plan §Constitution Check): nada consume modelo, reloj ni herramienta de pago.

---

## Phase 3: User Story 1 — Completar el diagnóstico y ver un resultado útil (P1) 🎯 MVP

**Goal**: de bienvenida a resultado con 3 recomendaciones, sin datos personales.

**Independent Test**: quickstart §Escenario 1 con los perfiles A–D en 360 px.

### Tests for User Story 1 (rojo primero) ⚠️

- [x] T014 [P] [US1] `src/domain/__tests__/opportunities.test.ts`: ≥24 entradas, 8 categorías × ≥3, ids únicos, sin cifras de ROI/garantías, campos obligatorios no vacíos. _Requisitos: 5.1, 5.8_
- [x] T015 [P] [US1] `src/domain/__tests__/segmentation.test.ts`: mapeo de perfil (incl. `otro` por tamaño), niveles de madurez, categorías ordenadas por señales, intención por urgencia/inversión, complejidad. _Requisitos: 6.1_
- [x] T016 [P] [US1] `src/domain/__tests__/scoring.test.ts`: tablas de pesos, suma = total, rangos 30/55/75, `leadTier`, vectores fijos para A–D, reproducibilidad. _Requisitos: 6.2, 6.3, 5.3_
- [x] T017 [P] [US1] `src/domain/__tests__/engine.test.ts`: perfiles A–D → categorías esperadas; exactamente 3; ≤2 por categoría; exclusión por capacidad técnica; penalización y advertencia por madurez; relleno para respuestas mínimas y "otro"; muchas categorías; determinismo; `reasons` cita respuestas; confianza; `validateResult` rechaza ROI/garantías/PII/complejidad. _Requisitos: 5.2–5.9, 6.5_
- [x] T018 [P] [US1] `src/domain/__tests__/questions.test.ts`: 12 preguntas, 6 pantallas, máximos 3 y 2, sin la palabra "madurez" en textos visibles, tiempo estimado total 2–4 min. _Requisitos: 2.1, 2.3, 2.5_
- [x] T019 [US1] `src/components/__tests__/wizard-flow.test.tsx`: recorrer las 6 pantallas con Testing Library, "Continuar" deshabilitado sin respuesta, límite de selección múltiple, pantalla de procesamiento, resultado con 3 tarjetas y CTA. _Requisitos: 1.1, 2.2, 2.3, 2.6, 7.1, 7.2_

### Implementation for User Story 1

- [x] T020 [P] [US1] Catálogo en `src/domain/opportunities.ts` (24 oportunidades, textos con `TODO_COMERCIAL` donde aplique) y `defaultsByProfile`. _Requisitos: 5.1, 5.5, 13.7_
- [x] T021 [P] [US1] `src/domain/segmentation.ts`. _Requisitos: 6.1_
- [x] T022 [P] [US1] `src/domain/scoring.ts` con tablas exportadas. _Requisitos: 6.2, 6.3_
- [x] T023 [P] [US1] `src/domain/copy.ts`: etiquetas legibles de enums, intro por perfil×categoría, corto/medio plazo, advertencias, CTA por intención. _Requisitos: 6.5, 7.2, 5.8_
- [x] T024 [US1] `src/domain/engine.ts` (algoritmo de contracts/result-schema.md) y `src/lib/recommendation-provider.ts` (`RecommendationProvider`, `RulesProvider`, `validateResult`). _Requisitos: 5.2–5.9_
- [x] T025 [US1] `src/components/wizard/wizard-reducer.ts` (pasos, respuestas, progreso, tiempo restante) + `Wizard.tsx`, `StepQuestion.tsx`, `StepNav.tsx`, `ProcessingScreen.tsx`. _Requisitos: 2.2, 2.3, 2.6, 3.1_
- [x] T026 [US1] Resultado: `src/components/result/` (`ResultView`, `ResultSummary`, `OpportunityLevel`, `RecommendationCard`, `NextSteps`, `Warnings`, `ResultCta`). _Requisitos: 7.1–7.3, 6.4_
- [x] T027 [US1] Páginas: `src/app/page.tsx` (bienvenida con `welcome/Hero`, `WhatYouGet`, `TrustNote`), `src/app/eventos/[slug]/page.tsx`, `src/app/diagnostico/page.tsx`, `src/app/privacidad/page.tsx`. _Requisitos: 1.1, 1.2, 12.1, 10.2_
- [x] T028 [US1] Metadata, Open Graph (`src/app/opengraph-image.tsx`), `not-found.tsx`, robots por defecto (index), `theme-color`. _Requisitos: 12.3_

**Checkpoint**: MVP demostrable sin backend.

---

## Phase 4: User Story 2 — Dejar un contacto cualificado (P2)

**Goal**: formulario validado, envío idempotente, correo a Amacrux o modo demo.

**Independent Test**: quickstart §Escenario 5 y `curl` de contracts/leads-api.md.

### Tests for User Story 2 (rojo primero) ⚠️

- [x] T029 [P] [US2] `src/domain/__tests__/validation.test.ts`: `LeadSchema` (límites, email, teléfono opcional, consentimiento literal true, honeypot), `AnswersSchema`, `StoredSessionSchema` versión. _Requisitos: 8.3, 4.3_
- [x] T030 [P] [US2] `src/app/api/leads/__tests__/route.test.ts`: 200 demo, 200 entregado (Resend mockeado), 200 duplicado por idempotencia, 200 honeypot sin envío, 400 inválido con `fields`, 429 tras 5 envíos, 502 fallo de Resend, 503 configuración parcial; los logs no contienen email/nombre. _Requisitos: 9.1–9.5, 10.3, 10.4, 8.7_
- [x] T031 [US2] `src/components/__tests__/lead-form.test.tsx`: errores por campo, botón bloqueado durante envío, doble clic = un solo `saveLead`, error reintentable conserva datos, confirmación, "Prefiero no dejar mis datos" vuelve al resultado. _Requisitos: 8.1–8.6, 7.4_

### Implementation for User Story 2

- [x] T032 [P] [US2] `src/lib/leads/repository.ts` (`LeadRepository`, `LocalLeadRepository`, `HttpLeadRepository` con timeout y clasificación de errores) y `src/lib/idempotency.ts`. _Requisitos: 9.6, 8.4, 8.5_
- [x] T033 [P] [US2] `src/lib/leads/email.ts` (asunto y cuerpo texto/HTML del contrato, etiquetas legibles). _Requisitos: 9.1_
- [x] T034 [US2] `src/app/api/leads/route.ts` (Zod, honeypot, rate limit, idempotencia, Resend, demo, logs sin PII) y `src/app/api/health/route.ts`. _Requisitos: 9.1–9.5, 10.6_
- [x] T035 [US2] `src/components/lead/` (`LeadForm` con react-hook-form + Zod, interés preseleccionado, consentimientos separados, `LeadSkip`, `LeadConfirmation`) e integración en el wizard (`lead` → `confirmation`, `skipContact`). _Requisitos: 8.1–8.7, 7.4, 10.1, 10.2_
- [x] T036 [US2] `docs/fixtures/lead-valid.json` y `docs/CONFIG.md` (variables, modo demo, límites del rate limit en memoria, cómo borrar/anonimizar leads recibidos). _Requisitos: 10.7, 14.2, 15.2_

**Checkpoint**: leads entregados o simulados con honestidad.

---

## Phase 5: User Story 3 — Robustez en el evento (P3)

**Goal**: atrás, recarga, reinicio, storage corrupto, capacidades ausentes, errores.

**Independent Test**: quickstart §Escenarios 2, 3, 6.

### Tests for User Story 3 (rojo primero) ⚠️

- [x] T037 [P] [US3] `src/components/__tests__/wizard-reducer.test.ts`: atrás conserva respuestas, cambiar una anterior conserva las posteriores válidas, reinicio limpia todo, transición `error` conserva `answers`. _Requisitos: 3.2, 3.3, 3.4, 14.3_
- [x] T038 [P] [US3] `src/lib/__tests__/storage.test.ts`: guarda sin PII, restaura, descarta corrupto/versión distinta con aviso, funciona con `sessionStorage` que lanza, nunca guarda `Lead`. _Requisitos: 4.1–4.5_
- [x] T039 [P] [US3] `src/components/__tests__/resilience.test.tsx`: recarga simulada restaura paso; diálogo de reinicio en 2 acciones; sin `navigator.share` no hay botón compartir pero sí copiar; error de generación muestra estado con reintentar/reiniciar. _Requisitos: 3.4, 4.2, 7.4, 14.3_

### Implementation for User Story 3

- [x] T040 [US3] Persistencia en el wizard (hidratación desde `storage.ts`, escritura en cada avance, aviso de datos descartados). _Requisitos: 4.1–4.3_
- [x] T041 [US3] Reinicio: botón en `Header`, `Dialog` de confirmación, limpieza de storage y estado; `assessment_restarted`. _Requisitos: 3.4_
- [x] T042 [US3] Errores: `src/app/error.tsx`, overlay de error en el wizard con reintentar/reiniciar, `error_shown`; timeouts en `HttpLeadRepository`. _Requisitos: 14.3, 8.5_
- [x] T043 [US3] `src/lib/share.ts` + `src/components/result/ShareResult.tsx` (copiar texto; compartir solo si `navigator.share`). _Requisitos: 7.4_

**Checkpoint**: sobrevive a manos ajenas, recargas y fallos.

---

## Phase 6: User Story 4 — QR, campaña y embudo anónimo (P4)

**Goal**: dirección de campaña, UTM en sesión, once eventos sin PII.

**Independent Test**: quickstart con `NEXT_PUBLIC_ANALYTICS=console` y la pestaña Consola.

### Tests for User Story 4 (rojo primero) ⚠️

- [x] T044 [P] [US4] `src/lib/__tests__/analytics.test.ts`: cada evento pasa `AnalyticsEventSchema.strict()`, orden del embudo en un recorrido completo, `noop` no falla, `console` imprime, `plausible` solo si configurado. _Requisitos: 11.1–11.3_
- [x] T045 [P] [US4] `src/lib/__tests__/campaign.test.ts`: parseo de `/eventos/[slug]` y UTM, rechazo de valores fuera de patrón, nunca junto a PII. _Requisitos: 1.3, 12.1, 12.2, 10.3_

### Implementation for User Story 4

- [x] T046 [US4] `src/lib/campaign.ts` + captura en bienvenida y `eventos/[slug]`, guardado en sesión. _Requisitos: 1.3, 12.1, 12.2_
- [x] T047 [US4] Instrumentar `track` en bienvenida, wizard, resultado, formulario, reinicio y errores. _Requisitos: 11.1_
- [x] T048 [US4] Adaptador Plausible (script solo con `NEXT_PUBLIC_ANALYTICS=plausible` y `NEXT_PUBLIC_PLAUSIBLE_DOMAIN`). _Requisitos: 11.2_

---

## Phase 7: Polish & Cross-Cutting

- [x] T049 Revisión responsive y accesibilidad con el navegador integrado (360/768/1280, dark mode, reduced motion, teclado); corregir hallazgos. _Requisitos: 13.2–13.5_
- [x] T050 Rendimiento: tamaño de bundle, imágenes con tamaños fijos, sin red hasta el lead; anotar en `docs/DECISIONS.md`. _Requisitos: 14.1, 14.5_
- [x] T051 [P] Documentación: `docs/INSTALL.md`, `docs/EVENT-GUIDE.md` (perfiles A–D paso a paso, QR, modo demo, reinicio), `docs/TODO-COMERCIAL.md`, `docs/PUBLISH-CHECKLIST.md`, `README.md`. _Requisitos: 15.2_
- [x] T052 [P] Session log en la KB: `kb/Auphere/partnerships/amacrux-diagnostico-evento/sessions/2026-09-16-spec-y-mvp.md` y actualizar `last-session`. _Requisitos: 15.2_
- [x] T053 `pnpm check` y `pnpm build` en verde; ejecutar quickstart completo y anotar resultados. _Requisitos: 15.1, 15.3_
- [ ] T054 (opcional) Job `test-amacrux-event` en `.github/workflows/ci.yml` espejo de `test-console`. _Requisitos: 15.3_

---

**Revisión 2026-09-16 (tras prueba local del usuario)**: wizard rediseñado a una pregunta por pantalla con avance automático y etiquetas cortas (Req. 2.1–2.2), formulario de contacto reducido (Req. 8.2) y sello "Partner oficial de Auphere" (Req. 13.8). Tests actualizados: 88.

**Estado 2026-09-16**: T001–T053 entregadas — Entregado: rama `DEMO-AMACRUX-EVENT`, 2026-09-16 (sin PR). T054 (job de CI) pendiente y opcional. T050: sin Lighthouse en esta máquina; verificado que la bienvenida es estática, no hay peticiones de red hasta el envío del lead y las fuentes van autoalojadas.

## Phase 8: Base de leads en Supabase (v2, 2026-09-16)

- [x] T055 [P] Tests `src/lib/leads/__tests__/store.test.ts` y ampliación de `src/app/api/leads/__tests__/route.test.ts` (rojo primero). _Requisitos: 9.7, 9.8, 9.9, 10.4_
- [x] T056 `src/lib/env.server.ts`: `leadStorageConfig`, `LEADS_TO` múltiple, `destinationsMode`. _Requisitos: 9.7, 9.8_
- [x] T057 `src/lib/leads/store.ts` (`buildLeadRow`, `insertLead`, `markEmailDelivered`, REST sin SDK). _Requisitos: 9.7_
- [x] T058 `src/app/api/leads/route.ts` (guardar → correo → anotar; 200 parcial, 502 total) y `api/health` con `storage`/`email`. _Requisitos: 9.7–9.9_
- [x] T059 `supabase/migrations/0001_leads.sql` (tabla, índices, RLS, vista `leads_panel`, SQL de borrado). _Requisitos: 9.7, 10.7_
- [x] T060 Leak-check con `SUPABASE_`; `SaveOutcome.stored`; docs (CONFIG, PUBLISH-CHECKLIST, .env.example, DECISIONS D17/D18, TODO). _Requisitos: 9.2, 15.2_
- [x] T061 Retirar Cal.com (código, test, evento, docs, spec). _Requisitos: 7.4_
- [x] T063 `docs/n8n-leads-sheet.json` + `docs/leads-sheet-headers.csv` + webhook `LEADS_WEBHOOK_URL` (copia a Google Sheets de Auphere y Amacrux). _Requisitos: 9.10_
- [ ] T062 (usuario) Crear proyecto Supabase, ejecutar migración, variables en Vercel, lead de prueba y verificación en `leads_panel`. _Requisitos: 9.7_

## Dependencies & Execution Order

- Setup (T001–T004) → Foundational (T005–T012) → Puertas (T013, T007) → US1 (T014–T028) → US2 (T029–T036) → US3 (T037–T043) → US4 (T044–T048) → Polish (T049–T054).
- US2, US3 y US4 dependen de US1 (wizard y resultado), pero sus tests de dominio/lib (T029, T030, T038, T044, T045) pueden escribirse en paralelo con US1.
- Dentro de cada historia: tests → dominio → lib → componentes → páginas.

## Parallel Example: User Story 1

```bash
# Tests en paralelo (rojo):
T014 opportunities.test.ts · T015 segmentation.test.ts · T016 scoring.test.ts · T017 engine.test.ts · T018 questions.test.ts
# Implementación en paralelo (ficheros distintos):
T020 opportunities.ts · T021 segmentation.ts · T022 scoring.ts · T023 copy.ts
```

## Implementation Strategy

1. Setup + Foundational + Puertas.
2. US1 completa → demo sin backend (MVP del evento).
3. US2 (leads) → US3 (robustez) → US4 (medición).
4. Polish, documentación, verificación final.

## Notes

- Los commits los ejecuta la persona: el agente entrega los mensajes y para.
- Marcar cada texto pendiente con `TODO_COMERCIAL: validar con Amacrux`.
