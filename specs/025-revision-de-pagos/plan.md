# Implementation Plan: el equipo confirma o rechaza los pagos desde WhatsApp

**Branch**: `025-revision-de-pagos` | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/025-revision-de-pagos/spec.md`

## Summary

Una herramienta nueva del agente, `payments.request_review`, abre una
revisión de pago cuando el cliente manda un comprobante o dice que pagó por
el enlace. La revisión avisa a cada revisor del negocio desde el número del
propio negocio: el comprobante tal como entró y un mensaje con el resumen y
dos botones, **Confirmar pago** y **Rechazar pago**, cuyo id lleva la
revisión. La pulsación se intercepta en el webhook antes de que llegue al
agente, resuelve la revisión una sola vez y encola tres textos fijos: al que
pulsó, al resto de revisores y al cliente. Rechazar silencia al agente en esa
conversación para que la tome una persona. Los revisores se editan en
Ajustes del agente y se aplican al publicar. Dos tablas, una migración, un
servidor MCP, ningún endpoint nuevo, ninguna dependencia nueva.

**Iteración 1** (esta entrega): ventana de 24 horas abierta, Historias 1, 2
y 3. **Iteración 2**: plantilla con respuestas rápidas para la ventana
cerrada, tipo `button` en el adaptador y la marca en Conversaciones
(Historia 4). Ver research D8.

## Technical Context

**Language/Version**: Python 3.14 (API, worker, MCP) · TypeScript 5 / Next.js 16 (consola)

**Primary Dependencies**: FastAPI · SQLAlchemy async · react-hook-form + zod — **ninguna nueva**

**Storage**: PostgreSQL con RLS. Tablas nuevas `payment_reviews` y `payment_review_notices` (migración `0137_payment_reviews`); política `policies.payment_review` en `agent_configs`; fila nueva en `tool_catalog`; dos filas en `console_audit_vocabulary`

**Testing**: pytest `unit` e `isolation` (API); pytest de MCP (`apps/mcp/tests`); vitest en la consola; staging con número real

**Target Platform**: API y worker en AWS, consola en Vercel

**Project Type**: monorepo — API + worker (con MCP en proceso) + consola

**Performance Goals**: aviso y respuesta encolados en la misma transacción; el despachador los envía al instante por `pg_notify`

**Constraints**: sale del número del negocio (D1) · el primero que pulsa gana (D5) · la pulsación no llama al modelo (D6) · el cliente nunca ve a los revisores (R1.6)

**Scale/Scope**: una herramienta, un servicio de resolución, un desvío en el webhook, una sección de formulario, una migración

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante | ☑ | Tablas con RLS forzada. La pulsación se resuelve dentro de la sesión del tenant resuelto por el número de negocio; un token de otro tenant no existe. Test en `tests/isolation/test_payment_reviews_scope.py` |
| II | Corte por superficie de confianza | ☑ | Superficie `1`: escribe a números que el partner puso en la lista, desde el número del negocio, solo con lo que el agente ya sabe del pedido |
| III | Lo leído es dato, nunca instrucción | ☑ | El resumen viene del agente como campos acotados; la pulsación solo se interpreta por el id del botón |
| IV | Acción `mutates` con aprobación; auditoría nombra a la persona | ☑ | La herramienta es `mutates_db`/`sends_message` y se bloquea en el Playground. `payment_review.opened` y `payment_review.resolved` con el teléfono y el nombre del revisor |
| V | Estados honestos; la ausencia se diseña | ☑ | La herramienta dice cuántos avisos salieron y cuáles no; con cero, el agente pasa a una persona. Ventana del cliente cerrada → `customer_notified=false`, no se finge |
| VI | Por API `console.*` | ☑ | Revisores por `GET/PUT …/agent/settings` |
| VII | Test primero | ☑ | Cada bloque nace con su test rojo |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | `[[clients/flor-y-encanto]]` |

### Las tres puertas

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Revisiones y avisos con RLS; un token de A pulsado en el número de B no resuelve nada | T-ISO |
| **Licencias** | Ninguna dependencia nueva | T-LIC |
| **Medidor** | Avisos y respuestas son mensajes de canal medidos por el despachador; la pulsación no llama al modelo | T-MET |

## Project Structure

```text
apps/api/alembic/versions/0137_payment_reviews.py         # tablas, RLS, tool_catalog, vocabulario
apps/api/src/nexus_api/db/models/payment_review.py        # PaymentReview, PaymentReviewNotice
apps/api/src/nexus_api/services/agent_payment_review.py   # revisores en policies (espejo de agent_audience)
apps/api/src/nexus_api/services/payment_reviews.py        # textos, resolve_tap
apps/api/src/nexus_api/api/webhooks/meta.py               # desvío de la pulsación
apps/api/src/nexus_api/api/console/agent_settings.py      # payment_review en GET/PUT
apps/api/src/nexus_api/api/console/agent_drafts.py        # fila del resumen del borrador
apps/api/src/nexus_api/api/console/capability_names.py    # nombre de negocio
apps/mcp/src/nexus_mcp/servers/payments/                  # payments.request_review
apps/mcp/src/nexus_mcp/registry.py                        # registro
apps/console/src/components/agent-tools/                  # sección «Revisión de pagos»
```

## Complexity Tracking

Ninguna desviación de la constitución.
