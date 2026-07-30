"""Set a cobranza tenant's admin whitelist WITH per-admin roles, PROD-safe.

Replaces ``policies.admin_access.admin_phones`` + ``admins`` on a freshly
promoted agent_config (via ``AgentConfigService.set_admin_access``), so the
old admins are dropped and only the ones passed here remain. ``role`` is
``full`` (query + all changes) or ``readonly`` (query only — the worker
strips write tools for that sender).

Admins are passed as JSON via env (NOT hardcoded — they are per-business PII,
not code):

    NEXUS_COBRANZA_ADMINS_JSON='[
      {"phone": "+58...", "role": "full", "name": "Dueño"},
      {"phone": "+58...", "role": "readonly", "name": "Consulta"}
    ]'

Usage (dry-run by default — prints the diff, writes NOTHING):

    NEXUS_DATABASE_URL=... NEXUS_COBRANZA_ADMINS_JSON='[...]' \\
      uv run python apps/api/scripts/set_cobranza_admins.py mouna

Add ``--apply`` to actually stage + promote the new config version.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Make ``nexus_api`` importable when run via plain ``python``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.tenant import Tenant
from nexus_api.services.agent_config_service import AgentConfigService

_VALID_ROLES = {"full", "readonly"}


def _load_admins() -> list[dict[str, Any]]:
    raw = os.environ.get("NEXUS_COBRANZA_ADMINS_JSON", "").strip()
    if not raw:
        raise SystemExit(
            "ERROR: set NEXUS_COBRANZA_ADMINS_JSON (JSON list of {phone, role, name?})"
        )
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise SystemExit("ERROR: NEXUS_COBRANZA_ADMINS_JSON must be a non-empty JSON list")
    admins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        phone = str(item.get("phone") or "").strip()
        role = str(item.get("role") or "full").strip().lower()
        if not phone:
            raise SystemExit("ERROR: every admin needs a 'phone'")
        if role not in _VALID_ROLES:
            raise SystemExit(f"ERROR: role must be one of {_VALID_ROLES}, got {role!r}")
        if phone in seen:
            continue
        seen.add(phone)
        admins.append({"phone": phone, "role": role, "name": item.get("name")})
    return admins


async def _amain(slug: str, apply: bool) -> int:
    admins = _load_admins()
    phones = [a["phone"] for a in admins]

    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if tenant is None:
            print(f"ERROR: no tenant with slug={slug!r}")
            return 1
        current = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant.id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            )
        ).scalar_one_or_none()
        if current is None:
            print(f"ERROR: tenant {slug!r} has no ACTIVE agent_config")
            return 1
        cur_access = (current.policies or {}).get("admin_access") or {}
        cur_phones = list(cur_access.get("admin_phones") or [])
        cur_version = current.version

    print(f"tenant   : {slug} (id={tenant.id})")
    print(f"config   : active v{cur_version} → would stage v{cur_version + 1}")
    print(f"admins - : {cur_phones or '—'}   (se eliminan)")
    print("admins + :")
    for a in admins:
        print(f"           {a['phone']}  role={a['role']}  name={a.get('name') or '—'}")

    if not apply:
        print("\nDRY-RUN (nada escrito). Re-ejecuta con --apply para promover.")
        return 0

    async with Session() as session, tenant_scoped_session(session, tenant.id):
        svc = AgentConfigService(session)
        promoted = await svc.set_admin_access(
            actor="set_cobranza_admins.py",
            admin_phones=phones,
            admins=admins,
        )
    print(
        f"\nOK: {slug} promovido a agent_config v{promoted.version} con "
        f"{len(admins)} admin(s). Publica el refresh de cache / reinicia el worker."
    )
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    positional = [a for a in argv if not a.startswith("-")]
    slug = (
        (positional[0] if positional else None) or os.environ.get("NEXUS_COBRANZA_SLUG") or "mouna"
    )
    raise SystemExit(asyncio.run(_amain(slug, "--apply" in argv)))
