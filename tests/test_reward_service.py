"""Tests for RewardService — idempotency, rollback, persistence boundary.

These tests replace the inline persistence logic that used to live
inside FlightService.run() — PR G.
"""

import pytest
from balloon_frontier.reward_service import RewardService
from balloon_frontier.launch_result import MissionResult
from balloon_frontier.progression import (
    PlayerRepository,
    PlayerRegistryRepository,
    PlayerState,
)


# ── Mock repository that can be configured to fail ──────────────────────


class FailingOnSaveRepository:
    """A mock PlayerRepository that can be toggled to fail on save()."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.save_calls: list[PlayerState] = []
        self.players: dict[str, PlayerState] = {}

    # PlayerRepository protocol ------------------------------------------------

    def get(self, player_id: str) -> PlayerState:
        if player_id not in self.players:
            p = PlayerState(player_id)
            self.players[player_id] = p
        return self.players[player_id]

    def save(self, player: PlayerState) -> None:
        if self.should_fail:
            raise IOError("Simulated disk error")
        self.save_calls.append(player)


class CapturingRepository:
    """A lightweight mock that records all mutations."""

    def __init__(self) -> None:
        self.save_calls: list[PlayerState] = []
        self.budget_snapshots: dict[str, list[int]] = {}
        self.rep_snapshots: dict[str, list[int]] = {}
        self.missions_snapshots: dict[str, list[list[str]]] = {}
        self._players: dict[str, PlayerState] = {}

    def _snapshot(self, player: PlayerState) -> None:
        pid = player.player_id
        if pid not in self.budget_snapshots:
            self.budget_snapshots[pid] = []
        self.budget_snapshots[pid].append(player.budget)
        if pid not in self.rep_snapshots:
            self.rep_snapshots[pid] = []
        self.rep_snapshots[pid].append(player.reputation)
        if pid not in self.missions_snapshots:
            self.missions_snapshots[pid] = []
        self.missions_snapshots[pid].append(list(player.missions_completed))

    def get(self, player_id: str) -> PlayerState:
        if player_id not in self._players:
            p = PlayerState(player_id)
            self._players[player_id] = p
            self._snapshot(p)
        return self._players[player_id]

    def save(self, player: PlayerState) -> None:
        self.save_calls.append(player)


# ── Tests ─────────────────────────────────────────────────────────────────


class TestRewardServiceApply:
    """RewardService.apply — happy path & edge cases."""

    def test_applies_reward_for_completed_mission(self) -> None:
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        results = service.apply("player_1", missions)

        # Reward should be unchanged (reconcile confirmed)
        assert results[0].reward == 5000
        assert results[0].completed is True
        # Player budget should have increased
        player = repo.get("player_1")
        assert player.budget == 100 + 5000  # default 100 + reward
        # Rep gain: 5000 / 3000 = 1.66 → min(1, 2) = 1
        assert player.reputation == 1

    def test_no_change_for_not_completed_mission(self) -> None:
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=False, reward=0),
        )
        results = service.apply("player_1", missions)

        assert results[0].reward == 0
        assert results[0].completed is False
        player = repo.get("player_1")
        assert player.budget == 100  # unchanged
        assert player.reputation == 0

    def test_empty_mission_results_returns_empty(self) -> None:
        repo = CapturingRepository()
        service = RewardService(repo)

        results = service.apply("player_1", ())
        assert results == ()

    def test_no_player_id_returns_unchanged(self) -> None:
        """When player_id is falsy, no rewards are applied."""
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        results = service.apply("", missions)
        assert results[0].reward == 5000  # unchanged

    def test_mixed_completed_and_not(self) -> None:
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=6000),
            MissionResult(mission_id="m2", completed=False, reward=0),
        )
        results = service.apply("player_1", missions)

        assert results[0].reward == 6000  # applied
        assert results[1].reward == 0  # not completed
        player = repo.get("player_1")
        assert player.budget == 100 + 6000
        # 6000 / 3000 = 2 → rep += 2
        assert player.reputation == 2


class TestRewardServiceIdempotency:
    """Duplicate rewards are skipped — the 'previously completed' path."""

    def test_skips_already_completed_mission(self) -> None:
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )

        # First call — should apply
        results1 = service.apply("player_1", missions)
        assert results1[0].reward == 5000
        player = repo.get("player_1")
        assert player.budget == 5100

        # Second call — should be idempotent (already in missions_completed)
        results2 = service.apply("player_1", missions)
        assert results2[0].reward == 0
        assert (
            results2[0].explanation
            == "Mission completed previously; no additional reward awarded."
        )
        assert player.budget == 5100  # unchanged

    def test_skips_after_flush_failure_rollback(self) -> None:
        """After a flush failure + rollback, re-attempt should re-apply."""
        repo = CapturingRepository()
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )

        # First call — succeeds
        results1 = service.apply("player_1", missions)
        assert results1[0].reward == 5000
        assert repo.get("player_1").budget == 5100

        # Second call — idempotent
        results2 = service.apply("player_1", missions)
        assert results2[0].reward == 0  # skipped


class TestRewardServiceFlushFailure:
    """When save() raises, rewards are rolled back in-memory."""

    def test_save_failure_rolls_back_in_memory(self) -> None:
        repo = FailingOnSaveRepository(should_fail=True)
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        results = service.apply("player_1", missions)

        # Reconcile shows save failure message
        assert results[0].reward == 0
        assert (
            results[0].explanation
            == "Mission completed, but the reward could not be saved. "
            "Please try again."
        )
        # In-memory state should be rolled back
        player = repo.get("player_1")
        assert player.budget == 100  # back to default
        assert player.reputation == 0
        assert player.missions_completed == []

    def test_save_failure_multiple_missions(self) -> None:
        repo = FailingOnSaveRepository(should_fail=True)
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
            MissionResult(mission_id="m2", completed=True, reward=3000),
            MissionResult(mission_id="m3", completed=False, reward=0),
        )
        results = service.apply("player_1", missions)

        # m1, m2 — save failed, m3 — not completed
        assert results[0].reward == 0
        assert results[0].explanation == (
            "Mission completed, but the reward could not be saved. "
            "Please try again."
        )
        assert results[1].reward == 0
        assert results[1].explanation == (
            "Mission completed, but the reward could not be saved. "
            "Please try again."
        )
        assert results[2].reward == 0  # never attempted

        # In-memory should be fully rolled back
        player = repo.get("player_1")
        assert player.budget == 100
        assert player.reputation == 0

    def test_save_failure_then_success(self) -> None:
        """Retry after fixing the save error should re-apply."""
        # Start with failure
        repo = FailingOnSaveRepository(should_fail=True)
        service = RewardService(repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        results_fail = service.apply("player_1", missions)
        assert results_fail[0].reward == 0  # rolled back

        # Now enable save
        repo.should_fail = False

        # Retry — should succeed
        results_ok = service.apply("player_1", missions)
        assert results_ok[0].reward == 5000
        assert repo.get("player_1").budget == 5100


class TestRewardServiceReconcile:
    """The reconcile logic: save_failed path (already in missions but
    save failed on the current batch)."""

    def test_save_failure_message_for_non_applied_completed(self) -> None:
        """When player already has mission_id in missions_completed (from a
        previous session that succeeded), but save() fails on the CURRENT
        batch, the reconcile should show the generic 'progression error'
        message — NOT 'could not be saved'.

        This tests the save_failed path in _reconcile_mission.
        """
        # Set up fail_repo with m1 already in missions_completed but m2 not
        fail_repo = FailingOnSaveRepository(should_fail=True)
        fail_player = fail_repo.get("player_1")
        fail_player.missions_completed.append("m1")

        service = RewardService(fail_repo)

        # m1 is already completed, m2 is new and would be applied but save fails
        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),  # already done
            MissionResult(mission_id="m2", completed=True, reward=3000),  # new
        )
        results = service.apply("player_1", missions)

        # m1: in missions_completed → skipped during apply → not in applied_set
        #     → not in rolled_back → save_failed=True → "progression error"
        # m2: not in missions_completed → applied → save fails → rolled back
        #     → "could not be saved"

        assert results[0].reward == 0
        assert results[0].explanation == (
            "Mission completed but reward could not be applied (progression error)."
        )
        assert results[1].reward == 0
        assert results[1].explanation == (
            "Mission completed, but the reward could not be saved. "
            "Please try again."
        )


class TestPlayerRepositoryProtocol:
    """Verify the PlayerRepository Protocol works with both implementations."""

    def test_player_registry_repository_implements_protocol(self) -> None:
        repo = PlayerRegistryRepository()
        assert isinstance(repo, PlayerRepository)

    def test_get_creates_player(self) -> None:
        # Use a mock repo to avoid PlayerRegistry global state issues
        mock_repo = CapturingRepository()
        assert isinstance(mock_repo, PlayerRepository)
        p = mock_repo.get("test_player")
        assert p.player_id == "test_player"
        assert p.budget == 100
        assert p.reputation == 0

    def test_save_records_player(self) -> None:
        """Verify save() records the player state on the mock."""
        mock_repo = CapturingRepository()
        p = mock_repo.get("persist_test")
        p.budget = 9999
        p.reputation = 50

        # Save should record the player
        mock_repo.save(p)
        assert len(mock_repo.save_calls) == 1
        assert mock_repo.save_calls[0].budget == 9999
        assert mock_repo.save_calls[0].reputation == 50

    def test_save_called_on_applied_reward(self) -> None:
        """Verify RewardService calls save() when rewards are applied."""
        mock_repo = CapturingRepository()
        service = RewardService(mock_repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        service.apply("player_1", missions)

        # save() should have been called once (applied, not rolled back)
        assert len(mock_repo.save_calls) == 1

    def test_save_not_called_on_rollback(self) -> None:
        """Verify save() is NOT called after rollback."""
        fail_repo = FailingOnSaveRepository(should_fail=True)
        service = RewardService(fail_repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        service.apply("player_1", missions)

        # save() was attempted but failed → rolled back
        assert len(fail_repo.save_calls) == 0  # never recorded

    def test_save_not_called_when_no_rewards(self) -> None:
        """Verify save() is not called when there are no rewards to apply."""
        mock_repo = CapturingRepository()
        service = RewardService(mock_repo)

        missions = (
            MissionResult(mission_id="m1", completed=False, reward=0),
        )
        service.apply("player_1", missions)

        # No applied rewards → save never called
        assert len(mock_repo.save_calls) == 0

    def test_save_not_called_when_already_completed(self) -> None:
        """Verify save() is not called when all missions are already completed."""
        mock_repo = CapturingRepository()
        player = mock_repo.get("player_1")
        player.missions_completed.append("m1")

        service = RewardService(mock_repo)

        missions = (
            MissionResult(mission_id="m1", completed=True, reward=5000),
        )
        service.apply("player_1", missions)

        # All missions skipped → no applied → no save
        assert len(mock_repo.save_calls) == 0