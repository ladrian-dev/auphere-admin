"""Las propuestas pendientes de la ficha — spec 047, T069 y T072 (requisitos 5.8, 8.3, 13.2, 18.2).

``business_suggestions`` guarda lo que no se aplicó solo:

- lo leído (de la web, un documento o las redes) que contradice un dato escrito
  por una persona (5.8), y lo que una lectura propone añadir (sedes, servicios,
  preguntas…);
- lo «Sugerido · confirma» del constructor (18.3);
- lo que trae un ClientSpec importado: importar **no escribe nada**, deja cada
  cambio como propuesta (:func:`propose_import`).

Una persona decide cada una (:func:`decide`): aceptar, editar o descartar. Lo
aceptado se aplica por el servicio de su sección (su adaptador ``apply``), con
la misma validación sin modelo que al proponerlo (``client_spec.validate_value``)
y la procedencia que le toca: lo del constructor queda «Propuesto por el
constructor», lo importado «Importado» y lo leído pasa a «Escrito por» quien lo
aceptó (13.2). Sin caducidad.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import BusinessSuggestion
from nexus_api.services.business import client_spec
from nexus_api.services.business.client_spec import KEY_SECTIONS, Problem
from nexus_api.services.business.sections import Actor
from nexus_api.services.business.writes import (
    NothingWritten,
    Op,
    SectionWritten,
    WriteContext,
    section_adapter,
)

Decision = Literal["accept", "edit", "discard"]
_DECIDED: dict[str, str] = {"accept": "accepted", "edit": "edited", "discard": "discarded"}


class AlreadyDecided(Exception):
    """Alguien ya decidió esa propuesta."""


class InvalidValue(ValueError):
    """Lo propuesto (o lo editado) no pasa el validador."""

    def __init__(self, problems: Sequence[Problem]) -> None:
        super().__init__("invalid value")
        self.problems = list(problems)


class SectionNotWritable(Exception):
    """La sección todavía no sabe aplicar propuestas (su servicio no registró
    su adaptador)."""

    def __init__(self, section: str) -> None:
        super().__init__(section)
        self.section = section


def section_of(pointer: str) -> str:
    key, _rest = client_spec.split_pointer(pointer)
    return KEY_SECTIONS[key]


async def pending(session: AsyncSession) -> list[BusinessSuggestion]:
    """Las propuestas sin decidir del cliente del contexto, de la más vieja a la más nueva."""
    rows = (
        await session.scalars(
            sa.select(BusinessSuggestion)
            .where(
                BusinessSuggestion.tenant_id == require_current_tenant(),
                BusinessSuggestion.decision.is_(None),
            )
            .order_by(BusinessSuggestion.created_at, BusinessSuggestion.id)
        )
    ).all()
    return list(rows)


@dataclass(frozen=True)
class Decided:
    suggestion_id: uuid.UUID
    decision: str
    section: str
    written: SectionWritten | None


def _provenance_for(source: str) -> tuple[str, str]:
    """``(source, kind)`` con que se escribe lo aceptado."""
    if source == "builder":
        return "builder", "builder_applied"
    if source == "import":
        return "import", "import"
    # Lo leído que una persona acepta pasa a ser suyo (13.2).
    return "person", "edit"


async def decide(
    session: AsyncSession,
    suggestion_id: uuid.UUID,
    decision: Decision,
    *,
    actor: Actor,
    value: Any = None,
    audit_actor: str | None = None,
) -> Decided:
    """Acepta, edita o descarta una propuesta (ver el módulo)."""
    tenant_id = require_current_tenant()
    row = await session.scalar(
        sa.select(BusinessSuggestion)
        .where(BusinessSuggestion.tenant_id == tenant_id, BusinessSuggestion.id == suggestion_id)
        .with_for_update()
    )
    if row is None:
        raise LookupError("unknown suggestion")
    if row.decision is not None:
        raise AlreadyDecided
    section = section_of(row.pointer)
    written: SectionWritten | None = None
    if decision != "discard":
        chosen = row.proposed_value if decision == "accept" else value
        problems = client_spec.validate_value(row.pointer, chosen)
        if problems:
            raise InvalidValue(problems)
        adapter = section_adapter(section)
        if adapter is None or adapter.apply is None:
            raise SectionNotWritable(section)
        source, kind = _provenance_for(row.source) if decision == "accept" else ("person", "edit")
        op = "add" if row.pointer.endswith("/-") else "replace"
        try:
            written = await adapter.apply(
                session,
                [Op(op=op, path=row.pointer, value=chosen)],
                WriteContext(
                    actor=actor,
                    source=source,
                    kind=kind,
                    review="confirmed",
                    source_url=row.source_url if source != "person" else None,
                    audit_actor=audit_actor,
                ),
            )
        except NothingWritten:
            written = None
    row.decision = _DECIDED[decision]
    row.decided_at = datetime.now(UTC)
    row.decided_by = actor.id
    await session.flush()
    return Decided(suggestion_id=row.id, decision=row.decision, section=section, written=written)


# ── importar un ClientSpec como propuesta (T072) ────────────────────────────────


@dataclass
class ImportProposal:
    base_hash: str
    ops: list[dict[str, Any]] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    created: int = 0


async def _open_same(session: AsyncSession, pointer: str, value: Any) -> bool:
    found = await session.scalar(
        sa.select(BusinessSuggestion.id).where(
            BusinessSuggestion.tenant_id == require_current_tenant(),
            BusinessSuggestion.pointer == pointer,
            BusinessSuggestion.decision.is_(None),
            BusinessSuggestion.proposed_value == sa.literal(value, type_=JSONB()),
        )
    )
    return found is not None


async def propose_import(
    session: AsyncSession, document: Mapping[str, Any], *, dry_run: bool
) -> ImportProposal:
    """Un ClientSpec importado → sus cambios como propuestas, cada una validada
    sin modelo. Con ``dry_run``, solo lo que propondría. Un documento que no
    vale no propone nada."""
    current = await client_spec.export_document(session, provenance=False)
    base_hash = client_spec.state_hash(current)
    _spec, problems = client_spec.validate_document(document)
    if problems:
        return ImportProposal(base_hash=base_hash, problems=problems)
    out = ImportProposal(base_hash=base_hash)
    for op in client_spec.diff_ops(current, document):
        op_problems = client_spec.validate_value(op["path"], op["value"])
        if op_problems:
            out.problems.extend(op_problems)
            continue
        out.ops.append(op)
    if dry_run or out.problems:
        return out
    tenant_id = require_current_tenant()
    for op in out.ops:
        if await _open_same(session, op["path"], op["value"]):
            continue
        session.add(
            BusinessSuggestion(
                tenant_id=tenant_id,
                pointer=op["path"],
                proposed_value=op["value"],
                current_value=op["current"],
                source="import",
            )
        )
        out.created += 1
    await session.flush()
    return out


__all__ = [
    "AlreadyDecided",
    "Decided",
    "Decision",
    "ImportProposal",
    "InvalidValue",
    "SectionNotWritable",
    "decide",
    "pending",
    "propose_import",
    "section_of",
]
