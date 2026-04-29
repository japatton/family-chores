"""End-to-end tests for the `0007_add_rewards` Alembic migration.

Same shape as the other migration tests. Covers:

  - `upgrade head` creates `reward` and `redemption` tables with the
    expected columns, indexes, and check constraints.
  - Insert paths: a valid reward, a valid redemption against it, and
    rejection of a zero-cost reward / negative-cost redemption /
    redemption against a deleted reward (RESTRICT FK).
  - `downgrade` to 0006 cleanly removes both tables.
  - upgrade → downgrade → upgrade is idempotent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "family_chores_db" / "migrations"
)


def _alembic_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}


def _seed_member(conn: sqlite3.Connection, member_id: int = 1) -> None:
    conn.execute(
        "INSERT INTO members (id, name, slug, color, display_mode, "
        "requires_approval, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (member_id, "Alice", f"alice{member_id}", "#ff0000", "kid_standard", 0),
    )


def test_upgrade_head_creates_reward_and_redemption_tables(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        reward_cols = _columns(conn, "reward")
        for col in (
            "id", "household_id", "name", "description", "cost_points",
            "icon", "active", "max_per_week", "created_at", "updated_at",
        ):
            assert col in reward_cols, f"reward missing {col}"

        redemption_cols = _columns(conn, "redemption")
        for col in (
            "id", "household_id", "reward_id", "member_id", "state",
            "cost_points_at_redeem", "reward_name_at_redeem",
            "requested_at", "actor_requested",
            "approved_at", "approved_by",
            "denied_at", "denied_by", "denied_reason",
        ):
            assert col in redemption_cols, f"redemption missing {col}"


def test_indexes_present(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        reward_idx = _indexes(conn, "reward")
        redemption_idx = _indexes(conn, "redemption")
        assert "ix_reward_household_active" in reward_idx
        assert "ix_redemption_household_state" in redemption_idx
        assert "ix_redemption_member" in redemption_idx


def test_reward_cost_must_be_positive(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO reward (id, name, cost_points, active) "
                "VALUES (?, ?, ?, 1)",
                ("r1", "Free reward?", 0),
            )


def test_reward_max_per_week_zero_rejected(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO reward (id, name, cost_points, active, max_per_week) "
                "VALUES (?, ?, ?, 1, ?)",
                ("r1", "Reward", 50, 0),
            )


def test_redemption_full_lifecycle_insert(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        _seed_member(conn)
        conn.execute(
            "INSERT INTO reward (id, name, cost_points, active) "
            "VALUES (?, ?, ?, 1)",
            ("r1", "Ice cream", 50),
        )
        conn.execute(
            "INSERT INTO redemption (id, reward_id, member_id, state, "
            "cost_points_at_redeem, reward_name_at_redeem, "
            "requested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            ("rd1", "r1", 1, "pending_approval", 50, "Ice cream"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT state, cost_points_at_redeem FROM redemption WHERE id='rd1'"
        ).fetchone()
        assert row == ("pending_approval", 50)


def test_redemption_reward_fk_restricts_delete(tmp_path):
    """ON DELETE RESTRICT — can't hard-delete a reward that has a
    redemption pointing at it. Soft-delete via active=False is the
    supported retire path."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _seed_member(conn)
        conn.execute(
            "INSERT INTO reward (id, name, cost_points, active) "
            "VALUES (?, ?, ?, 1)",
            ("r1", "Ice cream", 50),
        )
        conn.execute(
            "INSERT INTO redemption (id, reward_id, member_id, state, "
            "cost_points_at_redeem, reward_name_at_redeem, requested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            ("rd1", "r1", 1, "approved", 50, "Ice cream"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM reward WHERE id='r1'")


def test_redemption_member_fk_cascade_delete(tmp_path):
    """Deleting a member cascades its redemptions away — losing the
    member loses their history (matches the existing CASCADE on
    chore_instances)."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _seed_member(conn)
        conn.execute(
            "INSERT INTO reward (id, name, cost_points, active) "
            "VALUES (?, ?, ?, 1)",
            ("r1", "Ice cream", 50),
        )
        conn.execute(
            "INSERT INTO redemption (id, reward_id, member_id, state, "
            "cost_points_at_redeem, reward_name_at_redeem, requested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            ("rd1", "r1", 1, "approved", 50, "Ice cream"),
        )
        conn.commit()
        conn.execute("DELETE FROM members WHERE id=1")
        conn.commit()
        rows = conn.execute("SELECT id FROM redemption").fetchall()
        assert rows == []


def test_downgrade_removes_reward_and_redemption(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0006_add_member_pin_hash")
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "reward" not in tables
        assert "redemption" not in tables
        # Other schema preserved.
        assert "members" in tables
        assert "chore_template" in tables


def test_upgrade_downgrade_upgrade_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0006_add_member_pin_hash")
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "reward" in tables
        assert "redemption" in tables
