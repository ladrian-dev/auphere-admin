# Implementation Plan: Lo que te necesita

**Branch**: `071-lo-que-te-necesita` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/071-lo-que-te-necesita/spec.md` y el contrato fijo [contracts/api.md](contracts/api.md).

Este plan cubre la **API y el worker**. La consola se construye a la vez contra el mismo contrato y tiene su propio reparto de tareas.

## Summary

Cinco piezas, en este orden de dependencia:

1. **La regla única, entera** (`services/attention.py`): a los siete motivos de cada cliente se suman los cinco del partner (tope de construcción al 80 % o agotado, cuenta baja o vacía, cobro fallido). La regla da también la gravedad, el alcance, el arreglo y el orden del contrato. Sigue siendo pura: hechos dentro, filas fuera.
2. **La lectura en vivo** (`services/attention_live.py`): lee los hechos del partner y de cada cliente y devuelve **la lista**. La llaman el Panel (`/console/home` → `panel.attention`), `GET /console/attention` y el repaso que resuelve avisos. Ninguno la recalcula.
3. **`GET /console/attention`**: `{items, errors}`, con los permisos y los módulos de quien mira.
4. **Avisos que se resuelven solos**: `resolve_cleared(session, partner_id)` marca `handled_at` y suelta la `dedupe_key` de los avisos de condición pendientes cuyo código ya no está en la lista. Se llama donde hoy se rearma y en un repaso del worker cada hora. `build.budget.*` pasa a ser un aviso del partner.
5. **La campana**: `NotificationOut.condition`; `unread-count` no cuenta los avisos de condición y `read-all` solo marca los informativos.

**Verificación**: tests unitarios de la regla, de integración de la lista, de la resolución y de la campana, y el test de aislamiento `tests/isolation/test_071_attention_scope.py`.

## Technical Context

**Language/Version**: Python 3.11 (API y worker).

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async. Sin dependencias nuevas.

**Storage**: PostgreSQL. **Sin migración**: `console_notifications.handled_at` existe desde la 0227 y basta.

**Testing**: pytest (unit, integration e isolation de la API; unit del worker).

**Target Platform**: AWS ECS, como hoy.

**Project Type**: Web service.

**Performance Goals**:
- La lista lee lo mismo que ya leía el Panel (fichas y bolsas de los clientes) más cuatro lecturas del partner (partida, cuenta, libro del mes y suscripción).
- El Panel no lee dos veces: la lista le devuelve las fichas que ya leyó para contar «Clientes atendiendo».
- Resolver tras un cambio lee solo el partner y el cliente tocado (`refs=`); el repaso horario lee todo.

**Constraints**:
- **Ningún aviso puede volver en bucle.** Soltar la `dedupe_key` de un aviso que su emisor sigue viendo lo haría salir otra vez en el siguiente tick. Por eso la regla de la cuenta es un **superconjunto** de lo que avisa `wallet_alerts` (research.md §R3), un aviso «bajo» no se resuelve mientras su hermano «agotado» siga en la lista (§R4), y el resto de emisores ya se limitan por su propia fila (bolsa, partida, tope del agente) o por la transición (canal, conector, escalón de cobro).
- **Solo los partners con la consola nueva.** La campana de la consola de antes no tiene «Ahora»: para ellos nada cambia (§R6).
- La campana del cliente (lite) no cambia (§R7).

**Scale/Scope**: unos 10 partners, decenas de clientes.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto; whitelist exhaustiva | ☑ | El partner sale del principal; los clientes, de `partner_tenants` del partner; cada ficha y cada bolsa se leen con el contexto de su cliente (`tenant_scoped_session`, `as_client`), la cuenta y la partida con el del partner. La resolución filtra por `partner_id` y por el `ref` de un cliente del partner. Test de aislamiento que barre la lista, el Panel y la campana de dos partners: `tests/isolation/test_071_attention_scope.py`. |
| II | Corte por superficie | ☑ | Superficie `0`: la API de la consola y su worker, que ya existen. |
| III | Lo leído es dato | ☑ | No hay modelo ni contenido leído: la lista son estados del sistema. |
| IV | Acción consecuente con confirmación; auditoría nombra a la persona | ☑ | Resolver un aviso no es una acción del partner ni cambia nada suyo: marca una fila de la campana. Las acciones de la lista son las que ya existen, con su confirmación. |
| V | Estados honestos; la ausencia se diseña | ☑ | Es el motivo de la spec: lo que ya no pasa deja de decirse. `errors` dice qué parte no se pudo leer y, sin leerla, no se resuelve nada de esa parte. Una fila cuyo arreglo no tiene el partner (módulo apagado) no sale. |
| VI | Por API, nunca navegando la consola | ☑ | `GET /console/attention` es una lectura de la API. |
| VII | Test primero; nada de `skip` | ☑ | tasks.md: cada criterio nace como test en rojo; ningún `skip`. |
| VIII | Licencias | ☑ | Sin dependencias nuevas. |
| IX | KB dueña del porqué | ☑ | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 3. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | **Garantía 1 (RLS / partner)**, rozada: la lista junta datos del partner y de sus clientes; la campana y la resolución filtran por partner. | T004 |
| **Licencias** | Ninguna dependencia nueva. | — |
| **Medidor** | Nada nuevo: no llama a modelos ni a herramientas de pago. | — |

## Project Structure

### Documentation (this feature)

```text
specs/071-lo-que-te-necesita/
├── spec.md
├── contracts/api.md
├── plan.md
├── research.md
└── tasks.md
```

### Source Code

```text
apps/api/src/nexus_api/
├── services/attention.py                  # la regla: cliente + partner, gravedad, arreglos, orden
├── services/attention_live.py             # la lista en vivo, resolve_cleared y sus variantes
├── services/partner_panel.py              # el Panel lee la lista
├── services/client_overview.py            # integration_reauth cuenta también los conectores; saldo de la bolsa
├── services/console_home_blocks.py        # BagBlock.balance_micros
├── services/whatsapp_account_events.py    # canal reconectado → resolver
├── services/connectors/service.py         # conector renovado → resolver
├── api/console/attention.py               # GET /console/attention
├── api/console/home.py                    # panel.attention = la lista
├── api/console/client_bags.py             # asignar, mover y subir el tope → resolver
├── api/console/notifications.py           # condition, unread-count, read-all
├── api/console/schemas_home_usage.py      # PanelAttentionOut ampliada, AttentionListOut
├── api/console/schemas_onboarding.py      # NotificationOut.condition
└── api/admin/partner_money.py             # subir la partida → resolver
apps/api/tests/{unit,integration/attention,isolation}/…
apps/worker/src/nexus_worker/
├── metering/consumer.py                   # build.budget.* al partner, sin cliente
├── streams/wallet_crons.py                # attention_resolve_tick; el relleno del día 1 resuelve
└── bootstrap.py                           # attention-resolve-cron
apps/worker/tests/unit/…
```

**Structure Decision**: monorepo existente. La regla pura y la lectura con base van en dos módulos (`attention.py` y `attention_live.py`) porque `client_overview` importa la regla y la lectura importa `client_overview`.

## Diseño

### 1. La regla (`attention.py`)

- `PARTNER_REASONS = (build_cap_exhausted, build_cap_warning, account_empty, account_low, billing_payment_failed)`.
- `PartnerFacts(build, account, billing_failed)` → `partner_attention()`:
  - partida: el `state` de `build_budget._state` (≥ 80 % `warning`, ≥ 100 % `exhausted`);
  - cuenta, **vacía** si lo asignable es 0 o el porcentaje con que avisa `wallet_alerts` llega al 100 %; **baja** si no está vacía y ese porcentaje llega al 80 %, o le queda menos del 20 % de lo cargado en el mes, o menos de 7 días al ritmo de los últimos 7 (D2);
  - cobro: la suscripción en `payment_failed` o `unpaid` (§R5).
- Gravedad (`critical`): `*_exhausted`, `*_empty`, `no_balance`, `channel_problem`, `billing_payment_failed`; el resto, `warning`.
- Arreglos del partner: `request_build_extension` → `/usage`; `buy_balance` → `/billing`; `fix_billing` → `/billing`. Los de cliente, los de hoy (`FIXES`, `REQUEST_INSTEAD`), que pasan aquí desde `partner_panel`.
- Orden (`order_items`): gravedad; dentro, primero el partner (por `PARTNER_REASONS`), luego los clientes por `ATTENTION_REASONS` y `ref`.
- `data`: `pct`, `spent`, `cap` (partida); `available` (cuenta, bolsa); `days_left` (`account_low`, `low_balance`).

### 2. La lista (`attention_live.live_attention`)

- `Gate(permissions, modules)` de quien mira, o ninguna (el repaso, que necesita la verdad entera):
  - filas de cliente: `clients:read` y el módulo `clients`; sin `usage:write`, «Pedir saldo»;
  - partida: `usage:read` y el módulo `usage`;
  - cuenta: `usage:read` y el módulo `usage` o `billing`;
  - cobro: `billing:read` y el módulo `billing`.
- Lee lo que la puerta deja ver, cada parte en su `try`: `errors` dice `partner` o `clients`. Un cliente cuya ficha no se pudo leer no da filas y marca `clients` (estado parcial, §V).
- Devuelve también qué se leyó (familias del partner, `ref` leídos) para que resolver no toque lo que no sabe, y las fichas y las bolsas para el Panel.

### 3. `resolve_cleared(session, partner_id, *, refs=None)`

- Solo partners con la consola nueva. Lee la lista sin puerta.
- Sobre los avisos `audience = partner`, `handled_at IS NULL` y de un tipo de la tabla §2.1:
  - del partner (`build.budget.*`, `wallet.*`, `billing.payment_failed`): por tipo, se lleve o no un cliente (los `build.budget.*` de antes lo llevaban);
  - de cliente: por tipo y `external_client_ref`; un cliente que ya no es del partner, resuelto; uno que no se leyó, intacto;
  - un aviso «bajo» no se resuelve mientras su hermano «agotado» esté en la lista (§R4).
- `UPDATE … SET handled_at = now(), dedupe_key = NULL`. No envía nada (D3).
- Variantes: `resolve_cleared_detached(partner_id, refs=…)` (su propia sesión, nunca lanza) y `resolve_cleared_for_tenant(tenant_id)`.
- Llamadas: tras asignar y mover saldo (`refs` de los clientes), tras subir el tope del agente (`after_commit`), tras subir la partida (admin, `refs=()`), tras el canal reconectado y el aviso de cuenta resuelto, tras el conector renovado (`after_commit`), tras el relleno del día 1 y en `attention-resolve-cron` cada hora.

### 4. La campana (`notifications.py`)

- `Viewer.conditions`: verdadero para el partner con la consola nueva.
- `condition` en cada aviso; `unread-count` (y el `unread` de la página) sin los de condición; `read-all` solo marca informativos. La lite, igual que hoy.

### 5. `build.budget.*` del partner

`_record_build_line` emite con `emit_detached(partner_id=…, external_client_ref=None)` en vez de `announce(tenant_id=<cliente>)`.

## Complexity Tracking

| Añadido | Por qué hace falta | Por qué no basta lo simple |
|---|---|---|
| Regla de la cuenta como superconjunto del aviso de `wallet_alerts` | Que soltar la clave no haga volver el aviso cada 15 minutos. | Con solo D2, una cuenta postpago o un redondeo en el 80 % harían que el emisor y la regla discreparan, y el aviso se resolvería y volvería sin fin. |
| «Bajo» cubierto por «agotado» | Lo mismo con `wallet.low`, que el emisor crea también al 100 %. | Por código estricto, el aviso de «queda poco» se resolvería al agotarse y volvería en el siguiente tick. |
| Saber qué se leyó | Resolver solo lo que se sabe (§V). | Una ficha que no se lee daría «sin canal con problemas» y resolvería un problema real. |
| Un cron más | Requisito 2.3. | Colgarlo del de las bolsas lo ataría a los partners con bolsas y a que su pasada no falle. |
