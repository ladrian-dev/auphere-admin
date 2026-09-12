"""Spec 005 · everything that talks to the payment provider lives here.

This package is a **boundary**, not a folder. No ``import stripe`` may appear
anywhere else in the codebase, and ``tests/unit/test_billing_boundary.py``
fails the build if one does.

The reason is written down in ``specs/005-membresias-y-cobro/research.md`` D2
and D5: the Stripe account currently belongs to a partner of Auphere while the
company's own fiscal registration is completed, and it **will** be migrated.
Migrating touches keys, catalogue and customers. With the provider imported in
eight modules that is an excavation; behind one boundary it is a contained job.

Two rules this package enforces on itself:

* **It never debits.** The only subtraction in the system is ``debit_wallet``
  on the turn path. An external notice may add balance, never remove it
  (ADR-037 D3) — also enforced by the boundary test.
* **It is never on the turn path.** A provider outage must not stop an agent
  from answering with the balance it already has (CE-004).
"""

from __future__ import annotations

__all__: list[str] = []
