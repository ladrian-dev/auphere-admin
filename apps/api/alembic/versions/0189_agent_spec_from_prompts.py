"""Cada versión de antes recibe su AgentSpec, sin cambiar lo que responde —
spec 047, T095 (requisitos 16.4 y 55.1; research D4).

Para cada versión **activa o en borrador** sin ``spec``, se escribe un AgentSpec en
modo «instrucciones»:

- ``legacy_text`` es su prompt sin el bloque «Datos vigentes del negocio» (que la
  compilación por revisión vuelve a poner igual): compilarlo da los mismos bytes;
- sus herramientas con forma de catálogo (las demás siguen en la versión, que es lo
  que construye el runtime);
- su política de modelo si ya la tenía; si no, sigue en su modelo de hoy;
- el aviso de IA que decidió una persona (CP-31), o sin decidir;
- su equipo (``admin_access``) como ``team_access``.

**No se toca ``system_prompt_rendered``**: el runtime sigue leyendo lo mismo
(CE-009). La regla es una copia congelada de ``services/agent_spec/legacy.py`` y
la prueba de la migración comprueba que dan lo mismo.

Revision ID: 0189_agent_spec_from_prompts
Revises: 0188_sector_tests_v1
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0189_agent_spec_from_prompts"
down_revision: str | Sequence[str] | None = "0188_sector_tests_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MARK = "\n\n### Datos vigentes del negocio\n"
LEGACY_DEPLOYMENT = "nexus/current-binding"
_PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def _instructions_of(prompt: str) -> str:
    at = prompt.rfind(MARK)
    return prompt[:at] if at >= 0 else prompt


def _description(name: str) -> str:
    text = f"Agente {name} configurado antes de la fábrica de agentes."
    return text if len(text) >= 20 else (text + " " * 20)[:20]


def _disclosure(policies: dict[str, Any]) -> dict[str, Any]:
    console = policies.get("console")
    decision = console.get("ai_disclosure") if isinstance(console, dict) else None
    if not isinstance(decision, dict) or "enabled" not in decision:
        return {"decided": False}
    out: dict[str, Any] = {"decided": True}
    if decision.get("enabled"):
        out["mode"] = "first_message"
        text = str(decision.get("disclosure_message") or "").strip()[:200]
        if text:
            out["text"] = text
    return out


def _model_policy(policies: dict[str, Any]) -> dict[str, Any]:
    policy = dict(policies.get("model_policy") or {})
    if policy.get("kind") in {"profile", "pinned"}:
        return policy
    return {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT}


def _team(policies: dict[str, Any]) -> list[dict[str, Any]]:
    access = dict(policies.get("admin_access") or {})
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    entries = list(access.get("admins") or []) + [
        {"phone": p} for p in access.get("admin_phones") or []
    ]
    for entry in entries:
        phone = str((entry or {}).get("phone") or "").strip()
        if not _PHONE.match(phone) or phone in seen:
            continue
        seen.add(phone)
        member: dict[str, Any] = {"phone_e164": phone, "level": "full"}
        label = str((entry or {}).get("name") or "").strip()[:60]
        if label:
            member["label"] = label
        out.append(member)
    return out[:50]


def spec_for(name: str, prompt: str, tools: list[str], policies: dict[str, Any]) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": (name or "Agente")[:40], "description": _description(name)},
        "instructions": {"legacy_text": _instructions_of(prompt or "")},
        "tools": [t for t in dict.fromkeys(tools or []) if _TOOL.match(t)][:60],
        "ai_disclosure": _disclosure(policies),
        "model_policy": _model_policy(policies),
        "memory": {"scope": "shared"},
    }
    team = _team(policies)
    if team:
        doc["team_access"] = team
    return doc


def upgrade() -> None:
    bind = op.get_bind()
    # La migración corre como dueña de las tablas: la RLS no la filtra.
    rows = bind.execute(
        sa.text(
            "SELECT c.id, a.name, c.system_prompt_rendered, c.tools, c.policies "
            "FROM agent_configs c JOIN agents a ON a.tenant_id = c.tenant_id AND a.id = c.agent_id "
            "WHERE c.spec IS NULL AND c.status IN ('active', 'staged')"
        )
    ).all()
    for cfg_id, name, prompt, tools, policies in rows:
        doc = spec_for(str(name or ""), str(prompt or ""), list(tools or []), dict(policies or {}))
        bind.execute(
            sa.text("UPDATE agent_configs SET spec = CAST(:s AS jsonb) WHERE id = :id"),
            {"s": json.dumps(doc, ensure_ascii=False), "id": cfg_id},
        )


def downgrade() -> None:
    op.execute(
        "UPDATE agent_configs SET spec = NULL WHERE spec->>'mode' = 'instructions' "
        "AND spec->'identity'->>'description' LIKE 'Agente % configurado antes de la fábrica de agentes.%'"
    )
