"""Add-on runtime configuration loader.

Reads `/data/options.json` produced by Supervisor from the add-on's `options`
block in `config.yaml`. Falls back to schema defaults so the backend still
boots during local development when `/data/options.json` is absent.

`data_dir` is resolved per-call from `FAMILY_CHORES_DATA_DIR` (not cached at
import time) so test fixtures can point it elsewhere without reloading the
module.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})
WEEK_STARTS = frozenset({"monday", "sunday"})

DB_FILENAME = "family_chores.db"
BAK_FILENAME = "family_chores.db.bak"
OPTIONS_FILENAME = "options.json"


def _resolve_data_dir() -> Path:
    return Path(os.environ.get("FAMILY_CHORES_DATA_DIR", "/data"))


@dataclass(frozen=True, slots=True)
class Options:
    log_level: str = "info"
    week_starts_on: str = "monday"
    sound_default: bool = False
    data_dir: Path = field(default_factory=_resolve_data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def db_backup_path(self) -> Path:
        return self.data_dir / BAK_FILENAME

    @property
    def options_path(self) -> Path:
        return self.data_dir / OPTIONS_FILENAME


def _coerce_log_level(value: Any) -> str:
    level = str(value).lower().strip() if value is not None else "info"
    return level if level in LOG_LEVELS else "info"


def _coerce_week_start(value: Any) -> str:
    start = str(value).lower().strip() if value is not None else "monday"
    return start if start in WEEK_STARTS else "monday"


def load_options(path: Path | None = None) -> Options:
    """Load options from `/data/options.json`, returning defaults on any issue."""
    data_dir = _resolve_data_dir()
    target = path if path is not None else data_dir / OPTIONS_FILENAME

    if not target.exists():
        return Options(data_dir=data_dir)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Options(data_dir=data_dir)
    if not isinstance(raw, dict):
        return Options(data_dir=data_dir)

    return Options(
        log_level=_coerce_log_level(raw.get("log_level")),
        week_starts_on=_coerce_week_start(raw.get("week_starts_on")),
        sound_default=bool(raw.get("sound_default", False)),
        data_dir=data_dir,
    )
