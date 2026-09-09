"""``GET /console/session/tool-catalog`` — qué herramientas publica una sesión.

Lo pide la edición en cada turno, desde la máquina del partner. La forma está en
`specs/001-puesto-trabajo-partner/contracts/console-mcp.md`.

**No acepta parámetros de ámbito**, y no por descuido: el catálogo del teammate
es el declarativo de Auphere, igual para todos. La tenencia no la da variar el
catálogo — la imponen la RLS y `client_scope` cuando la herramienta se ejecuta.
Un filtro por cliente aquí convertiría un documento público en una superficie con
ámbito, y sería una tercera cosa que mantener sincronizada.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.services.session_tool_catalog import build_session_catalog

from .schemas_workstation import SessionToolCatalogOut

router = APIRouter(prefix="/session")


@router.get("/tool-catalog", response_model=SessionToolCatalogOut)
async def session_tool_catalog(
    _: ConsolePrincipal = Depends(require_console_principal("workstation:read")),
) -> SessionToolCatalogOut:
    return SessionToolCatalogOut.model_validate(build_session_catalog())
