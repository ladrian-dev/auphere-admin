"""Grader diferido: turno → ``nexus:grade`` → veredicto en el mensaje (WP-21).

Cierra el bucle del muestreo. Lo que importa comprobar aquí no es que
"funcione", sino las tres propiedades por las que diferir es aceptable:

1. El veredicto acaba escrito **en el mensaje concreto** que salió sin
   graduar. Si se escribiera en otro, la auditoría de calidad diría
   cosas falsas sobre conversaciones reales.
2. **No reescribe la respuesta.** El mensaje ya se envió al cliente;
   cambiar su contenido ahora sería mentir sobre lo que leyó.
3. Un fallo del grader no bloquea la cola ni deja el mensaje colgado en
   ``deferred`` para siempre.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from nexus_worker.streams.grade_consumer import (
    GRADE_STREAM,
    drain_once,
    publish_grade_job,
)

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantPlan,
)

pytestmark = pytest.mark.asyncio

CONTENT = "Abrimos de 9 a 18."


class _Verdict:
    def __init__(self, overall: str, feedback: str) -> None:
        self.overall = overall
        self.feedback = feedback


class _FakeGrader:
    """Sustituye al LLM: el objetivo es medir el circuito, no gastar."""

    def __init__(self, *, overall: str = "pass", boom: bool = False) -> None:
        self.overall = overall
        self.boom = boom
        self.calls: list[dict] = []

    async def grade(self, **kwargs):
        self.calls.append(kwargs)
        if self.boom:
            raise RuntimeError("el proveedor dice que no")
        return _Verdict(self.overall, "todo bien" if self.overall == "pass" else "faltó el horario")


@pytest.fixture
async def clean_stream(fake_redis):
    await fake_redis.delete(GRADE_STREAM)
    yield fake_redis
    await fake_redis.delete(GRADE_STREAM)


async def _seed(tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Tenant + conversación + mensaje saliente marcado ``deferred``."""
    sm = get_sessionmaker()
    async with sm() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name="Diferido",
                slug=f"diferido-{tenant_id.hex[:8]}",
                plan=TenantPlan.PRO,
            )
        )
        await session.commit()

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        suffix = tenant_id.hex[:8]
        channel = Channel(
            tenant_id=tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3460{suffix}",
            status=ChannelStatus.ACTIVE,
        )
        session.add(channel)
        await session.flush()
        customer = Customer(tenant_id=tenant_id, identifier=f"+3461{suffix}", name="cliente")
        session.add(customer)
        await session.flush()
        conv = Conversation(
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conv)
        await session.flush()
        msg = Message(
            tenant_id=tenant_id,
            conversation_id=conv.id,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.SENT,
            content=CONTENT,
            # El estado que deja el pipeline cuando el turno salió sin
            # graduar: es el punto de partida de todo este archivo.
            outcome_overall="deferred",
        )
        session.add(msg)
        await session.flush()
        conv_id, msg_id = conv.id, msg.id
        await session.commit()
    return conv_id, msg_id


async def _message(tenant_id: uuid.UUID, msg_id: uuid.UUID):
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        return (
            await session.execute(
                sa.text(
                    "SELECT outcome_overall, outcome_feedback, content FROM messages WHERE id = :m"
                ),
                {"m": str(msg_id)},
            )
        ).one()


async def test_the_verdict_lands_on_the_message_that_went_out_ungraded(clean_stream) -> None:
    tenant_id = uuid.uuid4()
    conv_id, msg_id = await _seed(tenant_id)

    await publish_grade_job(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        message_id=msg_id,
        intent="info",
        user_message="¿a qué hora abren?",
        response=CONTENT,
        tool_calls=[{"tool": "kg.query", "status": "ok"}],
    )

    grader = _FakeGrader(overall="fail")
    assert await drain_once(clean_stream, grader=grader, consumer_name="test") == 1

    overall, feedback, content = await _message(tenant_id, msg_id)
    assert overall == "fail"
    assert feedback == "faltó el horario"
    # La propiedad que hace aceptable diferir: el veredicto se guarda,
    # la respuesta NO se toca. El cliente ya la leyó.
    assert content == CONTENT

    # El grader tiene que ver lo que devolvieron las herramientas: sin
    # eso no puede distinguir un dato consultado de uno inventado.
    assert grader.calls[0]["tool_envelopes"] == [{"tool": "kg.query", "status": "ok"}]


async def test_a_grader_failure_does_not_leave_the_message_stuck(clean_stream) -> None:
    """Un turno que se queda en ``deferred`` para siempre es peor que uno
    marcado ``error``: el primero parece pendiente y nadie lo mira."""
    tenant_id = uuid.uuid4()
    conv_id, msg_id = await _seed(tenant_id)
    await publish_grade_job(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        message_id=msg_id,
        intent="info",
        user_message="hola",
        response=CONTENT,
    )

    assert await drain_once(clean_stream, grader=_FakeGrader(boom=True), consumer_name="test") == 1
    overall, _feedback, _content = await _message(tenant_id, msg_id)
    assert overall == "error"


async def test_reprocessing_does_not_overwrite_a_settled_verdict(clean_stream) -> None:
    """El ``AND outcome_overall = 'deferred'`` del UPDATE. Sin él,
    reprocesar el stream tras un incidente reescribiría veredictos ya
    cerrados con lo que diga el grader hoy."""
    tenant_id = uuid.uuid4()
    conv_id, msg_id = await _seed(tenant_id)
    for _ in range(2):
        await publish_grade_job(
            tenant_id=tenant_id,
            conversation_id=conv_id,
            message_id=msg_id,
            intent="info",
            user_message="hola",
            response=CONTENT,
        )

    await drain_once(clean_stream, grader=_FakeGrader(overall="pass"), consumer_name="test")
    assert (await _message(tenant_id, msg_id))[0] == "pass"

    # Segunda vuelta con un grader que diría lo contrario.
    await clean_stream.xgroup_setid(GRADE_STREAM, "nexus-grade", id="0")
    await drain_once(clean_stream, grader=_FakeGrader(overall="fail"), consumer_name="test")
    assert (await _message(tenant_id, msg_id))[0] == "pass", "un veredicto cerrado fue reescrito"


async def test_an_unusable_job_is_acked_and_does_not_block_the_queue(clean_stream) -> None:
    tenant_id = uuid.uuid4()
    conv_id, msg_id = await _seed(tenant_id)

    await clean_stream.xadd(GRADE_STREAM, {"tenant_id": "no-soy-un-uuid", "message_id": "x"})
    await publish_grade_job(
        tenant_id=tenant_id,
        conversation_id=conv_id,
        message_id=msg_id,
        intent="info",
        user_message="hola",
        response=CONTENT,
    )

    await drain_once(clean_stream, grader=_FakeGrader(), consumer_name="test")
    assert (await _message(tenant_id, msg_id))[0] == "pass", "el trabajo bueno no se procesó"
