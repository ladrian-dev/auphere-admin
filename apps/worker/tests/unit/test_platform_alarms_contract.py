"""Spec 051, R9.4-R9.9: lo que el código registra y lo que Terraform vigila.

Desde la spec 051 estas alertas solo se escriben en el registro, y quien avisa a
una persona es una alarma de CloudWatch. Si los dos lados se separan no falla
nada: la alerta se registra y nadie se entera. Por eso se comprueban aquí, igual
que ``bootstrap.py`` y su contrato de nombres.
"""

from __future__ import annotations

import ast
import re
import time
from datetime import date
from pathlib import Path

import pytest
from fakeredis import aioredis as fakeaioredis
from structlog.testing import capture_logs

from nexus_worker.streams import meta_reconciliation_cron as reconciliation
from nexus_worker.streams import platform_watcher as watcher

_ROOT = Path(__file__).resolve().parents[4]
_ALARMS = _ROOT / "infra" / "terraform" / "30-observability" / "alarms.tf"


def _terraform() -> str:
    return _ALARMS.read_text(encoding="utf-8")


def _block(header: str) -> str:
    """El bloque de HCL que abre ``header``, hasta su llave de cierre."""
    source = _terraform()
    start = source.index(header)
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"bloque sin cerrar: {header}")


def _local_number(name: str) -> int:
    match = re.search(rf"^\s*{name}\s*=\s*(\d+)\s*$", _terraform(), re.MULTILINE)
    assert match, f"falta el local {name} en {_ALARMS.name}"
    return int(match.group(1))


def _kinds_in_code() -> set[str]:
    tree = ast.parse(Path(watcher.__file__).read_text(encoding="utf-8"))
    kinds: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Alert"):
            continue
        kind = next(k.value for k in node.keywords if k.arg == "kind")
        assert isinstance(kind, ast.Constant), "un kind tiene que ser un literal: su alarma lo cita"
        kinds.add(str(kind.value))
    return kinds


def _kinds_in_terraform() -> set[str]:
    return set(re.findall(r"^\s*(\w+)\s*=\s*\"", _block("platform_alert_kinds = {"), re.MULTILINE))


def test_code_really_raises_kinds() -> None:
    assert "dlq_entries" in _kinds_in_code(), "el barrido del código no está leyendo nada"


def test_every_kind_has_its_alarm_and_every_alarm_its_kind() -> None:
    """R9.7. Un tipo sin alarma se registra y no avisa a nadie."""
    assert _kinds_in_code() == _kinds_in_terraform()


@pytest.mark.asyncio
async def test_the_filter_looks_for_what_the_watcher_logs() -> None:
    """R9.4. Si cambia el nombre del evento, el filtro deja de contar sin decir nada."""
    alert = watcher.Alert(kind="dlq_entries", dedup_key="k", subject="s", detail="d")
    with capture_logs() as logs:
        await watcher._notify(alert)

    [entry] = [e for e in logs if e["log_level"] == "error"]
    assert entry["kind"] == "dlq_entries", "la dimensión de la métrica sale de este campo"
    filter_block = _block('resource "aws_cloudwatch_log_metric_filter" "platform_alert"')
    assert f'$.event = \\"{entry["event"]}\\"' in filter_block
    assert '"$.kind"' in filter_block


@pytest.mark.asyncio
async def test_the_filter_looks_for_what_the_reconciliation_logs() -> None:
    """R9.6."""
    with capture_logs() as logs:
        await reconciliation._alert(reconciliation.ReconciliationReport(day=date(2026, 11, 3)))

    [entry] = logs
    assert entry["log_level"] == "error"
    filter_block = _block('resource "aws_cloudwatch_log_metric_filter" "meta_reconciliation"')
    assert f'$.event = \\"{entry["event"]}\\"' in filter_block


def test_a_condition_that_persists_does_not_alert_every_hour() -> None:
    """R9.5. El vigilante repite cada hora; la alarma tiene que seguir en ALARM
    entre dos repeticiones, aunque se pierda una."""
    window = _local_number("alert_period_seconds") * _local_number("alert_evaluation_periods")
    assert window > 2 * watcher.DEDUP_TTL_S
    assert _local_number("alert_period_seconds") <= 300, "R9.4: avisar en minutos, no en una hora"


def _alarm_transitions(log_times: list[float]) -> int:
    """Cuántas veces pasaría la alarma de OK a ALARM con estos registros: un
    registro la enciende, y vuelve a OK tras una ventana entera sin ninguno."""
    window = _local_number("alert_period_seconds") * _local_number("alert_evaluation_periods")
    transitions, last = 0, None
    for at in log_times:
        if last is None or at - last > window:
            transitions += 1
        last = at
    return transitions


@pytest.mark.asyncio
async def test_a_new_dead_message_fires_the_alarm_with_old_ones_inside(monkeypatch) -> None:
    """El defecto, de punta a punta. Con la DLQ llena de agosto la alarma se quedaba
    en ALARM para siempre, y un mensaje que moría hoy no producía ninguna transición."""
    logged: list[float] = []
    clock = {"now": time.time()}

    async def notify(alert: watcher.Alert) -> None:
        if alert.kind == "dlq_entries":
            logged.append(clock["now"])

    monkeypatch.setattr(watcher, "_notify", notify)
    redis = fakeaioredis.FakeRedis()
    start = clock["now"]
    await redis.xadd(watcher.DLQ_STREAM, {"dlq_error": "viejo"}, id=f"{int(start * 1000) - 1}-0")

    # Un día de vigilante. El dedupe real caduca a la hora: aquí se borra a mano.
    for hour in range(24):
        clock["now"] = start + hour * 3600
        for key in await redis.keys("nexus:alert:sent:dlq:*"):
            await redis.delete(key)
        await watcher.process_tick(redis, now=clock["now"])
    assert _alarm_transitions(logged) == 1, "la entrada vieja avisa una vez"

    clock["now"] += 3600
    await redis.xadd(watcher.DLQ_STREAM, {"dlq_error": "nuevo"}, id=f"{int(clock['now'] * 1000)}-0")
    await watcher.process_tick(redis, now=clock["now"])

    assert _alarm_transitions(logged) == 2, "el mensaje nuevo avisa, con la vieja dentro"


def _alarm_description(kind: str, workspace: str) -> str:
    match = re.search(
        rf'^\s*{kind}\s*=\s*"(.*)"\s*$', _block("platform_alert_kinds = {"), re.MULTILINE
    )
    assert match, kind
    template = re.search(
        r'alarm_description\s*=\s*"(.*)"',
        _block('resource "aws_cloudwatch_metric_alarm" "platform_alert"'),
    )
    assert template
    return (
        template.group(1)
        .replace("${each.value}", match.group(1))
        .replace("${each.key}", kind)
        .replace("${local.scheduler_log_group}", f"/nexus/{workspace}/scheduler")
        .replace("${terraform.workspace}", workspace)
    )


def test_the_dlq_alarm_says_what_to_do() -> None:
    """Lo que llega al correo es esta descripción, no el detalle del registro."""
    description = _alarm_description("dlq_entries", "prod")
    assert "./scripts/ops/dlq.sh prod list" in description
    assert "docs/dlq.md" in description
    assert "no avisa si crece" not in description


def test_what_the_alarm_points_at_exists() -> None:
    assert (_ROOT / "docs" / "dlq.md").is_file()
    assert (_ROOT / "scripts" / "ops" / "dlq.sh").is_file()
    runbook = (_ROOT / "docs" / "dlq.md").read_text(encoding="utf-8")
    for command in ("list", "discard", "reinject"):
        assert f"./scripts/ops/dlq.sh prod {command}" in runbook
        assert f"./scripts/ops/dlq.sh staging {command}" in runbook


@pytest.mark.parametrize("kind", sorted(_kinds_in_code()))
def test_every_description_fits_in_cloudwatch(kind: str) -> None:
    """CloudWatch rechaza una descripción de más de 1024 caracteres, y el ``apply``
    fallaría en producción, no aquí."""
    assert len(_alarm_description(kind, "staging")) <= 1024


@pytest.mark.parametrize("name", ["platform_alert", "meta_reconciliation"])
def test_no_metric_carries_a_tenant(name: str) -> None:
    """R9.8. El detalle de cada negocio se queda en el registro."""
    block = _block(f'resource "aws_cloudwatch_log_metric_filter" "{name}"')
    assert "tenant" not in block
    dimensions = re.search(r"dimensions\s*=\s*\{([^}]*)\}", block)
    assert dimensions is None or re.findall(r"(\w+)\s*=", dimensions.group(1)) == ["kind"]


@pytest.mark.parametrize("name", ["platform_alert", "meta_reconciliation"])
def test_alarms_notify_only_in_production(name: str) -> None:
    """R9.9. Staging aparca sus servicios y da un ``worker_dead`` cada mañana."""
    assert 'alert_actions_enabled = terraform.workspace == "prod"' in _terraform()
    block = _block(f'resource "aws_cloudwatch_metric_alarm" "{name}"')
    assert re.search(r"actions_enabled\s*=\s*local\.alert_actions_enabled", block)
    assert re.search(r"alarm_actions\s*=\s*local\.alarm_actions", block)
