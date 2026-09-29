# Implementation Plan: el número se puede mover

**Branch**: `021-numero-puede-mover` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/021-el-numero-se-puede-mover/spec.md`

## Summary

Un número de WhatsApp desvinculado queda **libre**: el mismo cliente lo
recupera con su historial, y otro cliente —del mismo partner o de otro— lo
conecta. Para eso la unicidad del número deja de contar los canales
desvinculados, y desvincular deshace en Meta lo que conectar hizo: da de baja
el número y, si era el último de su cuenta de WhatsApp Business en ese
cliente, desuscribe nuestra aplicación y borra las credenciales. Si Meta falla,
el canal queda desvinculado igual en la consola y la tarjeta dice qué falta y
cómo reintentar.

Lo que ya está en staging desde la spec 019 —endpoint, acción, tarjeta,
diálogo, vocabulario— se reutiliza. La investigación (Fase 0) corrigió una
frase de la spec: el choque de un número ya se captura como 409
`number_in_use`; el defecto es que ese aviso es **falso** para un número que su
dueño soltó.

## Technical Context

**Language/Version**: Python 3.14 (API, canales) · TypeScript 5 / Next.js 16 (consola)

**Primary Dependencies**: FastAPI · SQLAlchemy async · Alembic · el cliente de Meta que ya existe (`nexus_channels.whatsapp_meta.meta_client`) — **ninguna nueva**

**Storage**: PostgreSQL con RLS. Un índice único parcial sustituye a una restricción; una clave opcional más en `channels.config`

**Testing**: pytest (`unit`, `integration`, `isolation`) · vitest en la consola. Meta se simula en local; CE-004 y CE-005 se cierran en staging con número real

**Target Platform**: API en AWS, consola en Vercel

**Project Type**: monorepo — servicio web + consola

**Performance Goals**: desvincular termina en la consola en una transacción; las llamadas a Meta van detrás y no bloquean el «desvinculado»

**Constraints**: el canal nunca queda a medias en silencio (R3) · desuscribir es por WABA, no por número: con un hermano vivo no se toca (R2.3) · no se revela de quién es un número en uso (R1.5)

**Scale/Scope**: un canal por número; hoy tres clientes vivos en producción con un número cada uno

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante | ☑ | Todas las lecturas siguen bajo RLS. El índice parcial **no lee** la fila ajena: deja de chocar con ella. Test en `tests/isolation/test_channel_number_scope.py`: un tenant no ve, no altera y no averigua el dueño de un número ajeno |
| II | Corte por superficie de confianza | ☑ | Superficie `0`. Las llamadas a Meta son las mismas que el alta ya hace, deshechas |
| III | Lo leído es dato, nunca instrucción | ☑ | Lo que Meta devuelve se traduce a un código cerrado (`number_held_by_previous_owner`); su texto nunca se enseña tal cual |
| IV | Acción `mutates` con aprobación; auditoría nombra a la persona | ☑ | Desvincular ya pide confirmación y ya audita; ahora el registro dice además qué se consiguió en Meta y qué no |
| V | Estados honestos; la ausencia se diseña | ☑ | `unlink_pending` es el estado «a medias», **visible** en la tarjeta con su reintento. Un número retenido por el dueño anterior tiene su frase, no un error genérico |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | El Companion no entra |
| VII | Test primero | ☑ | Cada bloque tiene su test rojo antes; el de Meta caído (CE-006) es el primero que se escribe, porque es el modo de fallo nuevo |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | Enlaza a la sesión del 2026-09-29; la garantía 1 no cambia de redacción |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía cambia de promesa. Se añade un test porque la regla de unicidad cambia de forma y conviene dejar escrito que no revela nada | `T-ISO` en `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | `T-LIC` |
| **Medidor** | Nada | `T-MET` |

## Project Structure

### Documentation (this feature)

```text
specs/021-el-numero-se-puede-mover/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/unlink.md
└── tasks.md          # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0132_number_unique_when_live.py
├── src/nexus_api/
│   ├── db/models/channel.py                 # la unicidad, parcial
│   ├── api/console/channels.py              # desvincular deshace en Meta; reintento
│   ├── api/console/whatsapp.py              # _NUMBER_UNIQUE apunta al índice nuevo; 409 number_held_by_previous_owner
│   └── api/console/schemas_channels.py      # unlink_pending
└── tests/
    ├── unit/test_endpoint_console_channels.py      # desvincular: último/no último, Meta caído, reintento
    ├── unit/test_endpoint_console_whatsapp.py      # reconectar revive la fila; B conecta lo que A soltó
    └── isolation/test_channel_number_scope.py

apps/channels/src/nexus_channels/whatsapp_meta/
└── meta_client.py                           # deregister_phone

apps/console/src/
├── components/channels/channel-card.tsx     # «queda pendiente en Meta» + reintentar
├── lib/backend/channels.ts                  # unlink_pending
└── i18n/lanes/channels.ts                   # la copia de pendiente, reintento y number_held_by_previous_owner
```

**Structure Decision**: ningún módulo nuevo. El endpoint de desvincular crece,
el cliente de Meta gana una llamada, y la tarjeta gana un estado.

## Fase 1 — diseño

| Artefacto | Qué fija |
|---|---|
| [`research.md`](research.md) | Las cinco decisiones, y la corrección a la spec |
| [`data-model.md`](data-model.md) | El índice parcial, `unlink_pending`, cuándo se borra cada credencial |
| [`contracts/unlink.md`](contracts/unlink.md) | Qué devuelve desvincular en cada estado; qué código nuevo devuelve el alta |
| [`quickstart.md`](quickstart.md) | Qué se comprueba en local y qué solo en staging |

### El orden de entrega

1. **El índice**, solo. Migración + modelo + la constante del 409. No cambia
   nada observable salvo que B deja de recibir un «en uso» falso: es la
   Historia 1 entera, y se puede soltar a producción sin tocar Meta.
2. **Deshacer en Meta**, con el estado pendiente escrito **antes** de llamar
   (research D2). Es la Historia 2 y la 3 juntas: no se pueden separar sin
   dejar el modo de fallo sin cubrir.
3. **La tarjeta** que enseña lo pendiente y reintenta.
4. **La frase para B** cuando Meta retiene el número.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué no |
|---|---|---|
| Dos transacciones en desvincular (estado antes, Meta después) | Con una sola, un fallo entre Meta y el commit deja el número dado de baja sin que la base lo sepa — el silencio que R3 prohíbe | Una transacción con Meta dentro: es la que deja huérfanos. Meta primero y base después: es la que deja la base mintiendo |
| `unlink_pending` en `config` | Es lo que hace visible y reintentable lo que quedó a medias | Un flag booleano no dice **qué** faltó, y un reintento ciego repetiría pasos ya hechos contra Meta |
