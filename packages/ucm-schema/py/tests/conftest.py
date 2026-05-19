import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture(scope="session")
def valid_fixtures() -> dict:
    return json.loads((FIXTURES_DIR / "valid.json").read_text())


@pytest.fixture(scope="session")
def invalid_fixtures() -> dict:
    return json.loads((FIXTURES_DIR / "invalid.json").read_text())
