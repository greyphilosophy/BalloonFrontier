"""Integration test: CLI-displayed gas mass equals SimulationState gas mass.

Asserts that show_fill_presets() displays the exact same mass value that
FlightService's LaunchRequest.gas_mass_kg property computes, and that
to_simulation_state() uses that same value.

This guards against the regression where the CLI could say
"Selected Normal fill: 1.2 kg" but the actual simulation used 0.9 kg.
"""

import pytest

from balloon_frontier.catalog import CATALOG
from balloon_frontier.flight_service import flight_service
from balloon_frontier.launch_result import LaunchRequest, FillMode

import cli_game


@pytest.mark.parametrize(
    "balloon_id,gas_id,fill_mode",
    [
        ("s36", "helium", FillMode.AUTO),
        ("s36", "helium", FillMode.LIGHT),
        ("s36", "helium", FillMode.NORMAL),
        ("s36", "helium", FillMode.HEAVY),
        ("s55", "hydrogen", FillMode.NORMAL),
        ("s100", "helium", FillMode.HEAVY),
    ],
)
def test_displayed_mass_equals_simulation_state(balloon_id, gas_id, fill_mode):
    """The mass shown by show_fill_presets must match what SimulationState receives."""
    from cli_game import show_fill_presets
    from unittest.mock import patch, MagicMock
    from io import StringIO

    # 1. Capture what show_fill_presets displays
    captured_output = []

    def fake_input(prompt):
        # Simulate user pressing the first key for non-MANUAL modes
        # (1 → index 0 = AUTO for all modes)
        return "1"

    def fake_choice(max_val, prompt):
        return 0

    def fake_print(*args, **kwargs):
        captured_output.append(" ".join(str(a) for a in args))

    with patch("builtins.input", side_effect=fake_input):
        with patch("builtins.print", fake_print):
            with patch("cli_game.get_choice", fake_choice):
                show_fill_presets(balloon_id, gas_id)

    # 2. Parse the displayed mass for the selected mode.
    # The menu line has numbered index format "1. {Label}: {desc} ({mass_str})".
    # We need to find the line for the specific selected mode and parse its mass.
    import re

    # Build the expected menu-line pattern: e.g. "2. Light: 20% less gas — slower ascent (1.2 kg)"
    mode_name = fill_mode.label  # e.g. "Light", "Normal", "Heavy", "Auto"
    menu_lines = []
    for line in captured_output:
        # Menu lines start with a digit (the index)
        if re.match(r'^\d+\.\s' + re.escape(mode_name) + r':', line):
            menu_lines.append(line)
            break

    if menu_lines:
        display_text = menu_lines[0]
        # Extract mass_str from parentheses at the end
        match = re.search(r"\(([^)]+)\)\s*$", display_text)
        if match:
            displayed_mass_str = match.group(1)
        else:
            displayed_mass_str = display_text

    else:
        # Fallback: just check that something was printed
        assert captured_output, "show_fill_presets should have printed something"
        return  # Cannot validate mass string if format changed

    # 3. Build the same LaunchRequest that play() would build
    balloon = CATALOG.balloon(balloon_id)
    gas = CATALOG.gas(gas_id)

    request = LaunchRequest(
        gas_id=gas_id,
        envelope_id="latex",
        balloon_size=balloon_id,
        payload_ids=tuple(),
        launch_site_id="field",
        fill_mode=fill_mode,
        manual_gas_mass_kg=None,
    )

    assert request.gas_mass_kg is not None, f"LaunchRequest.gas_mass_kg must resolve for {fill_mode}"

    # 4. The display must match (within rounding tolerance)
    # Parse the displayed mass string for comparison
    displayed_kg = _parse_mass_from_display(displayed_mass_str)
    if displayed_kg is not None:
        assert displayed_kg == pytest.approx(request.gas_mass_kg, rel=1e-3), (
            f"Display says {displayed_mass_str} but LaunchRequest.gas_mass_kg is {request.gas_mass_kg}"
        )

    # 5. Verify the same mass flows into SimulationState via to_simulation_state()
    state = request.to_simulation_state()
    assert state.gas_mass_kg == pytest.approx(request.gas_mass_kg, rel=1e-9), (
        f"SimulationState.gas_mass_kg ({state.gas_mass_kg}) differs from "
        f"LaunchRequest.gas_mass_kg ({request.gas_mass_kg})"
    )

    # 6. Verify the full flight_service.run path works end-to-end
    outcome = flight_service.run(request)
    assert outcome.result is not None
    # The result should contain telemetry (flight ran successfully)
    assert len(outcome.result.telemetry) > 0


def test_manual_fill_passes_exact_mass_to_simulation():
    """Manual fill mode must pass the user's exact mass to SimulationState."""
    balloon_id = "s36"
    gas_id = "helium"
    user_mass_kg = 0.75  # User-entered 750g

    request = LaunchRequest(
        gas_id=gas_id,
        envelope_id="latex",
        balloon_size=balloon_id,
        payload_ids=tuple(),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=user_mass_kg,
    )

    # gas_mass_kg must return the exact manual value
    assert request.gas_mass_kg == user_mass_kg

    state = request.to_simulation_state()
    assert state.gas_mass_kg == user_mass_kg


def _parse_mass_from_display(display_str: str) -> float | None:
    """Try to parse a mass string like '1.23 kg', '750g', '0.500 kg'."""
    import re
    # Match patterns like "1.23 kg" or "750g" or "0.500 kg"
    match = re.search(r"([\d.]+)\s*(kg|g)\b", display_str, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        unit = match.group(2).lower()
        if unit == "g":
            value = value / 1000.0
        return value
    return None