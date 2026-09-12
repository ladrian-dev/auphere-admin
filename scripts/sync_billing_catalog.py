#!/usr/bin/env python3
"""Create the membership catalogue in a Stripe account. Idempotent.

Spec 005 · research D5.3.

    uv run python scripts/sync_billing_catalog.py --dry-run
    uv run python scripts/sync_billing_catalog.py --apply

**A person runs this, with the keys, against an account that can charge.** It
lives outside ``apps/`` on purpose: an API command would leave creating real
prices in production one POST away.

**Idempotent by our tier code**, carried in ``metadata.tier_code`` on every
object it creates. Recognising an existing price by its display name would
break the moment someone edits the commercial copy; recognising it by our own
key is what lets this run twice safely — and what makes recreating the whole
catalogue against a NEW account a single command on the day the Stripe account
migrates from the partner's name to the company's.

The free tier is never created upstream. It is not billed, so it has no price
and should not exist in the provider's account at all.

After ``--apply`` it prints the price ids so they can be written into
``membership_tiers.stripe_price_id``.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from typing import Any

#: Mirrors the seed of migration 0116. Duplicated on purpose: this script runs
#: against an account, not against our database, and must work on a machine
#: that cannot reach the database at all.
TIERS: list[dict[str, Any]] = [
    {"code": "free", "name": "Nexus Free", "cents": 0},
    {"code": "pro", "name": "Nexus Pro", "cents": 2_000},
    {"code": "team", "name": "Nexus Team", "cents": 6_000},
    {"code": "business", "name": "Nexus Business", "cents": 15_000},
]


@dataclasses.dataclass(frozen=True)
class Step:
    """One tier that is missing upstream and would be created."""

    code: str
    name: str
    cents: int


def _tier_code(obj: Any) -> str | None:
    """Our tier code from a provider object, whichever shape it arrives in.

    Stripe's SDK returns ``StripeObject``, which behaves as both an object and
    a mapping, and a plain dict is what a raw API response looks like. Reading
    only one of the two makes the idempotency check silently find nothing and
    create every price a second time.
    """
    meta: Any = obj.get("metadata") if isinstance(obj, dict) else getattr(obj, "metadata", None)
    if not meta:
        return None
    if isinstance(meta, dict):
        return meta.get("tier_code")
    return getattr(meta, "tier_code", None)


def plan_catalog(tiers: list[dict[str, Any]], client: Any) -> list[Step]:
    """What is missing. Reads the account first; never assumes it is empty."""
    existing = {
        _tier_code(price)
        for price in client.prices.list({"limit": 100, "active": True}).data
        if _tier_code(price)
    }
    return [
        Step(code=t["code"], name=t["name"], cents=t["cents"])
        for t in tiers
        if t["code"] != "free" and t["code"] not in existing
    ]


def apply(plan: list[Step], client: Any, *, dry_run: bool) -> list[tuple[str, str]]:
    """Create what is missing. Returns ``(tier_code, price_id)`` per creation."""
    made: list[tuple[str, str]] = []
    for step in plan:
        if dry_run:
            print(f"  [dry-run] crearía {step.code}: {step.name} — {step.cents / 100:.2f} USD/mes")
            continue
        product = client.products.create(
            {"name": step.name, "metadata": {"tier_code": step.code}}
        )
        price = client.prices.create(
            {
                "product": product.id,
                "currency": "usd",
                "unit_amount": step.cents,
                "recurring": {"interval": "month"},
                "metadata": {"tier_code": step.code},
            }
        )
        made.append((step.code, price.id))
        print(f"  creado {step.code}: {price.id}")
    return made


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="di qué harías, no lo hagas")
    group.add_argument("--apply", action="store_true", help="créalo de verdad")
    args = parser.parse_args(argv)

    api_key = os.environ.get("BILLING_API_KEY") or os.environ.get("NEXUS_BILLING_API_KEY")
    if not api_key:
        print(
            "Falta BILLING_API_KEY. Este script toca una cuenta con capacidad de "
            "cobro: la clave la pones tú, no vive en el repositorio.",
            file=sys.stderr,
        )
        return 2

    import stripe

    client = stripe.StripeClient(api_key=api_key)
    live = not api_key.startswith("sk_test_")
    if live and args.apply:
        print("⚠️  Clave de PRODUCCIÓN. Esto crea precios reales.")
        if input("Escribe el nombre de la cuenta para continuar: ").strip() == "":
            print("Cancelado.", file=sys.stderr)
            return 1

    plan = plan_catalog(TIERS, client)
    if not plan:
        print("El catálogo ya está completo. No hay nada que crear.")
        return 0

    print(f"Faltan {len(plan)} niveles: {', '.join(s.code for s in plan)}")
    made = apply(plan, client, dry_run=args.dry_run)
    if made:
        print("\nEscribe estos ids en membership_tiers.stripe_price_id:\n")
        for code, price_id in made:
            print(
                f"  UPDATE membership_tiers SET stripe_price_id = '{price_id}' "
                f"WHERE code = '{code}';"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
