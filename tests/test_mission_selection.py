"""Tests for mission selection and per-flight assignment.

Covers:
- deterministic selection via seed
- no duplicates within a flight
- graceful fallback when the mission pool is empty
"""

import pytest

from balloon_frontier.missions import Mission, register_mission, MISSIONS

# Import after registry import so tests can manipulate MISSIONS safely.
from balloon_frontier.mission_selection import (
    choose_mission_count,
    select_missions,
    fallback_mission_ids,
)


@pytest.fixture(autouse=True)
def _clear_missions():
    MISSIONS.clear()
    yield
    MISSIONS.clear()


def _register(ids):
    for mid in ids:
        register_mission(Mission(id=mid, title=mid, description="desc"))


def test_choose_mission_count_payload_1_to_3():
    assert choose_mission_count(payload_count=0) == 1
    assert choose_mission_count(payload_count=1) == 1
    assert choose_mission_count(payload_count=2) == 2
    assert choose_mission_count(payload_count=3) == 3
    assert choose_mission_count(payload_count=10) == 3


def test_select_missions_deterministic_with_seed():
    _register(["m1", "m2", "m3", "m4", "m5"])

    a = select_missions(mission_count=3, seed=123)
    b = select_missions(mission_count=3, seed=123)

    assert a == b
    assert len(a) == 3
    assert len(set(a)) == 3


def test_select_missions_unique_and_clamped_to_pool_size():
    _register(["m1", "m2"])

    chosen = select_missions(mission_count=3, seed=1)
    assert chosen == ["m1", "m2"] or set(chosen) == {"m1", "m2"}
    assert len(chosen) == 2
    assert len(set(chosen)) == 2


def test_select_missions_empty_pool_falls_back_to_safe_default():
    MISSIONS.clear()

    chosen = select_missions(mission_count=2, seed=999)
    assert chosen == fallback_mission_ids()


def test_select_missions_handles_invalid_mission_count_gracefully():
    _register(["m1", "m2", "m3"])

    assert select_missions(mission_count=-5, seed=1) == ["m1"]
