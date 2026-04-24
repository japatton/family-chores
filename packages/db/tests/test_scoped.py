"""Unit tests for `family_chores_db.scoped`.

Verifies the SQL semantics: `None` produces `IS NULL`, a string produces
`= 'value'`. End-to-end behavior (services thread the helper through
real queries) is exercised by the FakeAuthStrategy integration tests in
`family_chores/tests/test_household_scoping.py`.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from family_chores_db.base import Base
from family_chores_db.models import Member
from family_chores_db.scoped import scoped


def _engine_with_three_members(tmp_path):
    """Tiny SQLite + 3 members spanning the household_id cases."""
    eng = create_engine(f"sqlite:///{tmp_path / 'scoped.db'}", future=True)
    Base.metadata.create_all(eng)
    with Session(eng, expire_on_commit=False) as s:
        s.add_all(
            [
                Member(name="UnscopedAlice", slug="ua", household_id=None),
                Member(name="HouseholdAlice", slug="ha", household_id="house-a"),
                Member(name="HouseholdBob", slug="hb", household_id="house-b"),
            ]
        )
        s.commit()
    return eng


def test_scoped_none_matches_only_null_rows(tmp_path):
    eng = _engine_with_three_members(tmp_path)
    with Session(eng) as s:
        rows = s.query(Member.name).filter(scoped(Member.household_id, None)).all()
    assert sorted(r[0] for r in rows) == ["UnscopedAlice"]


def test_scoped_value_matches_only_that_household(tmp_path):
    eng = _engine_with_three_members(tmp_path)
    with Session(eng) as s:
        rows = s.query(Member.name).filter(scoped(Member.household_id, "house-a")).all()
    assert sorted(r[0] for r in rows) == ["HouseholdAlice"]


def test_scoped_value_excludes_null_rows(tmp_path):
    """Multi-tenant queries must NOT see unscoped (single-tenant) rows."""
    eng = _engine_with_three_members(tmp_path)
    with Session(eng) as s:
        rows = s.query(Member.name).filter(scoped(Member.household_id, "house-b")).all()
    assert sorted(r[0] for r in rows) == ["HouseholdBob"]


def test_scoped_unknown_household_returns_nothing(tmp_path):
    eng = _engine_with_three_members(tmp_path)
    with Session(eng) as s:
        rows = s.query(Member.name).filter(scoped(Member.household_id, "ghost")).all()
    assert rows == []


def test_scoped_compiles_to_is_null_for_none():
    """SQL-string-level check that `None` becomes `IS NULL`, not `= NULL`.

    Catches a regression where someone "fixes" the helper to use `==`
    everywhere (the original prompt's first-draft trap from §4 of the
    monorepo prompt).
    """
    expr = scoped(Member.household_id, None)
    sql = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "IS NULL" in sql.upper()


def test_scoped_compiles_to_eq_for_string_value():
    expr = scoped(Member.household_id, "abc")
    sql = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert "'abc'" in sql
    assert "IS NULL" not in sql.upper()
