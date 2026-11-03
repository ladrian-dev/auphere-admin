"""Spec 051, R9.4-R9.9: lo que el código registra y lo que Terraform vigila.

Desde la spec 051 estas alertas solo se escriben en el registro, y quien avisa a
una persona es una alarma de CloudWatch. Si los dos lados se separan no falla
nada: la alerta se registra y nadie se entera. Por eso se comprueban aquí, igual
que ``bootstrap.py`` y su contrato de nombres.
"""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

import pytest
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
