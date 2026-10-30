"""Spec 047, T175 — corregir una respuesta desde la Bandeja (historia 32; requisitos
52.1 a 52.6; ``contracts/lite-app-api.md`` §3; research D35).

- **Dónde** (52.1): «Corregir esta respuesta» sobre una respuesta del agente, en la
  lite y en la app, con el texto y el alcance (``business`` o ``agent``).
- **Qué tipo** (52.2): dato o comportamiento, en el borrador antes de enviar.
- **Un dato** se aplica al momento: en la ficha (una pregunta frecuente) si es de
  todo el negocio, en el conocimiento del agente si es solo suyo; con historial
  y deshacer, y el agente lo usa desde el siguiente mensaje.
- **Un comportamiento** llega al partner como propuesta, con su prueba.
- **Lo que ve el partner** (52.3): la lección y la paráfrasis, nunca el mensaje.
- **La paráfrasis** (52.4) la escribe un modelo (aquí uno de mentira), sin datos
  personales, y la persona la revisa y la edita.
- **Datos personales** (52.5): teléfono, nombre, correo o documento se detectan y
  bloquean guardar (``pii_present``).
- **Procedencia y auditoría** (52.6): «Corregido por {persona} desde la Bandeja».
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AuditLog,
    BusinessChange,
    BusinessFaq,
    BusinessFieldProvenance,
    ConsoleNotification,
    Conversation,
    Customer,
    InboxCorrection,
    KnowledgeDocument,
    Message,
    MessageDirection,
    MessageStatus,
)
from nexus_api.db.models.agent_spec import Proposal
from nexus_api.services.business import writes
from nexus_api.services.improvement import corrections, paraphrase
from tests.conftest import add_client_phone, make_inbox

from ..business._business_world import Biz, active_prompt, new_business, seed_agent

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

LITE = "/console/lite"
QUESTION = "Hola, soy Lucía Pérez, mi móvil es +34 612 345 678. ¿Dónde puedo aparcar?"


@dataclass
class FakeParaphraser:
    """Un modelo de mentira que repite lo que le llega, con los datos del
    contacto dentro: lo que salga sin ellos lo quitó el servicio, no el modelo."""

    seen: list[str] = field(default_factory=list)
    #: El partner atado al proxy cuando se llamó al modelo.
    partners: list[uuid.UUID | None] = field(default_factory=list)

    async def __call__(self, customer_text: str) -> str:
        from nexus_api.core.llm_proxy import current_llm_proxy_partner

        self.seen.append(customer_text)
        self.partners.append(current_llm_proxy_partner())
        return "Lucía Pérez (+34 612 345 678, lucia@correo.es) pregunta dónde se puede aparcar."


@pytest.fixture
async def fake_paraphraser() -> AsyncIterator[FakeParaphraser]:
    fake = FakeParaphraser()
    paraphrase.set_paraphraser(fake)
    yield fake
    paraphrase.set_paraphraser(None)


@dataclass
class Inbox:
    biz: Biz
    person: dict[str, Any]
    agent_id: uuid.UUID
    config_id: uuid.UUID
    conversation: uuid.UUID
    question: uuid.UUID
    answer: uuid.UUID
    other_conversation: uuid.UUID

    def headers(self, **kw: Any) -> dict[str, str]:
        out: dict[str, str] = self.person["headers"](**kw)
        return out

    def url(self, message_id: uuid.UUID | None = None) -> str:
        return f"{LITE}/inbox/{self.conversation}/messages/{message_id or self.answer}/corrections"


@pytest.fixture
async def inbox(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    fake_paraphraser: FakeParaphraser,
) -> Inbox:
    """Barbería Cultor con Recepción y una conversación en la que Lucía Pérez
    pregunta por el aparcamiento y el agente no lo sabe."""
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")
    agent_id, config_id = await seed_agent(
        db_session, biz.tenant_id, name="Recepción", prompt="Eres Recepción."
    )
    seeded = await make_inbox(db_session, partner_id=biz.partner_id, tenant_id=biz.tenant_id)
    conversation = seeded["conversations"][0]
    now = datetime.now(UTC)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        conv = await db_session.get(Conversation, conversation)
        assert conv is not None
        customer = await db_session.get(Customer, conv.customer_id)
        assert customer is not None
        customer.name = "Lucía Pérez"
        question = Message(
            tenant_id=biz.tenant_id,
            conversation_id=conversation,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content=QUESTION,
            created_at=now - timedelta(seconds=30),
        )
        answer = Message(
            tenant_id=biz.tenant_id,
            conversation_id=conversation,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.SENT,
            content="No tengo esa información, lo siento.",
            actor_kind="agent",
            created_at=now - timedelta(seconds=20),
        )
        db_session.add_all([question, answer])
        conv.last_message_at = now
        await db_session.flush()
        ids = (question.id, answer.id)
    return Inbox(
        biz=biz,
        person=seeded["member"],
        agent_id=agent_id,
        config_id=config_id,
        conversation=conversation,
        question=ids[0],
        answer=ids[1],
        other_conversation=seeded["conversations"][1],
    )


async def _draft(
    client: Any, inbox: Inbox, text: str, scope: str = "business", **kw: Any
) -> dict[str, Any]:
    resp = await client.post(
        inbox.url(), json={"text": text, "scope": scope}, headers=inbox.headers(**kw)
    )
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def _send(client: Any, inbox: Inbox, draft: dict[str, Any], expect: int = 200) -> Any:
    resp = await client.post(
        f"{LITE}/corrections/{draft['id']}/send",
        headers={**inbox.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert resp.status_code == expect, resp.text
    return resp.json()


async def _rows(db_session: AsyncSession, tenant_id: uuid.UUID, stmt: Any) -> list[Any]:
    async with tenant_scoped_session(db_session, tenant_id):
        return list((await db_session.scalars(stmt)).all())


# ── el borrador ────────────────────────────────────────────────────────────


async def test_the_draft_says_its_kind_and_a_paraphrase_without_personal_data(
    client: Any, inbox: Inbox, fake_paraphraser: FakeParaphraser
) -> None:
    """52.1, 52.2 y escenario 3: el tipo y la paráfrasis, a la vista antes de enviar."""
    draft = await _draft(client, inbox, "El aparcamiento está en la calle de atrás.")
    assert draft["kind"] == "data" and draft["scope"] == "business"
    assert draft["status"] == "draft" and draft["revision"] == 1
    assert draft["lesson"] == "El aparcamiento está en la calle de atrás."
    assert draft["agent"] == {"id": str(inbox.agent_id), "name": "Recepción"}
    assert draft["pii"] == []
    # El modelo leyó lo que preguntó el cliente…
    assert fake_paraphraser.seen and "aparcar" in fake_paraphraser.seen[-1]
    # …y la paráfrasis sale sin su nombre, su teléfono ni su correo.
    para = draft["paraphrase"]
    assert "aparcar" in para
    for leaked in ("Lucía", "Pérez", "612", "345 678", "lucia@correo.es"):
        assert leaked not in para, leaked
    # El borrador no repite el mensaje del cliente.
    assert QUESTION not in str(draft)


async def test_the_paraphrase_goes_out_with_the_partners_key(
    client: Any, inbox: Inbox, fake_paraphraser: FakeParaphraser
) -> None:
    """Con el proxy obligatorio (staging) el modelo de la paráfrasis solo sale con
    la clave del partner del cliente (fallo el-constructor-no-llega-al-modelo-en-staging)."""
    await _draft(client, inbox, "El aparcamiento está en la calle de atrás.")
    assert fake_paraphraser.partners == [inbox.biz.partner_id]

    rule = await _draft(client, inbox, "No des citas los festivos.", scope="agent")
    assert rule["kind"] == "behavior"


async def test_only_an_answer_of_the_agent_is_corrected(
    client: Any, db_session: AsyncSession, inbox: Inbox, console_world: dict[str, Any]
) -> None:
    question = await client.post(
        inbox.url(inbox.question),
        json={"text": "Otra cosa.", "scope": "business"},
        headers=inbox.headers(),
    )
    assert question.status_code == 422
    assert question.json()["detail"]["code"] == "not_an_agent_reply"
    unknown = await client.post(
        inbox.url(uuid.uuid4()), json={"text": "x", "scope": "business"}, headers=inbox.headers()
    )
    assert unknown.status_code == 404
    elsewhere = await client.post(
        f"{LITE}/inbox/{inbox.other_conversation}/messages/{inbox.answer}/corrections",
        json={"text": "x", "scope": "business"},
        headers=inbox.headers(),
    )
    assert elsewhere.status_code == 404
    # El partner no llega aquí: solo la persona del cliente.
    partner = await client.post(
        inbox.url(), json={"text": "x", "scope": "business"}, headers=inbox.biz.headers()
    )
    assert partner.status_code == 403


async def test_the_same_key_is_the_same_draft(client: Any, inbox: Inbox) -> None:
    first = await client.post(
        inbox.url(),
        json={"text": "El aparcamiento está detrás.", "scope": "business"},
        headers={**inbox.headers(), "Idempotency-Key": "fix-1"},
    )
    again = await client.post(
        inbox.url(),
        json={"text": "El aparcamiento está detrás.", "scope": "business"},
        headers={**inbox.headers(), "Idempotency-Key": "fix-1"},
    )
    assert first.status_code == 201 and again.status_code in (200, 201)
    assert first.json()["id"] == again.json()["id"]


async def test_the_paraphrase_and_the_lesson_are_edited_before_sending(
    client: Any, inbox: Inbox
) -> None:
    """52.4: la persona revisa la paráfrasis y la edita, con ``If-Match``."""
    draft = await _draft(client, inbox, "El aparcamiento está en la calle de atrás.")
    url = f"{LITE}/corrections/{draft['id']}"
    edited = await client.patch(
        url,
        json={"paraphrase": "Un cliente pregunta dónde aparcar."},
        headers={**inbox.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["paraphrase"] == "Un cliente pregunta dónde aparcar."
    assert edited.json()["revision"] == draft["revision"] + 1
    stale = await client.patch(
        url,
        json={"paraphrase": "Otra."},
        headers={**inbox.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert stale.status_code == 412 and stale.json()["detail"]["code"] == "revision_conflict"
    # Cambiar la lección vuelve a decir de qué tipo es.
    rule = await client.patch(
        url,
        json={"lesson": "Nunca prometas aparcamiento gratis."},
        headers={**inbox.headers(), "If-Match": f'"{edited.json()["revision"]}"'},
    )
    assert rule.status_code == 200, rule.text
    assert rule.json()["kind"] == "behavior"
    missing = await client.patch(url, json={"paraphrase": "x"}, headers=inbox.headers())
    assert missing.status_code == 428


# ── un dato ────────────────────────────────────────────────────────────────


async def test_a_fact_of_the_business_applies_at_once_with_history_and_undo(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    """Escenario 1 y 52.6: en la ficha, «Corregido por Valeria desde la Bandeja»."""
    draft = await _draft(client, inbox, "El aparcamiento está en la calle de atrás.")
    sent = await _send(client, inbox, draft)
    assert sent["status"] == "applied" and sent["applied_change_id"]

    tid = inbox.biz.tenant_id
    (faq,) = await _rows(db_session, tid, sa.select(BusinessFaq))
    assert faq.a == "El aparcamiento está en la calle de atrás."
    assert faq.q == draft["paraphrase"]
    (change,) = await _rows(
        db_session, tid, sa.select(BusinessChange).where(BusinessChange.section == "faqs")
    )
    assert (change.kind, change.actor_kind, change.origin) == (
        "correction",
        "client_user",
        "lite_web",
    )
    assert str(change.id) == sent["applied_change_id"]
    (prov,) = await _rows(
        db_session,
        tid,
        sa.select(BusinessFieldProvenance).where(
            BusinessFieldProvenance.pointer == f"/faqs/{faq.id}"
        ),
    )
    assert (prov.source, prov.actor_kind, prov.origin) == (
        "inbox_correction",
        "client_user",
        "lite_web",
    )
    (audit,) = await _rows(
        db_session, tid, sa.select(AuditLog).where(AuditLog.action == "business.correction_applied")
    )
    assert audit.actor.startswith("client:") and audit.after_json is not None
    assert audit.after_json["origin"] == "lite_web"
    # El agente lo sabe desde el siguiente mensaje.
    prompt = await active_prompt(db_session, tid, inbox.config_id)
    assert "calle de atrás" in prompt
    await writes.drain_after_commit()

    undone = await client.post(f"{LITE}/corrections/{draft['id']}/undo", headers=inbox.headers())
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "undone"
    live = await _rows(
        db_session, tid, sa.select(BusinessFaq).where(BusinessFaq.archived_at.is_(None))
    )
    assert live == []
    assert "calle de atrás" not in await active_prompt(db_session, tid, inbox.config_id)


async def test_a_fact_of_one_agent_goes_to_its_own_knowledge(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    phone = await add_client_phone(db_session, membership_id=inbox.person["membership_id"])
    resp = await client.post(
        inbox.url(),
        json={"text": "La entrada para coches está por la calle Luna.", "scope": "agent"},
        headers=phone["headers"](),
    )
    assert resp.status_code == 201, resp.text
    draft = resp.json()
    sent = await client.post(
        f"{LITE}/corrections/{draft['id']}/send",
        headers={**phone["headers"](), "If-Match": f'"{draft["revision"]}"'},
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "applied"

    tid = inbox.biz.tenant_id
    (doc,) = await _rows(db_session, tid, sa.select(KnowledgeDocument))
    assert doc.agent_id == inbox.agent_id, "solo para este agente"
    assert doc.content_text is not None and "calle Luna" in doc.content_text
    (audit,) = await _rows(
        db_session, tid, sa.select(AuditLog).where(AuditLog.action == "knowledge.taught")
    )
    assert audit.after_json is not None and audit.after_json["origin"] == "app"
    assert await _rows(db_session, tid, sa.select(BusinessFaq)) == []

    undone = await client.post(f"{LITE}/corrections/{draft['id']}/undo", headers=phone["headers"]())
    assert undone.status_code == 200, undone.text
    async with tenant_scoped_session(db_session, tid):
        removed = await db_session.get(KnowledgeDocument, doc.id, populate_existing=True)
    assert removed is not None and removed.removed_at is not None


# ── un comportamiento ──────────────────────────────────────────────────────


async def test_a_behavior_reaches_the_partner_as_a_proposal_with_its_test(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    """Escenario 2, 52.2 y 52.3: la lección y la paráfrasis, nunca el mensaje."""
    draft = await _draft(client, inbox, "No des citas los festivos.", scope="agent")
    sent = await _send(client, inbox, draft)
    assert sent["status"] == "proposed"

    tid = inbox.biz.tenant_id
    proposals = await _rows(
        db_session, tid, sa.select(Proposal).where(Proposal.author == "correction")
    )
    # El parche y su prueba juntos, como una sugerencia: las mejoras del agente
    # los deciden igual.
    (patch,) = proposals
    assert patch.kind == "agent_spec_patch" and patch.agent_id == inbox.agent_id
    assert str(patch.id) == sent["proposal_id"]
    assert patch.diff["ops"] == [
        {"op": "add", "path": "/rules/-", "value": "No des citas los festivos."}
    ]
    assert patch.diff["test"]["criteria"][0]["text"] == "No des citas los festivos."
    assert patch.diff["test"]["first_message"]
    assert QUESTION not in str(patch.diff) and "Lucía" not in str(patch.diff)
    # Nada se aplicó al agente ni a la ficha.
    assert await _rows(db_session, tid, sa.select(BusinessFaq)) == []

    (audit,) = await _rows(
        db_session, tid, sa.select(AuditLog).where(AuditLog.action == "correction.proposed")
    )
    assert audit.after_json is not None and audit.after_json["origin"] == "lite_web"

    async with db_session.begin():
        (notice,) = (
            await db_session.scalars(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == inbox.biz.partner_id,
                    ConsoleNotification.kind == "agent.correction.proposed",
                )
            )
        ).all()
    assert notice.payload["agent_id"] == str(inbox.agent_id)
    assert notice.payload["by"] == "Valeria Ríos"
    bell = await client.get("/console/notifications", headers=inbox.biz.headers())
    assert bell.status_code == 200, bell.text

    async with tenant_scoped_session(db_session, tid):
        seen = await corrections.for_partner(db_session, agent_id=inbox.agent_id)
    (item,) = seen
    assert item["lesson"] == "No des citas los festivos."
    assert item["paraphrase"] == draft["paraphrase"]
    for payload in (str(seen), str(notice.payload), bell.text):
        for leaked in (QUESTION, "Lucía", "612 345 678", str(inbox.question), str(inbox.answer)):
            assert leaked not in payload, leaked
    assert "message_id" not in item and "conversation_id" not in item


async def test_the_partner_decides_a_behavior_in_the_agents_improvements(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    """52.3 y 51.4: la corrección de comportamiento aparece en las mejoras del agente
    con su lección, su paráfrasis y su prueba; aceptarla la lleva al borrador detrás
    de la puerta, y descartarla la rechaza con su motivo."""
    first = await _send(
        client, inbox, await _draft(client, inbox, "No des citas los festivos.", scope="agent")
    )
    second = await _send(
        client, inbox, await _draft(client, inbox, "Siempre saluda por el nombre.", scope="agent")
    )
    base = f"/console/clients/{inbox.biz.ref}/agents/{inbox.agent_id}/improvements"
    listed = await client.get(base, headers=inbox.biz.headers())
    assert listed.status_code == 200, listed.text
    corrections_ = {i["lesson"]: i for i in listed.json()["items"] if i["kind"] == "correction"}
    assert set(corrections_) == {"No des citas los festivos.", "Siempre saluda por el nombre."}
    item = corrections_["No des citas los festivos."]
    assert item["origin"] == "lite_web" and item["test"] is not None
    assert item["diff"]["ops"][0]["value"] == "No des citas los festivos."
    for leaked in (QUESTION, "Lucía", str(inbox.question), str(inbox.answer)):
        assert leaked not in listed.text

    accepted = await client.post(f"{base}/{first['id']}/accept", headers=inbox.biz.headers())
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted" and accepted.json()["test_id"]
    again = await client.post(f"{base}/{first['id']}/accept", headers=inbox.biz.headers())
    assert again.status_code == 409, "una vez decidida, cerrada"

    discarded = await client.post(
        f"{base}/{second['id']}/discard", json={"reason": "No aplica"}, headers=inbox.biz.headers()
    )
    assert discarded.status_code == 200, discarded.text
    left = await client.get(base, headers=inbox.biz.headers())
    assert [i for i in left.json()["items"] if i["kind"] == "correction"] == []

    tid = inbox.biz.tenant_id
    rows = await _rows(db_session, tid, sa.select(InboxCorrection))
    assert {r.lesson: r.status for r in rows} == {
        "No des citas los festivos.": "accepted",
        "Siempre saluda por el nombre.": "rejected",
    }
    actions = {
        a.action
        for a in await _rows(
            db_session,
            tid,
            sa.select(AuditLog).where(
                AuditLog.action.in_(["correction.accepted", "correction.rejected"])
            ),
        )
    }
    assert actions == {"correction.accepted", "correction.rejected"}


# ── datos personales ───────────────────────────────────────────────────────


async def test_personal_data_blocks_saving_until_it_is_removed(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    """52.5 y garantía 8: nada con datos de un cliente final llega a la ficha."""
    lesson = (
        "Dile a Lucía Pérez que aparque detrás; su móvil es 612 345 678, "
        "su correo lucia@correo.es y su DNI 12345678Z."
    )
    draft = await _draft(client, inbox, lesson)
    kinds = {(p["field"], p["kind"]) for p in draft["pii"]}
    assert {
        ("lesson", "name"),
        ("lesson", "phone"),
        ("lesson", "email"),
        ("lesson", "document"),
    } <= kinds
    for p in draft["pii"]:
        assert 0 <= p["start"] < p["end"] <= len(lesson)
    # Las posiciones, no los datos: el servidor no los repite.
    assert "612 345 678" not in str(draft["pii"])

    refused = await _send(client, inbox, draft, expect=422)
    assert refused["detail"]["code"] == "pii_present"
    tid = inbox.biz.tenant_id
    assert await _rows(db_session, tid, sa.select(BusinessFaq)) == []
    assert (
        await _rows(
            db_session, tid, sa.select(BusinessChange).where(BusinessChange.section == "faqs")
        )
        == []
    )

    # Una paráfrasis editada con un correo también bloquea.
    clean = await client.patch(
        f"{LITE}/corrections/{draft['id']}",
        json={
            "lesson": "El aparcamiento está detrás del local.",
            "paraphrase": "Un cliente (pepe@correo.es) pregunta dónde aparcar.",
        },
        headers={**inbox.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert clean.status_code == 200, clean.text
    assert {(p["field"], p["kind"]) for p in clean.json()["pii"]} == {("paraphrase", "email")}
    again = await _send(client, inbox, clean.json(), expect=422)
    assert again["detail"]["code"] == "pii_present"

    fixed = await client.patch(
        f"{LITE}/corrections/{draft['id']}",
        json={"paraphrase": "Un cliente pregunta dónde aparcar."},
        headers={**inbox.headers(), "If-Match": f'"{clean.json()["revision"]}"'},
    )
    assert fixed.status_code == 200 and fixed.json()["pii"] == []
    sent = await _send(client, inbox, fixed.json())
    assert sent["status"] == "applied"
