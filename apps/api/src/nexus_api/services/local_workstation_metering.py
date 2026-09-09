"""El medidor de las sesiones locales — Requisito 10.

**Un solo medidor.** El consumo de modelo de una sesión en la máquina del partner
entra en el mismo `usage_ledger` que todo lo demás, con `debit_wallet`. Un
contador aparte para esta superficie sería un segundo sitio donde las cifras
dejan de cuadrar, y el partner vería dos números que no suman.

**El reloj de máquina no se factura, y aquí no hay forma de hacerlo.** La máquina
es del partner y ya está pagada: es la ventaja económica de la superficie `3a`
frente a la `2`, donde los 121 $/mes/partner salen precisamente de facturar
reloj. La garantía no es una nota en un documento — es que esta función **no
recibe ninguna duración**, así que no se puede facturar tiempo ni por accidente.

**Dónde lo ve el partner**: en el mismo consumo de la consola —`/usage`— que ya
mira. No hay pantalla nueva, porque no hay concepto nuevo: es modelo consumido.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.metering.wallet import DebitResult, debit_wallet, partner_id_for_tenant

#: Espacio de nombres de la clave. Sin él, un id que se repitiera en otro carril
#: cancelaría un cobro ajeno — y eso se descubre cuadrando facturas, tarde.
KEY_PREFIX = "local_exec:"


def idempotency_key_for(execution_id: uuid.UUID) -> str:
    """Clave derivada de la ejecución: un resultado repetido no cobra dos veces."""
    return f"{KEY_PREFIX}{execution_id}"


def chargeable_units(*, outcome: str, model_units: int) -> int:
    """Lo que se cobra según cómo acabó.

    Una **denegación** no consumió modelo: el gate dijo que no antes de llamar a
    nadie. Cobrarla sería cobrar por decir que no. Una expirada o terminada sí
    consumió hasta que se cortó, y se cobra lo consumido.
    """
    if outcome == "denegada":
        return 0
    return max(0, model_units)


async def meter_local_model_use(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    execution_id: uuid.UUID,
    outcome: str,
    model_units: int,
) -> DebitResult | None:
    """Asienta el consumo de modelo de una ejecución local.

    Devuelve ``None`` cuando no hay nada que cobrar o el tenant no cuelga de
    ningún partner — no se inventa un asiento para que cuadre una gráfica.
    """
    units = chargeable_units(outcome=outcome, model_units=model_units)
    if units == 0:
        return None
    partner_id = await partner_id_for_tenant(session, tenant_id)
    if partner_id is None:
        return None
    return await debit_wallet(
        partner_id=partner_id,
        qty=units,
        idempotency_key=idempotency_key_for(execution_id),
        tenant_id=tenant_id,
    )


__all__ = [
    "KEY_PREFIX",
    "chargeable_units",
    "idempotency_key_for",
    "meter_local_model_use",
]
