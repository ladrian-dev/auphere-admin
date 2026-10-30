"""Spec 048 (CE-001): AgendaPro no está en el código de los servicios.

Barre lo que se despliega —el código de la API, el worker y el MCP, sus
plantillas, semillas y skills, la imagen del worker y los secretos de
Terraform— y falla si vuelve a aparecer. Las migraciones históricas (y la que lo
borra) se quedan fuera: son el registro de lo que hubo. La consola y el panel
tienen su propio barrido (``no-agendapro.test.ts``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
_SWEPT = (
    _ROOT / "apps" / "api" / "src",
    _ROOT / "apps" / "api" / "scripts",
    _ROOT / "apps" / "worker" / "src",
    _ROOT / "apps" / "worker" / "skills",
    _ROOT / "apps" / "mcp" / "src",
)
_FILES = (
    _ROOT / "apps" / "worker" / "Dockerfile",
    _ROOT / "apps" / "api" / "RUNBOOK.md",
    _ROOT / "apps" / "mcp" / "README.md",
    _ROOT / "infra" / "terraform" / "20-services" / "variables.tf",
)
_WORDS = ("agendapro", "browserbase", "stagehand")


def _texts() -> list[Path]:
    out = [p for p in _FILES if p.is_file()]
    for root in _SWEPT:
        out.extend(
            p
            for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    return out


def test_nothing_deployed_names_agendapro() -> None:
    found = []
    for path in _texts():
        try:
            text = path.read_text(encoding="utf-8").lower()
        except UnicodeDecodeError:
            continue
        found.extend(f"{path.relative_to(_ROOT)}: {w}" for w in _WORDS if w in text)
    assert found == []


@pytest.mark.parametrize(
    "gone",
    [
        "apps/mcp/servers/agendapro_public_mcp",
        "apps/mcp/src/nexus_mcp/servers/agendapro_public",
        "apps/mcp/src/nexus_mcp/transports",
        "apps/mcp/src/nexus_mcp/subprocess_tool.py",
        "apps/worker/src/nexus_worker/streams/async_booking_cron.py",
        "apps/worker/src/nexus_worker/streams/no_show_scrape_cron.py",
        "apps/api/src/nexus_api/services/connectors/seeds/agendapro.yaml",
    ],
)
def test_the_pieces_are_gone(gone: str) -> None:
    assert not (_ROOT / gone).exists()
