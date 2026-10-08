"""Consola lite de un cliente en la base local — spec 030 (quickstart).

Enciende el acceso de un cliente con los módulos pedidos e invita a una
persona, por el MISMO servicio que usa el admin (``services/client_access``),
así que la auditoría y las reglas son las de verdad. Imprime el enlace de la
invitación para abrirlo en la consola local.

Uso (lee NEXUS_DATABASE_URL del entorno):

    uv run python scripts/dev_seed_client_access.py \\
        --client flor-y-encanto --modules panel,inbox,usage \\
        --email valeria@minegocio.test --name "Valeria Ríos"

``--client`` es el ``external_client_ref`` del cliente (el ``{ref}`` de la
consola del partner). Si el cliente no tiene WhatsApp conectado, ``inbox``
se rechaza igual que en el admin. ``--console-origin`` cambia el prefijo del
enlace impreso (por defecto ``console_base_url``).

Solo para desarrollo: se niega a correr con ``NEXUS_ENVIRONMENT`` de
producción.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import PartnerTenant
from nexus_api.services import client_access
from nexus_api.services.client_access import ClientAccessError

ACTOR = "operator:dev-seed@auphere.local"


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Consola lite de un cliente en la base local (spec 030)."
    )
    p.add_argument("--client", required=True, help="external_client_ref del cliente")
    p.add_argument("--modules", default="panel,usage", help="panel,inbox,usage")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default=None)
    p.add_argument("--console-origin", default=None)
    return p.parse_args()


async def main() -> int:
    args = _args()
    settings = get_settings()
    if settings.is_prod:
        print("dev_seed_client_access: se niega a correr en producción.", file=sys.stderr)
        return 2
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        tenant_id = await session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.external_client_ref == args.client
            )
        )
        if tenant_id is None:
            print(f"No hay ningún cliente con ref {args.client!r}.", file=sys.stderr)
            return 1
        try:
            await client_access.set_access(
                session, tenant_id, enabled=True, modules=modules, actor=ACTOR
            )
            invitation, token = await client_access.invite(
                session, tenant_id, email=args.email, name=args.name, actor=ACTOR
            )
        except ClientAccessError as exc:
            print(f"No se pudo: {exc.code}", file=sys.stderr)
            return 1
    origin = (args.console_origin or settings.console_base_url).rstrip("/")
    print(f"Acceso encendido para {args.client} con {', '.join(modules)}.")
    print(f"Invitación para {invitation.email} (caduca {invitation.expires_at:%Y-%m-%d}):")
    print(f"  {origin}/invite/{token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
