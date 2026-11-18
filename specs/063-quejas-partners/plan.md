# Implementation Plan: Las quejas de los partners del 2026-11-18

**Branch**: `063-quejas-partners-2026-11-18` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/063-quejas-partners/spec.md`

## Summary

Cuatro arreglos, cada uno en el sitio donde nace el fallo y sin piezas nuevas:

1. **El idioma** (requisito 1). La regla deja de ser una línea del bloque de
   operación y pasa a ser un mensaje de sistema propio, el último del turno antes
   de la conversación (research D1).
   - Se pinta en tiempo de ejecución, así que llega a todos los agentes publicados
     sin volver a publicarlos.
   - Al ir la última, manda incluso sobre un prompt que diga «Never answer in
     English». Dentro del bloque perdía ante esa frase (0/2); sola y al final acertó
     10/10.
   - Dice «contesta en el idioma del último mensaje del cliente» y, si el partner
     limitó los idiomas, «solo en estos; si no, en el principal».
   - Va siempre, también en agentes sin política de consola (D4).
   - La reescritura del evaluador conserva el idioma (D11).
   - Los idiomas se editan en un solo sitio: «Cómo habla» del AgentSpec, con un
     interruptor nuevo, «Responder solo en estos idiomas».
   - Al guardar, se copian a la política del turno, igual que ya se hace con el
     aviso de IA (D2).
   - Los otros dos sitios que escribían el idioma dejan de hacerlo: la página de
     ajustes antigua y el Companion.
2. **El canal** (requisito 2).
   - **La causa raíz:** la tarjeta de un agente «Listo · sin canal» llevaba a
     Canales **del cliente**, no a su pestaña Canales, y así el partner quedaba en un
     bucle. Ahora lleva a `?tab=channels` del agente (D12).
   - La tarjeta de Canales del cliente enlaza la configuración de cada número por
     la ruta que ya existe y que redirige dentro del agente.
   - Si el número está «Sin configurar», dice «No responde a nadie».
   - Al conectar un número desde esa página, la consola abre su configuración (D7).
   - La regla «qué agente atiende un número sin agente» queda una sola, con la
     caída al agente vivo más antiguo que ya existía (D8).
   - Un agente cuyo número está sin configurar deja de verse «Listo · sin canal»
     (D10).
3. **El borrador** (requisito 3).
   - El constructor pide la salida en JSON cuando el modelo lo admite.
   - Distingue una salida cortada de un JSON ilegible.
   - Registra el tipo de error y su posición, sin una sola palabra de la salida (D5).
   - Sin reintentos.
4. **Los nombres** (requisito 4).
   - Un nombre que el cliente dio al constructor no cuenta como «de otro cliente».
   - Lo que el constructor escriba por su cuenta y nombre a otro se quita trozo a
     trozo, en vez de tumbar el borrador.
   - «Desde una plantilla» devuelve un error con nombre en lugar de un 500 (D6).

Sin migraciones de esquema, sin dependencias nuevas y sin gasto nuevo.

## Technical Context

**Language/Version**: Python 3.11 (API y worker, uv) y TypeScript 5 con Next.js 16 (consola, pnpm).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Pydantic 2, LiteLLM (ya instalada), structlog; en la consola, React 19 y `@nexus/ui`. **Ninguna nueva.**

**Storage**: PostgreSQL con RLS. Sin cambios de esquema. Lo que cambia son dos JSONB que ya existen: `agent_configs.spec`, que gana `voice.languages_limited`, y `agent_configs.policies.console.languages`, que gana `limited`. Las dos son opcionales y por defecto valen «sin límite».

**Testing**: pytest (unitarias de API y worker, integración con base y `tests/isolation/`), Vitest en la consola. Además, la comprobación en staging de la quickstart, con el mismo guion de la reproducción.

**Target Platform**: ECS en AWS (API y runner) y Vercel (consola).

**Project Type**: web-service (API + worker) y web-app (consola).

**Performance Goals**: ninguno nuevo. La regla de idioma suma unas sesenta palabras por turno. El modo JSON no añadió tokens en la prueba (5385 frente a 5642 y 5807).

**Constraints**:
- ningún log con texto de la salida del modelo, de la descripción, de la ficha ni de mensajes;
- ningún reintento automático del constructor;
- los agentes publicados no se vuelven a publicar;
- la consola no enseña el nombre de otro cliente.

**Scale/Scope**:
- API: unos 9 ficheros de producción.
- Worker: 3.
- Consola: unos 7.
- Además: 2 contratos, 2 documentos de `docs/` y sus pruebas.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La garantía 5 queda rozada por el requisito 4: la guarda de nombres de otros clientes cambia qué cuenta como ajeno. Test: `apps/api/tests/isolation/test_063_builder_foreign_names.py`. Comprueba dos cosas: un borrador del constructor que nombra a otro cliente del partner sin haberlo recibido nunca llega con ese nombre, ni en el AgentSpec ni en lo que devuelve la API; y un nombre que solo aparece en la entrada de un cliente no exime a otro cliente. Nada más cruza tenants: la sincronía de idiomas escribe en la versión del propio agente, dentro de su `tenant_scoped_session`, y el resumen de canales ya está acotado por la RLS. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, declarada en la spec. |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | La regla de idioma es una instrucción de operador en un mensaje `system`. El idioma del cliente lo infiere el modelo de su mensaje, que sigue siendo dato: el mensaje no puede cambiar la regla, solo el idioma de la respuesta, que es lo que se pide. |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Limitar los idiomas es una edición del borrador por una persona, que pasa por publicar como cualquier cambio. El constructor no puede activarlo (1.9): el validador lo rechaza con `author != "person"`, igual que el aviso de IA. |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Un número «Sin configurar» dice que no responde a nadie, en vez de parecer activo. Sin agente, la tarjeta no ofrece una configuración que no existe, sino crear uno (2.5). La página de ajustes antigua deja de tener un campo de idiomas que ya no hace nada. El fallo de plantilla tiene nombre. |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS tiene su test en `tasks.md`, y los guiones de reproducción son el primer rojo de cada requisito. El modo JSON se prueba con el `LiteLLMProvider` real contra un servidor local y el mapa local, en un subproceso, porque una prueba con el transporte sustituido no ve los parámetros que LiteLLM rechaza (memoria del 2026-11-05). |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Dependencias nuevas: ninguna. Se descartó `json-repair` (D5). |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[bugs/2026-11-18-quejas-partners-prod]]`, que enlaza de vuelta a `specs/063-quejas-partners`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **5** (prompt aislado), por la guarda de nombres del constructor | `tests/isolation/test_063_builder_foreign_names.py` |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada nuevo. El constructor sigue en «Construcción y pruebas» y el turno en la bolsa del cliente. Una prueba fija que un borrador fallido no sale de la bolsa (3.5). | tarea de 3.5 |

## Project Structure

### Documentation (this feature)

```text
specs/063-quejas-partners/
├── spec.md
├── research.md          # evidencia, reproducciones y decisiones D1–D9
├── plan.md
├── data-model.md
├── quickstart.md        # cómo se comprueba en local y en staging
├── contracts/
│   ├── agent-spec-voice.md     # el campo nuevo de «Cómo habla» y la regla del turno
│   └── console-api.md          # resumen de canales y error de «Desde una plantilla»
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/nexus_api/
├── services/agent_console_policy.py     # LanguagesPolicy.limited; language_rule(); merge conserva languages
├── services/agent_spec/schema.py        # Voice.languages_limited
├── services/agent_spec/validator.py     # el constructor no cambia el límite (1.9)
├── api/console/agent_spec_drafts.py     # sincroniza voice → policies.console.languages
├── companion/tools/proposals.py         # fuera primary_language
├── services/builder/agent_draft.py      # nombres de la entrada; quitar el trozo; detalle de bad_json
├── api/console/agent_builder.py         # «Desde una plantilla»: error con nombre
├── services/channel_config.py           # _agent_of y agent_channels, con la regla del principal (D8)
└── api/console/channels.py (+ schemas_channels.py)  # audience_mode en el resumen

apps/api/src/nexus_api/services/agent_lifecycle.py   # reason "unconfigured" en ready_no_channel (D10)

apps/worker/src/nexus_worker/
├── runtime/console_context.py           # expone language_rule; el bloque ya no lleva idiomas
├── runtime/pipeline.py                  # la regla, último mensaje de sistema; _RETRY_SYSTEM_TEMPLATE (D11)
├── runtime/llm.py                       # acomplete_detailed + supports_json_object
└── jobs/handlers/agent_draft.py         # modo JSON, «cortado», registro del detalle

apps/console/src/
├── components/builder/block-editor.tsx  # «Responder solo en estos idiomas» + resumen
├── components/agent-tools/agent-settings-form.tsx  # fuera el campo de idiomas
├── components/channels/channel-card.tsx # «Configurar», «No responde a nadie», sin agente
├── components/channels/whatsapp-connect.tsx  # al terminar, a la configuración
├── components/builder/life-model.ts (+ agent-builder.tsx, clients v2)  # «Listo · número sin configurar»
├── lib/backend/channels.ts              # audience_mode
├── (lugar donde se pinta el error de «Desde una plantilla»)
└── i18n/lanes/*.ts

specs/047-la-fabrica-de-agentes/contracts/agent-spec.schema.json   # voice.languages_limited
docs/agentes.md · docs/canales.md                                  # spec viva, mismo commit
```

**Structure Decision**: el monorepo de siempre. Cada cambio va en el fichero que
ya posee el comportamiento: no hay módulos nuevos, salvo las pruebas.

## Complexity Tracking

Nada que la spec no pidiera. Se descartaron tres cosas:

- **Volver a publicar los agentes** para recompilar su prompt. La regla del turno
  basta, y en staging quedó probado (D1).
- **Una migración** que reescriba los idiomas de las versiones publicadas. Las
  versiones no se tocan, y el principal solo cuenta cuando no se sabe el idioma (D2).
- **Un reintento automático o una librería que repare JSON.** Cuestan más dinero o
  esconden el fallo (D5).
