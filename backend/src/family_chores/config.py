"""Add-on runtime configuration loader.

Reads `/data/options.json` produced by Supervisor from the add-on's `options`
block in `config.yaml`. Falls back to schema defaults so the backend still
boots during local development when `/data/options.json` is absent.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("FAMILY_CHORES_DATA_DIR", "/data"))
OPTIONS_PATH = DATA_DIR / "options.json"

LOG_LEVELS = {"debug", "info", "warning", "error"}
WEEK_STARTS = {"monday", "sunday"}


@dataclass(frozen=True, slots=True)
class Options:
    log_level: str = "info"
    week_starts_on: str = "monday"
    sound_default: bool = False
    data_dir: Path = DATA_DIR


def _coerce_log_level(value: Any) -> str:
    level = str(value).lower().strip() if value is not None else "info"
    return level if level in LOG_LEVELS else "info"


def _coerce_week_start(value: Any) -> str:
    start = str(value).lower().strip() if value is not None else "monday"
    return start if start in WEEK_STARTS else "monday"


def load_options(path: Path | None = None) -> Options:
    """Load options from `/data/options.json`, returning defaults on any issue."""
    target = path if path is not None else OPTIONS_PATH
    if not target.exists():
        return Options()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Options()
    if not isinstance(raw, dict):
        return Options()
    return Options(
        log_level=_coerce_log_level(raw.get("log_level")),
        week_starts_on=_coerce_week_start(raw.get("week_starts_on")),
        sound_default=bool(raw.get("sound_default", False)),
        data_dir=DATA_DIR,
    )
