"""Shared test helpers: fixture loading."""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Return the parsed JSON fixture stored at tests/fixtures/<name>."""
    return json.loads((FIXTURES / name).read_text())
