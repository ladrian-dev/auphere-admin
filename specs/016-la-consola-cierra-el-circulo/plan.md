# Implementation Plan: la consola cierra el círculo

**Branch**: `016-la-consola-cierra-el-circulo` | **Date**: 2026-09-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-la-consola-cierra-el-circulo/spec.md`

## Summary

Un partner deja a un cliente atendiendo sin que Auphere intervenga. La mayor parte es **la mitad barata de superficies ya abiertas**: renderizar el Embedded Signup de WhatsApp que ya existe y activar el tenant al volver; una transacción para mover cupo; una definición única de «sin cupo» que pinta ficha, lista y portada y emite un aviso en el momento del turno saltado; separar publicar de activar en el alta; una tarjeta de modelo sobre un endpoint que ya existe; enlazar la agenda pública de AgendaPro desde la consola (lo único que hoy atiende citas — ver R6 en `research.md`); sincronizar al guardar una clave y traducir sus campos; y `can()` más un test permitido/denegado en cada una de las 69 acciones de servidor. Sin dependencias nuevas, sin tablas nuevas, una migración de vocabulario de auditoría.

## Technical Context

**Language/Version**: Python 3.11 (`apps/api`, `apps/worker`, `apps/channels`, `apps/mcp`), TypeScript 5.9 / React 19 / Next.js 16 (`apps/console`), Node ≥ 22.12 para Vite 8 (en esta máquina 22.11 + `NODE_OPTIONS=--experimental-require-module`)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Redis, LangGraph (worker); `@nexus/ui` (Base UI + Tailwind v4), react-hook-form + zod, sonner; SDK de Meta ya integrado (`lib/meta-fb-sdk.ts`). **Ninguna dependencia nueva.**

**Storage**: PostgreSQL (Aurora en prod) con RLS forzada por tenant y por partner; Redis para caché y streams. Sin migración de esquema; una migración de datos (vocabulario de auditoría).

**Testing**: pytest (`unit`, `integration`, `isolation` — esta última bloquea el merge), Vitest (consola y `@nexus/ui`), Playwright + axe (consola real). Test primero en cada requisito (§VII).

**Target Platform**: consola en Vercel (Next standalone), API y workers en AWS ECS `eu-south-2`.

**Project Type**: monorepo web (API + workers Python, consola Next.js BFF sin base de datos).

**Performance Goals**: «sin cupo» visible en < 60 s desde el turno saltado (CE-002); lista de clientes con el estado de cupo en **una** consulta por página (lote por partner), no una por cliente; mover cupo en una transacción corta (dos filas bloqueadas).

**Constraints**: `partner_allocations` es FORCE RLS por `app.partner_id` — no se lee desde una sesión de tenant; `evaluate_partner_wallet_alerts` exige sesión sin transacción abierta; el `code` de Meta es de un solo uso; nada de credenciales en logs, auditoría ni respuestas; la consola nunca guarda credenciales de backend.

**Scale/Scope**: 2 partners y 3 clientes en producción hoy; diseño válido para cientos de clientes por partner (lote por partner, dedupe por cliente/día). 8 requisitos, ~25 ficheros tocados en la API/worker y ~30 en la consola.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.
Una fila en rojo detiene el plan: se corrige el diseño o se enmienda la constitución.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Ningún endpoint nuevo acepta `tenant_id`/`partner_id`; `move` resuelve los dos refs por `PartnerTenant` del principal y bloquea filas FORCE-RLS por partner; `quota_state` usa sesión de partner; AgendaPro y conectores encienden herramientas solo del tenant (`auto_enable_connector_tools`). Tests: `tests/isolation/test_24_partner_wallet_rls.py` (ampliar con `move` cruzado), `test_console_scope.py` (nuevos endpoints en la barrida de 404 opaco), `test_16_model_binding_scoped.py` |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0` declarada en la spec. R6 se reescribe precisamente para **no** abrir la superficie `1` (navegador con credenciales): la URL pública es la mitad barata que ya está abierta |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | No se añade lectura de contenido externo al agente; la URL de AgendaPro es configuración, no instrucción; la consola no muestra `detail` crudo del backend (`actionErrorText`) |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Conectar canal, mover cupo, cambiar modelo, enlazar agenda y conectar conector escriben `audit_log` con el principal (`console:{email}`); mover cupo y desenlazar piden confirmación en pantalla. Ninguna entra en la lista cerrada de aprobaciones durables (borrar, rotar claves, apagar la revelación) |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Sin claves de Meta: nota, no botón; `last_sync: error` es un estado, no un toast; «sin cupo» es un estado con nombre en tres pantallas; AgendaPro sin runtime de credenciales **no** ofrece un formulario que promete lo que no hace |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | Todo por `/console/*`; el navegador de Meta es el del proveedor, no la consola |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio N.m tiene su test en `tasks.md`; `companion.spec` se salta solo por flag de partner, no por comodidad |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Dependencias nuevas: **ninguna** |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]`, `[[nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22]]`; la desviación de R6 se anota en la KB al aprobarse |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | 1 (RLS: cupo por partner, canal/modelo/URL por tenant), 2 (whitelist: herramientas encendidas por conector), 4 (rastro: cinco acciones auditadas), 6 (logs sin tokens ni URLs con secretos) | `T-ISO-*` en `tests/isolation/` (move cruzado entre partners → 404 y suma intacta; endpoints nuevos en la barrida de 404 opaco; modelo de otro partner) |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | — (se verifica con `pnpm-lock.yaml` y `uv.lock` sin cambios) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada nuevo: los turnos siguen midiéndose (spec 004); el modelo cambia el peso por turno (spec 007) y el partner lo ve como «×N créditos» antes de elegir | `T-MOD-*` (relative_cost en `GET /console/models` y en la tarjeta) |

**Complejidad que hay que justificar:** ninguna fuera de lo que la spec pide. La única desviación es de **alcance** (R6), documentada en `research.md` y en la spec.

## Project Structure

### Documentation (this feature)

```text
specs/016-la-consola-cierra-el-circulo/
├── plan.md              # este fichero
├── research.md          # Fase 0: decisiones R1–R8 + vocabulario de auditoría
├── data-model.md        # Fase 1: entidades tocadas y transiciones
├── quickstart.md        # Fase 1: cómo validar
├── contracts/
│   ├── console-api.md   # endpoints nuevos/cambiados
│   └── console-screens.md
├── checklists/requirements.md
└── tasks.md             # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
apps/api/src/nexus_api/
├── api/console/
│   ├── whatsapp.py            # + activate_tenant_if_ready, 409 number_in_use, health en la respuesta
│   ├── wallet.py              # + POST /wallet/allocations/move
│   ├── tenants.py             # health con "quota" (lote por partner)
│   ├── home.py                # issues con out_of_quota
│   ├── deps.py                # client_health(out_of_quota=…)
│   ├── models.py              # relative_cost, allowed, auditoría
│   ├── integrations.py        # NUEVO: PUT …/integrations/agendapro/public-url
│   └── tools.py               # api-key sincroniza; ConnectorOut.last_sync; AgendaPro como public_url
├── metering/wallet.py         # move_allocation, quota_state (lote)
├── services/
│   ├── wallet_alerts.py       # notify_client_out_of_quota_detached, clients_without_quota vía quota_state
│   ├── console_notifications.py # kinds client.out_of_quota, client.model_reset
│   └── connectors/service.py  # sync tras api-key (reutiliza sync_tools_for)
├── db/models/console_notification.py
└── alembic/versions/0128_console_audit_vocab_016.py
apps/worker/src/nexus_worker/runtime/dispatcher.py   # turno saltado → aviso
apps/api/tests/{unit,integration,isolation}/…        # un test por criterio

apps/console/src/
├── app/(console)/clients/[ref]/channels/page.tsx    # WhatsAppConnect real / nota de ausencia
├── components/channels/whatsapp-connect-by-auphere.tsx  # NUEVO (sustituye a -unavailable)
├── app/(console)/usage/{actions.ts,move-allocation.tsx}  # una llamada
├── lib/backend/{home-usage.ts,models.ts(NUEVO),agent-tools.ts,channels.ts}
├── app/(console)/clients/[ref]/page.tsx             # missing con enlaces, "sin cupo"
├── components/clients/clients-table.tsx             # punto "sin cupo"
├── app/(console)/page.tsx                           # incidencia out_of_quota
├── app/(console)/clients/new/{actions.ts,wizard.tsx,wizard-state.ts}  # etapa activate
├── components/agent-tools/{model-picker.tsx(NUEVO),tools-catalog.tsx,lib.ts}
├── app/(console)/clients/[ref]/agent/settings/page.tsx  # tarjeta Modelo
├── app/(console)/clients/[ref]/tools/actions.ts     # setAgendaProUrlAction, connectApiKey con last_sync
├── components/notifications/render.ts               # dos tipos nuevos
├── i18n/lanes/{channels,home-usage,agent-tools,onboarding}.ts
├── src/test/actions.ts                              # NUEVO: ayudante para probar acciones
└── app/**/__tests__/*.actions.test.ts               # 69 acciones × permitido/denegado
infra/README-console.md                              # nombres reales de NEXUS_META_*
```

**Structure Decision**: monorepo existente; cada requisito toca la API (y el worker en R3) y la consola en su carril. No se crea ningún paquete ni servicio nuevo.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

## Re-evaluación tras el diseño

Las nueve filas siguen en verde. El diseño de R6 **reduce** riesgo respecto a la spec original (no guarda credenciales de cliente final sin consumidor). La desviación queda escrita en `spec.md` §Clarificaciones para que el owner la confirme antes de `/speckit-implement`; si prefiere el formulario de credenciales, es una spec aparte (superficie `1`, Browserbase, licencias y medidor nuevos).
