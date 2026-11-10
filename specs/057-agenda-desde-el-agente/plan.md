# Plan de implementación: La agenda desde el agente

**Rama**: `057-agenda-desde-el-agente` | **Fecha**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Entrada**: `specs/057-agenda-desde-el-agente/spec.md`, con las cuatro decisiones de Luis del 2026-11-09.

## Resumen

Siete requisitos sobre la API, el worker y la consola de partners, sin abrir ninguna superficie:

- **El alta pregunta «Gestiona citas»** y, si hace falta, enciende Reservas en la misma petición, antes de que el constructor escriba. Con agenda, la v1 lleva las 9 `reservas.*` y procedimientos para reservar. Sin agenda, ninguna (`research.md` R1).
- **«Agenda (Reservas)» en Conectores**: rutas propias `GET`/`PUT …/agenda` y `…/agenda/tools`, que escriben las 9 de una vez y reutilizan el diálogo de herramientas (R2).
- **La propuesta de texto**: un trabajo `agenda_text` en el worker, medido como construcción, que deja una propuesta `agent_spec_patch` del constructor sobre todo lo que habla de citas. Se acepta, se edita o se descarta (R3).
- **Reservas sin terminar**: el turno lee si la agenda está lista; si no, quita las herramientas que buscan o reservan y añade una nota para pasar la cita a una persona. La puerta deja de bloquear por eso y avisa (R4).
- **Encender Reservas solo prepara a quien da citas** (R5), con aviso en la lista de agentes.
- **El aviso «No tenemos herramienta para»** se contrasta con lo que el agente tiene al leerlo (R6). La revisión avisa cuando el texto prohíbe la agenda (R3.8).
- **Encender desde el agente**: un servicio bajo la RLS del cliente, con permiso `agents:write`; apagar sigue en Acceso (R7).

Una migración: el tipo de trabajo `agenda_text` y el motivo de espera `agenda_not_ready`.

## Contexto técnico

**Lenguaje/versión**: Python 3.11 (API y worker, uv). TypeScript con Next.js 16 y React 19 (consola).

**Dependencias principales**: FastAPI, SQLAlchemy 2 y Alembic, LangGraph (worker), LiteLLM (constructor), `@nexus/ui` (Base UI, Tailwind v4, OKLCH). **Ninguna nueva.**

**Almacenamiento**: PostgreSQL con RLS forzada. Una migración (`0229_agenda_from_agent`): `ck_jobs_kind` admite `agenda_text` y `ck_conversations_waiting_reason` admite `agenda_not_ready` (motivo nuevo de la Bandeja, también en la consola y en la app). Sin tablas ni columnas nuevas: la propuesta va en `proposals`, la agenda es la lista de herramientas de la versión, y el módulo, `client_access` + `reservation_settings`.

**Pruebas**:
- pytest: `apps/api/tests/{unit,integration,isolation}` y `apps/worker/tests/unit`.
- Vitest + Testing Library: consola.
- Manual en staging: el recorrido de Spa Jemma (`quickstart.md`).

**Plataforma**: AWS (staging desde `develop`) y Vercel para la consola.

**Tipo de proyecto**: monorepo web: API, worker y consola de partners.

**Rendimiento**:
- `GET …/agenda` y la lista de agentes no añaden más de una consulta por agente.
- El turno lee `agenda_ready` con `session.get` y dos `EXISTS`, nunca `not_ready` completo.
- La propuesta, como mucho lo mismo que «Generar borrador» (p90 < 30 s).

**Restricciones**:
- Sin punto y coma en los textos de la consola (`src/i18n/__tests__/words.test.ts`).
- Sin `tenant_id` ni `partner_id` en los cuerpos.
- Ningún campo de respuesta con nombre de cuerpo de mensaje (`test_console_scope.py`, regla 3).
- Toda acción de servidor con su prueba de permitido y denegado.
- Sin `!important` ni hex en JSX; tokens de `@nexus/ui`.
- Los cinco estados (cargando, vacío, error, parcial, ideal) en `AgendaRow` y en el interruptor del alta.

**Alcance**: 7 requisitos y unas 45 tareas en 3 apps, en `tasks.md`.

## Constitution Check

*Antes de la Fase 0 y repasado después del diseño: todo en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants. `tenant_id` del contexto. Lista blanca exhaustiva | ☑ | Nuevo `tests/isolation/test_057_agenda_from_agent.py`: garantía 1 (otro partner no enciende ni escribe nada) y garantía 2 (encender Reservas no da `reservas.*` a quien no da citas; el filtro de «no lista» quita también de la lista blanca de `dispatch`). `test_console_scope.py` cubre las tres rutas nuevas (se amplía `_minimal_body`). `turn_on_from_agent` corre bajo `nexus_app` con el partner de `scope.mapping` |
| II | Corte por superficie | ☑ | Superficie `0`. No se abre ninguna |
| III | Lo leído es dato | ☑ | La propuesta recibe el AgentSpec y la ficha valladas, como el constructor (`fence`). La nota de «agenda no lista» viaja como `system`, nunca mezclada con lo leído |
| IV | Acción consecuente con persona nombrada | ☑ | Encender Reservas desde un agente pide confirmación (2.3) o va dicho en el alta (1.3) y se audita con `console:<correo>`, el agente y el modo (7.5). La propuesta nunca se aplica sola |
| V | La pantalla no miente; la ausencia se diseña | ☑ | El aviso de lo que falta se recalcula (R6). «La agenda aún no está lista» con sus motivos (4.4). La agenda preparada se ve en la lista (5.3). Sin interruptor si Reservas no se ofrece |
| VI | Por API, nunca navegando la consola | ☑ | No aplica: no hay agentes que operen la consola |
| VII | Test primero | ☑ | Cada tarea de `tasks.md` empieza por su prueba en rojo, con las frases literales de Spa Jemma. Ningún `skip` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | `[[research/2026-11-09-agenda-desde-el-agente]]` y ADR-049 §Enmiendas del 2026-11-09 |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías **1** (RLS: encender y escribir solo en el cliente de la ruta) y **2** (lista blanca por agente: la agenda solo con su interruptor; el filtro de «no lista» también en `dispatch`) | T005 y T006 en `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | **Modelo**: la propuesta del constructor (`agenda_text`) va en `usage_turn(source=SOURCE_BUILDER)`, cuenta en `partner_build_budget` y la frena `require_build_room`. Nada sale de la bolsa del cliente | T024 |

## Estructura del proyecto

### Documentación (esta feature)

```text
specs/057-agenda-desde-el-agente/
├── spec.md
├── plan.md              # este archivo
├── research.md          # decisiones R1–R7 y lo visto en staging
├── data-model.md        # lo que cambia en datos (sin tablas nuevas)
├── contracts/
│   ├── console-api.md   # rutas nuevas y campos nuevos
│   └── events.md        # motivo de traspaso agenda_not_ready y auditoría
├── quickstart.md        # cómo comprobarlo en local y en staging
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Código

```text
apps/api/
├── alembic/versions/0229_agenda_from_agent.py
├── src/nexus_api/
│   ├── api/console/
│   │   ├── agenda.py                    # nuevo: GET/PUT …/agenda, GET …/agenda/tools
│   │   ├── agent_builder.py             # draft-jobs: agenda + reservas; draft_options
│   │   ├── schemas_agent_builder.py     # DraftJobIn, DraftOptionsOut, TemplateOptionOut
│   │   ├── agent_draft_routes.py        # _spec_and_missing recalculado (R6)
│   │   ├── capabilities_client.py       # _set_spec_tools
│   │   ├── agents_list.py               # AgentOut.agenda
│   │   └── __init__.py                  # monta agenda.router
│   ├── services/
│   │   ├── reservations/turn_on.py      # nuevo: turn_on_from_agent
│   │   ├── reservations/passing.py      # gives_appointments, agenda_ready, pass_to_reservas(scope=)
│   │   ├── reservations/admin.py        # apply_choice → givers; admin_view sin operator:%
│   │   ├── reservations/auto_pass.py    # usa la parte común de turn_on
│   │   ├── reservations/settings.py     # suggested_choice
│   │   ├── builder/agent_draft.py       # DraftRequest.agenda, build_messages, sanitize, plantilla, en blanco
│   │   ├── builder/agenda_text.py       # nuevo: la propuesta (modelo y respaldo sin modelo)
│   │   ├── agent_spec/compiler.py       # forbids_agenda
│   │   ├── agent_spec/review.py         # no_hours → warn; agenda_not_ready; forbids_agenda
│   │   ├── agent_spec/missing.py        # still_missing (R6)
│   │   └── proposal_state.py            # ttl por llamada
│   └── db/models/jobs.py                # JOB_KINDS + agenda_text
└── tests/{unit,integration,isolation}/…

apps/worker/src/nexus_worker/
├── jobs/handlers/agenda_text.py         # nuevo, dentro de usage_turn(SOURCE_BUILDER)
├── jobs/handlers/__init__.py
├── runtime/pipeline.py                  # filtro y nota de agenda no lista
├── runtime/booking_brake.py             # no salta tras escalar con la agenda no lista
├── runtime/dispatcher.py                # motivo agenda_not_ready
└── simulation/runner.py                 # agenda_ready: real en playground, True en la suite

apps/console/src/
├── components/builder/builder-new.tsx           # interruptor y modo
├── components/builder/agenda-row.tsx            # nuevo
├── components/builder/agent-connectors.tsx      # AgendaRow primera
├── components/builder/missing-capabilities.tsx  # «Gestionar citas»
├── components/builder/proposals.tsx             # antes/después por bloque, «Editar»
├── components/builder/agent-cards.tsx           # aviso «agenda preparada»
├── components/clients/access/reservas-fields.tsx  # extraído de client-console-card
├── app/(console)/clients/[ref]/agents/agenda-actions.ts  # nuevo
├── lib/backend/agenda.ts                        # nuevo
└── i18n/lanes/agenda.ts                         # nuevo
```

**Decisión de estructura**: el monorepo que ya existe. Una sola ruta nueva en la API (`agenda.py`) en vez de estirar `agent_integrations.py`, porque la agenda no es un conector: no tiene conexión, permiso ni ajustes (`research.md` R2).

## Documentación viva que cambia en el mismo commit que el código

- `docs/agentes.md`: §2 «El constructor» (la agenda en el alta), §4 «La puerta» (`no_hours` a aviso, `agenda_not_ready`, `forbids_agenda`), la propuesta de la agenda y el aviso recalculado.
- `docs/reservas.md`: «Activarlo» (desde el agente; solo los que dan citas) y «El agente» (lo que hace el turno cuando la agenda no está lista).
- `specs/047-la-fabrica-de-agentes/contracts/events.md`: el motivo `agenda_not_ready`.

## Seguimiento de complejidad

| Qué se añade | Por qué | Lo simple que se descartó |
|---|---|---|
| Plazo de 7 días para la propuesta de la agenda | Espera a que el partner la lea; a los 15 minutos ya estaría caducada | Reabrirla como las sugerencias (`suggestions.py:785`): es un apaño que esconde la caducidad |
| Un tipo de trabajo nuevo y su migración | La propuesta llama al modelo y tiene que medirse y no bloquear la petición | El copiloto síncrono: no se mide y tarda lo que tarde el modelo dentro de la petición |
| Leer «agenda lista» en cada turno | 4.3 pide reservar desde el mensaje siguiente; ninguna escritura de Reservas invalida el bundle | Guardarlo en el bundle cacheado: se quedaría viejo |
