from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Tuple, Union, runtime_checkable

from t_9e7d641e.contracts import FillMode, MissionCategory, PresentationStyle


DEFAULT_PRESENTATION_STYLE = PresentationStyle.WEB

ActorId = Union[str, int]
JsonObject = Dict[str, Any]


@dataclass(frozen=True)
class MissionDesignIntent:
    """Transport-neutral mission design intent collected by a GUI.

    A GUI implementation stores this intent (per actor) and later uses it
    to build a LaunchRequest for the core controller.
    """

    gas_id: str
    envelope_id: str
    balloon_size: str
    payload_ids: Tuple[str, ...] = ()
    launch_site_id: str = "default"

    # Kept optional so protocol-level stubs/tests can construct minimal
    # instances without needing full UI state.
    fill_mode: Optional[FillMode] = None
    manual_gas_mass_kg: Optional[float] = None
    mission_filter: Optional[MissionCategory] = None

    # Extra GUI-provided metadata for audit / tracking.
    context_data: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class LaunchResponse:
    """Result payload produced by a GUI adapter after launching an activity."""

    activity_id: str
    state: str

    # UI-rendered outcome payload.
    # Implementations should return JSON-serializable data.
    view: Optional[JsonObject] = None

    error: Optional[str] = None


@dataclass(frozen=True)
class StatusResponse:
    """Status payload for a previously-launched activity."""

    state: Optional[str]
    view: Optional[JsonObject] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class RecoverResponse:
    """Recovery payload produced by a GUI adapter."""

    ok: bool
    from_activity_id: str
    recovered_activity_id: str

    state: Optional[str] = None
    view: Optional[JsonObject] = None
    error: Optional[str] = None


@runtime_checkable
class GuiAdapter(Protocol):
    """Backend adapter interface that a web/mobile GUI can implement.

    Implementations are responsible for:
    - storing per-actor mission design intents
    - translating UI inputs into transport-neutral requests
    - invoking controller/session logic
    - returning JSON-serializable view payloads for the front-end
    """

    def set_mission_design(
        self,
        actor_id: ActorId,
        *,
        gas_id: str,
        envelope_id: str,
        balloon_size: str,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: str = "default",
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> MissionDesignIntent: ...

    async def launch(
        self,
        actor_id: ActorId,
        *,
        payload_ids: Optional[Tuple[str, ...]] = None,
        launch_site_id: Optional[str] = None,
        fill_mode: Optional[FillMode] = None,
        manual_gas_mass_kg: Optional[float] = None,
        mission_filter: Optional[MissionCategory] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> LaunchResponse: ...

    def status(self, activity_id: str) -> StatusResponse: ...

    async def recover(self, actor_id: ActorId, activity_id: str) -> RecoverResponse: ...


__all__ = [
    "ActorId",
    "MissionDesignIntent",
    "LaunchResponse",
    "StatusResponse",
    "RecoverResponse",
    "GuiAdapter",
]
