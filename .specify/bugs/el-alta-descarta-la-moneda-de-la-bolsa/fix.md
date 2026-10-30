# Bug Fix: el alta descarta la moneda de la bolsa que se eligió

- **Slug**: el-alta-descarta-la-moneda-de-la-bolsa
- **Fixed**: 2026-10-29
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Si la persona elige la moneda de la bolsa en «Más ajustes», el alta crea la
bolsa vacía en esa moneda, en la misma transacción que el cliente. Sin elección,
nada cambia: la bolsa nace más tarde en la moneda de su país (requisito 43.12).

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/services/wallet/bags.py` | modified | `empty_bag(tenant_id, partner_id, currency)`, que reutiliza `bag_for_update` |
| `apps/api/src/nexus_api/services/tenant_lifecycle.py` | modified | `NewClient.wallet_currency`; `create_client` añade la bolsa con ella, ya con la RLS del cliente |
| `apps/api/src/nexus_api/api/console/tenants.py` | modified | `_new_client` pasa la moneda elegida a `NewClient` |
| `apps/api/tests/integration/clients/test_create_three_fields.py` | added test | `test_the_bag_is_born_in_the_chosen_currency`, con tres países |
