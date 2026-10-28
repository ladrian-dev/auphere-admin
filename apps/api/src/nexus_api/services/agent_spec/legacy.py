"""El modo «instrucciones» — spec 047, T078 y T095 (requisito 16.4; research D4).

Un agente de antes de la 047 no tiene AgentSpec: su versión es un prompt ya
renderizado más sus herramientas y políticas. :func:`spec_from_version` lo
envuelve en un AgentSpec en modo «instructions» que compila **exactamente** el
mismo prompt:

- ``legacy_text`` es el prompt sin el bloque de la ficha (``instructions_of``),
  que la compilación vuelve a poner igual;
- las herramientas son las de la versión;
- el modelo: si la versión ya tiene ``policies.model_policy`` (T145), esa; si no,
  el agente sigue fijado por el camino de hoy (``LEGACY_DEPLOYMENT``), que el
  runtime lee como «sin política»: nada cambia (D44, D45);
- el aviso de IA: el que ya decidió una persona para esa versión
  (``policies.console.ai_disclosure``, CP-31); si nadie lo decidió, **sin
  decidir** (16.6), y la revisión lo dirá;
- el equipo (``policies.admin_access.admins``) pasa a ``team_access``.
"""

from __future__ import annotations

import re
from typing import Any, Final

from nexus_api.services.agent_spec.schema import AgentSpec, dump
from nexus_api.services.business.compilation import instructions_of

#: El modelo de un agente de antes: «el que tiene hoy». No es un despliegue del
#: catálogo; el runtime lo lee como la ausencia de ``model_policy``.
LEGACY_DEPLOYMENT: Final = "nexus/current-binding"
_PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")
_TOOL = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


def _description(name: str) -> str:
    text = f"Agente {name} configurado antes de la fábrica de agentes."
    return text if len(text) >= 20 else (text + " " * 20)[:20]


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


def disclosure_of(policies: dict[str, Any] | None) -> dict[str, Any]:
    console = (policies or {}).get("console")
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


def model_policy_of(policies: dict[str, Any] | None) -> dict[str, Any]:
    policy = dict((policies or {}).get("model_policy") or {})
    if policy.get("kind") in {"profile", "pinned"}:
        return policy
    return {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT}


def spec_from_version(
    *,
    agent_name: str,
    system_prompt_rendered: str,
    tools: list[str] | None,
    policies: dict[str, Any] | None,
) -> AgentSpec:
    """El AgentSpec «instructions» de una versión de antes. Compila los mismos bytes."""
    policies = dict(policies or {})
    doc: dict[str, Any] = {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {
            "name": (agent_name or "Agente")[:40],
            "description": _description(agent_name),
        },
        "instructions": {"legacy_text": instructions_of(system_prompt_rendered or "")},
        # Las herramientas de antes que no tienen la forma del catálogo no se
        # pierden: siguen en la versión (``agent_configs.tools``), que es lo que
        # construye el runtime.
        "tools": [t for t in dict.fromkeys(tools or []) if _TOOL.match(t)][:60],
        "ai_disclosure": disclosure_of(policies),
        "model_policy": model_policy_of(policies),
        "memory": {"scope": "shared"},
    }
    team = _team(policies)
    if team:
        doc["team_access"] = team
    return AgentSpec.model_validate(doc)


def runtime_model_policy(spec: AgentSpec) -> dict[str, Any] | None:
    """Lo que va a ``policies.model_policy`` para el runtime: nada si el agente
    sigue en su modelo de hoy."""
    policy = dump(spec)["model_policy"]
    if policy.get("kind") == "pinned" and policy.get("deployment") == LEGACY_DEPLOYMENT:
        return None
    return dict(policy)


__all__ = [
    "LEGACY_DEPLOYMENT",
    "disclosure_of",
    "model_policy_of",
    "runtime_model_policy",
    "spec_from_version",
]
