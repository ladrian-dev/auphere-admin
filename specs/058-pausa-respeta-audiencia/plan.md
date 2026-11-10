# Implementation Plan: La pausa respeta la audiencia

**Branch**: `058-pausa-respeta-audiencia` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/058-pausa-respeta-audiencia/spec.md`

## Summary

Hoy, un contacto fuera de la audiencia de un número que escribe a un cliente en
pausa (o con el canal o el agente en pausa, archivado, en alta o sin publicar)
abre «Espera a una persona» y avisa a la gente del cliente. La causa es que, en
`gate_for`, las puertas de estado van antes que la de audiencia. El plan:

1. **Sube la puerta de audiencia al primer puesto**, salvo en un número solo de
   envío, que queda como hoy (research D1).
2. **Libera la espera de puerta** de una conversación cuyo contacto escribe ya
   fuera de la audiencia. Respeta lo que una persona se asignó y no pisa el motivo
   de una espera que no es de puerta (D3).
3. **Añade una limpieza de operador**, en seco por defecto, que hace lo mismo con
   las esperas que ya existen en los números con audiencia propia (D4).

Sin migraciones, sin dependencias y sin gasto.

## Technical Context

**Language/Version**: Python 3.11 (API y worker, uv)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Dramatiq/worker propio, structlog. Ninguna nueva.

**Storage**: PostgreSQL con RLS (`conversations`, `conversation_events`, `messages`, `console_notifications`, `client_push_events`). Sin cambios de esquema.

**Testing**: pytest. Unitarias del worker (`apps/worker/tests/unit`), integración de la API con base (`apps/api/tests/integration`) y aislamiento (`apps/api/tests/isolation`).

**Target Platform**: ECS en AWS (runner del worker; la tarea suelta para el guion).

**Project Type**: web-service (API + worker).

**Performance Goals**: ninguno nuevo. La puerta usa un dato que el turno ya calcula (`facts.out_of_audience`). La limpieza recorre una vez los tenants, conversación a conversación, solo las que esperan por un motivo de puerta.

**Constraints**:
- el mensaje se guarda siempre (047, 2.1);
- ningún aviso por un contacto fuera de la audiencia;
- ningún log con teléfono ni texto;
- ningún despliegue lanza la limpieza.

**Scale/Scope**: 2 ficheros de producción del runtime (`dispatcher.py`, `inbox_lifecycle.py`), 1 servicio y 1 guion nuevos, 5 ficheros de pruebas y 3 documentos.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La puerta y la liberación corren dentro del turno, en la `tenant_scoped_session` del tenant del turno. La limpieza abre una `tenant_scoped_session` por tenant y cierra los avisos con `mark_waiting_handled`, que filtra por partner y referencia. Test: `apps/api/tests/isolation/test_058_audience_cleanup_per_tenant.py` (la limpieza de un cliente no toca las esperas ni los avisos de otro, aunque tengan la misma forma). No hay herramientas en juego. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, declarada en la spec. Runtime y Bandeja que ya existen. |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | No entra contenido leído en ningún prompt. La puerta decide antes de llamar al modelo. |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | No hay acción del agente. La limpieza es una acción de operador, en seco por defecto, con `--apply` explícito. Deja el evento `released` en cada conversación y el log por tenant. |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | La Bandeja deja de enseñar esperas falsas, y una espera que ya no es cierta sale de ella. Conversaciones sigue enseñando el mensaje con su etiqueta. No hay UI nueva. |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica: no hay agente operando la plataforma. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS tiene su test en `tasks.md`. Se escriben y se ven en rojo antes de tocar `dispatcher.py` e `inbox_lifecycle.py`. |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Dependencias nuevas: ninguna. |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[bugs/2026-11-10-pausa-avisa-fuera-de-audiencia]]`, que enlaza de vuelta a `specs/058-pausa-respeta-audiencia`. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **1 (RLS), rozada por la limpieza**: recorre todos los tenants | `T002` en `apps/api/tests/isolation/test_058_audience_cleanup_per_tenant.py` |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | — (no hay tarea: no entra nada) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada. Se envían menos correos, y eso alivia el cupo compartido de Resend | — (no hay gasto que medir) |

## Project Structure

### Documentation (this feature)

```text
specs/058-pausa-respeta-audiencia/
├── spec.md
├── plan.md              # este fichero
├── research.md          # D1–D7
├── data-model.md        # sin migración; transiciones nuevas
├── quickstart.md        # cómo comprobarlo, en local, staging y prod
├── contracts/
│   └── turn-gates.md    # el orden de las puertas y el guion
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/worker/src/nexus_worker/runtime/
└── dispatcher.py                 # gate_for (D1), _apply_gate (D3), docstring con el orden

apps/api/src/nexus_api/services/
├── inbox_lifecycle.py            # leave_gate_wait (D3) y la guarda de mark_waiting_reason
└── audience_cleanup.py           # NUEVO: run(factory, apply=...) (D4)

apps/api/scripts/
└── release_out_of_audience_waits.py   # NUEVO: guion de operador, en seco por defecto

apps/worker/tests/unit/
└── test_gate_order_audience.py   # NUEVO: el orden de gate_for (req. 1.1, 1.2, 1.4, 1.7)

apps/api/tests/integration/
├── test_dispatcher_058_audience_first.py  # NUEVO: el turno de verdad (req. 1, 2)
└── test_audience_cleanup.py               # NUEVO: la limpieza (req. 3)

apps/api/tests/isolation/
└── test_058_audience_cleanup_per_tenant.py  # NUEVO: garantía 1 en la limpieza

docs/consola-lite.md                                  # spec viva (D6)
specs/047-la-fabrica-de-agentes/contracts/events.md   # §2, una línea (D6)
apps/api/RUNBOOK.md                                   # cómo lanzar la limpieza (D6)
```

**Structure Decision**: el cambio va donde ya vive cada pieza. La puerta, en el
despachador del worker. La transición de la conversación, en `inbox_lifecycle`,
que es donde viven todas las suyas y lo que importa el worker. La limpieza va
como servicio de la API más un guion de operador, igual que
`reservations/auto_pass.py` con `pass_booking_to_reservas.py`.

## Complexity Tracking

Sin violaciones de la constitución. Hay una cosa que la spec no pedía
literalmente y el plan añade:

| Añadido | Por qué | Alternativa más simple descartada |
|---|---|---|
| Guarda en `mark_waiting_reason` para no sobrescribir el motivo de una conversación `escalated` con `out_of_audience` | Lo pide el requisito 2.2 («NO DEBE … cambiar su motivo»). Hoy se sobrescribe, y una espera que no es de puerta se queda en la Bandeja sin texto | Dejarlo como está: la Bandeja enseñaría una espera con un motivo que no se pinta |
