"""Sector guides for the builder — spec 047, amendment of 2026-10-29 (requirement 58;
research D47, D66 and D67).

- ``schema``: the shape of a guide and the normalised label;
- ``catalog``: Auphere's guides derived from the vertical templates, and the
  generic one;
- ``roles``: the role patterns the builder receives as examples;
- ``generated``: the guide generated for one client whose sector has none;
- ``resolve``: which guide a client gets;
- ``client_data``: «sin datos del cliente», before converting a guide;
- ``promotion``: the operator panel's list and «Convertir en guía de Auphere».
"""

from nexus_api.services.builder.guides.schema import (
    Guide,
    GuideInvalid,
    label_key,
    render,
    validate_guide,
    validate_tests,
)

__all__ = ["Guide", "GuideInvalid", "label_key", "render", "validate_guide", "validate_tests"]
