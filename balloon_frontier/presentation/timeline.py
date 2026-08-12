"""Deterministic telemetry compression for short launch montages."""

from collections.abc import Iterable, Mapping
from typing import Any

from .flight_moment import FlightEvent, FlightMoment, FlightPhase

MAX_PRESENTATION_FRAMES = 24
_MIN_ASCENT_M = 0.1


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


def _final_phase(point: Any) -> FlightPhase:
    if bool(_value(point, "crashed", default=False)):
        return FlightPhase.CRASHED
    if bool(_value(point, "landed", default=False)):
        return FlightPhase.LANDED
    return FlightPhase.COMPLETE


def build_flight_moments(
    telemetry: Iterable[Any],
    max_frames: int = 7,
) -> list[FlightMoment]:
    """Select representative telemetry while preserving important flight events.

    The older Discord message-edit animation capped this at nine frames to reduce
    API traffic. GIF and local-terminal playback do not have that constraint, so
    callers can now request up to 24 representative moments.
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
    start_altitude = altitudes[0]

    # Failed/grounded launches should not fabricate LIFTOFF or APOGEE merely
    # because telemetry contains more than one sample. Keep only the real start
    # and terminal state for a flat flight.
    if peak <= start_altitude + _MIN_ASCENT_M:
        final = _moment(points[-1], peak, _final_phase(points[-1]))
        if len(points) == 1:
            return [final]
        return [
            _moment(points[0], peak, FlightPhase.PRELAUNCH),
            final,
        ]

    selected: dict[int, list[tuple[FlightPhase, FlightEvent | None]]] = {}

    def add(index: int, phase: FlightPhase, event: FlightEvent | None = None) -> None:
        entry = (phase, event)
        entries = selected.setdefault(index, [])
        if entry not in entries:
            entries.append(entry)

    add(0, FlightPhase.PRELAUNCH)

    liftoff_index = next(
        (
            index
            for index in range(1, len(points))
            if altitudes[index] > start_altitude + _MIN_ASCENT_M
            or float(_value(points[index], "velocity_mps", "vel", default=0.0)) > 0.1
        ),
        None,
    )
    if liftoff_index is not None:
        add(liftoff_index, FlightPhase.ASCENT, FlightEvent.LIFTOFF)

    add(peak_index, FlightPhase.APOGEE, FlightEvent.PEAK_ALTITUDE)

    for index, point in enumerate(points):
        if bool(_value(point, "burst", default=False)):
            add(index, FlightPhase.BURST)
            break

    final_index = len(points) - 1
    add(final_index, _final_phase(points[-1]))

    for threshold, event in (
        (800.0, FlightEvent.CLOUD_ENTRY),
        (12000.0, FlightEvent.ENTER_STRATOSPHERE),
    ):
        crossing = next(
            (index for index, altitude in enumerate(altitudes) if altitude >= threshold),
            None,
        )
        if crossing is not None:
            add(crossing, FlightPhase.ASCENT, event)

    candidates = [
        index
        for index in (
            list(range(1, peak_index))
            + list(range(peak_index + 1, final_index))
        )
        if index not in selected
    ]

    def count() -> int:
        return sum(len(entries) for entries in selected.values())

    while count() < max_frames and candidates:
        existing = sorted(selected)
        best = max(
            candidates,
            key=lambda index: min(abs(index - chosen) for chosen in existing),
        )
        add(
            best,
            FlightPhase.ASCENT if best < peak_index else FlightPhase.DESCENT,
        )
        candidates.remove(best)

    indexes = sorted(selected)
    mandatory = {
        0,
        peak_index,
        final_index,
    }
    if liftoff_index is not None:
        mandatory.add(liftoff_index)
    mandatory |= {
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
