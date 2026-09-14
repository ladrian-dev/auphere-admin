# Implementation Plan: la cuota cobra por carril

**Branch**: `007-pesos-de-cuota-por-carril` | **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-pesos-de-cuota-por-carril/spec.md`

## Summary

Sustituir el peso único por modelo por **tres pesos, uno por carril** (entrada,
lectura de caché, salida), derivados de la tarifa del propio carril con un
multiplicador único de **2,2x**. Con eso el margen deja de depender de la mezcla
de trabajo y pasa a ser 54,5 % por construcción en los dieciocho carriles del
catálogo, donde hoy cinco modelos venden la salida por debajo de coste y el sexto
incumple el suelo en caché.

El cambio en sí es pequeño —una función pura gana un factor por carril—. Lo que
la investigación destapó y **dobla el trabajo** es que la cuota ponderada no se
calcula sólo al debitar: **viaja por el sistema y está persistida**, ponderada
con una constante global que deja de ser constante (D4). Medir y ponderar se
separan: el grafo acumula nativos, y la ponderación ocurre una vez, en el borde.

## Technical Context

**Language/Version**: Python 3.11 (`apps/api`, `apps/worker`), gestionado con `uv`

**Primary Dependencies**: FastAPI · SQLAlchemy 2 (async) · Alembic · Dramatiq ·
LangGraph (el grafo del Companion). **Ninguna nueva.**

**Storage**: PostgreSQL. Tablas tocadas: `model_profiles` (catálogo de
plataforma, sin RLS) y `companion.runs`. Sólo por adición de columnas.

**Testing**: `pytest` — `tests/unit/`, `tests/integration/` (Docker),
`tests/isolation/` (bloqueante en PR). `ruff` + `mypy --strict`.
Verificación completa: `./scripts/verify.sh`.

**Target Platform**: Linux server (AWS `eu-south-2`, cuenta `793033583982`)

**Project Type**: servicio web multi-tenant + worker

**Performance Goals**: cero consultas nuevas en el camino caliente. Los pesos se
leen por el catálogo cacheado que ya existe (TTL 300 s) y que ya se lee en el
mismo camino para valorar el turno.

**Constraints**: **producción tiene tres clientes reales con tráfico.** Nada se
revalora, nada se reprecifica y el despliegue es reversible por revert (D5).

**Scale/Scope**: seis modelos servibles en el catálogo, dieciocho carriles. Dos
puntos que debitan, cuatro módulos que tocan la fórmula.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | `model_profiles` es catálogo de plataforma y **no gana `tenant_id`**: la garantía no es una política, es que no hay columna por la que alcanzarlo. Test: `tests/isolation/test_pool_not_exposed_to_tenant.py`, cuya lista `FORBIDDEN` crece con los tres nombres nuevos |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie **`0`**, declarada en la spec. No hay llamante nuevo, ni credencial nueva, ni camino nuevo al modelo. Se añaden columnas a una tabla que ya existe |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | **No aplica por construcción**: esta spec no introduce ninguna lectura de contenido externo ni toca el camino de mensajes. Los únicos datos nuevos son números de un catálogo que escribe una migración |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | **No añade ninguna acción `mutates`.** No hay endpoint nuevo: los pesos los escribe una migración. Los débitos siguen dejando asiento idempotente en `usage_ledger`, sin cambio |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Un modelo sin los tres pesos **no se ofrece**: ni botón apagado ni pantalla que explique lo que no hay. Es la conducta que la 004 ya fijó para el peso único, extendida |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | **No aplica**: no interviene ningún agente ni ningún navegador |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS nace como test y se ve en rojo antes de implementar. Y el invariante se verifica **rompiéndolo a propósito** (quickstart §1): un test que pasa no demuestra que vigile |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | **Ninguna dependencia nueva.** `Decimal` es biblioteca estándar; SQLAlchemy y Alembic ya están. Nada que leer ni que citar |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`, y **R7 obliga a enmendarlo en el mismo commit**: baja el margen objetivo de 65 % a 54,5 % y retira dos afirmaciones que la medición refuta |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **Garantía 1 (Postgres RLS)**, por el lado de «no abrir puerta»: se añaden columnas al plano económico y ninguna puede asomar por una ruta de cliente final | tarea en `tests/isolation/` que amplía `FORBIDDEN` y **se ve en rojo** antes de añadir los nombres |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna** | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Modelo, y nada más.** Es el objeto entero de la spec. El partner lo ve en Consumo, en la misma unidad de siempre; lo que cambia es la tasa de conversión desde tokens nativos | tareas de `quota.py`, `consumer.py`, `companion.py` y `graph.py` |

## Project Structure

### Documentation (this feature)

```text
specs/007-pesos-de-cuota-por-carril/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/requirements.md
├── contracts/
│   └── quota-unit-v2.md        # sustituye al contrato de la 004
└── tasks.md                    # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   ├── 0120_quota_weights_per_lane.py      # nueva: 3 columnas + siembra derivada
│   └── 0121_companion_run_native_input.py  # nueva: uncached_input_tokens
├── src/nexus_api/
│   ├── metering/
│   │   ├── quota.py              # la fórmula. Gana dos factores, pierde la constante 0,1
│   │   └── pricing_policy.py     # weights_for(): los tres pesos; UnweightedModel
│   ├── billing/pricing.py        # el comentario del 65 % pasa a decir 54,5 % (R7.2)
│   ├── db/models/
│   │   ├── model_profile.py      # 3 columnas
│   │   └── companion.py          # uncached_input_tokens
│   └── api/console/companion.py  # deja de des-ponderar; debita con los tres pesos
└── tests/
    ├── unit/                     # fórmula, margen, cliente final, paridad API↔worker
    ├── integration/              # invariante del suelo sobre el catálogo REAL
    └── isolation/                # FORBIDDEN con los tres nombres nuevos

apps/worker/src/nexus_worker/
├── metering/
│   ├── consumer.py               # _turn_quota y billable_qty por carril
│   └── pricing.py                # ModelPrice gana los tres pesos
└── runtime/companion/graph.py    # acumula NATIVO, deja de ponderar

docs/billing.md                   # spec viva: los tres pesos y el suelo (R7.3)
/Users/lmatos/Work/Auphere/nexus/decisions/ADR-037-*.md   # enmienda (R7.1)
```

**Structure Decision**: no hay estructura nueva. El trabajo cae en los módulos de
medición que ya existen en los dos servicios, más dos migraciones y tres
documentos. La única pieza nueva es el contrato `quota-unit-v2.md`, que sustituye
al de la 004 en vez de convivir con él — dos contratos de la misma unidad
divergirían, que es el mismo argumento que el repo ya aplica a las listas de
puertas.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **D4: separar medir de ponderar en `graph.py` + columna nueva en `companion.runs`.** La spec pedía cambiar una fórmula; esto cambia además dónde se acumula y qué se persiste | La cuota ponderada **ya está persistida** (`companion.runs.input_tokens`, migración `0093`) y se des-pondera restando `0,1 × cache_read`. Esa inversión sólo funciona con un factor global único. Con pesos por carril deja de ser invertible: para des-hacerla haría falta el modelo, que el punto de acumulación no tiene | **Que el grafo pondere con el peso del modelo**: mete el catálogo de precios dentro del bucle del agente y deja la ponderación en dos sitios, que es el defecto que se corrige. **Reinterpretar la columna en sitio**: deja filas cuya lectura depende de su fecha y un `downgrade()` que no puede devolver los datos |
| **Dos migraciones en vez de una** | Tocan tablas distintas con motivos distintos (catálogo de plataforma · turnos del Companion) y se pueden revertir por separado | Una sola migración obliga a revertir las dos cosas juntas cuando sólo una salga mal |

> Ninguna de las dos añade superficie de confianza ni dependencias. Son coste de
> implementación, no de riesgo.

## Re-evaluación del Constitution Check tras el diseño

Las nueve filas siguen en verde. El diseño **no** movió ninguna:

- La adición de D4 no abre superficie: es una columna más en una tabla que ya
  existe y una resta que deja de hacerse.
- El invariante del suelo (R2) se comprueba contra el **catálogo real de la
  base**, no contra una lista en un test, para que añadir un modelo sin pesos no
  pase en verde. Eso refuerza §VII en vez de relajarlo.
- Sigue sin haber dependencias (§VIII) y sin acciones `mutates` nuevas (§IV).
