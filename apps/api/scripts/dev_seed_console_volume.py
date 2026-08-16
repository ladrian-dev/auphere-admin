"""Seed a console partner with Facelad-like VOLUME to measure ``GET /console/home``
(CP-08 acceptance: < 1 s p95) and the usage pages (CP-22). **Dev only.**

Idempotent: clients are ``vol-01..vol-NN`` under the partner (default
``demo``); every run tops up to the requested totals and never duplicates
(deterministic slugs/refs, ``ON CONFLICT DO NOTHING`` on usage rows keyed
``vol:<tenant>:<n>``). Refuses to run when ``NEXUS_ENV`` looks like prod or
the database host is not local.

Defaults: 24 clients · 6 000 conversations · 60 000 usage rows this month
(channel.message + llm.* + media.*, ~7 % QA, ~3 % unpriced) · a few failed
messages in the last 24 h + one degraded channel + one client without an
active agent, so the incidents block has something to show.

Usage::

    cd apps/api && uv run python scripts/dev_seed_console_volume.py \
        [--partner-slug demo] [--clients 24] [--conversations 6000] [--usage-rows 60000]

Then measure (mint a console token — see LANE-RULES §Local):

    for i in $(seq 20); do curl -s -o /dev/null -w '%{time_total}\\n' \
        -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/console/home; done | sort -n
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    Partner,
    PartnerTenant,
    Tenant,
    TenantPlan,
    TenantStatus,
)


def _refuse_if_not_local(url: str) -> None:
    env = (os.environ.get("NEXUS_ENV") or os.environ.get("ENV") or "dev").lower()
    host = urlparse(url.replace("+asyncpg", "")).hostname or ""
    if env.startswith("prod") or host not in {"localhost", "127.0.0.1", "postgres", "db"}:
        sys.exit(f"refusing to seed volume: env={env!r} host={host!r} (dev only)")


async def _ensure_clients(
    session: AsyncSession, partner: Partner, n: int
) -> list[tuple[uuid.UUID, str]]:
    out: list[tuple[uuid.UUID, str]] = []
    for i in range(1, n + 1):
        ref = f"vol-{i:02d}"
        mapping = await session.scalar(
            sa.select(PartnerTenant).where(
                PartnerTenant.partner_id == partner.id, PartnerTenant.external_client_ref == ref
            )
        )
        if mapping is None:
            tid = uuid.uuid4()
            session.add(
                Tenant(
                    id=tid,
                    name=f"Volumen {i:02d}",
                    slug=f"{partner.slug}-vol-{i:02d}",
                    plan=TenantPlan.PRO,
                    status=TenantStatus.ACTIVE if i != n else TenantStatus.PROVISIONING,
                    partner_id=partner.id,
                )
            )
            await session.flush()
            session.add(
                PartnerTenant(
                    partner_id=partner.id,
                    external_client_ref=ref,
                    tenant_id=tid,
                    client_name=f"Volumen {i:02d}",
                )
            )
            await session.flush()
        else:
            tid = mapping.tenant_id
        out.append((tid, ref))
    await session.commit()
    return out


async def _ensure_runtime_rows(sm: async_sessionmaker[AsyncSession], tid: uuid.UUID, i: int) -> None:
    """Channel + agent + customer per client, in a scoped transaction."""
    async with sm() as session, tenant_scoped_session(session, tid):
        ch = await session.scalar(sa.select(Channel).where(Channel.type == ChannelType.WHATSAPP))
        if ch is None:
            ch = Channel(
                id=uuid.uuid4(),
                tenant_id=tid,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+3499{i:02d}{tid.int % 100000:05d}",
                config={"role": "agent"},
                # one degraded channel → incidents block
                status=ChannelStatus.DEGRADED if i == 3 else ChannelStatus.ACTIVE,
            )
            session.add(ch)
        agent = await session.scalar(
            sa.select(AgentConfig).where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        )
        if agent is None and i != 5:  # client 5 stays without an active agent
            session.add(
                AgentConfig(
                    tenant_id=tid,
                    version=1,
                    status=AgentConfigStatus.ACTIVE,
                    system_prompt_rendered="You are a helpful assistant (volume seed).",
                    tools=[],
                )
            )
        await session.execute(
            sa.text(
                "INSERT INTO customers (id, tenant_id, identifier, preferences) "
                "VALUES (:id, :t, :ident, '{}'::jsonb) ON CONFLICT DO NOTHING"
            ),
            {"id": str(uuid.uuid5(tid, "customer")), "t": str(tid), "ident": f"+3466{i:02d}000000"},
        )


async def _top_up_conversations(
    sm: async_sessionmaker[AsyncSession], tid: uuid.UUID, target: int, i: int
) -> int:
    async with sm() as session, tenant_scoped_session(session, tid):
        have = int(await session.scalar(sa.text("SELECT count(*) FROM conversations")) or 0)
        missing = max(0, target - have)
        if missing == 0:
            return 0
        ch_id = await session.scalar(sa.select(Channel.id).limit(1))
        cust_id = uuid.uuid5(tid, "customer")
        await session.execute(
            sa.text(
                """
                INSERT INTO conversations (id, tenant_id, channel_id, customer_id, status,
                                           created_at, updated_at)
                SELECT gen_random_uuid(), :t, :ch, :cu, 'closed',
                       date_trunc('month', now()) + (g || ' minutes')::interval,
                       now()
                  FROM generate_series(1, CAST(:n AS int)) AS g
                """
            ),
            {"t": str(tid), "ch": str(ch_id), "cu": str(cust_id), "n": missing},
        )
        # A few failed outbound messages in the last 24 h on 2 clients.
        if i in (2, 7):
            conv_id = await session.scalar(sa.text("SELECT id FROM conversations LIMIT 1"))
            for k in range(3):
                await session.execute(
                    sa.text(
                        """
                        INSERT INTO messages (id, tenant_id, conversation_id, direction, status,
                                              content, tool_calls, attempts, created_at, updated_at)
                        VALUES (:id, :t, :c, 'outbound', 'failed', 'seed', '[]'::jsonb, 1,
                                now() - interval '2 hours', now())
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {"id": str(uuid.uuid5(tid, f"failed-{k}")), "t": str(tid), "c": str(conv_id)},
                )
        return missing


async def _top_up_usage(
    sm: async_sessionmaker[AsyncSession], tid: uuid.UUID, target: int
) -> int:
    """``target`` rows this month for this tenant, keyed ``vol:<tenant>:<n>``.
    Deterministic ``occurred_at`` per n so re-runs hit ``ON CONFLICT``."""
    async with sm() as session, tenant_scoped_session(session, tid):
        have = int(
            await session.scalar(
                sa.text(
                    "SELECT count(*) FROM usage_records WHERE tenant_id = :t "
                    "AND idempotency_key LIKE :p"
                ),
                {"t": str(tid), "p": f"vol:{tid}:%"},
            )
            or 0
        )
        if have >= target:
            return 0
        rows_sql = sa.text(
            """
            INSERT INTO usage_records (tenant_id, occurred_at, meter, quantity, billable_qty,
                                       cost_usd, provider, model, idempotency_key, source)
            SELECT CAST(:t AS uuid),
                   LEAST(now() - interval '1 minute',
                         date_trunc('month', now()) + ((g * 37) % (extract(day from now())::int * 1440) || ' minutes')::interval),
                   m.meter, m.qty, m.qty,
                   CASE WHEN g % 33 = 0 THEN NULL ELSE m.cost END,
                   'anthropic', 'anthropic/claude-sonnet-4-6',
                   'vol:' || CAST(:t AS text) || ':' || g, m.source
              FROM generate_series(CAST(:lo AS int), CAST(:hi AS int)) AS g
              JOIN LATERAL (
                   SELECT * FROM (VALUES
                     ('channel.message','channel',1.0::numeric,0.0125::numeric),
                     ('channel.message','channel',1.0,0.0125),
                     ('channel.message','channel',1.0,0.0125),
                     ('llm.input_tokens','channel',900.0,0.0027),
                     ('llm.output_tokens','channel',120.0,0.0018),
                     ('llm.input_tokens','qa',700.0,0.0021),
                     ('media.image','channel',1.0,0.002),
                     ('media.audio','channel',1.0,NULL)
                   ) AS v(meter, source, qty, cost)
                   OFFSET (g % 8) LIMIT 1
              ) AS m ON true
            ON CONFLICT (idempotency_key, occurred_at) DO NOTHING
            """
        )
        await session.execute(rows_sql, {"t": str(tid), "lo": have + 1, "hi": target})
        return target - have


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partner-slug", default="demo")
    ap.add_argument("--clients", type=int, default=24)
    ap.add_argument("--conversations", type=int, default=6000)
    ap.add_argument("--usage-rows", type=int, default=60000)
    args = ap.parse_args()

    url = os.environ.get("NEXUS_DATABASE_URL")
    if not url:
        from nexus_api.config import get_settings

        url = get_settings().database_url
    _refuse_if_not_local(url)
    engine = create_async_engine(url)
    sm = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async with sm() as session:
        partner = await session.scalar(sa.select(Partner).where(Partner.slug == args.partner_slug))
        if partner is None:
            print(f"partner {args.partner_slug!r} not found", file=sys.stderr)
            return 2
        if partner.max_clients < args.clients + 5:
            partner.max_clients = args.clients + 5
        clients = await _ensure_clients(session, partner, args.clients)
        # Partition of the current month must exist (owner-level DDL, so
        # outside the scoped sessions below).
        await session.execute(
            sa.text("SELECT ensure_month_partition('usage_records', :d)"),
            {"d": datetime.now(UTC).date()},
        )
        await session.commit()

    per_client_conv = -(-args.conversations // args.clients)
    per_client_usage = -(-args.usage_rows // args.clients)
    added_conv = added_usage = 0
    for i, (tid, ref) in enumerate(clients, start=1):
        await _ensure_runtime_rows(sm, tid, i)
        added_conv += await _top_up_conversations(sm, tid, per_client_conv, i)
        added_usage += await _top_up_usage(sm, tid, per_client_usage)
        print(f"  {ref}: ok")
    await engine.dispose()
    print(
        f"seeded partner={args.partner_slug} clients={len(clients)} "
        f"+conversations={added_conv} +usage_rows={added_usage} (targets "
        f"{args.conversations}/{args.usage_rows})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
