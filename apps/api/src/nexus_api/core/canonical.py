"""La huella canónica de un documento JSON — spec 047.

Una función pura, sin base de datos ni servicios: la usan el estado de las
propuestas (``services/proposal_state``) y las herramientas del Companion, que no
pueden importar servicios (``tests/isolation/test_companion_tools_imports.py``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_hash(payload: Any) -> str:
    """SHA-256 hexadecimal de un JSON canónico: el mismo estado da siempre la
    misma huella (``sort_keys`` y separadores compactos)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


__all__ = ["canonical_hash"]
