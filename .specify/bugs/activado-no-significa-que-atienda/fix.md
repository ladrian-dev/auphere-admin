# Bug Fix: «¡Tu primer cliente activo!» llega con `can_serve: true` sin ningún canal

- **Slug**: activado-no-significa-que-atienda
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_client_can_serve` responde ahora a dos preguntas: ¿la puerta del libro está
abierta? (`allow_channel_turn`, como en D8) y ¿hay un canal de clientes activo?
(un `Channel` activo que no sea el del Playground, leído con sesión de tenant).
Devuelve `(can_serve, missing)` y el aviso `client.activated` lleva `missing` en
el payload. La consola nombra lo que falta —«falta conectar WhatsApp», «sin
cuota» o las dos— y los avisos antiguos sin `missing` conservan su texto.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/console_notifications.py` | modificado | `_client_can_serve` → `tuple[bool, list[str]]`; payload con `missing` |
| `apps/api/tests/unit/test_endpoint_console_onboarding.py` | añadido test | `test_activation_names_what_is_missing_channel_wise` |
| `apps/console/src/components/notifications/render.ts` | modificado | Elige copy por `missing` |
| `apps/console/src/i18n/lanes/onboarding.ts` | añadidas 2 claves | `…cannot_serve.whatsapp`, `…cannot_serve.both` |
| `apps/console/src/components/notifications/__tests__/render.test.ts` | añadido test | tres variantes del copy |

## Diff Highlights

```py
# console_notifications.py
if not await allow_channel_turn(tenant_id):
    missing.append("quota")
async with factory() as scoped, tenant_scoped_session(scoped, tenant_id):
    has_channel = (await scoped.scalar(
        sa.select(Channel.id).where(Channel.status == ChannelStatus.ACTIVE, customer_facing_channel()).limit(1)
    )) is not None
if not has_channel:
    missing.append("whatsapp")
return not missing, missing
```

```ts
// render.ts
const key = noChannel && noQuota ? "…cannot_serve.both" : noChannel ? "…cannot_serve.whatsapp" : "…cannot_serve";
```

## Tests Added or Updated

- API: `test_activation_names_what_is_missing_channel_wise` — sin canal y solo
  canal de Playground → `missing ∋ whatsapp`; con WhatsApp activo → no; los tres en
  `warning` porque ninguno tiene cuota. El test de integración D8
  (`test_wallet_alerts.py`) sigue verde: sin cuota → `can_serve=False`.
- Consola: `names the missing piece when the client has an agent but no channel`.

## Local Verification

```
uv run --directory apps/api ruff check … && ruff format … && mypy --strict console_notifications.py   # limpios
uv run pytest tests/unit/test_endpoint_console_onboarding.py tests/integration/test_wallet_alerts.py -q
  19 passed
pnpm exec tsc --noEmit && pnpm exec eslint --max-warnings 0 src/components/notifications …          # limpios
NODE_OPTIONS=--experimental-require-module pnpm exec vitest run src/components/notifications src/i18n
  Test Files 4 passed · Tests 32 passed
```

No se reprodujo en el navegador: el aviso se emite una sola vez por cliente
(dedupe) y el cliente de prueba ya lo había recibido antes del arreglo. La forma
del payload y el copy quedan fijados por los tests.

## Deviations from Assessment

Ninguna.

## Follow-ups

- El aviso sigue diciendo la referencia (`panaderia-la-espiga`) en vez del nombre
  del cliente: A7 del plan.
- «Sin cupo» como estado visible del cliente en ficha y lista es B3 (spec 016).
