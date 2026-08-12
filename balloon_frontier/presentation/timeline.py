"""Deterministic telemetry compression for short launch montages."""

from collections.abc import Iterable, Mapping
from typing import Any

from .flight_moment import FlightEvent, FlightMoment, FlightPhase

MAX_PRESENTATION_FRAMES = 24


def _value(point: Any, *names: str, default: Any = None) -> Any:
    if isinstance(point, Mapping):
        for name in names:
            if name in point:
                return point[name]
    for name in names:
        if hasattr(point, name):
            return getattr(point, name)
    return default


def _moment(
    point: Any,
    peak: float,
    phase: FlightPhase,
    event: FlightEvent | None = None,
) -> FlightMoment:
    return FlightMoment(
        float(_value(point, "time_s", "time", default=0.0)),
        max(0.0, float(_value(point, "altitude_m", "alt", default=0.0))),
        float(_value(point, "velocity_mps", "vel", default=0.0)),
        peak,
        phase,
        event,
        bool(_value(point, "burst", default=False)),
        bool(_value(point, "landed", default=False)),
        bool(_value(point, "crashed", default=False)),
    )


def build_flight_moments(
    telemetry: Iterable[Any],
    max_frames: int = 7,
) -> list[FlightMoment]:
    """Select representative telemetry while preserving important flight events.

    The older Discord message-edit animation capped this at nine frames to reduce
    API traffic.  GIF and local-terminal playback do not have that constraint,
    so callers can now request up to 24 representative moments.
    """

    points = list(telemetry)
    if not points:
        return [FlightMoment(0, 0, 0, 0, FlightPhase.COMPLETE)]

    max_frames = min(MAX_PRESENTATION_FRAMES, max(4, int(max_frames)))
    altitudes = [
        max(0.0, float(_value(point, "altitude_m", "alt", default=0.0)))
        for point in points
    ]
    peak_index = max(range(len(points)), key=altitudes.__getitem__)
    peak = altitudes[peak_index]
    selected = {
        0: [(FlightPhase.PRELAUNCH, None)],
        peak_index: [(FlightPhase.APOGEE, FlightEvent.PEAK_ALTITUDE)],
        len(points) - 1: [(FlightPhase.COMPLETE, None)],
    }
    if len(points) > 1:
        selected[1] = [(FlightPhase.ASCENT, FlightEvent.LIFTOFF)]

    for index, point in enumerate(points):
        if bool(_value(point, "burst", default=False)):
            selected.setdefault(index, []).append((FlightPhase.BURST, None))
            break

    final = points[-1]
    if bool(_value(final, "crashed", default=False)):
        selected[len(points) - 1] = [(FlightPhase.CRASHED, None)]
    elif bool(_value(final, "landed", default=False)):
        selected[len(points) - 1] = [(FlightPhase.LANDED, None)]

    for threshold, event in (
        (800.0, FlightEvent.CLOUD_ENTRY),
        (12000.0, FlightEvent.ENTER_STRATOSPHERE),
    ):
        crossing = next(
            (index for index, altitude in enumerate(altitudes) if altitude >= threshold),
            None,
        )
        if crossing is not None:
            selected.setdefault(crossing, [(FlightPhase.ASCENT, event)])

    candidates = list(range(1, peak_index)) + list(
        range(peak_index + 1, len(points) - 1)
    )

    def count() -> int:
        return sum(len(entries) for entries in selected.values())

    while count() < max_frames and candidates:
        existing = sorted(selected)
        best = max(
            candidates,
            key=lambda index: min(abs(index - chosen) for chosen in existing),
        )
        selected[best] = [
            (
                FlightPhase.ASCENT if best < peak_index else FlightPhase.DESCENT,
                None,
            )
        ]
        candidates.remove(best)

    indexes = sorted(selected)
    mandatory = {
        0,
        1 if len(points) > 1 else 0,
        peak_index,
        len(points) - 1,
    } | {
        index
        for index, entries in selected.items()
        if any(event is not None for _, event in entries)
    }
    removable = [index for index in indexes if index not in mandatory]
    while count() > max_frames and removable:
        removed = removable.pop(len(removable) // 2)
        indexes.remove(removed)
        selected.pop(removed, None)

    return [
        _moment(points[index], peak, phase, event)
        for index in indexes
        for phase, event in selected[index]
    ]
