"""Root pytest configuration and shared test plugins."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = [
    "tests.fixtures.m9.build_fixtures",
]


def pytest_configure(config: pytest.Config) -> None:
    if not config.option.basetemp:
        tmp_dir = Path(__file__).resolve().parent.parent / ".pytest_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(tmp_dir)
