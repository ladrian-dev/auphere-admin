# Implementation Plan: volver a la aplicación, y entrar con Google

**Branch**: `009-volver-y-entrar-desde-la-app` | **Date**: 2026-09-15 | **Spec**: [spec.md](spec.md)

**Input**: [spec.md](spec.md) · **Fase 0**: [research.md](research.md) · **KB**: `[[ADR-039-volver-y-entrar-desde-la-app-de-escritorio]]`

## Summary

Dos capacidades que empujan contra la misma frontera: la lista cerrada de seis
funciones del `preload` de la barra. Pasa a ocho —`showApp` y `redeemCode`— y
sigue siendo cerrada, declarada y vigilada por un test.

**Historia 1** (P1, entregable sola, sin tocar autenticación): una acción en la
barra que devuelve a la pantalla del equipo, visible **sólo** con la consola
delante.

**Historia 2** (P2): la consola, al volver del callback de Google, enseña un
código de ocho caracteres; tecleado en la barra, acuña una **sesión nueva** para
la aplicación. El código va atado a la máquina que lo pidió.

**El descubrimiento que abarata la Historia 2**: casi todo existe.
`console_identity.start_session(...)` ya acuña sesiones por el camino correcto,
`core/pairing_codes.py` trae el alfabeto, la longitud, el TTL y el hash, y
`PairingRateLimiter` trae la defensa de intentos. Lo nuevo es **una tabla y qué
ata el código** — no el mecanismo del código.

## Technical Context

**Language/Version**: Python 3.11 (API) · TypeScript 5.7 / Node 22 (escritorio y consola)

**Primary Dependencies**: FastAPI + SQLAlchemy + Alembic · Electron 44 · Next.js 16 · Redis

**Storage**: PostgreSQL, esquema `console_auth`. Migración **0122** (la más alta hoy es `0121_companion_run_native_input`)

**Testing**: pytest (`tests/unit`, `tests/integration`) · vitest (`apps/desktop/tests`, `apps/console/src/**/__tests__`)

**Target Platform**: macOS 13+ (la mitad de Windows no está portada)

**Project Type**: desktop-app + web-service + BFF

**Performance Goals**: sin objetivos nuevos. El canje es un acto manual y raro

**Constraints**: TTL de 10 min heredado del emparejamiento · 5 intentos por ventana de 10 min · el `preload` no puede contener `login`/`session`/`cookie`/`token`

**Scale/Scope**: 2 partners, 3 clientes finales con tráfico. Un puñado de canjes al día en el peor caso

**Sin NEEDS CLARIFICATION**: `/speckit-clarify` cerró las cuatro el 2026-09-15.

## Constitution Check

*Rellenado antes de la Fase 0 y **vuelto a comprobar tras el diseño** (abajo).*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto; whitelist exhaustiva | ☑ | **No se toca.** `session_codes` vive en `console_auth`, como `principals`, que tampoco lleva tenant. El alcance de una persona sigue saliendo de `partner_memberships`. Sin herramientas, sin prompts, sin checkpointer |
| II | Corte por superficie; no se abre una nueva sin agotar la actual | ☑ | Superficie declarada en la spec. **No se abre ninguna de las cinco**: se amplía la lista del `preload` de seis a ocho, y se argumenta contra el precedente de `bar.ts:125` en [contracts/bar-preload.md](contracts/bar-preload.md). Se abre por la mitad barata: la Historia 1 va sola |
| III | Lo leído es dato, nunca instrucción | ☑ | El código tecleado es **dato**: ocho caracteres normalizados contra un alfabeto cerrado y comparados por hash. No se interpreta nada |
| IV | Acción `mutates` con aprobación durable; la auditoría nombra a la persona | ☑ | Canjear es un acto explícito de la persona, no de un agente: no entra en el gate de aprobaciones. La auditoría nombra `principal_id` y la máquina (R5.5), con el `user_agent` que `principal_sessions` ya guarda |
| V | Estados honestos; la ausencia se diseña | ☑ | R1.2: sin consola delante **no hay acción** —ni apagada ni explicada—. R4.7: el fallo del canje se pinta como estado, nunca en rojo, igual que los otros siete |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | No hay agente aquí. La cáscara habla con el BFF, como ya hace |
| VII | Test primero; el criterio es el test; nada de `skip` | ☑ | Cada criterio N.m nace como test antes del código. Ver «cómo se prueba» abajo |
| VIII | Licencias leídas; AGPL no | ☑ | **Ninguna dependencia nueva** (D8 de la investigación). Nada que leer |
| IX | La KB es dueña del porqué | ☑ | `[[ADR-039-volver-y-entrar-desde-la-app-de-escritorio]]`, escrito el 2026-09-15 para esta spec, con las dos alternativas descartadas |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **Ninguna de las 7.** No hay frontera de tenant | Ninguna en `tests/isolation/`. **Sí** la hay de **no suplantación**, que es otra cosa: `tests/integration/test_session_codes.py` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna** | — |
| **Medidor** — ¿qué gasta y dónde se ve? | **Nada.** Ni modelo, ni reloj de máquina, ni herramienta de pago | — |

> **Ojo con la puerta de aislamiento.** Que no haya test en `tests/isolation/` es
> correcto y hay que decirlo alto, porque a primera vista parece un hueco: ahí
> viven las 7 garantías **entre tenants**, y esto no cruza ninguna. La prueba que
> esta spec sí debe traer —que un código no sirve para entrar como otra persona,
> ni dos veces, ni desde otra máquina— es de suplantación y vive con el resto de
> los tests de identidad. Dejarla en `isolation/` la escondería entre cosas que
> comprueban algo distinto.

## Project Structure

### Documentation

```text
specs/009-volver-y-entrar-desde-la-app/
├── plan.md              # este fichero
├── research.md          # Fase 0 — qué existe ya
├── data-model.md        # Fase 1 — la tabla nueva
├── quickstart.md        # Fase 1 — cómo se valida a mano
├── contracts/
│   └── bar-preload.md   # la enmienda al contrato de la barra (spec 002)
├── checklists/requirements.md
└── tasks.md             # lo escribe /speckit-tasks
```

### Source code

```text
apps/api/
├── alembic/versions/0122_session_codes.py          # NUEVO
├── src/nexus_api/db/models/console_identity.py     # + SessionCode
├── src/nexus_api/services/session_codes.py         # NUEVO — emitir y canjear
├── src/nexus_api/api/console/auth_google.py        # el callback ofrece el código
├── src/nexus_api/api/console/session_codes.py      # NUEVO — las dos rutas
└── tests/integration/test_session_codes.py         # NUEVO — no suplantación

apps/console/src/
├── app/auth/google/callback/route.ts               # redirige a la pantalla del código
├── app/(auth)/desktop-code/page.tsx                # NUEVO — enseña el código
└── app/api/session/code/route.ts                   # NUEVO — proxy con la sesión

apps/desktop/src/
├── bar-state.ts                                    # BarAction += volver_a_la_app; BarState.surface
├── bar/bar.ts                                      # pinta la acción y la hoja del código
├── electron/bar-preload.ts                         # 6 → 8 funciones
├── electron/main.ts                                # bar:showApp, bar:redeem, empujar surface
├── app-runtime.ts                                  # el canje, junto a pair()
└── tests/…                                         # bar-state, no-own-auth, app-runtime-identity

specs/002-identidad-app-escritorio/contracts/desktop-bar.md   # MISMO COMMIT
```

**Structure Decision**: no se crea ningún paquete nuevo. Cada pieza va donde ya
vive su vecina: el código de sesión junto a la identidad de consola, la acción de
la barra junto a las otras cuatro, y el canje junto a `pair()` — que es su hermano
y conviene que se lean seguidos.

## Cómo se prueba (§VII)

El orden importa y es el que `/speckit-tasks` tiene que respetar.

| Criterio | Test | Dónde |
|---|---|---|
| R1.1–R1.2 | La acción aparece con `surface: "console"` y **no** aparece sin él | `apps/desktop/tests/bar-state.test.ts` |
| R1.3 | Volver no recarga la vista de la consola | manual (quickstart): es de Electron |
| R2.1–R2.2 | El `preload` expone exactamente ocho, y una novena pone rojo | `apps/desktop/tests/no-own-auth.test.ts` (se **actualiza**, no se borra) |
| R2.4 | Con cifrado no disponible, `volver_a_la_app` **sigue** ofreciéndose | `bar-state.test.ts` |
| R2.5 | El texto del `preload` no contiene `login`/`session`/`cookie`/`token` | `no-own-auth.test.ts:38`, **sin tocar** |
| R3.1–R3.5 | Emisión: sólo tras Google, hash guardado, uno vivo por persona, sin sesión no se emite | `apps/api/tests/integration/test_session_codes.py` |
| R4.1–R4.3 | El canje acuña sesión nueva; las dos son independientes; se puede cerrar una sin la otra | idem |
| R4.4–R4.6 | Un solo uso; caducado/usado/inexistente **indistinguibles**; límite de intentos | idem |
| R4.7 | El fallo se pinta como estado y nunca en rojo | `bar-state.test.ts` |
| R5.1–R5.6 | No suplantación: ni otra persona, ni otra máquina, ni en claro en logs, con auditoría | idem |

**Y una prueba de mutación por cada criterio de seguridad de R5**: se rompe la
guarda y se comprueba que el test se pone rojo. Un test de seguridad que nadie ha
visto fallar no es una guarda, es una intención.

## Complexity Tracking

| Violación | Por qué hace falta | Alternativa más simple, y por qué se rechazó |
|---|---|---|
| El `preload` pasa de 6 funciones a 8 | La barra no puede cambiar de superficie ni entregar un código sin un canal al proceso principal: es el propósito declarado de no dárselo | Reutilizar `openInBrowser` — no sirve: abre fuera, no cambia de superficie. Poner la vuelta sólo en el menú y el atajo — es el estado actual, y es el fallo |
| Tabla nueva en vez de reutilizar el emparejamiento | El de emparejamiento ata una **máquina** y emite credencial de dispositivo; éste ata una **persona** y emite sesión. Meter los dos en una tabla obligaría a columnas nulas según el caso | Añadir un tipo a `local_workstation` — mezclaría dos ciclos de vida y dos modelos de amenaza en una fila |

Todo lo demás del plan sale de la spec; no hay nada añadido por gusto.

## Constitution Check — segunda pasada, tras el diseño

Las nueve filas siguen en ☑, y el diseño **mejoró dos**:

- **§II**: la investigación (D5) encontró que la prohibición de `login`/`session`/
  `cookie`/`token` en el `preload` **no hay que enmendarla**. `redeemCode` entrega
  ocho caracteres y recibe un estado; el token no cruza el `preload`. La spec
  contemplaba tener que romper esa regla (R2.5) y no hace falta.
- **§I y §IV**: D2 encontró que `principal_sessions` ya guarda `user_agent`, y la
  cáscara ya se anuncia como `AuphereDesktop/<versión>` desde la spec 002. La
  auditoría puede decir qué máquina hizo qué **sin una columna nueva**.

**Ninguna fila empeoró y no hay nada que justificar en Complexity Tracking que no
estuviera ya.**

## Puertas que quedan

- `/speckit-tasks` — cada tarea con su `_Requisitos: N.m_`.
- `/speckit-analyze` en verde antes de `/speckit-implement`.
- **`/cso` obligatorio** antes de declarar hecha la Historia 2: toca autenticación
  y secretos de un solo uso. Un finding 🔴 bloquea.
- `./scripts/verify.sh` entero antes de fusionar.
