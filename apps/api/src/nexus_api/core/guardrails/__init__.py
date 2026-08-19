"""Guardarraíles — la capa nombrada (CO-07 · §24 de la investigación).

AgentKit nombra cinco: enmascarado de PII, detección de *jailbreak*,
moderación de contenido, comprobación contra la base de conocimiento y
pasos de aprobación para acciones críticas. En Nexus:

| Barandilla | Dónde vive |
|---|---|
| Pasos de aprobación | ``propose → confirm → apply`` (R3, CO-04) — **la fuerte** |
| Comprobación contra el conocimiento | regla R1, ``runtime/companion/grounding.py`` |
| Enmascarado de PII | :mod:`~nexus_api.core.guardrails.pii` |
| *Jailbreak* / inyección | :mod:`~nexus_api.core.guardrails.untrusted` |
| Moderación de contenido | no se implementa: el interlocutor del Companion es un miembro autenticado del partner, no público |

Que estén juntas y con nombre es el punto. Antes estaban repartidas: dos
enmascaradores de teléfono divergentes en ``services/``, un
``_strip_tags`` privado en el worker, y nada que las llamara "esto es lo
que impide que el agente haga daño".
"""

from __future__ import annotations

from nexus_api.core.guardrails.pii import (
    contains_pii,
    mask_email,
    mask_person_name,
    mask_phone,
    scrub_pii,
)
from nexus_api.core.guardrails.untrusted import (
    TAG_CLIENT_NAME,
    TAG_KNOWLEDGE,
    TAG_META_REJECTION,
    TAG_PAGE_CONTEXT,
    TAG_TOOL_RESULT,
    UNTRUSTED_PREAMBLE,
    fence,
    fenced_block,
    neutralise_tags,
)

__all__ = [
    "TAG_CLIENT_NAME",
    "TAG_KNOWLEDGE",
    "TAG_META_REJECTION",
    "TAG_PAGE_CONTEXT",
    "TAG_TOOL_RESULT",
    "UNTRUSTED_PREAMBLE",
    "contains_pii",
    "fence",
    "fenced_block",
    "mask_email",
    "mask_person_name",
    "mask_phone",
    "neutralise_tags",
    "scrub_pii",
]
