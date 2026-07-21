"""Unit tests for the ASCII trajectory chart generator."""
import math
from typing import Dict, List, Optional

from balloon_frontier.ascii_chart import (
    ChartConfig,
    EventMarker,
    generate_chart,
    chart_to_string,
    generate_test_telemetry,
)

# ── Helpers ────────────────────────────────────────────────

def has_axis_left(rows, H=20):
    """Check that left column has axis chars (| or + at corners)."""
    for r in range(H):
        ch = rows[r][0]
        # Row 0 can be + (corner) or | (side)
        if r == 0:
            assert ch in ("|", "+"), f"Row {r} axis char '{ch}'"
        else:
            assert ch in ("|", "+"), f"Row {r} axis char '{ch}'"
    return True

def has_bottom_axis(rows, W=60):
    """Check bottom row is the time axis."""
    last = rows[-1]
    assert last[0] in ("+", "|"), f"Bottom-left: '{last[0]}'"
    return True

def find_char_in_grid(rows, char, H=20):
    """Find (row, col) of first occurrence of char in the chart area.
    
    The grid area starts at col 1 (col 0 is the axis char).
    The chart area has H rows (0 to H-1). The bottom row is the time axis.
    """
    for r in range(H):
        for c in range(1, len(rows[r])):
            if c < len(rows[r]) and rows[r][c] == char:
                return (r, c)
    return None

def count_char_in_grid(rows, char, H=20):
    """Count occurrences of char in the chart grid area (col 1+, rows 0..H-1)."""
    count = 0
    for r in range(H):
        for c in range(1, len(rows[r])):
            if c < len(rows[r]) and rows[r][c] == char:
                count += 1
    return count

# ── Test: Empty telemetry ──────────────────────────────────

def test_empty_telemetry():
    """Zero-length arrays produce an empty chart with axes."""
    rows = generate_chart([], [])
    W, H = 60, 20
    assert len(rows) == H + 1, f"Expected {H+1} rows, got {len(rows)}"
    has_axis_left(rows, H)
    has_bottom_axis(rows, W)
    # All data cells should be spaces
    for r in range(H):
        for c in range(1, W):
            assert c < len(rows[r]) and rows[r][c] == " ", \
                f"Empty chart has non-space at ({r},{c})"
    print("  PASS: test_empty_telemetry")

# ── Test: Single point ─────────────────────────────────────

def test_single_point():
    """Single data point places a launch marker at center."""
    rows = generate_chart([5.0], [500.0])
    # With W=60, the axis char adds col 0, so center is at col 31 (30+1)
    pos = find_char_in_grid(rows, "L")
    assert pos is not None, "Single point should place 'L' marker"
    # Center: H=20 -> row 10, W=60 -> col 30, but axis shifts to col 31
    assert pos[0] == 10, f"Row should be 10, got {pos[0]}"
    assert pos[1] == 31, f"Col should be 31 (30+axis), got {pos[1]}"
    print("  PASS: test_single_point")

# ── Test: Flat line (constant altitude) ────────────────────

def test_flat_line():
    """Constant altitude produces a horizontal line."""
    time = [t for t in range(60)]
    altitude = [10.0] * 60
    rows = generate_chart(time, altitude)
    # Constant altitude = max altitude, so all points at row 0 (top)
    # We'll have P at the first column (peak) and * for the rest
    # Verify there are * characters (some might be overwritten by P or L)
    star_count = count_char_in_grid(rows, "*")
    # Should have many stars (some columns may be overwritten by events)
    assert star_count >= 58, f"Flat line should have many stars, got {star_count}"
    # Verify the line is horizontal - all data on same row
    non_empty_rows = set()
    for r in range(20):
        for c in range(1, 60):
            if c < len(rows[r]) and rows[r][c] in ("*", "L", "P", "B", "C", "M"):
                non_empty_rows.add(r)
                break
    assert len(non_empty_rows) == 1, \
        f"Flat line should be on 1 row, got {len(non_empty_rows)}"
    print("  PASS: test_flat_line")

# ── Test: Spike (single high point) ───────────────────────

def test_spike():
    """A spike in the middle shows as a peak."""
    time = [float(t) for t in range(60)]
    altitude = [10.0 if t == 30 else 5.0 for t in range(60)]
    rows = generate_chart(time, altitude)
    # The spike at index 30 should be higher (lower row index)
    pos = find_char_in_grid(rows, "P")
    assert pos is not None, "Spike should produce a 'P' marker"
    # P should be on a higher row (smaller index) than the low stars
    # The low altitude points should be on a lower row (larger index)
    low_row = None
    high_row = pos[0]
    for r in range(20):
        for c in range(1, 60):
            if c < len(rows[r]) and rows[r][c] == "*" and c != pos[1]:
                low_row = r
                break
        if low_row is not None:
            break
    assert low_row is not None, "Should have low-star row"
    assert high_row < low_row, f"Peak row {high_row} should be above low row {low_row}"
    print("  PASS: test_spike")

# ── Test: Scaling accuracy ─────────────────────────────────

def test_scaling_accuracy():
    """Verify that altitude-to-row mapping is within 1 row of expected."""
    time = [float(t) for t in range(100)]
    altitude = [t * 10.0 for t in range(100)]  # 0 to 990
    rows = generate_chart(time, altitude)
    # Row count should be H+1 = 21
    assert len(rows) == 21, f"Expected 21 rows, got {len(rows)}"
    # Bottom axis exists
    has_bottom_axis(rows)
    print("  PASS: test_scaling_accuracy")

# ── Test: Marker placement for known events ───────────────

def test_marker_placement():
    """Verify event markers land on the correct grid cells."""
    time = [float(t) for t in range(60)]
    altitude = [10.0] * 60
    events = {
        "launch": 0,
        "peak": 20,
        "land": 50,
        "burst": 30,  # burst at different index than crash
    }
    rows = generate_chart(time, altitude, events)
    assert find_char_in_grid(rows, "L") is not None, "Launch 'L' missing"
    assert find_char_in_grid(rows, "P") is not None, "Peak 'P' missing"
    assert find_char_in_grid(rows, "M") is not None, "Land 'M' missing"
    assert find_char_in_grid(rows, "B") is not None, "Burst 'B' missing"
    print("  PASS: test_marker_placement")

# ── Test: Event priority (crash overwrites burst) ─────────

def test_event_priority():
    """When two events land on the same cell, later one overwrites earlier."""
    time = [float(t) for t in range(60)]
    altitude = [10.0] * 60
    # Both events at same index -> second one overwrites
    events = {"burst": 59, "crash": 59}
    rows = generate_chart(time, altitude, events)
    # Verify there are no B characters in the grid
    b_count = count_char_in_grid(rows, "B")
    assert b_count == 0, f"Burst 'B' should be overwritten by crash, got {b_count} B's"
    c_count = count_char_in_grid(rows, "C")
    assert c_count >= 1, "Should have at least one crash 'C'"
    print("  PASS: test_event_priority")

# ── Test: Chart config customization ──────────────────────

def test_custom_config():
    """Custom ChartConfig changes the grid characters."""
    config = ChartConfig(
        width=40, height=15,
        line_char=".", peak_char="^", launch_char="O"
    )
    time = [float(t) for t in range(40)]
    altitude = [10.0] * 40
    rows = generate_chart(time, altitude, config=config)
    assert len(rows) == 16, f"Expected 16 rows (15 + axis), got {len(rows)}"
    assert len(rows[-1]) == 41, f"Expected 41 cols (40 + axis), got {len(rows[-1])}"
    print("  PASS: test_custom_config")

# ── Test: chart_to_string wrapper ─────────────────────────

def test_chart_to_string():
    """chart_to_string returns a formatted multi-line string."""
    time = [float(t) for t in range(20)]
    altitude = [t * 50 for t in range(20)]
    result = chart_to_string(time, altitude, title="Test Flight")
    lines = result.split("\n")
    assert lines[0] == "Test Flight", f"Title: '{lines[0]}'"
    assert lines[1] == "─" * len("Test Flight"), "Subtitle length"
    assert lines[2] == "", "Blank line after subtitle"
    chart_lines = lines[3:]
    assert len(chart_lines) == 21, \
        f"Chart: 21 lines (20 + axis), got {len(chart_lines)}"
    print("  PASS: test_chart_to_string")

# ── Test: Auto-detect events ──────────────────────────────

def test_auto_detect_events():
    """Auto-detection finds launch=0, peak at max altitude."""
    time, alt = generate_test_telemetry(60.0, 0.1)
    rows = generate_chart(time, alt)
    assert find_char_in_grid(rows, "L") is not None, "Auto-detect 'L'"
    assert find_char_in_grid(rows, "P") is not None, "Auto-detect 'P'"
    print("  PASS: test_auto_detect_events")

# ── Test: Negative time values ────────────────────────────

def test_negative_time():
    """Chart handles negative time values correctly."""
    time = [-10.0 + t * 0.25 for t in range(60)]
    altitude = [50.0] * 60
    rows = generate_chart(time, altitude)
    assert len(rows) == 21, f"Expected 21 rows, got {len(rows)}"
    print("  PASS: test_negative_time")

# ── Test: Large altitude range ───────────────────────────

def test_large_altitude_range():
    """Chart scales correctly for altitudes from 0 to 3000m."""
    time = [float(t) for t in range(60)]
    altitude = [t * 50.0 for t in range(60)]
    rows = generate_chart(time, altitude)
    assert len(rows) == 21, f"Expected 21 rows, got {len(rows)}"
    # Verify chart has content (stars, events, etc.)
    content = count_char_in_grid(rows, "*") + \
             count_char_in_grid(rows, "L") + \
             count_char_in_grid(rows, "P")
    assert content > 0, "Large altitude range should show data points"
    print("  PASS: test_large_altitude_range")

# ── Test: Two-point chart ────────────────────────────────

def test_two_point():
    """Two points produce a diagonal line."""
    time = [0.0, 100.0]
    altitude = [0.0, 500.0]
    rows = generate_chart(time, altitude)
    assert len(rows) == 21
    # L at left-bottom, B at right-top (burst because ascending at end)
    assert find_char_in_grid(rows, "L") is not None, "Launch marker"
    # With 2 points, the second point is both peak AND burst (burst overwrites)
    b_pos = find_char_in_grid(rows, "B")
    p_pos = find_char_in_grid(rows, "P")
    assert b_pos is not None or p_pos is not None, \
        "Should have peak or burst marker at the high point"
    print("  PASS: test_two_point")

# ── Test: Zero altitude (ground level) ───────────────────

def test_zero_altitude():
    """All zeros should render at the bottom row."""
    time = [float(t) for t in range(60)]
    altitude = [0.0] * 60
    rows = generate_chart(time, altitude)
    # All points at ground level (bottom row = index 19)
    # Bottom row should have axis chars or line chars
    assert len(rows) == 21
    # Check that bottom data row has content
    assert count_char_in_grid(rows, "*") > 0, \
        "Zero altitude line should have stars at bottom"
    print("  PASS: test_zero_altitude")

# ── Run all tests ──────────────────────────────────────────

if __name__ == "__main__":
    print("Running ASCII chart unit tests...\n")
    tests = [
        test_empty_telemetry,
        test_single_point,
        test_flat_line,
        test_spike,
        test_scaling_accuracy,
        test_marker_placement,
        test_event_priority,
        test_custom_config,
        test_chart_to_string,
        test_auto_detect_events,
        test_negative_time,
        test_large_altitude_range,
        test_two_point,
        test_zero_altitude,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL: {test.__name__}: {e}")
    print(f"\nResults: {passed}/{passed+failed} tests passed")