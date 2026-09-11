# Plan de implementación: el medidor dice la verdad

**Rama**: `004-medidor-y-pool-semanal` | **Fecha**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Entrada**: especificación en `/specs/004-medidor-y-pool-semanal/spec.md` ·
ADR `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` ·
evaluación `.specify/assessments/membresias-y-consumo-stripe/`

## Summary

Cuatro cambios pequeños en sitios que ya existen, y **una supresión** que es la
que da nombre a la spec.

1. **Cargar tres tarifas** que están a `NULL` desde la migración `0095`, para que
   el modelo que el Companion usa por defecto deje de medirse sin valorarse.
2. **Cambiar el período** del consumo incluido de mes a semana, anclado a la
   fecha de alta del partner. Una función de cálculo de vencimiento; el proceso
   de renovación no se toca porque dispara por caducidad.
3. **Meter un factor por modelo dentro de `quota_tokens()`**, junto al factor de
   lectura de caché que ya lleva, para que agotar un pool cueste lo mismo con
   cualquier cerebro.
4. **Separar los bolsillos**: el consumo de clientes finales deja de poder tocar
   el incluido.
5. **Quitar el segundo contador**: `budget_out` pasa a leer del libro y
   `sum_partner_companion_tokens` baja a ser atribución. Es borrar un camino de
   lectura, no añadir uno.

Y en pantalla, lo que la revisión de la spec añadió: el partner ve **una barra y
una fecha**, no una cifra de tokens.

**Nada de esto añade una dependencia, una tabla nueva ni un endpoint nuevo.**

## Technical Context

**Language/Version**: Python 3.11 (API y worker, gestionado con `uv`) ·
TypeScript 5 con React 19 (consola Next.js 16, panel de operador Next.js 16,
aplicación Electron)

**Primary Dependencies**: FastAPI · SQLAlchemy 2 asyncio · Alembic · asyncpg ·
structlog · Dramatiq (worker) · Next.js 16 · `@nexus/ui`.
**Dependencias nuevas: ninguna.**

**Storage**: PostgreSQL (Aurora en AWS, `eu-south-2`) con RLS `ENABLE` + `FORCE`
en las tablas del libro. Redis para el canal de eventos y el rate limit.

**Testing**: `pytest` con `pytest-asyncio` (`tests/unit`, `tests/integration`,
`tests/isolation`) · `vitest` en consola, panel y aplicación de escritorio

**Target Platform**: servicio en Linux (ECS Fargate) + consola y panel en Vercel
+ aplicación de escritorio macOS

**Project Type**: servicio web multi-tenant con tres superficies de lectura

**Performance Goals**: el débito ocurre **dentro del turno**, así que el coste
añadido por el factor de modelo tiene que ser **cero consultas nuevas por
llamada**: se sirve del catálogo ya cacheado con TTL de 300 s
(`nexus_worker.metering.pricing.get_catalog`).

**Constraints**:
- **Fail-closed sin excepción**: si el libro no se lee, saldo cero y sin llamada
  al modelo. Esta spec no relaja eso en ningún punto.
- **Idempotencia intacta**: `usage_ledger.idempotency_key` es UNIQUE y el mismo
  turno reprocesado no puede doblar. Ningún cambio puede tocar esa propiedad.
- **Un asiento no se reescribe**: cambiar un factor no recalcula lo ya debitado.
- **Sin despliegue para cambiar un número**: tamaño de pool y factor son datos.

**Scale/Scope**: decenas de partners, unidades de miles de turnos al día. El
catálogo de modelos cabe en memoria (decenas de filas) y cambia casi nunca.

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y **vuelta a comprobar** después del diseño
(§Re-evaluación).*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ✅ | El cambio **reduce** superficie: el presupuesto deja de recorrer `companion.runs` membresía a membresía reapuntando `app.principal_id`, y pasa a leer una fila de `partner_wallets` bajo RLS FORCE por `partner_id`. Ningún identificador llega del llamante. Test: `tests/isolation/test_budget_reads_wallet_scope.py` |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ✅ | Superficie declarada en la spec: **`0`**. Sin llamante nuevo, sin credencial nueva, sin camino nuevo al modelo |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ✅ | No aplica: esta spec no toca el contexto del modelo ni el catálogo de herramientas |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ✅ | No hay acción de agente nueva. Cambiar el tamaño del pool o un factor es acción **de operador** en el panel de admin, y entra en el vocabulario de auditoría existente nombrando a la persona |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ✅ | Es el corazón de la spec: R4 quita la contradicción entre pantalla y realidad; R5.4 reutiliza `en pausa por tope` en vez de inventar un estado; R7.4 exige que el medidor sea legible por lector de pantalla |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ✅ | No aplica |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ✅ | Cada criterio de los 7 requisitos nace como test y se ve en rojo. La lista está en [quickstart.md](./quickstart.md) |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ✅ | **Dependencias nuevas: ninguna.** `stripe` es de la Spec B |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ✅ | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`, y la ADR enlaza de vuelta a la carpeta de la evaluación |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **1 · Postgres RLS** (camino de lectura del presupuesto, que se simplifica) y **6 · Log + trace tagging** (la renovación semanal y cada débito siguen dejando asiento) | una tarea por garantía en `tests/isolation/` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna** | — (la tarea es verificar que el diff no añade ninguna) |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Modelo, y solo modelo.** Ni reloj de máquina ni herramienta de pago. Lo ve en Consumo de la consola y en Cuenta de la aplicación, como **barra y fecha** (R7) | tarea de UI en las dos superficies + tarea de contrato |

**Complejidad que hay que justificar:** ver §Complexity Tracking. Hay una sola
entrada, y es sobre el número de migraciones.

## Project Structure

### Documentation (this feature)

```text
specs/004-medidor-y-pool-semanal/
├── plan.md              # este fichero
├── research.md          # Fase 0 — las seis decisiones de diseño
├── data-model.md        # Fase 1 — columnas nuevas y su semántica
├── quickstart.md        # Fase 1 — cómo se verifica que funciona
├── contracts/
│   ├── budget-object.md # el objeto de presupuesto: antes y después
│   └── quota-unit.md    # la unidad de cuota con factor por modelo
├── checklists/
│   └── requirements.md  # checklist de calidad de la spec (completo)
└── tasks.md             # Fase 2 — lo crea /speckit-tasks, no este comando
```

### Source Code (repository root)

Lo que esta spec toca, y **nada más**:

```text
apps/api/
├── alembic/versions/
│   ├── 0114_model_prices_and_meter_prices.py   # Historia 1 — tarifas + reprecio
│   └── 0115_quota_weight_and_weekly_pool.py    # Historias 3 y 4 — factor + período
├── src/nexus_api/
│   ├── metering/
│   │   ├── quota.py          # + factor por modelo (misma función, segundo peso)
│   │   └── wallet.py         # next_period_end() semanal · débito con bolsillo
│   ├── api/console/
│   │   ├── companion.py      # budget_out lee del libro; la suma baja a atribución
│   │   ├── teammates.py      # consume el budget_out nuevo
│   │   ├── schemas_companion.py  # el objeto de presupuesto cambia de período
│   │   └── wallet.py         # disponible para asignar se calcula sobre purchased
│   ├── db/models/
│   │   ├── model_profile.py  # + quota_weight
│   │   └── partner.py        # + weekly_pool_tokens; cap mensual queda deprecado
│   └── config.py             # sin cambios (el modelo por defecto no se toca aquí)
└── tests/
    ├── unit/                 # quota con factor · vencimiento semanal · reparto
    ├── integration/          # renovación · caída a comprado · reprecio
    └── isolation/            # lectura del presupuesto bajo RLS · fuga a cliente final

apps/worker/src/nexus_worker/metering/
├── pricing.py                # ModelPrice + quota_weight en el catálogo cacheado
└── consumer.py               # el canal debita SOLO comprado

packages/companion-ui/src/
├── messages.ts               # 9 cadenas: 2 con cifras, 6 con «mes», y 1 que
│                             # pasa a ser FALSA («esperar no lo desbloquea»)
└── components/composer.tsx   # el aviso de pausa deja de pintar «X de Y»

apps/console/src/app/(console)/usage/page.tsx    # barra y fecha, no cifra
apps/admin/src/app/(dashboard)/partners/[id]/    # cifras absolutas (operador)
apps/desktop/src/app/routes/account.tsx          # barra y fecha, no cifra
```

> **`packages/companion-ui` entró en esta lista durante la Fase 1, no antes.**
> El primer borrador del contrato decía «nada: no interpreta `period`». Al
> verificarlo apareció que sí pinta cifras absolutas en el aviso de pausa y que
> una de sus cadenas —*«esperar no lo desbloquea»*— **deja de ser cierta** en
> cuanto el pool se repone solo cada semana. Es un paquete compartido por la
> consola y la aplicación, así que el fallo habría salido en las dos.

**Structure Decision**: no hay estructura nueva. Se trabaja dentro del reparto
que el repositorio ya tiene (`apps/api`, `apps/worker`, `apps/console`,
`apps/admin`, `apps/desktop`), tocando los ficheros listados arriba. La razón de
que la lista sea corta es el §1 del `research.md` de la evaluación: el aparato ya
estaba construido, sólo estaba desconectado y con el período equivocado.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **Dos migraciones en un PR**, donde la regla 3 de `[[nexus/PLAN-CONSOLE-V1]]` dice «una migración por PR» | La Historia 1 (cargar tarifas) es **desplegable sola** y entrega valor sola: hace visible un margen que hoy no existe. Fundirla con el cambio de período y el factor obliga a desplegar las cuatro cosas a la vez y a revertirlas juntas | Una sola migración `0114` con todo dentro haría que revertir el cambio de período —que es el que toca el comportamiento de producción— arrastrase también las tarifas, que no tienen ningún motivo para volver atrás. El coste de la regla se paga aquí en claridad de reversión |

Nada más. El resto del plan no añade nada que la spec no pidiera.

## Re-evaluación del Constitution Check (post-diseño)

Hecha después de escribir `research.md`, `data-model.md` y los contratos.

| # | Estado tras el diseño | Qué cambió respecto a la primera pasada |
|---|---|---|
| I | ✅ | El diseño **confirma** la reducción: el camino que recorría membresías desaparece. Se añade una prueba de que el partner no puede leer el presupuesto de otro y de que ningún endpoint de cliente final nombra pool ni saldo |
| V | ✅ | El diseño destapó un matiz: el objeto de presupuesto **sigue llevando** las cifras absolutas porque el panel de operador las necesita, y es la **interfaz del partner** la que deja de pintarlas (decisión D6 del research). Eso no es una pantalla que miente: es una pantalla que resume, y el dato sigue disponible para quien tiene que conciliar |
| VII | ✅ | Los criterios se tradujeron a 43 comprobaciones nombradas en `quickstart.md`, repartidas entre unidad, integración y aislamiento |
| VIII | ✅ | Verificado sobre el diseño final: cero dependencias nuevas en `pyproject.toml` y en los `package.json` |
| IX | ✅ | La ADR-037 enlaza a la carpeta de la evaluación, y esta spec enlaza a la ADR. Puente cerrado en las dos direcciones |

**Ninguna fila en rojo. La puerta pasa.**

Una consecuencia del diseño que conviene dejar escrita antes de `/speckit-tasks`:
`partners.companion_monthly_token_cap` **deja de leerse** pero **no se borra** en
esta spec. Borrar una columna y crear su sustituta en la misma migración deja un
`downgrade()` que no puede devolver los datos. Se marca como deprecada en el
modelo, con la migración que la eliminará nombrada en el comentario.
