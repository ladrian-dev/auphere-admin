"""Siembra dos teammates de ejemplo en un partner (spec 003, US1). **Solo dev.**

Idempotente por nombre. Se niega a correr contra una base que no sea local.

Uso::

    cd apps/api && uv run python scripts/seed_teammates_dev.py [--partner-slug demo]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nexus_api.core.respond_catalog import RESPOND_MODELS
from nexus_api.db.models import Partner, Teammate
from nexus_api.services.teammate_catalog import permissions_to_tool_names

SEED = (
    ("Sofía", "Atención al cliente", {"read": True, "contact": True}, False),
    ("Nilo", "Desarrollo", {"read": True, "write": True}, True),
)


async def main(partner_slug: str) -> int:
    from nexus_api.config import get_settings

    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    host = urlparse(url.replace("postgresql+asyncpg", "postgresql")).hostname or ""
    if os.environ.get("NEXUS_ENV", "dev").lower().startswith("prod") or host not in {
        "localhost",
        "127.0.0.1",
        "postgres",
    }:
        print("refusing: this seed only runs against a local database", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session, session.begin():
        partner = (
            await session.execute(sa.select(Partner).where(Partner.slug == partner_slug))
        ).scalar_one_or_none()
        if partner is None:
            print(f"no partner with slug {partner_slug!r}", file=sys.stderr)
            return 1
        model = RESPOND_MODELS[0][0]
        for name, job, perms, local_exec in SEED:
            exists = await session.scalar(
                sa.select(Teammate.id).where(
                    Teammate.partner_id == partner.id, Teammate.name == name
                )
            )
            if exists:
                print(f"= {name} ya existe")
                continue
            full = {
                "read": False,
                "write": False,
                "spend": False,
                "publish": False,
                "contact": False,
                **perms,
            }
            session.add(
                Teammate(
                    id=uuid.uuid4(),
                    partner_id=partner.id,
                    name=name,
                    job=job,
                    model=model,
                    tool_names=permissions_to_tool_names(full),
                    permissions=full,
                    local_exec=local_exec,
                    created_by="seed",
                )
            )
            print(f"+ {name} · {job}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--partner-slug", default="demo")
    sys.exit(asyncio.run(main(parser.parse_args().partner_slug)))
