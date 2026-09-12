# Plan de implementación: la membresía y el cobro

**Rama**: `005-membresias-y-cobro` | **Fecha**: 2026-09-12 | **Spec**: [spec.md](./spec.md)

**Entrada**: especificación en `/specs/005-membresias-y-cobro/spec.md` ·
ADR `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` ·
evaluación `.specify/assessments/membresias-y-consumo-stripe/` ·
Spec A `specs/004-medidor-y-pool-semanal/`, implementada y en verde

## Summary

La spec no nombra al proveedor. **Aquí se elige: Stripe**, y se justifica en
[research.md](./research.md) §D1.

Cinco piezas, y la cuarta es la que lleva el riesgo:

1. **Los niveles existen como dato** — tres de pago y uno gratuito, con su
   tamaño de pool y sus topes de teammates y personas. Hoy esos topes **no
   existen**: no hay `max_teammates` ni límite de miembros.
2. **Dos caminos de cobro**: suscripción recurrente y compra de crédito de una
   vez. Los dos por página alojada del proveedor, de modo que **ningún dato de
   tarjeta toca nuestra infraestructura**.
3. **Un webhook que solo suma.** Firma verificada antes de leer el cuerpo,
   registro del evento antes de actuar, respuesta rápida y trabajo aparte,
   idempotencia por identificador de evento. Y una regla dura: **ningún aviso
   externo resta saldo**.
4. **La escalera de impago**, que es donde se puede hacer daño de verdad: nada
   se archiva, nada se cancela, ninguna confirmación pendiente se pierde.
5. **El recibo deja de ser la factura** y pasa a decir lo que el proveedor no
   sabe.

Y una sexta que no está en la spec porque no es producto: **el diseño soporta
cambiar de cuenta de Stripe** sin tocar el saldo de nadie.

## Technical Context

**Language/Version**: Python 3.11 (API y worker, `uv`) · TypeScript 5 con React
19 (consola Next.js 16, panel de operador, aplicación Electron)

**Primary Dependencies**: FastAPI · SQLAlchemy 2 asyncio · Alembic · Dramatiq ·
Next.js 16 · `@nexus/ui`.
**Dependencia nueva: `stripe`** — PyPI, **licencia MIT**, 15.6.1 del
2026-09-01. Párrafo de licencia y justificación en [research.md](./research.md) §D1.

**Storage**: PostgreSQL (Aurora, `eu-south-2`) con RLS `ENABLE` + `FORCE` en lo
que es del partner. Redis para la cola del worker.

**Testing**: `pytest` (`tests/unit`, `tests/integration`, `tests/isolation`) ·
`vitest` en consola, panel y aplicación. Para el proveedor: sus **relojes de
prueba** y su CLI para reenviar eventos, de modo que la escalera de impago se
pueda recorrer entera sin esperar un mes.

**Target Platform**: ECS Fargate + consola y panel en Vercel

**Project Type**: servicio web multi-tenant con cobro por suscripción y prepago

**Performance Goals**:
- El webhook responde en **menos de 500 ms** y hace el trabajo aparte. No es un
  número de estilo: el proveedor **espera hasta 10 segundos** nuestra respuesta
  a `checkout.session.completed` antes de redirigir al cliente, y una página de
  gracias que tarda diez segundos parece un pago fallido.
- Ninguna consulta nueva en el camino del turno. El cobro no toca el medidor.

**Constraints**:
- **Ningún dato de tarjeta entra en nuestra infraestructura**, ni en logs.
- **La conciliación va en una sola dirección**: lo de fuera suma, nunca resta.
- **El libro sigue siendo la verdad** (ADR-037 D3). El proveedor cobra.
- **Idempotencia en los dos sentidos**: por identificador de evento al recibir,
  por clave de idempotencia al enviar.
- **Solo USD**, y la moneda de un cliente es irreversible en el proveedor.

**Scale/Scope**: decenas de partners. El volumen no es el problema aquí; la
corrección del dinero, sí.

## La cuenta de Stripe es de un socio, temporalmente

**Dato de contexto, decidido el 2026-09-12**: la cuenta es la de **Andrés
Matos**, socio de Auphere, mientras se completa el registro fiscal de la
empresa. **Se cobra de verdad con ella**, y se migrará cuando la entidad exista.

Lo que eso significa técnicamente, y que el plan trata:

> **Stripe no traspasa clientes, suscripciones ni métodos de pago entre
> cuentas.** Migrar no es un traspaso: es recrear el catálogo, recrear los
> clientes y **pedirle a cada partner que vuelva a introducir su tarjeta**.

Tres decisiones de diseño lo abaratan, y están en [research.md](./research.md) §D5:

1. **Ningún identificador del proveedor es clave de nada nuestro.** Son
   columnas de referencia, anulables y reemplazables.
2. **El catálogo de precios se crea con un script idempotente** parametrizado
   por cuenta, para poder recrearlo entero contra la cuenta nueva.
3. **Un runbook de migración** escrito antes de necesitarlo.

> **Y una ventaja ya ganada, que conviene decir en voz alta.** Como el tope es
> de la plataforma y no del proveedor (ADR-037 D3), **migrar de cuenta no toca
> el saldo de ningún partner**. Se pierde el método de pago y la suscripción; el
> crédito comprado es nuestro y se queda donde está. Si el proveedor fuera la
> fuente de verdad del saldo, esta migración sería una reconstrucción contable.
> Es un argumento retrospectivo a favor de D3 que no teníamos cuando se decidió.

## Constitution Check

*PUERTA: rellenada antes de la Fase 0 y vuelta a comprobar tras el diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante | ✅ | Todo lo que esta spec crea es **del partner o de plataforma**: suscripción, compra de crédito y registro de eventos. Ninguna entidad nueva lleva `tenant_id`, así que no hay superficie por la que alcance a un cliente final. Test: `tests/isolation/test_billing_not_exposed_to_tenant.py` |
| II | Corte por superficie de confianza | ✅ | Superficie **`0`**. El webhook es un llamante externo, pero no de clase nueva: Meta y TikTok ya entregan. Lo que tiene de distinto —acredita saldo— se contiene con firma, idempotencia y la regla de que nunca resta |
| III | Lo leído es dato, nunca instrucción | ✅ | **Aplica de lleno y no es obvio**: el cuerpo del webhook es contenido externo. No se actúa sobre él directamente — se verifica la firma y luego **se recupera el objeto de la API del proveedor**, que es la única fuente que cuenta. Un importe que venga en el cuerpo no acredita nada |
| IV | Acción consecuente por un humano, y queda dicho quién | ✅ | Contratar, cambiar de plan, comprar crédito y cancelar son acciones de una **persona** con permiso de facturación, y la auditoría la nombra. El webhook **no es una acción de agente**: es la confirmación de algo que una persona ya decidió |
| V | Estados honestos; la ausencia se diseña | ✅ | La escalera de impago tiene estado propio y la pantalla dice en cuál está y qué lo arregla. Un partner en el nivel gratuito **no ve un botón apagado** de crear teammate (R1.4) |
| VI | Por API, nunca por navegador | ✅ | Toda la integración es por API del proveedor. El catálogo se crea con un script, no clicando |
| VII | Test primero; nada de `skip` | ✅ | Cada criterio nace como test. El proveedor da relojes de prueba y reenvío de eventos, así que la escalera de impago se recorre entera en integración |
| VIII | Licencias leídas enteras; AGPL no | ✅ | **`stripe` (PyPI), licencia MIT**, 15.6.1 del 2026-09-01. Párrafo citado en [research.md](./research.md) §D1. `tests/unit/test_no_new_dependencies.py` la vigila: entra tocando su BASELINE en el mismo commit |
| IX | La KB es dueña del porqué | ✅ | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]`, que supersede ADR-022 §1-§5 y §8-§10 y conserva §13-§15 |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | **1 · Postgres RLS** (la suscripción y la compra son del partner) · **4 · Acción consecuente** (quién contrató, quién compró) · **6 · Log + trace** (ningún registro con dato de tarjeta) | una tarea de test por garantía en `tests/isolation/` |
| **Licencias** | **`stripe`, MIT.** Única dependencia nueva | tarea que añade la dependencia **y** su párrafo, y toca el BASELINE del test que la vigila |
| **Medidor** | **Nada nuevo se mide.** Esta spec pone precio a lo que la Spec A ya mide, y mete dinero en el cubo comprado. El partner lo ve en Consumo, en unidades, porque es dinero que pagó (R3.6) | tarea de UI + tarea de contrato |

**Complejidad que hay que justificar**: ver §Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-membresias-y-cobro/
├── plan.md              # este fichero
├── research.md          # Fase 0 — las ocho decisiones, y la mina del §D4
├── data-model.md        # Fase 1 — tablas y columnas nuevas
├── quickstart.md        # Fase 1 — cómo se verifica, con relojes de prueba
├── runbook-migracion-cuenta.md   # cómo se cambia de cuenta sin perder saldo
├── contracts/
│   ├── billing-api.md   # lo que la consola llama
│   └── webhook.md       # lo que el proveedor nos manda y qué hacemos con ello
├── checklists/
│   └── requirements.md  # completo
└── tasks.md             # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   ├── 0116_membership_tiers.py        # niveles, topes y estado de suscripción
│   └── 0117_billing_events.py          # registro de eventos y compras
├── src/nexus_api/
│   ├── billing/                        # paquete nuevo: todo lo del proveedor
│   │   ├── provider.py                 # el cliente, aislado tras una interfaz
│   │   ├── catalog.py                  # nivel → precio del proveedor
│   │   ├── checkout.py                 # abrir sesión de suscripción y de crédito
│   │   ├── events.py                   # verificar, registrar, despachar
│   │   └── ladder.py                   # estado de suscripción ← estado del proveedor
│   ├── api/console/
│   │   ├── billing.py                  # + contratar, cambiar, comprar, portal
│   │   └── wallet.py                   # se BORRA la puerta de recarga sin pago
│   ├── api/webhooks/
│   │   └── billing.py                  # el endpoint: firma → registrar → encolar → 200
│   ├── db/models/
│   │   ├── membership.py               # niveles y suscripción del partner
│   │   └── billing_event.py            # registro de avisos recibidos
│   └── services/
│       ├── membership_limits.py        # los topes, en un solo sitio
│       └── partner_receipt.py          # + línea de membresía y de consumo
└── tests/{unit,integration,isolation}/

apps/worker/src/nexus_worker/
└── billing/
    ├── process_event.py                # el trabajo de verdad, fuera del webhook
    └── expire_credit_cron.py           # los doce meses del saldo tras la baja

apps/console/src/app/(console)/billing/  # contratar, cambiar, comprar, estado
apps/admin/src/app/(dashboard)/partners/[id]/   # el operador ve la suscripción

scripts/
└── sync_billing_catalog.py             # idempotente, lo ejecuta Luis

# Documentación que describe lo que esta spec cambia, y se actualiza EN EL
# MISMO COMMIT que el cambio:
docs/companion/CONTRACT-V2.md           # §6, la escalera gana escalones
docs/billing.md                         # nuevo: cómo se cobra y cómo se migra
```

**Structure Decision**: un paquete `billing/` nuevo en la API, y **todo lo del
proveedor dentro**. No es organización por gusto: es lo que hace que cambiar de
cuenta —o algún día de proveedor— sea un trabajo acotado y no una excavación.
El resto del código conoce «una suscripción» y «una compra»; no conoce Stripe.

## Complexity Tracking

| Violación | Por qué hace falta | Alternativa más simple, y por qué se rechaza |
|---|---|---|
| **Dos migraciones** (`0116`, `0117`) contra la regla 3 de `[[nexus/PLAN-CONSOLE-V1]]` | Los niveles y sus topes (`0116`) son **desplegables solos** y entregan valor solos: fijan los límites sin cobrar nada. El registro de eventos y compras (`0117`) solo tiene sentido con el cobro | Una sola migración obliga a desplegar y revertir las dos mitades juntas, y la primera no tiene ningún riesgo mientras que la segunda toca dinero |
| **Un paquete nuevo** (`billing/`) en vez de meterlo en `services/` | El proveedor es una frontera, y la spec dice que la migración de cuenta va a pasar. Un paquete con una interfaz delante es lo que convierte esa migración en trabajo acotado | Repartirlo entre `services/` y `api/` funciona hoy y hace que mañana haya que buscar «dónde hablamos con Stripe» por todo el repositorio |
| **Un script fuera de `apps/`** (`scripts/sync_billing_catalog.py`) | Crea objetos en una cuenta con capacidad de cobro. No es código de la aplicación y **no debe poder ejecutarse por accidente desde ella** | Un comando de la API lo dejaría a un `POST` de distancia de crear precios en producción |

## Re-evaluación del Constitution Check (post-diseño)

| # | Estado | Qué cambió al diseñar |
|---|---|---|
| III | ✅ | **Reforzado, y es el hallazgo del diseño.** El cuerpo del webhook es contenido externo; el diseño no actúa sobre él, sino sobre el objeto **recuperado de la API**. La documentación del proveedor lo pide por otra razón (el cuerpo puede estar obsoleto), y el principio III lo pide por la nuestra: lo que llega de fuera es dato |
| IV | ✅ | El diseño distingue **quién decidió** (la persona, en la auditoría) de **qué lo confirmó** (el aviso del proveedor). Sin esa distinción, la auditoría diría que un webhook contrató un plan |
| V | ✅ | La escalera de impago mapea cuatro estados del proveedor a los cuatro nuestros, y **el mapeo es explícito** (research §D6). Un estado del proveedor que no esperábamos no puede caer en «al corriente» por defecto |
| VII | ✅ | Los relojes de prueba del proveedor permiten recorrer la escalera entera en integración, así que los criterios de R5 son tests de verdad y no comprobaciones de que existe una columna |
| VIII | ✅ | Verificado sobre el diseño final: **una** dependencia nueva, MIT |

**Ninguna fila en rojo. La puerta pasa.**

Dos consecuencias del diseño que conviene leer antes de `/speckit-tasks`:

1. **La mina de la finalización de facturas** ([research.md](./research.md) §D4).
   Si nuestro webhook no responde correctamente a `invoice.created`, el
   proveedor **retrasa la finalización de todas las facturas hasta 72 horas** —
   las de todos los partners, no solo la del evento. Es el peor modo de fallo de
   esta spec y no es evidente: el sistema no se cae, simplemente deja de
   facturar.
2. **`partners.status` no sirve** para el estado de suscripción. Solo admite
   `active` y `suspended`, y significa otra cosa: si un partner está operativo.
   Un partner impagado sigue estando operativo para leer su historia.
