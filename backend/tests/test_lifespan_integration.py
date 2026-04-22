"""Full-app lifespan boot test.

Exercises the real FastAPI `lifespan` — bootstrap → engine → catch-up
rollover → scheduler start/stop — then hits `/api/info` and asserts the
timezone + bootstrap fields.

The scheduler is disabled via env var during this test so we don't leak
APScheduler threads into pytest's event loop; the scheduler factory itself
has its own unit tests in test_scheduler.py.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from family_chores.app import create_app
from family_chores.config import Options


@pytest.fixture
def skip_scheduler(monkeypatch):
    monkeypatch.setenv("FAMILY_CHORES_SKIP_SCHEDULER", "1")


def test_full_lifespan_boots_and_reports_bootstrap(tmp_path, skip_scheduler):
    opts = Options(
        log_level="info",
        week_starts_on="monday",
        sound_default=False,
        timezone_override="UTC",
        data_dir=tmp_path,
    )
    app = create_app(options=opts)

    with TestClient(app) as client:
        info = client.get("/api/info").json()
        assert info["timezone"] == "UTC"
        assert info["bootstrap"] is not None
        # Fresh install → initialized, no banner.
        assert info["bootstrap"]["action"] == "initialized"
        assert info["bootstrap"]["banner"] is None

        # Reboot against same tmp_path → migrated, backup taken.
    assert (tmp_path / "family_chores.db").exists()

    app2 = create_app(options=opts)
    with TestClient(app2) as client:
        info = client.get("/api/info").json()
        assert info["bootstrap"]["action"] == "migrated"

    assert (tmp_path / "family_chores.db.bak").exists()


def test_lifespan_falls_back_to_utc_for_missing_tz(tmp_path, skip_scheduler):
    opts = Options(
        log_level="info",
        week_starts_on="monday",
        sound_default=False,
        timezone_override=None,
        data_dir=tmp_path,
    )
    app = create_app(options=opts)
    with TestClient(app) as client:
        assert client.get("/api/info").json()["timezone"] == "UTC"
