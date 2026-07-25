from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union, Literal

from t_9e7d641e.activity import ActivityContext
from t_9e7d641e.controller import GameController
from t_9e7d641e.contracts import (
    ActivityState,
    CancelRequest,
    FillMode,
    FlightOutcome,
    LaunchRequest,
    MissionCategory,
)

UserId = Union[str, int]


@dataclass(frozen=True)
class MissionDesign:
    """Interface-independent per-actor mission design.

    This is the data that an interface (Discord / CLI / GUI) collects from the
    user before creating a LaunchRequest.
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


@dataclass(frozen=True)
class GameActivity:
    """Transport-neutral view of an activity."""

    activity_id: str
    state: ActivityState
    outcome: Optional[FlightOutcome] = None
    error: Optional[str] = None
    owner_id: Optional[UserId] = None


InteractionKind = Literal[
    "set_mission_design",
    "launch",
    "status",
    "recover",
]


@dataclass(frozen=True)
class SessionInteraction:
    """Record of player-facing session interactions.

    This is for transport-neutral observability (e.g. for logging / UI
    history). The controller remains the source of truth for activity state.
    """

    timestamp: float
    actor_id: UserId
    kind: InteractionKind
    activity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class GameSession:
    """A transport-neutral session model.

    Tracks:
      - per-actor mission design intents
      - activity ownership and per-actor activity ids
      - a small interaction log for player-facing history

    Activity lifecycle/state transitions are owned by GameController.
    """

    controller: GameController

    mission_design_by_actor: Dict[UserId, MissionDesign] = field(default_factory=dict)
    activity_owner_by_id: Dict[str, UserId] = field(default_factory=dict)
    activity_ids_by_actor: Dict[UserId, List[str]] = field(default_factory=dict)
    interactions: List[SessionInteraction] = field(default_factory=list)

    created_at: float = field(default_factory=time.time)

    def _record(
        self,
        *,
        actor_id: UserId,
        kind: InteractionKind,
        activity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.interactions.append(
            SessionInteraction(
                timestamp=time.time(),
                actor_id=actor_id,
                kind=kind,
                activity_id=activity_id,
                details=details,
            )
        )

    def set_mission_design(
        self,
        actor_id: UserId,
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
    ) -> MissionDesign:
        design = MissionDesign(
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
        self.mission_design_by_actor[actor_id] = design
        self._record(actor_id=actor_id, kind="set_mission_design")
        return design

    def _require_design(self, actor_id: UserId) -> MissionDesign:
        design = self.mission_design_by_actor.get(actor_id)
        if design is None:
            raise ValueError(
                "No mission design found for this actor. Call set_mission_design first."
            )
        return design

    def build_launch_request(
        self,
        actor_id: UserId,
        *,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: Optional[str] = None,
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> LaunchRequest:
        design = self._require_design(actor_id)
        return LaunchRequest(
            gas_id=design.gas_id,
            envelope_id=design.envelope_id,
            balloon_size=design.balloon_size,
            payload_ids=tuple(
                payload_ids if payload_ids is not None else design.payload_ids
            ),
            launch_site_id=launch_site_id or design.launch_site_id,
            fill_mode=fill_mode or design.fill_mode,
            manual_gas_mass_kg=(
                manual_gas_mass_kg
                if manual_gas_mass_kg is not None
                else design.manual_gas_mass_kg
            ),
            mission_filter=(
                mission_filter
                if mission_filter is not None
                else design.mission_filter
            ),
            context_data=context_data if context_data is not None else design.context_data,
        )

    async def launch_async(
        self,
        actor_id: UserId,
        *,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: Optional[str] = None,
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> GameActivity:
        request = self.build_launch_request(
            actor_id,
            payload_ids=payload_ids,
            launch_site_id=launch_site_id,
            fill_mode=fill_mode,
            manual_gas_mass_kg=manual_gas_mass_kg,
            mission_filter=mission_filter,
            context_data=context_data,
        )
        ctx = await self.controller.launch_async(request)

        self.activity_owner_by_id[ctx.activity_id] = actor_id
        self.activity_ids_by_actor.setdefault(actor_id, []).append(ctx.activity_id)
        self._record(actor_id=actor_id, kind="launch", activity_id=ctx.activity_id)

        return GameActivity(
            activity_id=ctx.activity_id,
            state=ctx.state,
            outcome=ctx.outcome,
            error=ctx.error,
            owner_id=actor_id,
        )

    def status(self, activity_id: str) -> Optional[GameActivity]:
        ctx = self.controller.registry.try_get(activity_id)
        if ctx is None:
            return None

        owner = self.activity_owner_by_id.get(activity_id)
        # If the activity exists in the controller but we didn't track ownership
        # (e.g. old session replay), still return transport-neutral state.
        self._record(actor_id=owner if owner is not None else "unknown", kind="status", activity_id=activity_id)

        return GameActivity(
            activity_id=ctx.activity_id,
            state=ctx.state,
            outcome=ctx.outcome,
            error=ctx.error,
            owner_id=owner,
        )

    async def recover_async(self, actor_id: UserId, activity_id: str) -> GameActivity:
        ctx = self.controller.registry.try_get(activity_id)
        if ctx is None:
            raise ValueError("Unknown activity_id")
        if ctx.request is None:
            raise ValueError("This activity has no stored LaunchRequest to recover.")

        # If not complete, mark cancelled first (best-effort).
        if ctx.state != ActivityState.COMPLETE:
            try:
                self.controller.cancel(CancelRequest(activity_id=activity_id))
            except Exception:
                pass

        recovered_request = dataclasses.replace(
            ctx.request,
            context_data={
                "recovered_from": activity_id,
                **(ctx.request.context_data or {}),
            },
        )

        new_ctx = await self.controller.launch_async(recovered_request)

        self.activity_owner_by_id[new_ctx.activity_id] = actor_id
        self.activity_ids_by_actor.setdefault(actor_id, []).append(new_ctx.activity_id)
        self._record(
            actor_id=actor_id,
            kind="recover",
            activity_id=activity_id,
            details={"recovered_activity_id": new_ctx.activity_id},
        )

        return GameActivity(
            activity_id=new_ctx.activity_id,
            state=new_ctx.state,
            outcome=new_ctx.outcome,
            error=new_ctx.error,
            owner_id=actor_id,
        )

    def list_actor_activity_ids(self, actor_id: UserId) -> Tuple[str, ...]:
        return tuple(self.activity_ids_by_actor.get(actor_id, []))

    def get_activity_context(self, activity_id: str) -> ActivityContext:
        return self.controller.registry.get(activity_id)


__all__ = [
    "GameSession",
    "MissionDesign",
    "GameActivity",
    "SessionInteraction",
    "UserId",
]
