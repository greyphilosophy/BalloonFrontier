"""Transport-neutral flight and animation state."""

from dataclasses import dataclass
from enum import Enum


class FlightPhase(str, Enum):
    PRELAUNCH = "prelaunch"
    ASCENT = "ascent"
    APOGEE = "apogee"
    BURST = "burst"
    DESCENT = "descent"
    LANDED = "landed"
    CRASHED = "crashed"
    COMPLETE = "complete"


class FlightEvent(str, Enum):
    LIFTOFF = "liftoff"
    CLOUD_ENTRY = "cloud_entry"
    CLOUD_EXIT = "cloud_exit"
    ENTER_STRATOSPHERE = "enter_stratosphere"
    PEAK_ALTITUDE = "peak_altitude"


@dataclass(frozen=True)
class FlightMoment:
    time_s: float
    altitude_m: float
    velocity_mps: float
    peak_altitude_m: float
    phase: FlightPhase
    event: FlightEvent | None = None
    burst: bool = False
    landed: bool = False
    crashed: bool = False


@dataclass(frozen=True)
class RenderFrame:
    moment: FlightMoment
    animation_tick: int = 0
    balloon_offset_x: int = 0
    cloud_offset_x: int = 0
    star_phase: int = 0
    event_emphasis: bool = False
