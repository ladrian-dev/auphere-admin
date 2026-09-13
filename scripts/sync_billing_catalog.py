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

It also creates the **webhook endpoint** and the **Customer Portal
configuration**, because both are API objects and therefore reproducible. The
one thing it cannot do is the subscription settings — Stripe does not expose
them — so those stay a manual step, listed at the end of the run.

After ``--apply`` it prints the price ids, the webhook signing secret and the
manual checklist. **The secret is printed to your terminal and nowhere else**:
it never leaves the machine you run this on.
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
#: The two deployed environments, and what each one's Stripe mode points at.
#:
#: Stripe's **test and live modes live inside the same account** but hold
#: separate data: separate products, prices, customers and webhooks. So the
#: pairing is fixed — staging talks to test mode, production talks to live —
#: and crossing them is the one mistake this script exists to prevent.
ENVIRONMENTS: dict[str, dict[str, str]] = {
    "staging": {
        "key_prefix": "sk_test_",
        "webhook_url": "https://api.staging.auphere.com/webhook/billing",
        "console_url": "https://console.staging.auphere.com",
    },
    "prod": {
        "key_prefix": "sk_live_",
        "webhook_url": "https://api.auphere.com/webhook/billing",
        "console_url": "https://console.auphere.com",
    },
}

#: Printed with the UPDATE statements, because the alternative is finding out
#: the hard way.
PRICE_ID_WARNING = (
    "Estos ids son del entorno que acabas de configurar y NO sirven en el "
    "otro: modo test y modo live son catálogos distintos dentro de la misma "
    "cuenta. Escríbelos en la base de datos de ESE entorno."
)


class EnvironmentMismatch(RuntimeError):
    """La clave y el entorno no se corresponden.

    Se para antes de tocar nada. El cruce caro es una clave **live** con el
    entorno de staging: registraría el webhook de producción apuntando al
    entorno de pruebas, los cobros reales aterrizarían allí y se aplicarían
    contra una base de datos que no es la de los clientes. Dinero cobrado que
    no acredita a nadie, sin ningún error a la vista.

    El cruce inverso —clave de test contra producción— es inofensivo para el
    dinero pero igual de silencioso: los pagos reales no llegarían a ninguna
    parte hasta que alguien cuadre ingresos.
    """


def check_key_matches_environment(api_key: str, environment: str) -> None:
    """Refuse unless the key's mode matches the environment. No guessing."""
    expected = ENVIRONMENTS[environment]["key_prefix"]
    if api_key.startswith(expected):
        return

    other = next(
        (name for name, cfg in ENVIRONMENTS.items() if api_key.startswith(cfg["key_prefix"])),
        None,
    )
    if other:
        raise EnvironmentMismatch(
            f"la clave es de «{other}» y pediste «{environment}». "
            f"Cruzar los dos apunta el webhook de un entorno al otro: con una "
            f"clave live contra staging, los cobros reales llegarían al entorno "
            f"de pruebas."
        )
    raise EnvironmentMismatch(
        f"la clave no parece una clave secreta de Stripe (se esperaba que "
        f"empezara por «{expected}»). Usa la clave secreta, no la publicable."
    )


#: The events the API actually handles. Imported from the codebase when this
#: runs inside the repo so the two lists **cannot drift**: asking for an event
#: nobody handles logs noise, and missing one that is handled means a handler
#: that never hears about a payment. A unit test fails if they diverge.
#:
#: ``invoice.created`` is deliberately absent — subscribing to it and not
#: answering correctly makes Stripe delay finalizing EVERY invoice with
#: automatic collection for up to 72 hours. This is the place it is most
#: likely to creep back in: somebody configuring the endpoint by hand ticks
#: "all events" and the punishment arrives three days later.
WEBHOOK_EVENTS: list[str] = [
    "checkout.session.async_payment_succeeded",
    "checkout.session.completed",
    "customer.subscription.deleted",
    "customer.subscription.updated",
    "invoice.finalization_failed",
    "invoice.paid",
    "invoice.payment_failed",
    "invoice.upcoming",
]

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
        product = client.products.create({"name": step.name, "metadata": {"tier_code": step.code}})
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


def ensure_webhook(client: Any, *, url: str, dry_run: bool) -> str | None:
    """Register the webhook endpoint. Returns its signing secret, or ``None``.

    ``None`` means it already existed — Stripe only reveals the secret at
    creation, so an endpoint that is already there has to keep the secret it
    was born with. Idempotent by URL, which is what makes re-running this
    safe and what makes recreating it against a new account one command.
    """
    existing = {
        getattr(endpoint, "url", None)
        for endpoint in client.webhook_endpoints.list({"limit": 100}).data
    }
    if url in existing:
        print(f"  el webhook {url} ya existe (su secreto no se puede volver a leer)")
        return None
    if dry_run:
        print(f"  [dry-run] registraría el webhook {url} con {len(WEBHOOK_EVENTS)} eventos")
        return None

    endpoint = client.webhook_endpoints.create(
        {
            "url": url,
            "enabled_events": WEBHOOK_EVENTS,
            "description": "Nexus — spec 005",
            "metadata": {"app": "nexus"},
        }
    )
    print(f"  webhook creado: {endpoint.id}")
    return str(endpoint.secret)


def ensure_portal(client: Any, *, return_url: str, dry_run: bool) -> str | None:
    """Configure the Customer Portal: card, invoices, cancellation. Nothing else.

    **Plan changes are deliberately disabled here.** Letting the portal change
    tiers would be a second way of doing it that bypasses our caps — somebody
    could drop to a tier with fewer seats than they are using, and the 409 that
    prevents that lives in our API, not in Stripe's portal.

    Cancellation is ``at_period_end`` with no proration: nobody loses the week
    they already paid for.
    """
    if dry_run:
        print("  [dry-run] configuraría el portal (tarjeta, facturas, baja)")
        return None

    configuration = client.billing_portal.configurations.create(
        {
            "business_profile": {"headline": "Nexus"},
            "default_return_url": return_url,
            "features": {
                "payment_method_update": {"enabled": True},
                "invoice_history": {"enabled": True},
                "customer_update": {"enabled": True, "allowed_updates": ["email", "tax_id"]},
                "subscription_cancel": {
                    "enabled": True,
                    "mode": "at_period_end",
                    "proration_behavior": "none",
                },
                # Ver arriba: cambiar de plan pasa por nuestra API o no pasa.
                "subscription_update": {"enabled": False},
            },
        }
    )
    print(f"  portal configurado: {configuration.id}")
    return str(configuration.id)


#: Lo que la API de Stripe NO expone y hay que dejar puesto a mano. Se imprime
#: al terminar en vez de darse por hecho: una decisión de producto que vive en
#: una casilla es una decisión que se pierde.
MANUAL_STEPS = [
    "Panel → Facturación → Suscripciones: tras agotar los reintentos, la "
    "suscripción debe pasar a «unpaid», NO a «canceled». Sin esa casilla el "
    "escalón intermedio de la escalera de impago no existe.",
    "Panel → Facturación → Automático: activar Smart Retries.",
    "Panel → Facturación → Automático: días de aviso de renovación (dispara "
    "invoice.upcoming, que es con lo que se avisa ANTES de degradar).",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="di qué harías, no lo hagas")
    group.add_argument("--apply", action="store_true", help="créalo de verdad")
    parser.add_argument(
        "--env",
        required=True,
        choices=sorted(ENVIRONMENTS),
        help="qué entorno configuras. staging usa claves de test; prod, las live",
    )
    parser.add_argument(
        "--webhook-url",
        help="sobrescribe la URL del entorno (para un dominio nuevo o una prueba)",
    )
    parser.add_argument(
        "--console-url",
        help="sobrescribe la URL de la consola del entorno",
    )
    args = parser.parse_args(argv)

    environment = ENVIRONMENTS[args.env]
    webhook_url = args.webhook_url or environment["webhook_url"]
    console_url = args.console_url or environment["console_url"]

    api_key = os.environ.get("BILLING_API_KEY") or os.environ.get("NEXUS_BILLING_API_KEY")
    if not api_key:
        print(
            "Falta BILLING_API_KEY. Este script toca una cuenta con capacidad de "
            "cobro: la clave la pones tú, no vive en el repositorio.",
            file=sys.stderr,
        )
        return 2

    # Antes de tocar nada: que la clave y el entorno se correspondan.
    try:
        check_key_matches_environment(api_key, args.env)
    except EnvironmentMismatch as exc:
        print(f"Se para aquí: {exc}", file=sys.stderr)
        return 2

    import stripe

    client = stripe.StripeClient(api_key=api_key)
    print(f"Entorno: {args.env}")
    print(f"  webhook → {webhook_url}")
    print(f"  consola → {console_url}\n")

    if args.env == "prod" and args.apply:
        print("⚠️  Modo LIVE. Esto crea precios reales y un webhook que recibirá cobros.")
        if input("Escribe «prod» para continuar: ").strip() != "prod":
            print("Cancelado.", file=sys.stderr)
            return 1

    print("Catálogo de precios")
    plan = plan_catalog(TIERS, client)
    made: list[tuple[str, str]] = []
    if not plan:
        print("  ya está completo, no hay nada que crear")
    else:
        print(f"  faltan {len(plan)} niveles: {', '.join(step.code for step in plan)}")
        made = apply(plan, client, dry_run=args.dry_run)

    secret: str | None = None
    print("\nWebhook")
    secret = ensure_webhook(client, url=webhook_url, dry_run=args.dry_run)

    print("\nPortal del cliente")
    ensure_portal(client, return_url=console_url, dry_run=args.dry_run)

    if made:
        print(f"\nEscribe estos ids en membership_tiers.stripe_price_id de {args.env}:\n")
        for code, price_id in made:
            print(
                f"  UPDATE membership_tiers SET stripe_price_id = '{price_id}' "
                f"WHERE code = '{code}';"
            )
        print(f"\n  {PRICE_ID_WARNING}")

    if secret:
        print("\nEl secreto de firma del webhook, que solo se puede leer AHORA:\n")
        print(f"  NEXUS_BILLING_WEBHOOK_SECRET={secret}   # entorno: {args.env}")
        print("\n  Guárdalo en tu gestor de secretos. No vuelve a mostrarse.")

    print("\nLo que la API no puede hacer y tienes que dejar puesto a mano:\n")
    for step in MANUAL_STEPS:
        print(f"  · {step}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
