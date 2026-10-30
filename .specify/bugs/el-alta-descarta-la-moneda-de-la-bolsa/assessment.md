# Bug Assessment: el alta descarta la moneda de la bolsa que se eligió

- **Slug**: el-alta-descarta-la-moneda-de-la-bolsa
- **Created**: 2026-10-29
- **Source**: auditoría del constructor (`research/2026-10-29-auditoria-del-constructor/_index.md`, fallo 6)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

En «Nuevo cliente», la persona puede cambiar la moneda de la bolsa (EUR o USD,
requisito 43.3). La API la recibe y la tira.

## Symptom

Un cliente de Chile dado de alta con la bolsa en EUR acaba con la bolsa en USD,
la moneda que se deduce del país. Lo esperado: la bolsa nace en la moneda
elegida.

## Reproduction

1. `POST /console/clients` con `country = "CL"` y `wallet_currency = "EUR"`.
2. La bolsa se crea más tarde, al primer `bag_for_update`, con
   `currency_for(country)` = USD.
3. `GET` del cliente → `wallet_currency = "USD"`.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/tenants.py:815` — `new, _wallet_currency = _new_client(body)`: la moneda resuelta se descarta.
- `tenants.py:758` `_new_client` — resuelve bien la moneda (`body.wallet_currency or deduced.wallet_currency`).
- `apps/api/src/nexus_api/services/wallet/bags.py:206` `bag_for_update` — crea la bolsa perezosamente con `currency_for(country)`.

## Root Cause Hypothesis

La bolsa nace perezosa (requisito 43.12) y solo sabe deducir la moneda del país;
el alta no le pasa la elegida. Confianza: **alta** (lectura directa).

## Proposed Remediation

**Preferred**: en el alta, crear la bolsa vacía en la misma transacción con la
moneda resuelta, con una función `ensure_bag(session, tenant_id, partner_id,
currency)` en `bags.py` que `bag_for_update` reutiliza. Sin saldo no hay
conversión ni traspaso.

**Alternative**: llamar a `change_currency` después del alta. Descartada: deja un
traspaso `currency_change` de importe cero en el libro.

## Test plan

- Integración: alta con `country = "CL"` y `wallet_currency = "EUR"` → la bolsa
  existe y está en EUR.
- Integración: alta sin `wallet_currency` → la bolsa en la moneda del país, como hoy.
- Integración: repetir el alta con la misma `Idempotency-Key` no crea otra bolsa.
