from __future__ import annotations

import dataclasses
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union

from t_9e7d641e.activity import ActivityState
from t_9e7d641e.controller import GameController
from t_9e7d641e.contracts import (
    CancelRequest,
    FillMode,
    LaunchRequest,
    MissionCategory,
    PresentationStyle,
)
from t_9e7d641e.presentation import Presenter


UserId = Union[str, int]


@dataclass(frozen=True)
class MissionDesignIntent:
    """User-selected mission configuration.

    Discord commands mutate an in-memory instance of this per-user intent.
    The controller receives a typed LaunchRequest derived from the intent.
    """

    gas_id: str
    envelope_id: str
    balloon_size: str
    payload_ids: Tuple[str, ...] = ()
    launch_site_id: str = "default"
    fill_mode: FillMode = FillMode.AUTO
    manual_gas_mass_kg: Optional[float] = None
    mission_filter: Optional[MissionCategory] = None
    context_data: Optional[Dict[str, Any]] = None


class DiscordBotInterface:
    """Reference Discord-side interface (transport neutral).

    This class is intentionally Discord-library-agnostic.
    It produces Discord-shaped embed dicts using the shared Presenter.

    A separate, thin Discord adapter layer can map slash commands and
    interactions to these methods.
    """

    def __init__(self, *, controller: GameController, presenter: Optional[Presenter] = None):
        self.controller = controller
        self.presenter = presenter or Presenter()
        self._intent_by_user: Dict[UserId, MissionDesignIntent] = {}
        self._activity_owner: Dict[str, UserId] = {}

    # ----------------------------
    # Mission design
    # ----------------------------
    def set_mission_design(
        self,
        user_id: UserId,
        *,
        gas_id: str,
        envelope_id: str,
        balloon_size: str,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: str = "default",
        fill_mode: FillMode = FillMode.AUTO,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        intent = MissionDesignIntent(
            gas_id=gas_id,
            envelope_id=envelope_id,
            balloon_size=balloon_size,
            payload_ids=tuple(payload_ids or ()),
            launch_site_id=launch_site_id,
            fill_mode=fill_mode,
            manual_gas_mass_kg=manual_gas_mass_kg,
            mission_filter=mission_filter,
            context_data=context_data,
        )
        self._intent_by_user[user_id] = intent
        return self._render_discovery_intent(intent)

    def _render_discovery_intent(self, intent: MissionDesignIntent) -> Dict[str, Any]:
        # Emphasize discovery: what the chosen configuration reveals.
        mission_hint = self._mission_discovery_hint(intent.mission_filter)
        payload_part = ", ".join(intent.payload_ids) if intent.payload_ids else "(none)"
        fill_label = getattr(intent.fill_mode, "label", str(intent.fill_mode))

        return {
            "type": "mission_design",
            "title": "Balloon Frontier — Mission Design",
            "description": (
                f"Gas: {intent.gas_id} | Envelope: {intent.envelope_id} | Size: {intent.balloon_size}\n"
                f"Launch site: {intent.launch_site_id} | Fill: {fill_label}\n"
                f"Payload(s): {payload_part}\n\n"
                f"Discovery focus: {mission_hint}\n\n"
                f"Next: use /launch to attempt this mission."
            ),
            "intent": dataclasses.asdict(intent),
        }

    @staticmethod
    def _mission_discovery_hint(mission_filter: Optional[MissionCategory]) -> str:
        if mission_filter is None:
            return "No specific focus — you’ll learn the full system interplay (weather, flight physics, scoring)."
        mapping = {
            MissionCategory.EXPLORATION: "You’ll discover route viability and how weather steers altitude & survival.",
            MissionCategory.PRECISION: "You’ll discover how staging choices affect outcomes that hinge on accuracy.",
            MissionCategory.SURVIVAL: "You’ll discover what conditions best protect the crew and envelope integrity.",
            MissionCategory.ECONOMY: "You’ll discover which choices minimize penalties while keeping performance acceptable.",
            MissionCategory.CREW_SAFETY: "You’ll discover how safety-oriented parameters change the risk profile.",
        }
        return mapping.get(mission_filter, "You’ll discover mission-relevant dynamics.")

    def _require_intent(self, user_id: UserId) -> MissionDesignIntent:
        if user_id not in self._intent_by_user:
            raise ValueError("No mission design found for this user. Call set_mission_design first.")
        return self._intent_by_user[user_id]

    def build_launch_request(
        self,
        user_id: UserId,
        *,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: Optional[str] = None,
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> LaunchRequest:
        intent = self._require_intent(user_id)

        return LaunchRequest(
            gas_id=intent.gas_id,
            envelope_id=intent.envelope_id,
            balloon_size=intent.balloon_size,
            payload_ids=tuple(payload_ids if payload_ids is not None else intent.payload_ids),
            launch_site_id=launch_site_id or intent.launch_site_id,
            fill_mode=fill_mode or intent.fill_mode,
            manual_gas_mass_kg=(
                manual_gas_mass_kg if manual_gas_mass_kg is not None else intent.manual_gas_mass_kg
            ),
            mission_filter=(mission_filter if mission_filter is not None else intent.mission_filter),
            context_data=context_data if context_data is not None else intent.context_data,
        )

    # ----------------------------
    # Launch
    # ----------------------------
    async def launch(
        self,
        user_id: UserId,
        *,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: Optional[str] = None,
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request = self.build_launch_request(
            user_id,
            payload_ids=payload_ids,
            launch_site_id=launch_site_id,
            fill_mode=fill_mode,
            manual_gas_mass_kg=manual_gas_mass_kg,
            mission_filter=mission_filter,
            context_data=context_data,
        )

        ctx = await self.controller.launch_async(request)
        self._activity_owner[ctx.activity_id] = user_id

        if ctx.outcome is not None:
            embed = self.presenter.render(ctx.outcome, style=PresentationStyle.DISCORD)
        else:
            embed = {
                "title": "Balloon Frontier — Flight Result",
                "description": "No outcome available.",
                "fields": [],
            }

        return {
            "activity_id": ctx.activity_id,
            "state": ctx.state.value,
            "embed": embed,
            "error": ctx.error,
        }

    # ----------------------------
    # Status
    # ----------------------------
    def status(self, activity_id: str) -> Dict[str, Any]:
        ctx = self.controller.registry.try_get(activity_id)
        if ctx is None:
            return {
                "type": "status",
                "title": "Balloon Frontier — Activity Status",
                "description": "Unknown activity_id.",
                "state": None,
            }

        if ctx.state == ActivityState.COMPLETE and ctx.outcome is not None:
            embed = self.presenter.render(ctx.outcome, style=PresentationStyle.DISCORD)
            return {
                "type": "status",
                "title": "Balloon Frontier — Activity Complete",
                "description": "Your flight attempt has completed. Here’s the discovery-focused result:",
                "state": ctx.state.value,
                "embed": embed,
            }

        return {
            "type": "status",
            "title": "Balloon Frontier — Activity Status",
            "description": f"Current state: {ctx.state.value}",
            "state": ctx.state.value,
            "error": ctx.error,
        }

    # ----------------------------
    # Recovery
    # ----------------------------
    async def recover(self, user_id: UserId, activity_id: str) -> Dict[str, Any]:
        """Recover by re-running the prior launch configuration.

        In the unification framework, a "recovery" action is represented as
        a fresh LaunchRequest based on the previous ActivityContext.
        """

        ctx = self.controller.registry.try_get(activity_id)
        if ctx is None:
            return {
                "type": "recover",
                "ok": False,
                "description": "Unknown activity_id.",
            }
        if ctx.request is None:
            return {
                "type": "recover",
                "ok": False,
                "description": "This activity has no stored LaunchRequest to recover.",
            }

        # If the activity is still in progress, mark it cancelled first (best-effort).
        if ctx.state != ActivityState.COMPLETE:
            try:
                self.controller.cancel(CancelRequest(activity_id=activity_id))
            except Exception:
                pass

        recovered_request = dataclasses.replace(
            ctx.request,
            context_data={"recovered_from": activity_id, **(ctx.request.context_data or {})},
        )

        new_ctx = await self.controller.launch_async(recovered_request)
        self._activity_owner[new_ctx.activity_id] = user_id

        embed = (
            self.presenter.render(new_ctx.outcome, style=PresentationStyle.DISCORD)
            if new_ctx.outcome is not None
            else {
                "title": "Balloon Frontier — Flight Result",
                "description": "No outcome available.",
                "fields": [],
            }
        )

        return {
            "type": "recover",
            "ok": True,
            "from_activity_id": activity_id,
            "recovered_activity_id": new_ctx.activity_id,
            "state": new_ctx.state.value,
            "embed": embed,
            "error": new_ctx.error,
        }
