"""La solicitud que no llega a nada — spec 006, Requisito 6.1 y casos límite.

Una solicitud caducada **no deja rastro**: ni partner, ni cuenta, ni membresía.
Y el mismo correo puede volver a intentarlo, porque lo contrario convertiría un
enlace olvidado en una dirección quemada para siempre.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Partner, SignupStatus
from nexus_api.repositories.signup import SignupRequestRepository

pytestmark = pytest.mark.asyncio


class TestUnaCaducadaNoDejaNada:
    async def test_no_crea_partner_ni_cuenta(self, db_session) -> None:
        repo = SignupRequestRepository(db_session)
        email = f"cad-{uuid.uuid4().hex[:8]}@agencia.com"
        row, token = await repo.create(email=email, ttl_hours=24)
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.commit()

        antes = (
            await db_session.execute(sa.select(sa.func.count()).select_from(Partner))
        ).scalar_one()
        assert await repo.get_pending_by_token(token) is None
        await db_session.commit()
        despues = (
            await db_session.execute(sa.select(sa.func.count()).select_from(Partner))
        ).scalar_one()
        assert antes == despues

    async def test_se_marca_caducada_al_mirarla_no_solo_con_el_cron(self, db_session) -> None:
        """La caducidad perezosa existe para que el estado sea verdad aunque el
        cron no haya pasado: si sólo lo marcara el cron, entre dos pasadas la
        fila diría `pending` de algo que ya no lo está."""
        repo = SignupRequestRepository(db_session)
        row, token = await repo.create(email=f"lazy-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()
        await repo.get_pending_by_token(token)
        await db_session.commit()
        await db_session.refresh(row)
        assert row.status == SignupStatus.EXPIRED.value

    async def test_el_mismo_correo_puede_volver_a_intentarlo(self, db_session) -> None:
        repo = SignupRequestRepository(db_session)
        email = f"retry-{uuid.uuid4().hex[:8]}@agencia.com"
        primera, _t1 = await repo.create(email=email, ttl_hours=24)
        primera.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.commit()
        segunda, t2 = await repo.create(email=email, ttl_hours=24)
        await db_session.commit()
        assert segunda.id != primera.id
        assert await repo.get_pending_by_token(t2) is not None


class TestUnTokenUsadoDosVeces:
    async def test_el_segundo_uso_se_comporta_como_uno_invalido(self, db_session) -> None:
        repo = SignupRequestRepository(db_session)
        row, token = await repo.create(email=f"once-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        await db_session.commit()
        assert await repo.get_pending_by_token(token) is not None
        row.status = SignupStatus.CONSUMED.value
        await db_session.commit()
        assert await repo.get_pending_by_token(token) is None


class TestElCronDeCaducidad:
    async def test_barre_las_vencidas_y_no_toca_las_vivas(self, db_session) -> None:
        repo = SignupRequestRepository(db_session)
        vencida, _a = await repo.create(email=f"v-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        vencida.expires_at = datetime.now(UTC) - timedelta(hours=1)
        viva, _b = await repo.create(email=f"w-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        await db_session.commit()

        barridas = await repo.expire_overdue()
        await db_session.commit()
        assert barridas >= 1
        await db_session.refresh(vencida)
        await db_session.refresh(viva)
        assert vencida.status == SignupStatus.EXPIRED.value
        assert viva.status == SignupStatus.PENDING.value, "el cron se llevó una que seguía viva"

    async def test_no_toca_las_ya_consumidas(self, db_session) -> None:
        """Una consumida con fecha pasada NO debe pasar a `expired`: se usó, y
        reescribir su estado perdería esa información."""
        repo = SignupRequestRepository(db_session)
        row, _t = await repo.create(email=f"c-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        row.status = SignupStatus.CONSUMED.value
        row.expires_at = datetime.now(UTC) - timedelta(hours=5)
        await db_session.commit()
        await repo.expire_overdue()
        await db_session.commit()
        await db_session.refresh(row)
        assert row.status == SignupStatus.CONSUMED.value
