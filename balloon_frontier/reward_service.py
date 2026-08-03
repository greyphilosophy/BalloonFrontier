"""Balloon Frontier — Reward Service

Applies mission rewards to player progression with idempotency guarantees
and automatic rollback on persistence failure.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from balloon_frontier.progression import PlayerRepository

from balloon_frontier.launch_result import MissionResult

logger = logging.getLogger(__name__)


class RewardService:
    """Apply mission rewards while preserving the evaluator's real debrief."""

    def __init__(self, repository: PlayerRepository) -> None:
        self.repository = repository

    @staticmethod
    def _with_status(
        mission: MissionResult,
        *,
        status: str,
        emphasized: bool = True,
    ) -> MissionResult:
        """Append status to a real debrief, but preserve legacy empty-result text."""
        if not mission.explanation:
            return replace(mission, reward=0, explanation=status)
        suffix = f"*{status}*" if emphasized else status
        return replace(
            mission,
            reward=0,
            explanation=f"{mission.explanation}\n\n{suffix}",
        )

    def apply(
        self,
        player_id: str,
        mission_results: tuple[MissionResult, ...],
    ) -> tuple[MissionResult, ...]:
        if not mission_results:
            return ()

        player = self.repository.get(player_id)
        applied_rewards: list[str] = []
        reward_deltas: dict[str, tuple[int, int]] = {}
        rolled_back_rewards: set[str] = set()

        for mission in mission_results:
            if not mission.completed or mission.mission_id in player.missions_completed:
                continue
            player.budget += mission.reward
            reputation_gain = min(int(mission.reward / 3000), 2)
            player.reputation += reputation_gain
            player.missions_completed.append(mission.mission_id)
            applied_rewards.append(mission.mission_id)
            reward_deltas[mission.mission_id] = (mission.reward, reputation_gain)

        save_failed = False
        if applied_rewards:
            try:
                self.repository.save(player)
            except Exception:
                logger.exception("Failed to save player progression")
                save_failed = True
                for mission_id in applied_rewards:
                    budget_delta, reputation_delta = reward_deltas[mission_id]
                    player.budget -= budget_delta
                    player.reputation -= reputation_delta
                    player.missions_completed.remove(mission_id)
                    rolled_back_rewards.add(mission_id)
                applied_rewards.clear()

        if applied_rewards:
            for mission_id in applied_rewards:
                mission = next(
                    item for item in mission_results if item.mission_id == mission_id
                )
                logger.info(
                    "Applied mission reward for %s: budget=%d, rep=%d",
                    mission_id,
                    mission.reward,
                    min(int(mission.reward / 3000), 2),
                )

        applied_set = set(applied_rewards)

        def reconcile(mission: MissionResult) -> MissionResult:
            if not mission.completed:
                return mission
            if mission.mission_id in rolled_back_rewards:
                return self._with_status(
                    mission,
                    status=(
                        "Mission completed, but the reward could not be saved. "
                        "Please try again."
                    ),
                )
            if mission.mission_id in applied_set:
                return mission
            if save_failed:
                return self._with_status(
                    mission,
                    status=(
                        "Mission completed but reward could not be applied "
                        "(progression error)."
                    ),
                )
            return self._with_status(
                mission,
                status="Mission completed previously; no additional reward awarded.",
            )

        return tuple(reconcile(mission) for mission in mission_results)
