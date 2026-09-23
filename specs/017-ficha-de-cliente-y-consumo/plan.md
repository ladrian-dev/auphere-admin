# Implementation Plan: la ficha de cliente y el consumo, por flujo

**Branch**: `017-ficha-de-cliente-y-consumo` | **Date**: 2026-09-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-ficha-de-cliente-y-consumo/spec.md`

## Summary

Rediseñar la consola por flujo para un partner externo sin perder ningún dato
ni acción: cabecera de la ficha con los cuatro pasos de puesta en marcha y el
cupo, navegación en tres grupos filtrados por rol, barra de borrador que publica
desde cualquier pestaña, una sola pantalla de Capacidades agrupada por función y
filtrada por sector con Integraciones delante, Consumo en créditos en tres
bloques, alta de tres pasos que termina en la ficha, portada con una sola lista
de tareas, lista de clientes que dice quién está listo, Ajustes del agente por
secciones y lenguaje de negocio con ayuda alcanzable. Técnicamente: **ninguna
tabla nueva**; seis lecturas derivadas en la API (`sector`, `setup`, `quota`,
`conversations_7d`, `draft_screens` + `draft-diff`, `equivalence`), dos
endpoints de escritura nuevos (`PUT …/capabilities`, `PUT /billing/email`),
una migración de vocabulario de auditoría, y en la consola pantallas nuevas
sobre los bloques del Bloque C más cuatro bloques nuevos en `@nexus/ui`
(`NavTabs`, `DraftBar`, `RowActions`, `Kbd`). Se entrega en **siete
iteraciones**, una pantalla por iteración, cada una con prototipo aprobado,
tabla de paridad completa y suites en verde.

## Technical Context

**Language/Version**: TypeScript 5 / React 19 / Next.js 16 (App Router) en `apps/console`; Python 3.14 / FastAPI / SQLAlchemy async en `apps/api`.

**Primary Dependencies**: `@nexus/ui` (Base UI + Tailwind v4, tokens OKLCH), lucide-react, zod, sonner; FastAPI, Pydantic v2, Alembic. **Ninguna dependencia nueva.**

**Storage**: PostgreSQL (RLS por tenant y por partner). Sin cambios de esquema; una migración de datos (`0129`, vocabulario de auditoría).

**Testing**: Vitest + Testing Library (consola y `@nexus/ui`), Playwright + axe (21 vistas, ES/EN, 360/1 920 px, +30 % de texto), pytest (unit, integration, `tests/isolation`), Storybook addon-a11y en modo error para los prototipos.

**Target Platform**: web (Vercel para la consola, AWS ECS para la API); la app de escritorio comparte `@nexus/ui`, así que los bloques nuevos no rompen su CSP (nada que inyecte `<style>`).

**Project Type**: monorepo web (frontend BFF + API).

**Performance Goals**: la lista de clientes y la ficha no añaden consultas por fila (tres consultas agrupadas por página); la barra de borrador no pide el diff hasta abrirse; Capacidades carga en una llamada.

**Constraints**: constitución §V (la ausencia se diseña: nada apagado), §VII (test primero), §VIII (sin dependencias), lint propio de `@nexus/ui` (radios del enum, sin hex, sin medios pasos), copy ES/EN en lanes, `can()` en cada acción de servidor con test en el arnés `actions.ts`.

**Scale/Scope**: 12 requisitos, ~10 pantallas tocadas, 4 bloques DS nuevos, 2 endpoints nuevos + 1 de lectura nueva + 5 ampliados; estimación del plan de acción: 5–8 días por iteraciones.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.
Una fila en rojo detiene el plan: se corrige el diseño o se enmienda la constitución.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Ningún endpoint nuevo acepta `tenant_id`/`partner_id`; `capabilities` resuelve el tenant por `client_scope(ref)` y escribe la lista blanca **solo** de ese `AgentConfig`; `setup`/`quota`/`conversations_7d` de la lista se calculan sobre los tenants del partner (`PartnerTenant`) con sesión de partner; el filtro por sector es una vista sobre el catálogo común, no un permiso. Tests: `tests/isolation/test_console_scope.py` (endpoints nuevos en la barrida de 404 opaco), `test_2_tool_whitelist_contract.py` (la lista blanca escrita por `capabilities` es subconjunto del catálogo), `test_24_partner_wallet_rls.py` (equivalencia y reparto por partner), `test_20_usage_records_rls.py` (media de 30 días por partner) |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0` declarada; todo es lectura o escritura sobre `/console/*` |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | Los nombres de negocio y el glosario son copy del repo, no contenido externo; el diff del borrador se muestra como texto, nunca se ejecuta; ningún `detail` crudo del backend llega a pantalla (`actionErrorText`) |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Activar/desactivar capacidad (`console.capability.update`), publicar desde la barra (`console.agent.publish` con `from`), cambiar correo de facturación (`console.billing.email_update`) escriben `audit_log` con `console:{email}`; publicar, eliminar y mover cupo conservan sus confirmaciones. Ninguna entra en la lista de aprobaciones durables |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Sin sector: se dice y se muestra todo; capacidad no disponible: no hay conmutador apagado, hay motivo en «Ver todas»; saldo ilegible: Saldo lo dice, el resto sigue, equivalencia «≈ —»; rol sin permiso: sin botón, y la barra de borrador dice quién puede; el Playground nunca pinta un fallo como completado |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | El Companion sigue usando `console.list_tools`/`list_skills` y gana `console.get_capabilities` sobre el mismo endpoint; nada navega la consola |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio N.m tendrá su tarea de test en `tasks.md` antes de la de implementación; render tests por pantalla y rol; e2e por iteración; prototipos con axe antes del código |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Dependencias nuevas: **ninguna** (`Intl.*` del navegador para zonas e idiomas) |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]` (Bloque D, decisiones 3–5) y `[[nexus/AUDITORIA-UX-CONSOLA-2026-09-22]]`; cada iteración deja su log de sesión y las tres clarificaciones se anotan en el plan de acción |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | 1 (RLS: setup, cupo, borrador, capacidades y conversaciones por tenant dentro del partner) y 2 (whitelist por agente: `capabilities` enciende solo para ese tenant y solo del catálogo) | `T-ISO-*` en `tests/isolation/`: endpoints nuevos en `test_console_scope.py`; escritura de capacidades cruzada → 404 y lista blanca intacta; lista de clientes de otro partner nunca aparece |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | — (se verifica con `pnpm-lock.yaml` y `uv.lock` sin cambios al cerrar cada iteración) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada nuevo; «créditos» es el nombre en pantalla de la unidad que ya se descuenta y `equivalence` es una conversión de lectura | `T-USE-*` (Saldo muestra créditos y equivalencia con `basis`) |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/017-ficha-de-cliente-y-consumo/
├── spec.md              # clarificada (3 preguntas)
├── plan.md              # este fichero
├── research.md          # Fase 0: 12 decisiones
├── data-model.md        # Fase 1: sin esquema nuevo; entidades expuestas
├── parity.md            # R12.1: tabla antes → después por pantalla
├── quickstart.md        # cómo demostrar cada iteración
├── contracts/
│   ├── console-api.md   # endpoints nuevos y ampliados
│   └── console-screens.md
├── evidence/            # iteracion-N.md con prototipo aprobado y capturas
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/nexus_api/
├── api/console/
│   ├── tenants.py            # ClientOut/ClientSummaryOut: sector, setup, quota, conversations_7d
│   ├── deps.py               # client_setup(), sector_of()
│   ├── agents.py             # draft_screens; GET agent/draft-diff
│   ├── agent_drafts.py       # diff por pantalla (settings, capabilities, knowledge, prompt)
│   ├── capabilities_client.py  # GET/PUT clients/{ref}/capabilities (nuevo; no confundir con capabilities.py del Companion)
│   ├── capability_names.py   # mapa función + nombre de negocio ES/EN por nombre técnico (nuevo)
│   ├── wallet.py             # equivalence; allocations con client_name/consumed
│   ├── audit.py              # ?category=; vocabulary.categories
│   ├── billing.py            # PUT /billing/email
│   ├── playground.py         # título por fecha
│   └── schemas*.py
├── db/migrations/…/0129_console_audit_vocab_017.py
└── companion/tools/catalog.py  # console.get_capabilities

apps/api/tests/
├── integration/test_console_capabilities.py, test_console_draft_diff.py, test_console_client_setup.py, test_console_wallet_equivalence.py, test_console_billing_email.py, test_console_audit_category.py
├── unit/test_capability_names.py, test_console_audit_vocab_017.py
└── isolation/test_console_scope.py (+ nuevos), test_42_capabilities_whitelist_scoped.py

packages/ui/src/components/
├── nav-tabs.tsx, draft-bar.tsx, row-actions.tsx, kbd.tsx   # bloques nuevos, con story y test
└── stories/prototypes/*.stories.tsx                       # un prototipo por iteración

apps/console/src/
├── app/(console)/clients/[ref]/
│   ├── layout.tsx            # cabecera nueva (setup, cupo, Más) + NavTabs + DraftBar
│   ├── capabilities/page.tsx, integrations/page.tsx      # nuevas
│   ├── tools/page.tsx, skills/page.tsx                   # redirect a capabilities
│   ├── agent/settings/*      # secciones plegables (it. 6)
│   └── settings/page.tsx     # Datos + Zona de peligro (it. 7)
├── app/(console)/usage/*     # tres bloques; alerts → redirect a #alerts (it. 3)
├── app/(console)/clients/new/*   # tres pasos (it. 4)
├── app/(console)/page.tsx, clients/page.tsx              # (it. 5)
├── app/(console)/ayuda/page.tsx                          # glosario (it. 7)
├── components/clients/{client-header.tsx, setup-steps.tsx, client-nav.tsx, draft-bar-client.tsx, draft-diff-sheet.tsx}
├── components/capabilities/{catalog.tsx, capability-card.tsx, integrations-list.tsx}
├── components/usage/{balance.tsx, allocation-rows.tsx, adjust-dialog.tsx}
├── lib/backend/{clients.ts, agent.ts, capabilities.ts, wallet.ts}   # tipos y llamadas
├── i18n/lanes/{clients.ts, capabilities.ts, usage.ts, glossary.ts}
└── e2e/a11y.spec.ts (+ vistas nuevas), e2e/record.spec.ts (recorrido de la ficha)
```

**Structure Decision**: mismo monorepo y mismas carpetas que la 016; lo único
nuevo son módulos dentro de ellas. Los bloques de interfaz reutilizables van a
`packages/ui`; lo que sabe de permisos, i18n o rutas se queda en `apps/console`.

## Iteraciones (orden y contenido)

| # | Pantalla | Requisitos | API | DS nuevo | Cierra con |
|---|---|---|---|---|---|
| 1 | Ficha: cabecera, navegación, barra de borrador | R1, R2, R3, R12 | `sector`, `setup`, `quota`, `draft_screens`, `draft-diff`, `publish.from` | `NavTabs`, `DraftBar` | paridad it. 1 (ya redactada), e2e ficha × 4 roles |
| 2 | Capacidades + Integraciones | R4, R5 | `GET/PUT capabilities`, `capability_names`, 422 `needs_approval`, vocab 0129 | — | paridad Herramientas/Habilidades; Companion `get_capabilities` |
| 3 | Consumo | R6 | `equivalence`, `client_name/consumed`, redirect alerts | `RowActions` | paridad Consumo + Alertas + compra |
| 4 | Alta | R7 | — | — | métrica de clics (CE-003) |
| 5 | Inicio y lista | R8, R9 | `ClientSummaryOut` (setup, quota, conversations_7d); onboarding cuenta solo cliente final | — | paridad portada y lista |
| 6 | Ajustes del agente | R10 | — | `Kbd` (para el índice) | paridad Ajustes |
| 7 | Transversal | R11 | audit `category`, billing email, playground title | — | `/ayuda`, HelpHints, paridad de las cinco pantallas menores |

Cada iteración: prototipo → aprobación del owner → tests rojos → código →
suites en verde → paridad → merge a `develop` → staging → recorrido E2E.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Endpoint `capabilities` **además** de `tools` y `skills` | El Companion y el panel de operador siguen leyendo los dos catálogos; la consola necesita una sola vista con estado por tenant | Componerla en la consola duplica el cálculo «en borrador / en activa» y dobla las llamadas por clic |
| Mapa `capability_names.py` en el repo | Nombres de negocio y funciones son copy del producto, versionado y traducido | Columnas nuevas en `tools` mezclan runtime con copy y no cubren las habilidades |

## Re-evaluación tras el diseño

Las nueve filas siguen en ☑ tras leer `data-model.md` y los contratos: no
entra ninguna columna con `tenant_id` del llamante, ningún endpoint sale de
`/console/*`, no hay dependencias nuevas, y cada escritura nueva deja rastro.
La única complejidad añadida (dos filas arriba) está justificada y acotada a
la iteración 2.
