"""Lo común de las pruebas del constructor (spec 047, fases 8 a 11).

- :class:`FakeBuilder`: el modelo de la tarea ``build``, de mentira. Anota sus
  tokens por el mismo punto de paso que el proveedor de verdad, así que el
  medidor los ve en la partida «Construcción y pruebas».
- :func:`run_jobs`: corre los trabajos en cola con los manejadores de verdad del
  worker (``agent_draft``), con el modelo que se le dé.
- :func:`start_draft`: «Generar borrador» desde la consola.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Job


@dataclass
class FakeBuilder:
    reply: dict[str, Any] | str = field(default_factory=dict)
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    model: str = "anthropic/claude-sonnet-5-5"
    fail: bool = False

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        from nexus_worker.metering.collector import record_llm_usage

        self.calls.append(messages)
        if self.fail:
            raise TimeoutError("the provider did not answer")
        record_llm_usage(
            model=self.model,
            provider="anthropic",
            usage={"prompt_tokens": 3000, "completion_tokens": 1500},
            task="build",
        )
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)

    @property
    def prompt(self) -> str:
        assert self.calls, "the builder was never called"
        return "\n".join(m["content"] for m in self.calls[-1])


#: Lo que contesta el modelo para «Recepción» de una barbería.
RECEPTION: dict[str, Any] = {
    "voice": {"tone": "Cercano", "languages": ["es"], "register": "tu", "greeting": "¡Hola!"},
    "goal": "Que cada cliente salga con su cita.",
    "instructions": [{"title": "Cómo atiendes", "body": "Pregunta el servicio y el día."}],
    "procedures": [
        {
            "id": "reservar",
            "title": "Reservar",
            "when": "Cuando piden cita",
            "steps": "Busca hueco y reserva.",
            "tools": ["reservas.find_slots", "reservas.create"],
        }
    ],
    "tools": ["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"],
    "skills": [{"key": "booking", "enabled": True, "integration": None}],
    "connection_requests": [],
    "escalation": {"triggers": ["asks_for_human", "complaint"], "failed_attempts": 2},
    "rules": ["No ofrezcas descuentos."],
    "faqs": [{"q": "¿Hay aparcamiento?", "a": "Sí, detrás del local."}],
    "questions": [
        {
            "id": "cancelacion",
            "text": "¿Con cuánto tiempo hay que avisar para cancelar?",
            "why": "El agente lo dice al confirmar cada cita.",
            "options": ["24 horas", "2 horas"],
            "scope": "business",
            "target": "/policies/cancellation",
        },
        {
            "id": "trato",
            "text": "¿De tú o de usted?",
            "why": "Cambia todas las respuestas.",
            "options": ["tu", "usted"],
            "scope": "agent",
            "target": "/voice/register",
        },
    ],
    "discarded": {"count": 1, "reasons": ["El horario ya estaba en la ficha."]},
    "tests": [
        {
            "name": f"Prueba {n}",
            "persona": "Cliente",
            "first_message": f"Hola {n}",
            "plan": "Pide cita.",
            "expected_state": {"booking": {"created": True}} if n == 1 else {},
            "criteria": [{"key": "ok", "text": "Responde bien."}],
            "critical": n == 1,
        }
        for n in range(1, 10)
    ],
}


async def run_jobs(
    fake_redis: Any,
    builder: FakeBuilder | None,
    *,
    judge: Any | None = None,
    router: Any | None = None,
) -> int:
    """Corre los trabajos en cola con los manejadores de verdad. ``builder=None``
    es el generador sin modelo (local); ``judge`` y ``router`` son los del
    trabajo ``tests`` (sin ``router``, el que haya puesto la prueba)."""
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.agent_draft import make_agent_draft_handler
    from nexus_worker.jobs.handlers.agent_publish import make_publish_handler
    from nexus_worker.jobs.handlers.agent_tests import make_agent_tests_handler
    from nexus_worker.simulation.runner import default_router

    registry = JobRegistry()
    registry.register(
        "agent_draft",
        make_agent_draft_handler(complete_factory=lambda _tenant: builder),
        timeout_s=60,
    )
    registry.register(
        "tests",
        make_agent_tests_handler(
            judge_factory=lambda _tenant: judge,
            router_factory=(lambda: router) if router is not None else default_router,
        ),
        timeout_s=120,
    )
    registry.register(
        "publish",
        make_publish_handler(
            judge_factory=lambda _tenant: judge,
            router_factory=(lambda: router) if router is not None else default_router,
        ),
        timeout_s=120,
    )
    return await drain_once(fake_redis, registry=registry, store=DbJobStore())


async def start_draft(client: Any, url: str, headers: dict[str, str], **body: Any) -> Any:
    payload = {"name": "Recepción", "description": "Atiende las citas de la barbería por WhatsApp."}
    payload.update(body)
    return await client.post(f"{url}/agents/draft-jobs", json=payload, headers=headers)


async def job_row(db_session: AsyncSession, tenant_id: uuid.UUID, job_id: str | uuid.UUID) -> Job:
    async with tenant_scoped_session(db_session, tenant_id):
        job = await db_session.scalar(
            sa.select(Job)
            .where(Job.id == uuid.UUID(str(job_id)))
            .execution_options(populate_existing=True)
        )
    assert job is not None
    return job


__all__ = ["RECEPTION", "FakeBuilder", "job_row", "run_jobs", "start_draft"]
