"""Model-level tests: constraints, relationships, cascades."""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from family_chores.db.base import Base
from family_chores.db.models import (
    ActivityLog,
    AppConfig,
    Chore,
    ChoreAssignment,
    ChoreInstance,
    DisplayMode,
    InstanceState,
    Member,
    MemberStats,
    RecurrenceType,
)


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)

    @event.listens_for(eng, "connect")
    def _pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess


def test_member_defaults_applied(session):
    m = Member(name="Alice", slug="alice")
    session.add(m)
    session.commit()

    assert m.id is not None
    assert m.color == "#4f46e5"
    assert m.display_mode is DisplayMode.KID_STANDARD
    assert m.requires_approval is False
    assert m.created_at is not None
    assert m.updated_at is not None


def test_member_slug_is_unique(session):
    session.add(Member(name="Alice", slug="alice"))
    session.commit()
    session.add(Member(name="Second Alice", slug="alice"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_chore_points_must_be_nonnegative(session):
    session.add(
        Chore(name="Bad", points=-5, recurrence_type=RecurrenceType.DAILY, recurrence_config={})
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_chore_assignment_many_to_many(session):
    alice = Member(name="Alice", slug="alice")
    bob = Member(name="Bob", slug="bob")
    chore = Chore(name="Dishes", points=10, recurrence_type=RecurrenceType.DAILY)
    chore.assigned_members.extend([alice, bob])
    session.add_all([alice, bob, chore])
    session.commit()

    assignments = session.scalars(select(ChoreAssignment)).all()
    assert len(assignments) == 2
    reloaded = session.scalar(select(Chore))
    assert {m.slug for m in reloaded.assigned_members} == {"alice", "bob"}


def test_chore_instance_unique_per_member_date(session):
    m = Member(name="Alice", slug="alice")
    c = Chore(name="Dishes", points=10, recurrence_type=RecurrenceType.DAILY)
    session.add_all([m, c])
    session.commit()

    d = date(2026, 4, 21)
    session.add(ChoreInstance(chore_id=c.id, member_id=m.id, date=d))
    session.commit()
    session.add(ChoreInstance(chore_id=c.id, member_id=m.id, date=d))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_member_cascades_to_instances_and_stats(session):
    m = Member(name="Alice", slug="alice")
    c = Chore(name="Dishes", points=10, recurrence_type=RecurrenceType.DAILY)
    session.add_all([m, c])
    session.commit()

    session.add(ChoreInstance(chore_id=c.id, member_id=m.id, date=date(2026, 4, 21)))
    session.add(MemberStats(member_id=m.id, points_total=5))
    session.commit()

    session.delete(m)
    session.commit()

    assert session.scalars(select(ChoreInstance)).all() == []
    assert session.scalars(select(MemberStats)).all() == []
    assert session.scalars(select(Chore)).all() == [c]  # chore untouched


def test_deleting_chore_cascades_to_instances_only(session):
    m = Member(name="Alice", slug="alice")
    c = Chore(name="Dishes", points=10, recurrence_type=RecurrenceType.DAILY)
    session.add_all([m, c])
    session.commit()

    session.add(ChoreInstance(chore_id=c.id, member_id=m.id, date=date(2026, 4, 21)))
    session.commit()

    session.delete(c)
    session.commit()

    assert session.scalars(select(ChoreInstance)).all() == []
    assert session.scalars(select(Member)).all() == [m]


def test_time_window_stored_as_time(session):
    c = Chore(
        name="Brush",
        points=1,
        recurrence_type=RecurrenceType.DAILY,
        recurrence_config={},
        time_window_start=time(7, 0),
        time_window_end=time(8, 0),
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    assert c.time_window_start == time(7, 0)
    assert c.time_window_end == time(8, 0)


def test_instance_state_roundtrip(session):
    m = Member(name="Alice", slug="alice")
    c = Chore(name="Dishes", points=10, recurrence_type=RecurrenceType.DAILY)
    session.add_all([m, c])
    session.commit()

    inst = ChoreInstance(
        chore_id=c.id,
        member_id=m.id,
        date=date(2026, 4, 21),
        state=InstanceState.DONE_UNAPPROVED,
    )
    session.add(inst)
    session.commit()
    session.refresh(inst)
    assert inst.state is InstanceState.DONE_UNAPPROVED


def test_recurrence_config_is_json_roundtripped(session):
    c = Chore(
        name="Pill",
        points=2,
        recurrence_type=RecurrenceType.SPECIFIC_DAYS,
        recurrence_config={"days": [1, 3, 5]},
    )
    session.add(c)
    session.commit()
    session.refresh(c)
    assert c.recurrence_config == {"days": [1, 3, 5]}


def test_activity_log_autofills_ts(session):
    entry = ActivityLog(actor="test", action="created_member", payload={"id": 1})
    session.add(entry)
    session.commit()
    assert entry.ts is not None


def test_app_config_key_value_roundtrip(session):
    session.add(AppConfig(key="jwt_secret", value={"s": "abc123", "rotated_at": "t"}))
    session.commit()
    loaded = session.get(AppConfig, "jwt_secret")
    assert loaded is not None
    assert loaded.value == {"s": "abc123", "rotated_at": "t"}
