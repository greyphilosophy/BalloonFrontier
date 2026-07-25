"""Balloon Frontier — Reward Service

Applies mission rewards to player progression with idempotency guarantees
and automatic rollback on persistence failure.

This replaces the inline persistence logic that used to live inside
FlightService.run().  The flight engine no longer touches
PlayerRegistry directly — it delegates to RewardService.

## Usage

```python
from balloon_frontier.reward_service import RewardService
from balloon_frontier.progression import PlayerRegistryRepository

repo = PlayerRegistryRepository()
service = RewardService(repo)

# Apply rewards to a player's mission results
mission_results = (
    MissionResult(mission_id="sky_dive", completed=True, reward=5000, explanation="..."),
    MissionResult(mission_id="photo_run", completed=False, reward=0, explanation="..."),
)

updated_results = service.apply(
    player_id="player_42",
    mission_results=mission_results,
)
```

## Acceptance criteria (PR G)

* FlightService never imports PlayerRegistry.
* Reward idempotency and rollback live in RewardService.
* Reward application has focused unit tests.
* FlightService receives the service through dependency injection.
* Existing behavior remains unchanged.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from balloon_frontier.progression import PlayerRepository

from balloon_frontier.launch_result import MissionResult

logger = logging.getLogger(__name__)


class RewardService:
    """Applies mission rewards to player progression with rollback safety.

    Attributes:
        repository: Player persistence backing (e.g. PlayerRegistryRepository).
    """

    def __init__(self, repository: PlayerRepository) -> None:
        self.repository = repository

    def apply(
        self,
        player_id: str,
        mission_results: tuple[MissionResult, ...],
    ) -> tuple[MissionResult, ...]:
        """Apply mission rewards for a player, with idempotency and rollback.

        Args:
            player_id: The player whose rewards are being applied.
            mission_results: Mission results from the flight evaluation.

        Returns:
            Mission results reconciled with persistence status.
            Each result's reward/explanation is updated to reflect whether
            the reward was actually persisted or rolled back.
        """
        if not mission_results:
            return ()

        player = self.repository.get(player_id)

        # Phase 1: Apply deltas (budget, reputation, mission_completed)
        applied_rewards: list[str] = []
        reward_deltas: dict[str, tuple[int, int]] = {}  # mission_id -> (budget_delta, rep_delta)
        rolled_back_rewards: set[str] = set()

        for mr in mission_results:
            if not mr.completed:
                continue
            if mr.mission_id in player.missions_completed:
                continue

            player.budget += mr.reward
            rep_gain = min(int(mr.reward / 3000), 2)
            player.reputation += rep_gain
            player.missions_completed.append(mr.mission_id)
            applied_rewards.append(mr.mission_id)
            reward_deltas[mr.mission_id] = (mr.reward, rep_gain)

        # Phase 2: Persist (save), rollback on failure
        save_failed: bool = False
        if applied_rewards:
            try:
                self.repository.save(player)
            except Exception:
                logger.exception("Failed to save player progression")
                save_failed = True
                # Roll back in-memory changes for all applied rewards
                for mission_id in applied_rewards:
                    delta_budget, delta_rep = reward_deltas[mission_id]
                    player.budget -= delta_budget
                    player.reputation -= delta_rep
                    player.missions_completed.remove(mission_id)
                    rolled_back_rewards.add(mission_id)
                applied_rewards.clear()

        # Phase 3: Log applied rewards (only if save succeeded)
        if applied_rewards:
            for mission_id in applied_rewards:
                mr_entry = next(
                    mr for mr in mission_results if mr.mission_id == mission_id
                )
                rep_for_entry = min(int(mr_entry.reward / 3000), 2)
                logger.info(
                    "Applied mission reward for %s: budget=%d, rep=%d",
                    mission_id,
                    mr_entry.reward,
                    rep_for_entry,
                )

        # Phase 4: Reconcile displayed reward with persistence status
        applied_set = set(applied_rewards)

        def _reconcile_mission(mr: MissionResult) -> MissionResult:
            if not mr.completed:
                return mr

            if mr.mission_id in rolled_back_rewards:
                # Persistence failed: reward was reverted in-memory
                return MissionResult(
                    mission_id=mr.mission_id,
                    completed=True,
                    reward=0,
                    explanation=(
                        "Mission completed, but the reward could not be saved. "
                        "Please try again."
                    ),
                )

            if mr.mission_id in applied_set:
                # Reward was actually awarded
                return mr

            # Progression skipped: either already-completed or save failed
            if save_failed:
                return MissionResult(
                    mission_id=mr.mission_id,
                    completed=True,
                    reward=0,
                    explanation="Mission completed but reward could not be applied (progression error).",
                )
            return MissionResult(
                mission_id=mr.mission_id,
                completed=True,
                reward=0,
                explanation="Mission completed previously; no additional reward awarded.",
            )

        return tuple(_reconcile_mission(mr) for mr in mission_results)