# Tasks: las consolas son gratis mientras el Teammate se termina

- [X] T001 Tests: `apps/api/tests/integration/test_consoles_without_membership.py` (topes libres, pool con suscripción cancelada, 404 de los cuatro endpoints, `memberships_enabled` en Facturación) y casos nuevos en `tests/unit/test_billing_worker_apply.py` (sesión de suscripción y pago sin `kind=credit` no abonan). _Requisitos: 2.1, 2.2, 3.1, 3.3, 4.1_
- [X] T002 `config.py` `membership_enabled`; `membership_limits.memberships_enabled()`; topes y `_pool_refills_for` respetan el interruptor. _Requisitos: 1.1, 2.1, 2.2_
- [X] T003 `api/console/billing.py`: `require_memberships()` tras la persona en membresía, checkout, portal y cancelación; `BillingOut.memberships_enabled`. Barridos de aislamiento en verde. _Requisitos: 3.1, 3.2, 3.3_
- [X] T004 Worker `process_event.py`: solo `mode=payment` + `kind=credit` abona; avisos de suscripción ignorados con el interruptor apagado. _Requisitos: 4.1, 4.2_
- [X] T005 Las suites de la spec 005 encienden el interruptor con la fixture `memberships_on`; los stubs de Checkout de crédito llevan `mode` y `metadata.kind` como los crea `open_credit_session`. _Requisitos: 1.1_
- [X] T006 Consola `billing/page.tsx`: sin membresía, sección «Comprar saldo» + recibos; sin enlace al portal. _Requisitos: 3.3_
- [X] T007 `docs/billing.md` con el estado; ADR-043 en la KB.
