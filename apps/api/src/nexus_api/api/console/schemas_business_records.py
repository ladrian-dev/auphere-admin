"""Esquemas de la ficha: procedencia, historial, propuestas, fuentes y ClientSpec
(spec 047, de la T069 a la T072; ``contracts/console-api.md`` §3).

Nada de aquí lleva un cuerpo de mensaje, un teléfono de un cliente final ni un
coste (C1, C8, C9): la ficha es del negocio. El ClientSpec viaja como documento
(``spec``) con la forma de ``contracts/client-spec.schema.json``; sus campos los
valida el servidor (``services/business/client_spec.py``), no este esquema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Section = Literal[
    "basics",
    "locations",
    "hours",
    "special_dates",
    "services",
    "policies",
    "faqs",
    "sources",
    "links",
]
SectionState = Literal["complete", "read_pending", "pending", "optional"]
Source = Literal[
    "person", "web", "document", "social", "migrated", "builder", "inbox_correction", "import"
]
Origin = Literal["console", "lite_web", "app", "admin", "api", "system"]
ActorKind = Literal["partner_member", "client_user", "operator", "system", "builder"]
ChangeKind = Literal[
    "edit", "read_applied", "builder_applied", "correction", "migration", "import", "undo"
]
Network = Literal["web", "instagram", "facebook", "tiktok", "linkedin", "youtube", "x", "threads"]
BusinessAction = Literal["edit", "import", "undo", "decide"]


class PersonOut(BaseModel):
    """Quién escribió: su clase, su id y su nombre visible (``None`` si no lo hay)."""

    kind: ActorKind
    id: str | None = None
    name: str | None = None


class ProvenanceOut(BaseModel):
    source: Source
    by: PersonOut | None = None
    origin: Origin
    at: datetime
    source_url: str | None = None
    translated_from: str | None = None
    review: Literal["pending", "confirmed"]


class SectionOut(BaseModel):
    section: Section
    state: SectionState
    revision: int
    updated_at: datetime | None = None
    updated_by: PersonOut | None = None
    origin: Origin | None = None
    pending_suggestions: int = 0


class SuggestionOut(BaseModel):
    id: uuid.UUID
    pointer: str
    section: Section
    proposed_value: Any = None
    current_value: Any = None
    source: Source
    source_url: str | None = None
    translated_from: str | None = None
    created_at: datetime


class ProblemOut(BaseModel):
    """Un problema del documento: dónde (puntero) y qué (código cerrado)."""

    pointer: str
    code: str


class BusinessRecordOut(BaseModel):
    """``GET /console/clients/{ref}/business``: la ficha entera."""

    #: El ClientSpec v1, sin procedencia (va aparte, con nombres).
    spec: dict[str, Any]
    #: ``False`` si el documento no pasa el validador (un país o una moneda que
    #: aún no se saben, por ejemplo); ``problems`` dice dónde.
    valid: bool
    problems: list[ProblemOut] = Field(default_factory=list)
    sections: list[SectionOut]
    provenance: dict[str, ProvenanceOut]
    suggestions: list[SuggestionOut]
    allowed: list[BusinessAction]


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    network: Network
    url: str | None = Field(default=None, max_length=300)
    handle: str | None = Field(default=None, max_length=31)


class LinksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[LinkIn] = Field(max_length=20)


class LinkOut(BaseModel):
    id: uuid.UUID
    network: Network
    url: str | None = None
    handle: str | None = None


class LinksOut(BaseModel):
    links: list[LinkOut]
    revision: int


class ConfirmOut(BaseModel):
    section: Section
    state: SectionState
    revision: int
    confirmed: int


class ChangeOut(BaseModel):
    id: uuid.UUID
    section: Section
    kind: ChangeKind
    at: datetime
    by: PersonOut | None = None
    origin: Origin
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    undone_at: datetime | None = None
    undo_of: uuid.UUID | None = None
    undoable: bool


class HistoryOut(BaseModel):
    items: list[ChangeOut]


class UndoOut(BaseModel):
    section: Section
    #: La revisión que queda; ``None`` si deshacer no cambiaba nada.
    revision: int | None = None
    change_id: uuid.UUID | None = None


class DecideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accept", "edit", "discard"]
    #: Solo con ``edit``: el valor que vale en lugar del propuesto.
    value: Any = None


class DecideOut(BaseModel):
    suggestion_id: uuid.UUID
    decision: Literal["accepted", "edited", "discarded"]
    section: Section
    revision: int | None = None


class ImportOpOut(BaseModel):
    op: Literal["add", "replace", "archive"]
    path: str
    value: Any = None
    current: Any = None


class ImportOut(BaseModel):
    """``POST /import``: lo que el documento cambia, como propuestas."""

    dry_run: bool
    base_hash: str
    ops: list[ImportOpOut]
    problems: list[ProblemOut]
    #: Las propuestas que se crearon (0 con ``dry_run``).
    created: int


class SourceOut(BaseModel):
    """Una fuente de «Documentos y webs»: su estado, su tamaño y cuándo se leyó.
    Nunca su texto."""

    id: uuid.UUID
    kind: Literal["file", "web"]
    title: str
    url: str | None = None
    status: Literal["reading", "read", "failed"]
    failure: Literal["unreachable", "blocked", "no_text", "too_large"] | None = None
    size_bytes: int
    read_at: datetime | None = None
    created_at: datetime


class RemovedSourceOut(BaseModel):
    id: uuid.UUID
    kind: Literal["file", "web"]
    title: str
    restore_until: datetime


class SourcesOut(BaseModel):
    items: list[SourceOut]
    #: Lo quitado que aún se puede recuperar (10 minutos).
    removed: list[RemovedSourceOut]
    #: El tamaño máximo de un archivo, en bytes.
    max_bytes: int
    allowed: list[Literal["add", "remove", "reread"]]


class SourceUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2048)
    title: str | None = Field(default=None, max_length=255)


class SourceAcceptedOut(BaseModel):
    """``202``: la fuente, ya «Leyendo», y el trabajo que la lee."""

    source: SourceOut
    job_id: uuid.UUID


class SourceRemovedOut(BaseModel):
    id: uuid.UUID
    restore_until: datetime


__all__ = [
    "BusinessRecordOut",
    "ChangeOut",
    "ConfirmOut",
    "DecideIn",
    "DecideOut",
    "HistoryOut",
    "ImportOpOut",
    "ImportOut",
    "LinkIn",
    "LinkOut",
    "LinksIn",
    "LinksOut",
    "PersonOut",
    "ProblemOut",
    "ProvenanceOut",
    "RemovedSourceOut",
    "SectionOut",
    "SourceAcceptedOut",
    "SourceOut",
    "SourceRemovedOut",
    "SourceUrlIn",
    "SourcesOut",
    "SuggestionOut",
    "UndoOut",
]
