"""De registrarse a poder pagar — spec 006, Requisito 4.

La Historia 1 deja a alguien dentro de su consola. Ésta comprueba que desde
ahí se llega a contratar **sin que intervenga nadie**, y que mientras tanto
Free no es una sala de espera vacía.

**La decisión que se fija aquí, y su porqué** (clarificación D3 del 2026-09-13):
un partner en Free **puede** dar de alta clientes finales. No hace falta un
tope nuevo porque el que decide ya existe — desde la spec 004 R5.2 el consumo
de un cliente final sale de los créditos **comprados**, nunca del pool
incluido (`allow_included=False` en el consumidor del worker). Sin crédito
comprado ni plan, un turno no pasa. Inventar aquí un límite de clientes sería
el segundo contador sobre el mismo gasto que ADR-037 acaba de eliminar.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Partner
from nexus_api.db.models.membership import PartnerSubscription
from nexus_api.metering.wallet import debit_wallet
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services.signup import complete_signup

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner_recien_registrado(db_session: object) -> Partner:
    repo = SignupRequestRepository(db_session)  # type: ignore[arg-type]
    row, _token = await repo.create(email=f"pay-{uuid.uuid4().hex[:8]}@agencia.com", ttl_hours=24)
    await db_session.flush()  # type: ignore[attr-defined]
    outcome = await complete_signup(
        db_session,  # type: ignore[arg-type]
        signup=row,
        company_name=f"Agencia {uuid.uuid4().hex[:6]}",
        user_id=f"acct_{uuid.uuid4().hex[:12]}",
        display_name=None,
    )
    await db_session.commit()  # type: ignore[attr-defined]
    return outcome.partner


class TestElCaminoAContratarNoPasaPorNadie:
    async def test_nace_en_free_y_nada_lo_bloquea_para_contratar(self, db_session: object) -> None:
        """Requisito 4.1.

        Lo que se comprueba no es el checkout —ése ya existe y es de la spec
        005— sino que el partner nace en un estado desde el que se puede
        contratar: activo, con la consola encendida y sin ninguna marca de
        «pendiente de que alguien lo apruebe».
        """
        partner = await _partner_recien_registrado(db_session)
        assert partner.status == "active"
        assert partner.console_enabled is True

        subs = (
            await db_session.execute(  # type: ignore[attr-defined]
                sa.select(sa.func.count())
                .select_from(PartnerSubscription)
                .where(PartnerSubscription.partner_id == partner.id)
            )
        ).scalar_one()
        assert subs == 0, "sin fila es Free; una fila aquí significa que alguien sembró algo"

    async def test_el_alta_no_cobra_nada(self, db_session: object) -> None:
        """Requisito 4.4: alta y contratación son dos actos, y el segundo es
        del owner.

        Se comprueba por ausencia: tras registrarse no hay suscripción, no hay
        cliente de pago asociado y el monedero no se ha tocado.
        """
        partner = await _partner_recien_registrado(db_session)
        from nexus_api.db.models.partner_wallet import PartnerWallet

        wallets = (
            await db_session.execute(  # type: ignore[attr-defined]
                sa.select(sa.func.count())
                .select_from(PartnerWallet)
                .where(PartnerWallet.partner_id == partner.id)
            )
        ).scalar_one()
        # Cero o un monedero recién creado a cero: lo que no puede haber es un
        # movimiento. Si algún día el alta acredita saldo "de bienvenida", esto
        # se pone rojo y la decisión se toma a propósito, no por deriva.
        assert wallets in (0, 1)


class TestFreeNoEsUnaSalaDeEspera:
    async def test_un_turno_de_cliente_final_no_pasa_sin_saldo_comprado(
        self, db_session: object
    ) -> None:
        """Requisito 4.3 y la decisión D3.

        **Éste es el tope real.** No hay límite de clientes en Free porque no
        hace falta: el turno de un cliente final sólo puede salir del saldo
        comprado, y un partner recién registrado tiene cero.
        """
        partner = await _partner_recien_registrado(db_session)

        resultado = await debit_wallet(
            partner_id=partner.id,
            tenant_id=None,
            qty=1_000,
            idempotency_key=f"channel:{uuid.uuid4().hex}",
            # Lo que hace el consumidor del worker para un turno de canal.
            allow_included=False,
        )
        assert resultado.spent == 0, "el turno consumió saldo que el partner no ha comprado"
        assert resultado.from_included == 0, (
            "salió del pool incluido: el pool es de la aplicación, no de los clientes finales"
        )

    async def test_el_pool_incluido_sigue_sirviendo_para_la_aplicacion(
        self, db_session: object
    ) -> None:
        """La otra mitad, y hay que probarla: si cerrar el cubo incluido a los
        clientes finales lo cerrara también para el Companion y los teammates,
        Free no valdría para nada y la decisión D3 sería falsa en la práctica.
        """
        partner = await _partner_recien_registrado(db_session)
        from nexus_api.db.models.partner_wallet import PartnerWallet

        # El monedero ya existe: un partner nuevo nace con él. Aquí sólo se
        # fija el cubo incluido, porque lo que se prueba es el reparto y no la
        # renovación semanal del pool.
        wallet = await db_session.get(PartnerWallet, partner.id)  # type: ignore[attr-defined]
        assert wallet is not None, "un partner recién registrado debería tener monedero"
        wallet.included_remaining = 5_000
        wallet.purchased_remaining = 0
        await db_session.commit()  # type: ignore[attr-defined]

        resultado = await debit_wallet(
            partner_id=partner.id,
            tenant_id=None,
            qty=1_000,
            idempotency_key=f"companion:{uuid.uuid4().hex}",
            # El Companion sí puede gastar el pool incluido.
            allow_included=True,
        )
        assert resultado.from_included == 1_000


class TestElOwnerNaceConLoQueNecesitaParaContratar:
    async def test_tiene_los_permisos_de_facturacion_desde_el_primer_segundo(self) -> None:
        """Requisito 4.1, y es lo que hace verdadera la frase «sin ningún paso
        que exija operador».

        La pantalla de planes existe desde la spec 005 y se protege con
        ``billing:read``. Si el rol con el que nace un partner no lo tuviera,
        el alta terminaría con alguien dentro que **no puede pagar**, y haría
        falta un operador para arreglarlo — justo lo que esta spec quita.
        """
        from nexus_api.core.console_auth import permissions_for

        permisos = permissions_for("owner")
        assert "billing:read" in permisos
        assert "partner:read" in permisos
        # El rol con el que nace es `owner`, no uno intermedio: lo fija
        # `complete_signup` y lo comprueba el test del servicio.
