"""Balloon Frontier - ASCII Trajectory Chart Generator

Generates an ASCII art chart from flight telemetry data (time, altitude)
with event markers (launch, peak, burst, crash, land).

Grid size: 60 columns (X = time) x 20 rows (Y = altitude).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ChartConfig:
    """Configuration for the ASCII trajectory chart."""
    width: int = 60  # columns (X-axis: time)
    height: int = 20  # rows (Y-axis: altitude)
    line_char: str = "*"
    peak_char: str = "P"
    launch_char: str = "L"
    burst_char: str = "B"
    crash_char: str = "C"
    land_char: str = "M"  # "M" for gentle landing (meadow)
    grid_line_char: str = "·"  # subtle grid intersection
    axis_char: str = "+"
    altitude_axis_char: str = "|"
    time_axis_char: str = "—"
    empty_char: str = " "


@dataclass
class EventMarker:
    """A single event on the trajectory chart."""
    time_idx: int  # index in the time/altitude arrays
    char: str
    label: str  # human-readable label (e.g. "PEAK", "BURST")


def generate_chart(
    time: List[float],
    altitude: List[float],
    events: Optional[Dict[str, int]] = None,
    config: Optional[ChartConfig] = None,
) -> List[str]:
    """Generate an ASCII trajectory chart from flight telemetry.

    Args:
        time: Array of time values in seconds.
        altitude: Array of altitude values in meters (aligned with time).
        events: Optional dict mapping event names to indices in the arrays.
            Valid keys: "launch", "peak", "burst", "crash", "land".
            If not provided, events are auto-detected from the data.
        config: Optional chart configuration. Uses defaults if None.

    Returns:
        List of strings, one per row (top-to-bottom, highest altitude first).
    """
    if config is None:
        config = ChartConfig()

    W = config.width
    H = config.height
    N = len(time)

    # Handle edge cases
    if N == 0:
        return _empty_chart(W, H, config)

    if N == 1:
        return _single_point_chart(W, H, time[0], altitude[0], config)

    # Auto-detect events if not provided
    if events is None:
        events = _detect_events(time, altitude)

    # Scale data to grid coordinates
    grid = _build_grid(W, H, time, altitude, config)

    # Place event markers on the grid
    grid = _place_events(grid, time, altitude, events, W, H, config)

    # Render rows with axes
    return _render_grid(grid, W, H, time, altitude, config)


def _empty_chart(W: int, H: int, config: ChartConfig) -> List[str]:
    """Return a mostly empty chart for zero-length telemetry."""
    rows = []
    for r in range(H):
        row = list(config.empty_char * W)
        # Left axis
        row[0] = config.axis_char if r == 0 else config.altitude_axis_char
        rows.append("".join(row))
    # Bottom axis
    bottom = list(config.empty_char * W)
    bottom[0] = config.axis_char
    for i in range(1, W):
        bottom[i] = config.time_axis_char
    rows.append("".join(bottom))
    return rows


def _single_point_chart(W: int, H: int, t: float, alt: float, config: ChartConfig) -> List[str]:
    """Return a chart with just one point (and a launch marker)."""
    grid = [[config.empty_char for _ in range(W)] for _ in range(H)]
    # With a single point, place it centered in the chart
    gx = W // 2
    gy = H // 2
    grid[gy][gx] = config.launch_char
    return _render_grid(grid, W, H, [t], [alt], config)


def _detect_events(
    time: List[float],
    altitude: List[float],
) -> Dict[str, int]:
    """Auto-detect event indices from telemetry arrays."""
    events = {}
    N = len(altitude)

    # Launch: first index
    events["launch"] = 0

    # Peak: index of maximum altitude
    peak_idx = max(range(N), key=lambda i: altitude[i])
    events["peak"] = peak_idx

    # Burst: last index if final altitude > 0 (balloon kept going up)
    # Crash: last index if altitude dropped to 0 with negative velocity
    # Land: last index if altitude reached 0 with slow descent
    last = N - 1
    if last > 0:
        if altitude[last] == 0:
            # Check if it came from above
            if altitude[last - 1] > 0:
                # Simple heuristic: if altitude dropped quickly, it's a crash
                drop = altitude[last - 1]
                time_diff = time[last] - time[last - 1] if time[last] != time[last - 1] else 1
                speed = drop / time_diff
                if speed > 15.0:
                    events["crash"] = last
                else:
                    events["land"] = last
        elif altitude[last] > 0 and last > 0 and altitude[last] > altitude[last - 1]:
            # Still ascending at end — treat as burst
            events["burst"] = last

    return events


def _build_grid(
    W: int, H: int,
    time: List[float],
    altitude: List[float],
    config: ChartConfig,
) -> List[List[str]]:
    """Build a 2D character grid from telemetry data."""
    grid = [[config.empty_char for _ in range(W)] for _ in range(H)]

    N = len(time)
    t_min = time[0]
    t_max = time[-1]
    alt_max = max(altitude) if altitude else 0.0

    for i in range(N):
        # Map time index to X coordinate (0 to W-1)
        if t_max > t_min:
            gx = int((i / (N - 1)) * (W - 1))
        else:
            gx = 0

        # Map altitude to Y coordinate (H-1 = ground, 0 = top)
        if alt_max > 0:
            gy = H - 1 - int((altitude[i] / alt_max) * (H - 1))
        else:
            gy = H - 1

        # Clamp to grid
        gx = max(0, min(W - 1, gx))
        gy = max(0, min(H - 1, gy))

        # Place point (higher priority overwrites lower)
        grid[gy][gx] = config.line_char

    return grid


def _place_events(
    grid: List[List[str]],
    time: List[float],
    altitude: List[float],
    events: Dict[str, int],
    W: int, H: int,
    config: ChartConfig,
) -> List[List[str]]:
    """Place event marker characters on the grid."""
    N = len(time)
    t_min = time[0]
    t_max = time[-1]
    alt_max = max(altitude) if altitude else 0.0

    marker_map = {
        "burst": config.burst_char,
        "crash": config.crash_char,
        "land": config.land_char,
        "peak": config.peak_char,
        "launch": config.launch_char,
    }

    for event_name, idx in events.items():
        if idx < 0 or idx >= N:
            continue

        marker = marker_map.get(event_name)
        if not marker:
            continue

        # Map to grid coordinates
        if t_max > t_min and N > 1:
            gx = int((idx / (N - 1)) * (W - 1))
        else:
            gx = 0

        if alt_max > 0:
            gy = H - 1 - int((altitude[idx] / alt_max) * (H - 1))
        else:
            gy = H - 1

        gx = max(0, min(W - 1, gx))
        gy = max(0, min(H - 1, gy))

        # Overwrite with event marker
        grid[gy][gx] = marker

    return grid


def _render_grid(
    grid: List[List[str]],
    W: int, H: int,
    time: List[float],
    altitude: List[float],
    config: ChartConfig,
) -> List[str]:
    """Render the 2D grid into a list of strings with axes."""
    rows = []

    # Add altitude axis on the left
    for r in range(H):
        row = [config.altitude_axis_char] + list(grid[r])
        rows.append("".join(row))

    # Add time axis at the bottom
    bottom = [config.axis_char] + [config.time_axis_char] * W
    rows.append("".join(bottom))

    return rows


def chart_to_string(
    time: List[float],
    altitude: List[float],
    events: Optional[Dict[str, int]] = None,
    config: Optional[ChartConfig] = None,
    title: str = "Flight Trajectory",
) -> str:
    """Generate the ASCII chart and return it as a formatted string.

    Convenience wrapper around `generate_chart` that adds a title
    and joins rows with newlines.

    Args:
        time: Time array in seconds.
        altitude: Altitude array in meters.
        events: Optional event indices.
        config: Optional chart config.
        title: Chart title string.

    Returns:
        Formatted multi-line string of the chart.
    """
    chart = generate_chart(time, altitude, events, config)
    lines = [title, "─" * len(title), ""]
    lines.extend(chart)
    return "\n".join(lines)


# ── Test utilities ─────────────────────────────────────────

def generate_test_telemetry(duration: float = 60.0, dt: float = 0.1) -> Tuple[List[float], List[float]]:
    """Generate simple test telemetry (parabolic flight)."""
    import math
    time = []
    altitude = []
    t = 0.0
    while t <= duration:
        time.append(t)
        # Simple parabolic arc: altitude = sin(t * π / duration) * 1000
        alt = max(0, math.sin(t * math.pi / duration) * 1000)
        altitude.append(alt)
        t += dt
    return time, altitude


if __name__ == "__main__":
    # Quick demo
    time, alt = generate_test_telemetry(60.0, 0.1)
    print(chart_to_string(time, alt, title="Balloon Flight Trajectory"))
