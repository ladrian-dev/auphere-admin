"""``scripts/ops/dlq.sh``, contra un ``aws`` de mentira.

Es lo que se teclea en producción, y lo delicado es el JSON de ``--overrides``:
un motivo con espacios y comillas dentro de un JSON dentro de una orden. Aquí se
comprueba que llega entero, que el resultado de la tarea llega como código de
salida, y que no se lanza nada si el entorno no es uno de los dos.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = _ROOT / "scripts" / "ops" / "dlq.sh"

_FAKE_AWS = r"""#!/usr/bin/env bash
python3 -c 'import json, os, sys
with open(os.environ["AWS_CALLS"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")' "$@"
case "$1 $2" in
  "ecs describe-services")
    echo '{"awsvpcConfiguration":{"subnets":["subnet-1"],"securityGroups":["sg-1"],"assignPublicIp":"DISABLED"}}'
    ;;
  "ecs run-task")
    echo "${FAKE_RUN_TASK_OUTPUT-arn:aws:ecs:eu-south-2:1:task/nexus-prod/abc123}"
    ;;
  "ecs describe-tasks")
    echo "${FAKE_EXIT_CODE-0}"
    ;;
  "logs filter-log-events")
    echo '{"event": "ops.dlq.summary", "total": 25}'
    ;;
esac
"""


def _run(tmp_path: Path, *args: str, **env: str) -> tuple[subprocess.CompletedProcess[str], list]:
    fake = tmp_path / "bin" / "aws"
    fake.parent.mkdir(exist_ok=True)
    fake.write_text(_FAKE_AWS, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls.jsonl"
    calls.write_text("", encoding="utf-8")
    done = subprocess.run(
        ["bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
            "AWS_CALLS": str(calls),
            "DLQ_LOG_DELAY_S": "0",
            **env,
        },
    )
    made = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    return done, made


def _call(calls: list[list[str]], *prefix: str) -> list[str]:
    return next(c for c in calls if c[: len(prefix)] == list(prefix))


def _flag(call: list[str], name: str) -> str:
    return call[call.index(name) + 1]


def test_it_runs_the_scheduler_task_with_the_module_as_its_command(tmp_path: Path) -> None:
    done, calls = _run(tmp_path, "prod", "list", "--older-than", "30d")

    assert done.returncode == 0, done.stderr
    run_task = _call(calls, "ecs", "run-task")
    assert _flag(run_task, "--cluster") == "nexus-prod"
    assert _flag(run_task, "--task-definition") == "nexus-prod-scheduler"
    assert _flag(run_task, "--launch-type") == "FARGATE"
    assert _flag(run_task, "--region") == "eu-south-2"
    assert _flag(run_task, "--profile") == "nexus"
    overrides = json.loads(_flag(run_task, "--overrides"))
    assert overrides == {
        "containerOverrides": [
            {
                "name": "scheduler",
                "command": ["python", "-m", "nexus_worker.ops.dlq", "list", "--older-than", "30d"],
            }
        ]
    }
    network = json.loads(_flag(run_task, "--network-configuration"))
    assert network["awsvpcConfiguration"]["securityGroups"] == ["sg-1"]
    services = _call(calls, "ecs", "describe-services")
    assert _flag(services, "--services") == "nexus-prod-scheduler"


def test_a_reason_with_spaces_and_quotes_arrives_whole(tmp_path: Path) -> None:
    reason = 'rotación de Aurora, "26 de agosto" $HOME'
    done, calls = _run(
        tmp_path, "staging", "discard", "--older-than", "2d", "--yes", "--reason", reason
    )

    assert done.returncode == 0, done.stderr
    run_task = _call(calls, "ecs", "run-task")
    command = json.loads(_flag(run_task, "--overrides"))["containerOverrides"][0]["command"]
    assert command[-2:] == ["--reason", reason]
    assert _flag(run_task, "--cluster") == "nexus-staging"


def test_it_shows_the_log_lines_of_that_task(tmp_path: Path) -> None:
    done, calls = _run(tmp_path, "prod", "list")

    assert '"ops.dlq.summary"' in done.stdout
    logs = _call(calls, "logs", "filter-log-events")
    assert _flag(logs, "--log-group-name") == "/nexus/prod/scheduler"
    assert _flag(logs, "--log-stream-names") == "scheduler/scheduler/abc123"


def test_the_exit_code_of_the_task_is_the_exit_code_of_the_script(tmp_path: Path) -> None:
    done, _calls = _run(tmp_path, "prod", "reinject", "--all", FAKE_EXIT_CODE="3")
    assert done.returncode == 3


def test_a_task_that_never_ran_is_a_failure(tmp_path: Path) -> None:
    done, calls = _run(tmp_path, "prod", "list", FAKE_RUN_TASK_OUTPUT="None")
    assert done.returncode != 0
    assert not [c for c in calls if c[:2] == ["ecs", "wait"]]


def test_a_task_without_an_exit_code_is_a_failure(tmp_path: Path) -> None:
    done, _calls = _run(tmp_path, "prod", "list", FAKE_EXIT_CODE="None")
    assert done.returncode != 0


@pytest.mark.parametrize("args", [[], ["prod"], ["production", "list"], ["dev", "list"]])
def test_it_launches_nothing_without_a_known_environment(tmp_path: Path, args: list[str]) -> None:
    done, calls = _run(tmp_path, *args)
    assert done.returncode == 2
    assert calls == []


def test_the_profile_can_be_another(tmp_path: Path) -> None:
    _done, calls = _run(tmp_path, "prod", "list", AWS_PROFILE="otra")
    assert _flag(_call(calls, "ecs", "run-task"), "--profile") == "otra"
