import datetime as dt
from dataclasses import replace
from pathlib import Path

import pytest

from morgenzeitung.cli import _demo_raw
from morgenzeitung.config import DEFAULT_EVENT_EXCLUDE, load_config
from morgenzeitung.digest import build_digest

WED = dt.date(2026, 11, 18)


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch):
    """Konfiguration ohne echte .env und ohne Netz-Zugangsdaten."""
    for key in ("DASHBOARD_EMAIL", "IMAP_PASSWORD", "OPENAI_API_KEY", "COMIC_STYLE"):
        monkeypatch.delenv(key, raising=False)
    c = load_config(env_file=str(tmp_path / "gibt-es-nicht.env"))
    return replace(c, data_dir=tmp_path / "data", out_dir=tmp_path / "out", profile="test")


@pytest.fixture
def demo_digest():
    def make(day: dt.date = WED, issued: dt.date | None = None):
        return build_digest(_demo_raw(day), day, "Alex", DEFAULT_EVENT_EXCLUDE, [], issued)
    return make
