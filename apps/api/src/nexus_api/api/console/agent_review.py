"""La revisión de un agente en la consola — spec 047, T088 (requisito 22).

``GET …/agents/{agent_id}/review``: los hallazgos del borrador (o de la versión
activa si no hay borrador) con su gravedad y su arreglo, y la lista de
comprobaciones que corrieron (22.3). Queda guardada en ``agent_reviews``.

El arreglo que se puede aplicar en un clic (quitar una herramienta que no existe)
viaja como **propuesta**: la aplica una persona, con su huella (§IV).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from nexus_api.db.models.agent_spec import AgentReview
from nexus_api.services import proposal_state
from nexus_api.services.agent_spec.review import findings_json, load_input, review
from nexus_api.services.agent_spec.schema import dump

from .agent_draft_routes import agent_in_path
from .agent_spec_drafts import current_spec, spec_state_hash
from .deps import ClientScope

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")


class ReviewOut(BaseModel):
    version_number: int | None
    findings: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    blocking: int


def _without_mention(text: str, name: str) -> str:
    """El texto sin las frases que citan ``name``."""
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = [s for s in sentences if name not in s]
    return " ".join(kept).strip()


def _get(doc: Any, pointer: str) -> Any:
    node = doc
    for part in pointer.strip("/").split("/"):
        node = node[int(part)] if isinstance(node, list) else node.get(part)
        if node is None:
            return None
    return node


def _remove_tool_ops(
    doc: dict[str, Any], name: str, pointer: str | None = None
) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    # Una herramienta citada en un texto: el arreglo es quitar esa frase (y la
    # sección o la regla entera si no queda nada).
    in_text = pointer is not None and (
        pointer.endswith("/body") or pointer.startswith("/rules/") or pointer.endswith("/steps")
    )
    if pointer and in_text:
        text = _get(doc, pointer)
        if isinstance(text, str) and name in text:
            cleaned = _without_mention(text, name)
            if cleaned:
                ops.append({"op": "replace", "path": pointer, "value": cleaned})
            elif pointer.endswith("/body"):
                ops.append({"op": "remove", "path": pointer.rsplit("/", 1)[0]})
            elif pointer.startswith("/rules/"):
                ops.append({"op": "remove", "path": pointer})
        return ops
    if name in (doc.get("tools") or []):
        ops.append(
            {"op": "replace", "path": "/tools", "value": [t for t in doc["tools"] if t != name]}
        )
    for i, proc in enumerate(doc.get("procedures") or []):
        if name in (proc.get("tools") or []):
            ops.append(
                {
                    "op": "replace",
                    "path": f"/procedures/{i}/tools",
                    "value": [t for t in proc["tools"] if t != name],
                }
            )
    return ops


@router.get("/review", response_model=ReviewOut)
async def get_review(scope: ClientScope = Depends(agent_in_path("agents:read"))) -> ReviewOut:
    assert scope.agent_id is not None
    spec, cfg = await current_spec(scope)
    if spec is None or cfg is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "no_version"})
    data = await load_input(
        scope.session, agent_id=scope.agent_id, spec=spec, partner_id=scope.principal.partner.id
    )
    result = review(data)
    findings = findings_json(result.findings)
    writes = "agents:write" in scope.principal.permissions
    doc = dump(spec)
    state = spec_state_hash(spec)
    for item in findings:
        fix = item.get("fix") or {}
        if fix.get("kind") != "proposal" or not fix.get("remove_tool"):
            continue
        ops = _remove_tool_ops(doc, str(fix["remove_tool"]), fix.get("pointer"))
        if not ops or not writes:
            # A quien no puede aplicar se le explica, sin propuesta (19.5); sin
            # parche posible, se arregla editando.
            item["fix"] = {"kind": "edit", "pointer": fix.get("pointer")}
            continue
        proposal = await proposal_state.propose(
            scope.session,
            agent_id=scope.agent_id,
            kind="fix",
            author="builder",
            diff={"ops": ops},
            state_hash=state,
            summary=f"Quitar {fix['remove_tool']} de las instrucciones",
            created_by=scope.principal.actor,
        )
        item["fix"] = {"kind": "proposal", "proposal_id": str(proposal.id)}
    scope.session.add(
        AgentReview(tenant_id=scope.tenant.id, agent_config_id=cfg.id, findings=findings)
    )
    await scope.session.flush()
    return ReviewOut(
        version_number=cfg.agent_version_number,
        findings=findings,
        checks=list(result.checks),
        blocking=len(result.blocking),
    )


__all__ = ["router"]
