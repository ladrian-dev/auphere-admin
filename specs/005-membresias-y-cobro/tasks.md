# Tareas: la membresía y el cobro

**Entrada**: documentos de diseño en `/specs/005-membresias-y-cobro/`
**Rama**: `005-membresias-y-cobro`

**Tests**: **NO son opcionales.** §VII — cada criterio nace como test, se ve en
**ROJO**, y solo entonces se implementa. Un test que hace `skip` no cubre nada.

**Organización**: por historia de usuario, para que cada una se pueda desplegar
y probar sola.

## Reglas de este repo *(constitución)*

- Cada tarea cita `_Requisitos: N.m_`. Las puertas de plan citan «—».
- **Test primero (§VII)**: los bloques de tests van antes que los de
  implementación y se citan entre ellos.
- **Aislamiento (§I)**: una tarea de test por garantía declarada. En rojo
  bloquea el merge.
- **Licencias (§VIII)**: `stripe` 15.6.1, MIT. Entra con su párrafo citado y el
  BASELINE tocado **en el mismo commit**.
- **Medidor**: nada nuevo se mide. El saldo comprado se ve **en unidades** en
  Consumo (R3.6) — su tarea es T068.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: puede ir en paralelo (fichero distinto, sin dependencia pendiente).
- **[Story]**: `[US1]`…`[US5]`.

## Convenciones de ruta

- API: `apps/api/src/nexus_api/…`, tests en `apps/api/tests/{unit,integration,isolation}/`
- Worker: `apps/worker/src/nexus_worker/…`
- Consola: `apps/console/src/…`
- Migraciones: `apps/api/alembic/versions/`

> **Dos avisos que cuestan caro si se olvidan.**
> 1. El `revision` de una migración **no puede pasar de 32 caracteres**:
>    `alembic_version.version_num` es `varchar(32)` y revienta **después** de
>    haber hecho su trabajo. `0116_membership_tiers` (20) y `0117_billing_events`
>    (19) caben.
> 2. **No ejecutar `ruff format` sobre `alembic/`.** El CI solo formatea `src` y
>    `tests`; reformatear migraciones históricas ensucia el diff con 38 ficheros.

---

## Phase 1: Setup

**Propósito**: la dependencia, la frontera y las llaves. Nada de esto cobra.

- [X] T001 Añadir `stripe = "==15.6.1"` a `apps/api/pyproject.toml` y regenerar `apps/api/uv.lock` con `uv sync`. **Mismo commit que T002.** _Requisitos: —_
- [X] T002 Actualizar el BASELINE de `apps/api/tests/unit/test_no_new_dependencies.py` con `stripe` y dejar el párrafo MIT citado en el propio test, tal como lo recoge `research.md` §D1 (V56, §VIII) _Requisitos: —_
- [X] T003 [P] Crear el paquete `apps/api/src/nexus_api/billing/` con `__init__.py` y `provider.py`, donde vive el **único** `import stripe` del repositorio (research §D2) _Requisitos: 2.2, 2.6_
- [X] T004 [P] Añadir `billing_api_key`, `billing_public_key` y `billing_webhook_secret` a `apps/api/src/nexus_api/config.py` **sin valor por defecto y sin `change-me`**: si faltan, el paquete queda cerrado y las rutas responden `503 billing_unavailable` (contracts/webhook.md) _Requisitos: 2.2, 2.6_
- [X] T005 [P] Test estructural en `apps/api/tests/unit/test_billing_boundary.py`: recorre `src/` y **falla si aparece `import stripe` fuera de `nexus_api/billing/`** (V56, research §D2). Pasa desde el primer día a propósito — es un invariante, no una funcionalidad _Requisitos: —_
- [X] T006 [P] Test estructural en el mismo fichero: **el paquete `billing/` no importa `debit_wallet`** (research §D3, la conciliación va en una sola dirección) _Requisitos: 3.4_
- [X] T007 [P] Test estructural en el mismo fichero: **el camino del turno no importa `nexus_api.billing`** — ni `metering/`, ni `api/console/companion.py`, ni el runtime del agente. Cubre **CE-004** y **V57**: con el proveedor de pago caído el trabajo continúa con el saldo que ya hay, y solo deja de poderse comprar. Es la misma clase de avería que el `_require_wallet` de `resume_run` que la Spec A tuvo que quitar: una dependencia colada en el camino caliente que no se ve hasta que el externo falla _Requisitos: —_

---

## Phase 2: Foundational (bloquea todas las historias)

**⚠️ Ninguna historia puede empezar hasta que esto esté.**

### Tests de esquema (rojo primero)

- [X] T008 Test en `apps/api/tests/integration/test_migration_0116.py`: tras `upgrade`, `membership_tiers` existe con `CHECK (code IN ('free','pro','team','business'))`, `monthly_price_cents >= 0`, `weekly_pool_tokens >= 0`, `max_teammates >= 0`, `max_members >= 1`; `stripe_price_id` es `varchar(64)` **NULL, sin UNIQUE y sin FK**; y hay **cuatro filas** con las cifras de `data-model.md` _Requisitos: 1.1, 1.5_
- [X] T009 Test en el mismo fichero: `partner_subscriptions` existe con PK `partner_id`, `CHECK (state IN ('current','payment_failed','unpaid','canceled'))`, `tier_code` con FK a `membership_tiers.code` y **RLS `ENABLE` + `FORCE`** _Requisitos: 5.1_
- [X] T010 Test en `apps/api/tests/integration/test_migration_0117.py`: `billing_events` con `provider_event_id varchar(80) UNIQUE`, `payload jsonb`, **`partner_id` sin FK** (research: un aviso de una cuenta desconocida tiene que poder registrarse), índice parcial sobre `checkout_session_id`; y `partner_wallets.purchased_expires_at timestamptz NULL` _Requisitos: 4.2, 7.1_

### Migraciones y modelos

- [X] T011 Migración `apps/api/alembic/versions/0116_membership_tiers.py` — `revision = "0116_membership_tiers"`, crea las dos tablas, siembra las cuatro filas y activa RLS+FORCE por `partner_id` en `partner_subscriptions` copiando el patrón de la 0094 _Requisitos: 1.1, 1.5, 5.1_
- [X] T012 [P] Modelo `MembershipTier` en `apps/api/src/nexus_api/db/models/membership.py` _Requisitos: 1.1_
- [X] T013 [P] Modelo `PartnerSubscription` en el mismo fichero, con la nota de por qué **no se reutiliza `partners.status`**: su CHECK solo admite `'active'|'suspended'` y significa si el partner está operativo _Requisitos: 5.1_
- [X] T014 Migración `apps/api/alembic/versions/0117_billing_events.py` — `revision = "0117_billing_events"`, crea `billing_events` y añade `partner_wallets.purchased_expires_at` _Requisitos: 4.2, 7.1_
- [X] T015 [P] Modelo `BillingEvent` en `apps/api/src/nexus_api/db/models/billing_event.py` _Requisitos: 4.2_
- [X] T016 [P] Añadir `purchased_expires_at` a `PartnerWallet` en `apps/api/src/nexus_api/db/models/partner_wallet.py`, con el comentario de la invariante: **`NULL` mientras la cuenta viva** (research §D8) _Requisitos: 7.1_
- [X] T017 Registrar los tres modelos en `apps/api/src/nexus_api/db/models/__init__.py` y su `__all__` _Requisitos: 1.1, 4.2, 5.1_
- [X] T018 Test de reversibilidad en `apps/api/tests/integration/test_migration_reversibility.py`: `downgrade` deja el esquema como estaba, contra la base local _Requisitos: —_

### El puente con el proveedor

- [X] T019 Cliente del proveedor en `apps/api/src/nexus_api/billing/provider.py`: crear sesión, recuperar objeto, modificar suscripción, programar bajada. **Toda llamada que crea o modifica lleva clave de idempotencia** con el patrón de `contracts/webhook.md` — **nunca** con un id del proveedor, siempre con el nuestro _Requisitos: 2.1, 3.1_
- [X] T020 [P] `apps/api/src/nexus_api/billing/catalog.py`: resuelve `code → stripe_price_id` leyendo `membership_tiers`. **El mapeo es una fila, no un literal** (research §D5.2) _Requisitos: 1.5_
- [X] T021 [P] `scripts/sync_billing_catalog.py`: idempotente por `code`, parametrizado por cuenta vía `BILLING_API_KEY`, con `--dry-run` y `--apply`; escribe los `stripe_price_id` en `membership_tiers`. **Fuera de `apps/` a propósito** para que no se pueda disparar desde la API. Lo ejecuta Luis con sus claves _Requisitos: 1.5_
- [X] T022 Comprobación de arranque en `apps/api/src/nexus_api/billing/provider.py` (V61): **avisar** de que hay que comprobar a mano que la cuenta manda las suscripciones a `unpaid` tras agotar los reintentos. **Stripe no expone ese ajuste por API** —comprobado el 2026-09-12—, así que el aviso es lo único que se puede automatizar; la comprobación real vive en el runbook. Stripe pone `unpaid` **solo si el panel está configurado así**; con los valores por defecto el escalón «impagada» de ADR-037 D6 **no ocurre nunca** y un impago salta directo a cancelada. Es una decisión de producto que vive en una casilla de configuración, y las casillas se pierden — sobre todo al cambiar de cuenta _Requisitos: 5.1, 5.3_

**Checkpoint**: el esquema está, el catálogo se puede crear, y nadie ha cobrado nada.

---

## Phase 2b: Las puertas de la constitución

- [X] T023 Test de aislamiento **garantía 1 (RLS)** en `apps/api/tests/isolation/test_subscription_scope.py`: un partner **no ve** la fila de `partner_subscriptions` de otro, ni por la API ni por consulta directa con el rol de aplicación (V53). En rojo bloquea el merge (§I) _Requisitos: 5.1_
- [ ] T024 [P] Test de aislamiento **garantía 4 (acción consecuente)** en `apps/api/tests/isolation/test_billing_audit_names_the_person.py`: contratar, cambiar, comprar y cancelar dejan asiento que **nombra a la persona** de consola, no al proceso ni al partner (V12, V54, §IV) _Requisitos: 2.5_
- [X] T025 [P] Test de aislamiento **garantía 6 (log/trace)** en `apps/api/tests/isolation/test_billing_logs_carry_no_card.py`: con `structlog.testing.capture_logs()`, **ningún** registro del camino del cobro lleva patrón de tarjeta (PAN, CVC, `last4`) ni contenido de conversación. Copiar la forma de `test_wallet_events_are_logged.py`, que ya vigila esto para el libro. **Cubre V09, V27 y V55**, que el quickstart enuncia por separado por llegar desde tres requisitos distintos: es una sola comprobación _Requisitos: 2.2, 4.6_
- [X] T026 Test de aislamiento en `apps/api/tests/isolation/test_billing_not_exposed_to_tenant.py`: ninguna entidad de esta spec es alcanzable desde un tenant — no llevan `tenant_id` y no aparecen en ninguna ruta de tenant _Requisitos: 4.6_

> **Puerta del medidor**: nada nuevo se mide. Lo que sí hay que conectar es que
> el partner vea **en unidades** el saldo que pagó (R3.6). Su tarea es **T068**,
> dentro de la Historia 2, porque sin compra no hay nada que mostrar. La puerta
> no se borra: tiene dueño.

**Checkpoint**: las tres garantías tienen test. `/speckit-analyze` puede dar verde.

---

## Phase 3: Historia 1 — Un partner se suscribe y empieza a trabajar (P1) 🎯 MVP

**Objetivo**: una persona elige un plan, paga, y su cuenta queda con el nivel y
el pool **sin que nadie de Auphere intervenga**.

**Prueba independiente**: recorrido completo en modo de prueba; al final el
partner tiene nivel, pool y puede crear teammates hasta su tope.

### Tests de la Historia 1 (§VII — escribir, ver en ROJO, y solo entonces implementar) ⚠️

- [X] T027 [P] [US1] Test de contrato de `GET /console/billing/membership` en `apps/api/tests/integration/test_console_billing_contract.py`: la forma de `contracts/billing-api.md`, con `usage` incluido y **sin cifras de pool ni de saldo** — eso es del medidor único _Requisitos: 1.1, 5.7_
- [X] T028 [P] [US1] Test de integración del recorrido de suscripción en `apps/api/tests/integration/test_subscribe_flow.py` (V08, V10): al confirmarse el pago, **nivel y pool se aplican en el mismo acto** _Requisitos: 2.1, 2.3_
- [X] T029 [P] [US1] Test: abandonar el pago a medias **no cambia nada** (V11) _Requisitos: 2.4_
- [X] T030 [P] [US1] Test en `apps/api/tests/integration/test_billing_webhook.py`: firma inválida y firma ausente → `400`, **sin interpretar el cuerpo**, con rastro (V21, V22) _Requisitos: 4.1_
- [X] T031 [P] [US1] Test: el evento **se registra antes** de actuar — se fuerza un fallo del trabajo y la fila existe con `status='failed'` (V23) _Requisitos: 4.2_
- [X] T032 [P] [US1] Test: el webhook responde en **< 500 ms** con el trabajo encolado y no ejecutado (V24) _Requisitos: 4.3_
- [X] T033 [P] [US1] Test: cinco reenvíos del mismo evento acreditan **una vez**; entrega concurrente incluida (V16, V25) _Requisitos: 4.4_
- [X] T034 [P] [US1] Test: `subscription.updated` **antes** que `invoice.paid` no deja el estado incoherente (V26) _Requisitos: 4.5_
- [X] T035 [P] [US1] Test: el importe **se recupera de la API**, no se lee del cuerpo — cuerpo manipulado, se acredita el real (V28). Es §III hecho test _Requisitos: 4.1, 4.5_
- [X] T036 [P] [US1] Test unitario en `apps/api/tests/unit/test_billing_events_subscribed.py`: **`invoice.created` NO está en la lista de eventos manejados** (V29). Si lo estuviera y el manejador fallara, el proveedor retrasaría la finalización de **todas** las facturas hasta 72 horas _Requisitos: 4.3_
- [X] T037 [P] [US1] Test de topes en `apps/api/tests/integration/test_membership_limits.py` (V01, V02, V03, V06): el teammate `n+1` y la persona `n+1` fallan diciendo **cuál es el tope y cómo se sube**, y **no se archiva ninguno existente** _Requisitos: 1.2, 1.3, 1.6_
- [X] T038 [P] [US1] Test: cambiar `weekly_pool_tokens` de un nivel con un `UPDATE` surte efecto **sin reiniciar ni migrar** (V05) _Requisitos: 1.5_
- [X] T039 [P] [US1] Test en `apps/api/tests/integration/test_console_billing_contract.py` (V58): **la cifra absoluta del pool no sale por `/console/billing/membership`**, ni en `tier` ni en `catalog`; salen los topes y `consumption_multiple`, y el múltiplo **se calcula** — se cambia `weekly_pool_tokens` de un nivel y el múltiplo cambia solo, sin tocar ninguna otra fila. El panel de operador **sí** sigue viendo la cifra (Spec A R7.2) _Requisitos: 1.8_
- [X] T040 [P] [US1] Test: conceder un nivel **no toca `partners.max_clients`** (V07) _Requisitos: 1.7_
- [X] T041 [P] [US1] Test de consola en `apps/console/src/app/(console)/billing/__tests__/membership.test.tsx` (V04): en el nivel gratuito **no existe** el control de crear teammate ni el de ejecución en la máquina — **ni apagado**. La ausencia se diseña (§V) _Requisitos: 1.4_
- [X] T042 [P] [US1] Test en `apps/api/tests/unit/test_console_has_no_billing_credential.py`: `grep` en `apps/console` por las variables de clave del proveedor, al estilo del que ya existe para `NEXUS_ADMIN_TOKEN` (V13) _Requisitos: 2.6_
- [X] T043 [P] [US1] Test en `apps/api/tests/integration/test_billing_webhook.py` (V59, V60): **`invoice.finalization_failed` alerta al operador y NO degrada al partner** —la suscripción sigue `active`, nuestro estado no se mueve, y la alerta lleva `last_finalization_error`—; y el manejador **resuelve el partner por `client_reference_id`**, no buscando por `stripe_customer_id`. La primera mitad es la avería más silenciosa de la spec: una factura que no finaliza deja al partner trabajando y a nosotros sin cobrar, sin ningún síntoma _Requisitos: 4.5, 5.1_

### Implementación de la Historia 1

- [X] T044 [US1] `apps/api/src/nexus_api/services/membership_limits.py`: los topes en **un solo sitio**, con el error que dice el tope y cómo se sube (hace verde T037) _Requisitos: 1.2, 1.3_
- [X] T045 [US1] Enganchar el tope de teammates en `apps/api/src/nexus_api/api/console/teammates.py` _Requisitos: 1.2_
- [X] T046 [US1] Enganchar el tope de personas en `apps/api/src/nexus_api/api/console/invitations.py` y `team.py` _Requisitos: 1.3_
- [X] T047 [US1] `apps/api/src/nexus_api/billing/events.py`: leer el cuerpo **en crudo**, verificar la firma, `INSERT` por `provider_event_id`, resolver el partner, encolar, `200` (hace verde T030–T033) _Requisitos: 4.1, 4.2, 4.3, 4.4_
- [X] T048 [US1] Endpoint `POST /webhooks/billing` en `apps/api/src/nexus_api/api/webhooks/billing.py`, copiando el patrón de lectura cruda de `webhooks/meta.py` _Requisitos: 4.1, 4.3_
- [X] T049 [US1] Trabajo de fondo en `apps/worker/src/nexus_worker/billing/process_event.py`: **recupera el objeto de la API** antes de actuar (hace verde T035) _Requisitos: 4.5_
- [X] T050 [US1] Manejador de `invoice.paid` en `apps/api/src/nexus_api/billing/ladder.py`: aplica `tier_code`, `state='current'`, **copia `weekly_pool_tokens` al partner** y fija `current_period_end`, todo en la misma transacción (hace verde T028) _Requisitos: 2.3_
- [X] T051 [US1] Manejador de **`invoice.finalization_failed`** en `apps/api/src/nexus_api/billing/ladder.py`: **alerta al operador** con el `last_finalization_error` de la factura y **no toca el estado del partner** —no es culpa suya, y la suscripción sigue `active` en el proveedor. Sin este manejador, una factura que no finaliza es cobertura sin cobro y **no da ningún síntoma** (research §D10) _Requisitos: 4.5_
- [X] T052 [US1] `apps/api/src/nexus_api/billing/checkout.py`: sesión de suscripción con `success_url` llevando `{CHECKOUT_SESSION_ID}` y **`client_reference_id = partner_id`** (UUID de 36 caracteres; el límite documentado es 200), más el mismo valor en `metadata` de la suscripción. Es lo que permite resolver el partner **desde el aviso** en vez de buscando por `stripe_customer_id`, y lo que mantiene esa columna borrable (research §D10) _Requisitos: 2.1_
- [X] T053 [US1] `GET /console/billing/membership` y `POST /console/billing/checkout` en `apps/api/src/nexus_api/api/console/billing.py` — se **amplía** el router existente, no se sustituye. La respuesta describe cada nivel por **sus topes** y por un **`consumption_multiple` calculado en el servidor** a partir de `weekly_pool_tokens` —`null` en Free, `1` en el base—, y **nunca la cifra absoluta**, ni en `tier` ni en `catalog` (research §D9) _Requisitos: 1.1, 1.8, 2.1_
- [X] T054 [US1] `GET /console/billing/portal` en el mismo fichero: la gestión de tarjeta y las facturas se delegan al proveedor, que es lo que evita tocar datos de tarjeta _Requisitos: 2.2, 8.4_
- [X] T055 [US1] Auditoría que **nombra a la persona** de consola en contratar y cambiar, no al proceso (hace verde T024) _Requisitos: 2.5_
- [X] T056 [US1] Pantalla de membresía y planes en `apps/console/src/app/(console)/billing/page.tsx`, con los cinco estados (cargando, vacío, error, parcial, ideal). Cada nivel se presenta con **cuántos agentes y cuántas personas admite** y su múltiplo de consumo, **sin número de unidades** _Requisitos: 1.1, 1.8, 5.7_
- [X] T057 [US1] En el nivel gratuito, **no renderizar** los controles de teammate ni de ejecución en la máquina (hace verde T041) _Requisitos: 1.4_
- [X] T058 [US1] Traducir los errores del proveedor a los códigos de `contracts/billing-api.md`: **nunca** mostrar el mensaje crudo de una API externa a una persona (§III) _Requisitos: 5.7_

**Checkpoint**: un partner puede pagar y empezar. **Es el MVP y se despliega solo.**

---

## Phase 4: Historia 2 — Comprar crédito (P1)

**Objetivo**: el saldo sube después de un pago confirmado, y **solo** después.

**Prueba independiente**: se compra, se acredita una vez; se abandona, no se
acredita nada.

### Tests de la Historia 2 ⚠️

- [X] T059 [P] [US2] Test en `apps/api/tests/integration/test_buy_credit.py` (V14): compra completa → `purchased_remaining` sube por la cantidad comprada _Requisitos: 3.1_
- [X] T060 [P] [US2] Test: una **sesión abierta y no pagada** no acredita nada (V15) _Requisitos: 3.2_
- [X] T061 [P] [US2] Test: `checkout.session.completed` y `async_payment_succeeded` de **la misma sesión** acreditan **una vez** — son eventos distintos, así que el UNIQUE por `provider_event_id` no basta: la segunda ancla es `checkout_session_id` (V17) _Requisitos: 3.3_
- [X] T062 [P] [US2] Test: `payment_status == 'unpaid'` **no acredita** _Requisitos: 3.1, 3.2_
- [X] T063 [P] [US2] Test exhaustivo en `apps/api/tests/integration/test_no_external_debit.py` (V18): se recorren **todos** los tipos de evento manejados con el saldo en 50 000 y **nunca baja**. La avería que previene no es un caso, es una clase _Requisitos: 3.4_
- [X] T064 [P] [US2] Test: `POST /console/wallet/purchased` responde `404` **y la ruta no está en el código** (V19) _Requisitos: 3.5_
- [X] T065 [P] [US2] Test de consola (V20): el saldo comprado se ve **en unidades**, porque es dinero que el partner pagó _Requisitos: 3.6_

### Implementación de la Historia 2

- [X] T066 [US2] Sesión de crédito en `apps/api/src/nexus_api/billing/checkout.py`, con mínimo y máximo por compra validados en la API — un máximo protege de un cero de más tecleado _Requisitos: 3.1_
- [X] T067 [US2] Manejadores de `checkout.session.completed` y `checkout.session.async_payment_succeeded`: comprobar `payment_status != 'unpaid'`, anclar en `checkout_session_id`, y llamar a **`add_purchased`**, que ya existe, es idempotente por fila y está probado _Requisitos: 3.1, 3.3_
- [X] T068 [US2] `POST /console/billing/credit` en `apps/api/src/nexus_api/api/console/billing.py` y la vista de Consumo mostrando el saldo comprado **en unidades** — **ésta es la puerta del medidor** _Requisitos: 3.1, 3.6_
- [X] T069 [US2] **Borrar** `POST /console/wallet/purchased` de `apps/api/src/nexus_api/api/console/wallet.py:194` y su esquema. Se borra el endpoint, **no** el modelo ni `add_purchased`. Una puerta que añade saldo sin pago no debe existir ni apagada _Requisitos: 3.5_
- [X] T070 [US2] Pantalla de compra de crédito en `apps/console/src/app/(console)/billing/`, con los cinco estados _Requisitos: 3.1, 3.6_

**Checkpoint**: el partner puede recargar. US1 + US2 son el negocio completo.

---

## Phase 5: Historia 3 — El impago degrada, y nada desaparece (P2)

**Objetivo**: recorrer la escalera entera sin que se pierda trabajo de nadie.

**Prueba independiente**: con relojes de prueba se simula cada escalón y se
comprueba qué sobrevive.

> Aquí entra también **R7 (la caducidad a doce meses)**: su disparador es la
> cancelación, que es el último escalón de esta escalera. Separarla en otra
> historia dejaría un estado a medias.

### Tests de la Historia 3 ⚠️

- [ ] T071 [P] [US3] Test unitario en `apps/api/tests/unit/test_subscription_state_map.py` (V30): el mapeo cubre los ocho estados del proveedor (`trialing`, `active`, `incomplete`, `incomplete_expired`, `past_due`, `unpaid`, `canceled`, `paused`) y **un estado inventado hace fallar el manejador** dejando el estado anterior intacto. **No cae en `current` por defecto**: eso sería acceso regalado y silencioso _Requisitos: 5.1_
- [ ] T072 [P] [US3] Test en `apps/api/tests/integration/test_dunning_ladder.py` (V31): en **pago fallido** el pool **no se repone** en el ciclo siguiente y el saldo comprado **sí se gasta** _Requisitos: 5.2_
- [ ] T073 [P] [US3] Test (V32): en **impagada** el trabajo nuevo para con **el mismo** estado que ya existe para quedarse sin saldo (spec 003), no con uno nuevo _Requisitos: 5.3_
- [ ] T074 [P] [US3] Test (V33) — **el corazón de la spec**: en impagada **ningún teammate se archiva, ninguna tarea se cancela y ninguna confirmación pendiente se invalida**, y una confirmación pendiente **se puede responder sin saldo**. Se cuentan las tres cosas antes y después y se responde la confirmación (§IV, «borrar no existe»; spec 003 R9.3) _Requisitos: 5.3_
- [ ] T075 [P] [US3] Test (V34): un pago confirmado devuelve a **al corriente sin intervención manual** _Requisitos: 5.4_
- [ ] T076 [P] [US3] Test (V35): cancelar baja a Free **al terminar el período pagado**, con la historia intacta _Requisitos: 5.5_
- [ ] T077 [P] [US3] Test (V36): el aviso al partner sale **antes** del cambio de estado, no después _Requisitos: 5.6_
- [ ] T078 [P] [US3] Test de consola (V37): los cuatro estados se pintan diciendo **qué lo arregla**, sin presentarlo como un error del partner _Requisitos: 5.7_
- [ ] T079 [P] [US3] Test en `apps/api/tests/integration/test_purchased_expiry.py` (V43): con la cuenta viva, `purchased_expires_at` es **`NULL`** y el saldo no caduca aunque se avance un año _Requisitos: 7.1_
- [ ] T080 [P] [US3] Test (V44): al cancelar se fija a **12 meses** _Requisitos: 7.2_
- [ ] T081 [P] [US3] Test (V45): reactivar dentro del plazo lo vuelve a dejar a **`NULL`**, **sin que nadie reponga nada a mano** _Requisitos: 7.3_
- [ ] T082 [P] [US3] Test (V46): al cancelar, la respuesta dice **cuánto saldo conserva y hasta cuándo** _Requisitos: 7.4_
- [ ] T083 [P] [US3] Test (V47): al caducar queda **asiento en `usage_ledger`** con cuánto y cuándo. Esto **resta** saldo y no contradice D3: lo decide una regla nuestra, con fecha nuestra, y deja apunte _Requisitos: 7.5_

### Implementación de la Historia 3

- [ ] T084 [US3] `apps/api/src/nexus_api/billing/ladder.py`: el mapeo **exhaustivo** estado del proveedor → estado nuestro, con la tabla de `research.md` §D6 (hace verde T071) _Requisitos: 5.1_
- [ ] T085 [US3] Manejadores de `invoice.payment_failed`, `customer.subscription.updated` y `customer.subscription.deleted` _Requisitos: 5.1, 5.2, 5.5_
- [ ] T086 [US3] Pausar la reposición del pool en `apps/api/src/nexus_api/metering/wallet.py`: `renew_included_if_expired` no repone si el estado no es `current`. **El saldo comprado sigue gastándose** _Requisitos: 5.2, 5.3_
- [ ] T087 [US3] `DELETE /console/billing/subscription` en `apps/api/src/nexus_api/api/console/billing.py`: efecto a fin de período, **nada se archiva**, y fija `purchased_expires_at` a 12 meses _Requisitos: 5.5, 7.2, 7.4_
- [ ] T088 [US3] Reactivación: al volver a `current`, `purchased_expires_at` vuelve a **`NULL`** (hace verde T081) _Requisitos: 7.3_
- [ ] T089 [US3] `apps/worker/src/nexus_worker/billing/expire_credit_cron.py`: pone a cero los cubos cuya fecha pasó **dejando asiento con su motivo** (hace verde T083) _Requisitos: 7.5_
- [ ] T090 [US3] Notificación previa a la degradación, reutilizando `evaluate_partner_wallet_alerts` — que toma un `Partner`, no un id _Requisitos: 5.6_
- [ ] T091 [US3] Pintar los cuatro estados en `apps/console/src/app/(console)/billing/`, diciendo qué lo arregla _Requisitos: 5.7_
- [ ] T092 [US3] Actualizar `docs/companion/CONTRACT-V2.md` §6 con los escalones nuevos, **en el mismo commit** que el cambio _Requisitos: 5.3_

**Checkpoint**: la escalera se recorre entera y no se pierde nada de nadie.

---

## Phase 6: Historia 4 — Subir y bajar de plan (P2)

**Objetivo**: cambiar de plan sin perder nada de lo ya pagado.

**Prueba independiente**: se cambia en los dos sentidos y se comprueba el pool
de la semana en curso y el saldo comprado.

### Tests de la Historia 4 ⚠️

- [ ] T093 [P] [US4] Test unitario en `apps/api/tests/unit/test_pool_top_up.py` (V39): con 100 000 gastados de 500 000, subir a 1 000 000 deja **900 000** disponibles. Ni 1 000 000 (regalaría lo consumido) ni 400 000 (cobraría el nivel nuevo sin darlo). Aritmética exacta _Requisitos: 6.2_
- [ ] T094 [P] [US4] Test unitario (V42): cambio de nivel **en el mismo instante** que la reposición del ciclo — el pool no queda ni duplicado ni a cero _Requisitos: 6.5_
- [ ] T095 [P] [US4] Test de integración en `apps/api/tests/integration/test_plan_change.py` (V38): subir es **inmediato** y el pool nuevo está disponible en el mismo turno _Requisitos: 6.1_
- [ ] T096 [P] [US4] Test (V40): bajar se aplica **a fin de período** y el pool del ciclo en curso **no se reclama** _Requisitos: 6.3_
- [ ] T097 [P] [US4] Test (V41): **ninguna** de las cuatro transiciones altera `purchased_remaining` _Requisitos: 6.4_
- [ ] T098 [P] [US4] Test: bajar a un nivel con menos topes de los que ya se usan → `409 tier_below_usage` diciendo cuántos sobran, **sin archivar nada** _Requisitos: 1.6_

### Implementación de la Historia 4

- [ ] T099 [US4] `top_up_included_to(partner_id, new_pool_size)` en `apps/api/src/nexus_api/metering/wallet.py`: **suma la diferencia de tamaño**, no reinicia (hace verde T093, T094) _Requisitos: 6.2, 6.5_
- [ ] T100 [US4] Subida inmediata en `apps/api/src/nexus_api/billing/checkout.py`: modificar la suscripción con prorrateo y llamar a T099. **No abre página nueva** _Requisitos: 6.1, 6.2_
- [ ] T101 [US4] Bajada programada con *Subscription Schedule* y `proration_behavior='none'`, reflejada en `pending_tier_code` _Requisitos: 6.3_
- [ ] T102 [US4] `409 tier_below_usage` en `POST /console/billing/checkout`, con cuántos teammates o personas sobran _Requisitos: 1.6_
- [ ] T103 [US4] Pantalla de cambio de plan en `apps/console/src/app/(console)/billing/`, mostrando `pending_tier` cuando lo hay — si no se ve, el partner lo vuelve a pedir _Requisitos: 6.1, 6.3_

**Checkpoint**: se sube y se baja sin perder pool ni crédito.

---

## Phase 7: Historia 5 — El recibo dice lo que la factura no sabe (P3)

**Objetivo**: el recibo deja de ser el documento que se paga y gana lo que el
proveedor no sabe.

**Prueba independiente**: se emite un mes y se comprueba que ya no promete un
cobro y que el desglose sigue estando.

### Tests de la Historia 5 ⚠️

- [ ] T104 [P] [US5] Test en `apps/api/tests/integration/test_partner_receipt_v2.py` (V48): el recibo lleva línea de **membresía** y línea de **consumo** _Requisitos: 8.1_
- [ ] T105 [P] [US5] Test (V49): **no** dice «total a pagar» ni lleva vencimiento, y `PAYMENT_DUE_DAY` ya no interviene en el recibo _Requisitos: 8.2_
- [ ] T106 [P] [US5] Test (V50): conserva el desglose por cliente y el detalle de conversión de las comisiones en CLP con su tipo de cambio _Requisitos: 8.3_
- [ ] T107 [P] [US5] Test (V52): recibo y factura del proveedor **no se contradicen** en el importe del período _Requisitos: 8.5_
- [ ] T108 [P] [US5] Test de consola (V51): se llega a las facturas del proveedor desde la consola _Requisitos: 8.4_

### Implementación de la Historia 5

- [ ] T109 [US5] Línea de membresía y línea de consumo en `apps/api/src/nexus_api/services/partner_receipt.py` _Requisitos: 8.1_
- [ ] T110 [US5] Quitar «total a pagar» y el vencimiento del recibo; `PAYMENT_DUE_DAY` deja de aplicarse ahí _Requisitos: 8.2_
- [ ] T111 [US5] Enlace a las facturas del proveedor desde la consola, apoyado en `GET /console/billing/portal` (T054) _Requisitos: 8.4_

**Checkpoint**: los dos documentos existen, cada uno con su papel.

---

## Phase 8: Cierre

- [ ] T112 [P] `docs/billing.md` nuevo: cómo se cobra, la escalera, **la configuración de la cuenta del proveedor** —`unpaid` tras los reintentos, Smart Retries, días de aviso de renovación, endpoint en Workbench— y **el enlace al runbook de migración**. Sin esa configuración la escalera de D6 no existe, y es lo primero que se pierde al cambiar de cuenta _Requisitos: —_
- [ ] T113 [P] Actualizar `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` §«Estado de implementación» con lo que esta spec cerró y las decisiones que aparecieron al codificar (§IX) _Requisitos: —_
- [ ] T114 Recorrido de humo de `quickstart.md` con relojes de prueba, los diez pasos. **Si el paso 7 pierde una confirmación pendiente, la feature no está terminada por mucho que las suites estén verdes** _Requisitos: todos_
- [ ] T115 Ejecutar las tres suites de `apps/api` y la de consola, y **reportar las cifras reales** _Requisitos: todos_

---

## Dependencias y orden de ejecución

### Entre fases

- **Setup (1)**: sin dependencias.
- **Foundational (2)**: depende de Setup. **Bloquea todas las historias.**
- **Puertas (2b)**: dependen de Foundational; T023–T026 pueden ir en paralelo.
- **Historias (3–7)**: todas dependen de Foundational.
- **Cierre (8)**: depende de las historias que se quieran entregar.

### Entre historias

| Historia | Depende de | Por qué |
|---|---|---|
| **US1** (suscribirse) | Foundational | Ninguna. **Es el MVP y se despliega sola** |
| **US2** (crédito) | Foundational + **T047/T048** de US1 | Reutiliza el webhook. Sin él tendría que duplicarlo |
| **US3** (impago) | US1 | No hay impago sin suscripción |
| **US4** (cambio de plan) | US1 | Igual |
| **US5** (recibo) | Foundational | **Independiente**: el recibo ya existe. Se puede hacer en paralelo con US3 y US4 |

### Dentro de cada historia

- Los tests se escriben y **se ven fallar** antes de implementar (§VII).
- Modelos → servicios → endpoints → pantalla.

### Oportunidades de paralelismo

- T003–T006 en Setup.
- T012/T013 y T015/T016 en Foundational.
- T023–T026 (las cuatro de aislamiento).
- Todos los tests de una historia marcados [P].
- **US5 en paralelo con US3 y US4**, si hay dos personas.

---

## Ejemplo de paralelo: Historia 1

```bash
cd apps/api && uv run pytest tests/integration/test_billing_webhook.py tests/integration/test_subscribe_flow.py tests/integration/test_membership_limits.py -x
```

---

## Estrategia de entrega

### MVP primero (US1)

1. Fase 1 · Setup
2. Fase 2 · Foundational **(crítica: bloquea todo)**
3. Fase 2b · Las puertas
4. Fase 3 · US1
5. **PARAR Y VALIDAR**: un partner paga y trabaja, sin que nadie intervenga.
6. Desplegar. La migración 0116 va sola y no cobra nada.

### Entrega incremental

1. Setup + Foundational + puertas → base lista
2. US1 → **MVP**: se puede cobrar
3. US2 → el negocio completo: se puede recargar
4. US3 → la relación sobrevive a un impago
5. US4 → se puede crecer sin castigo
6. US5 → los documentos quedan en su sitio

---

## Notas

- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **Precondición de despliegue, no de tareas**: la asesoría fiscal. Bloquea
  salir a producción, no escribir el código. No hay tarea porque no se resuelve
  codificando.
- **T021 lo ejecuta Luis**, con sus claves, contra la cuenta de Andrés Matos.
  Yo escribo el script; no manejo claves ni opero el panel del proveedor.
