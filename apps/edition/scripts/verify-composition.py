#!/usr/bin/env python3
"""Comprueba que la edición compone sobre el sustrato sin tocar el núcleo.

Requisito 5.1, y la invariante D2 del plan: si esto falla, la opción A ha dejado de
ser composición y hay que replantear la spec antes de seguir construyendo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    from auphere_edition import SUBSTRATE_PINNED_COMMIT
    from auphere_edition.edition import (
        AuphereAgentCatalog,
        AuphereMcpTooling,
        build_enterprise_context,
    )
    from kiro_crew.config.loader import KiroCrewConfig  # type: ignore[import-not-found]

    ctx = build_enterprise_context(KiroCrewConfig.load())
    checks: list[tuple[str, bool, str]] = [
        ("perfil enterprise", ctx.profile == "enterprise", str(ctx.profile)),
        ("mcp_tooling es nuestro", isinstance(ctx.mcp_tooling, AuphereMcpTooling), type(ctx.mcp_tooling).__name__),
        ("agent_catalog es nuestro", isinstance(ctx.agent_catalog, AuphereAgentCatalog), type(ctx.agent_catalog).__name__),
        ("floor de seguridad intacto", type(ctx.security).__name__ == "PolicyAuthority",
         type(ctx.security).__name__),
        ("contract_version esperado", ctx.contract_version == 1, str(ctx.contract_version)),
    ]

    clone = Path(subprocess.run(
        ["git", "-C", str(Path.home() / "Workspace/_oss-research/kirocrew"), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True).stdout.strip() or ".")
    dirty = subprocess.run(["git", "-C", str(clone), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    checks.append(("clon en el commit fijado", head.startswith(SUBSTRATE_PINNED_COMMIT[:7]), head))
    checks.append(("clon sin modificar", dirty == "", f"{len(dirty.splitlines())} ficheros"))

    ok = True
    for name, passed, detail in checks:
        print(f"  {'OK ' if passed else 'FALLA'}  {name:<28} {detail}")
        ok = ok and passed
    print("\ncomposición verificada" if ok else "\nLA COMPOSICIÓN NO SE SOSTIENE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
