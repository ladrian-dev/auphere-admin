"""Los perfiles del router, versión 1 — spec 047, T139/T140 (ola 6).

``router_profiles`` nació vacía en la 0180. Aquí entra la v1 de los cinco
perfiles con las cifras de ``contracts/router-and-catalog.md`` §3, que son **el
punto de partida que el admin ajusta** desde su editor (T150):

- ``auto``, ``economy``, ``balanced`` y ``max``: las tareas de un agente
  (clasificar, responder, el turno con herramientas, escalar, ver, transcribir y
  juzgar). «Económico» no escala: pasa a una persona.
- ``platform``: las que no dependen del perfil del agente (construir, leer webs,
  extraer, resumir, traducir, embeddings, reordenar y moderar).

``reserve`` es el despliegue de reserva de cada tarea, para cuando no hay ninguno
certificado (requisito 40.7). Son filas que ya están en el catálogo. Ojo: la
reserva también pasa el filtro duro (residencia y retención cero), y hoy ninguna
fila tiene la retención cero comprobada (research D44).

Revision ID: 0182_router_profiles_v1
Revises: 0181_clients_active
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0182_router_profiles_v1"
down_revision: str | Sequence[str] | None = "0181_clients_active"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HAIKU = "anthropic/claude-haiku-4-5"
SONNET = "anthropic/claude-sonnet-4-6"
LUNA = "openai/gpt-5.6-luna"
VISION = "openai/gpt-4o"
WHISPER = "openai/whisper-1"


def _task(
    min_quality: float,
    max_cost: int,
    *,
    reserve: str | None,
    escalate_to: str | None = None,
    reasoning: str = "none",
    judge_sampling: str | float | None = None,
) -> dict[str, Any]:
    return {
        "min_quality": min_quality,
        "max_cost_per_call_micros": max_cost,
        "escalate_to": escalate_to,
        "reasoning": reasoning,
        "judge_sampling": judge_sampling,
        "reserve": reserve,
    }


_LATENCY = {"classify": 800, "tool_turn": 6000, "answer": 4000}

PROFILES: dict[str, dict[str, Any]] = {
    "auto": {
        "tasks": {
            "classify": _task(0.90, 200, reserve=LUNA),
            "answer": _task(
                0.92, 3000, reserve=HAIKU, escalate_to="medium", judge_sampling="by_risk"
            ),
            "tool_turn": _task(
                0.92,
                4000,
                reserve=HAIKU,
                escalate_to="medium",
                reasoning="low",
                judge_sampling="by_risk",
            ),
            "escalate": _task(0.95, 60000, reserve=SONNET, reasoning="medium"),
            "vision": _task(0.90, 4000, reserve=VISION),
            "transcribe": _task(0.90, 2000, reserve=WHISPER),
            "judge": _task(0.90, 2000, reserve=LUNA, judge_sampling="by_risk"),
        },
        "turn_cost_ceiling_micros": 80000,
        "max_calls_per_turn": 12,
        "max_escalations_per_hour": 3,
        "latency_p95_ms": _LATENCY,
    },
    "economy": {
        "tasks": {
            "classify": _task(0.88, 150, reserve=LUNA),
            # No escalate_to: «Económico» hands the conversation to a person.
            "answer": _task(0.90, 1500, reserve=HAIKU),
            "tool_turn": _task(0.90, 2000, reserve=HAIKU, reasoning="low"),
            "vision": _task(0.85, 1500, reserve=VISION),
            "transcribe": _task(0.90, 2000, reserve=WHISPER),
            "judge": _task(0.88, 1000, reserve=LUNA, judge_sampling=0.1),
        },
        "turn_cost_ceiling_micros": 30000,
        "max_calls_per_turn": 12,
        "max_escalations_per_hour": 0,
        "latency_p95_ms": _LATENCY,
    },
    "balanced": {
        "tasks": {
            "classify": _task(0.90, 200, reserve=LUNA),
            "answer": _task(0.93, 5000, reserve=HAIKU, escalate_to="top", reasoning="medium"),
            "tool_turn": _task(0.93, 6000, reserve=HAIKU, escalate_to="top", reasoning="medium"),
            "escalate": _task(0.95, 60000, reserve=SONNET, reasoning="medium"),
            "vision": _task(0.90, 4000, reserve=VISION),
            "transcribe": _task(0.90, 2000, reserve=WHISPER),
            "judge": _task(0.90, 2000, reserve=LUNA, judge_sampling=1.0),
        },
        "turn_cost_ceiling_micros": 100000,
        "max_calls_per_turn": 12,
        "max_escalations_per_hour": 3,
        "latency_p95_ms": _LATENCY,
    },
    "max": {
        "tasks": {
            "classify": _task(0.92, 1000, reserve=HAIKU),
            "answer": _task(0.95, 50000, reserve=SONNET, reasoning="medium"),
            "tool_turn": _task(0.95, 50000, reserve=SONNET, reasoning="medium"),
            "escalate": _task(0.97, 150000, reserve=SONNET, reasoning="high"),
            "vision": _task(0.93, 20000, reserve=VISION),
            "transcribe": _task(0.90, 2000, reserve=WHISPER),
            "judge": _task(0.92, 4000, reserve=LUNA, judge_sampling=1.0),
        },
        "turn_cost_ceiling_micros": 300000,
        "max_calls_per_turn": 12,
        "max_escalations_per_hour": 3,
        "latency_p95_ms": _LATENCY,
    },
    "platform": {
        "tasks": {
            "build": _task(0.93, 60000, reserve=SONNET, reasoning="medium"),
            "read_source": _task(0.90, 20000, reserve=HAIKU),
            "extract": _task(0.92, 2000, reserve=HAIKU),
            "summarize": _task(0.90, 3000, reserve=HAIKU),
            "translate": _task(0.90, 2000, reserve=HAIKU),
            "embed": _task(0.90, 200, reserve=None),
            "rerank": _task(0.90, 200, reserve=None),
            "moderate": _task(0.90, 200, reserve=None),
        },
        "turn_cost_ceiling_micros": None,
        "max_calls_per_turn": 12,
        "max_escalations_per_hour": 0,
    },
}

REASON = "v1 del contrato (router-and-catalog.md §3): el punto de partida que el admin ajusta."


def upgrade() -> None:
    conn = op.get_bind()
    for profile, policy in PROFILES.items():
        conn.execute(
            sa.text(
                "INSERT INTO router_profiles (profile, version, policy, published_by, reason) "
                "VALUES (:p, 1, CAST(:policy AS jsonb), 'migration:0182', :r) "
                "ON CONFLICT (profile, version) DO NOTHING"
            ),
            {"p": profile, "policy": json.dumps(policy), "r": REASON},
        )


def downgrade() -> None:
    op.execute("DELETE FROM router_profiles WHERE version = 1 AND published_by = 'migration:0182'")
