"""Auphere edition over the pinned substrate.

The core is never patched: everything here composes through the substrate's own
``kirocrew.plugins`` entry point. If a change here ever requires editing a file
inside the substrate, stop — that is the line between composing and forking, and
crossing it invalidates the assessment this feature rests on.
"""

SUBSTRATE_PINNED_COMMIT = "37933a5"
SUBSTRATE_VERSION = "0.7.0"

__all__ = ["SUBSTRATE_PINNED_COMMIT", "SUBSTRATE_VERSION"]
