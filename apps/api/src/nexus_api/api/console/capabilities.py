"""``GET /console/capabilities`` — qué hay, qué llega y qué no (CO-08, §5).

El Companion necesita saber dónde están las paredes. Si no, alucina
capacidades y manda al partner contra un muro — y una capacidad prometida
que no existe es una promesa rota **con el cliente del partner**, no con
nosotros.

Por qué es un endpoint y no una lectura de fichero
--------------------------------------------------
Sirviéndolo por HTTP entra por la misma tubería que el resto de las
herramientas del Companion: autorización, recorte por ``max_chars``, cita
con procedencia, y el recorrido del OpenAPI de
``tests/isolation/test_console_scope.py``. Además deja
``tool.call.started`` en el registro del turno, así que se puede auditar
qué sabía el Companion cuando dijo lo que dijo.

Por qué no se hornea en el prompt de sistema
--------------------------------------------
Un límite en el prompt no deja cita, no deja evento y no se puede versionar
sin invalidar el caché del prompt estable. Leerlo deja las tres cosas.

**No acepta ningún parámetro.** El documento es el mismo para todos los
partners: no hay nada aquí que dependa de quién pregunta, y un filtro por
cliente convertiría un catálogo público en una superficie con ámbito.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from nexus_api.companion.tools.support import (
    CapabilitiesUnavailable,
    load_capabilities,
)
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal

from .schemas_capabilities import CapabilitiesOut, CapabilityOut

router = APIRouter()


@router.get(
    "/capabilities",
    response_model=CapabilitiesOut,
    responses={503: {"description": "The capability document could not be read."}},
)
async def get_capabilities(
    # ``partner:read`` y no ``companion:use``: saber qué existe en la
    # plataforma no es un privilegio. Un rol que no puede usar el Companion
    # sigue mereciendo una respuesta honesta a "¿esto se puede?".
    _principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
) -> CapabilitiesOut:
    try:
        document = load_capabilities()
    except CapabilitiesUnavailable as exc:
        # 503 y no un documento vacío. Un catálogo vacío le diría al
        # Companion que NADA existe, y entonces negaría capacidades que sí
        # tenemos — que es peor que no responder. Con el 503, la herramienta
        # falla, el modelo lo ve y R1 le impide afirmar nada.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The capability document is not available right now.",
        ) from exc
    return CapabilitiesOut(
        version=document.version,
        entries=[
            CapabilityOut(
                key=entry.key,
                family=entry.family,
                status=entry.status,
                label=entry.label,
                note=entry.note,
                eta=entry.eta,
                replaced_by=list(entry.replaced_by),
            )
            for entry in document.entries
        ],
    )
