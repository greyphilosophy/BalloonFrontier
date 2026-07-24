#!/usr/bin/env python3
"""Balloon Frontier — CLI Game

Playable balloon building simulator with realistic sizing.

Usage:
    python3 cli_game.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.flight_service import flight_service, FlightOutcome
from balloon_frontier.launch_result import LaunchRequest, FillMode
from balloon_frontier.catalog import CATALOG


def format_mass_kg(mass_kg):
    """Format mass in kg with sensible precision."""
    if mass_kg < 1.0:
        return f"{mass_kg * 1000:.1f}g"
    elif mass_kg < 100:
        return f"{mass_kg:.3f} kg"
    else:
        return f"{mass_kg:.2f} kg"


def format_kg_compact(mass_kg: float) -> str:
    """Compact kg number formatting for UI ranges.

    Examples:
      - 0.03 -> "0.03"
      - 0.5  -> "0.5"
    """
    abs_val = abs(mass_kg)
    if abs_val < 0.1:
        s = f"{mass_kg:.2f}"
    elif abs_val < 1.0:
        s = f"{mass_kg:.1f}"
    else:
        s = f"{mass_kg:.2f}"
    return s.rstrip("0").rstrip(".")


def show_fill_presets(balloon_key, gas_type):
    """Show fill mode selection UI with presets and manual option.

    Uses LaunchRequest to compute all displayed masses from a single
    authoritative source: LaunchRequest.gas_mass_kg.  The same object
    is then reused for the final launch.
    """
    balloon = CATALOG.balloon(balloon_key)
    gas = CATALOG.gas(gas_type)

    while True:
        print("\n  Fill mode:")
        print("  ─────────────────────────────────────────────")

        for i, mode in enumerate(FillMode, start=1):
            label = mode.label
            desc = mode.description

            try:
                if mode == FillMode.MANUAL:
                    mass_str = "You choose"
                else:
                    # Build a one-shot request just to read gas_mass_kg
                    display_req = LaunchRequest(
                        gas_id=gas_type,
                        envelope_id="latex",
                        balloon_size=balloon_key,
                        payload_ids=tuple(),
                        launch_site_id="field",
                        fill_mode=mode,
                        manual_gas_mass_kg=None,
                    )
                    mass_str = format_mass_kg(display_req.gas_mass_kg)

                print(f"  {i}. {label}: {desc} ({mass_str})")
            except Exception as e:
                print(f"  {i}. {label}: {desc} (error: {e})")

        print()
        idx = get_choice(len(FillMode), f"Fill mode (1-{len(FillMode)})")
        if idx is None:
            return None, None

        selected_mode = list(FillMode)[idx]

        if selected_mode == FillMode.MANUAL:
            print("\n  Enter gas mass in grams:")
            raw = input("  Mass (g) > ").strip()
            if raw.lower() in ("q", "quit"):
                return None, None
            try:
                gas_mass_g = float(raw)
                gas_mass_kg = gas_mass_g / 1000.0
            except ValueError:
                print("  Invalid input. Try again.")
                continue
            print(f"\n  Selected manual fill: {format_mass_kg(gas_mass_kg)}")
            return selected_mode, gas_mass_kg
        else:
            # Use the mass computed by LaunchRequest.gas_mass_kg above.
            # We built a temp request already, but need to recompute since
            # we may have cycled through multiple modes.
            mass_request = LaunchRequest(
                gas_id=gas_type,
                envelope_id="latex",
                balloon_size=balloon_key,
                payload_ids=tuple(),
                launch_site_id="field",
                fill_mode=selected_mode,
                manual_gas_mass_kg=None,
            )
            gas_mass_kg = mass_request.gas_mass_kg
            print(f"\n  Selected {selected_mode.value} fill: {format_mass_kg(gas_mass_kg)}")
            return selected_mode, gas_mass_kg


def show_balloon_menu():
    """Display balloon selection menu and return the chosen balloon key."""
    print("\n  Balloon size:")
    print("  ─────────────────────────────────────────────")
    balloons = [b for b in CATALOG.all_balloons() if b.id not in ("s21", "s29")]
    for i, balloon in enumerate(balloons):
        print(f"  {i+1}. {balloon.name} ({balloon.max_volume_m3:.1f}m³, burst@{balloon.burst_volume_m3:.1f}m³, {balloon.mass_kg*1000}g)")
    print()
    return get_balloon_choice(balloons)


def get_balloon_choice(balloons):
    """Prompt user for balloon size selection."""
    idx = get_choice(len(balloons), f"Balloon (1-{len(balloons)})")
    return balloons[idx].id if idx is not None else None


def show_gas_menu():
    """Display gas type selection menu and return the chosen gas type."""
    print("\n  Gas type:")
    print("  ─────────────────────────────────────────────")
    gases = CATALOG.all_gases()
    for i, gas in enumerate(gases):
        print(f"  {i+1}. {gas.name} (molar mass={gas.molar_mass:.4f} kg/mol, {gas.gas_behavior})")
    print()
    idx = get_choice(len(gases), "Gas (1-4)")
    return gases[idx].id if idx is not None else None


def show_payloads_menu():
    """Display payload selection menu and return chosen payload IDs."""
    print("\n  Select payloads (space-separated numbers, or 'done'):")
    print("  ─────────────────────────────────────────────")
    payloads = CATALOG.all_payloads()
    for i, payload in enumerate(payloads):
        valve_note = " 🛡️" if payload.has_valve else ""
        print(f"  {i+1}. {payload.name}  ({payload.mass_kg} kg){valve_note}")
    print()
    # Add "none" option
    print(f"  {len(payloads)+1}. None")
    print()
    selected = []
    while True:
        raw = input("  Payloads > ").strip()
        if raw == "done" or raw == "":
            return selected if selected else ["none"]
        if raw.lower() in ("q", "quit"):
            return ["none"]
        nums = raw.split()
        chosen = []
        for n in nums:
            try:
                idx = int(n) - 1
                if 0 <= idx < len(payloads):
                    chosen.append(payloads[idx].id)
                elif idx == len(payloads) and n == str(len(payloads)+1):
                    # "none" selected - clear and return
                    return ["none"]
            except ValueError:
                pass
        if not chosen:
            print("  Invalid selection. Try again.")
        else:
            return chosen


def show_site_menu():
    print("\n  Launch site:")
    print("  ─────────────────────────────────────────────")
    sites = CATALOG.all_sites()
    for i, site in enumerate(sites):
        print(f"  {i+1}. {site.name}")
    print()
    idx = get_choice(len(sites), "Launch site (1-3)")
    return sites[idx].id if idx is not None else None


def get_choice(max_val, prompt):
    """Prompt user for a numbered choice between 1 and max_val."""
    while True:
        raw = input(f"  {prompt} (1-{max_val}, q to quit) > ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        try:
            val = int(raw)
            if 1 <= val <= max_val:
                return val - 1
            else:
                print(f"  Please enter a number between 1 and {max_val}")
        except ValueError:
            print("  Invalid input. Try again.")


def show_results(outcome: FlightOutcome, balloon_key, gas_type, gas_mass, payloads):
    """Display flight results with medal and stats."""
    result = outcome.result

    # Check if valve was selected
    has_valve = any(pid == "valve" for pid in payloads if pid != "none")
    valve_note = " 🛡️" if has_valve else ""

    # Use score and medal computed by FlightService (no local recomputation)
    score = outcome.score
    medal_name = outcome.medal_name
    medal_emoji = outcome.medal_emoji

    print("\n  ╔═══════════════════════════════════════════════╗")
    print("  ║              🎈 FLIGHT RESULTS 🎈             ║")
    print("  ╚═══════════════════════════════════════════════╝")

    balloon = CATALOG.balloon(balloon_key)
    print(f"  Balloon:    {balloon.name} latex")

    gas = CATALOG.gas(gas_type)
    print(f"  Gas:        {gas.name} ({format_mass_kg(gas_mass)})")

    payload_names = []
    for pid in payloads:
        if pid == "none":
            continue
        p = CATALOG.payload(pid)
        payload_names.append(p.name)
    print(f"  Payloads:   {', '.join(payload_names)}{valve_note}")

    print(f"  Peak Alt:   {result.peak_altitude_m:.1f}m")
    print(f"  Flight Time: {result.duration_s:.1f}s")

    if result.burst:
        print(f"  Result:     💥 BURST")
    elif result.landed:
        print(f"  Result:     ✅ LANDED")
    if result.crashed:
        print(f"  Status:     💥 CRASHED!")

    print(f"  Score:      {score:.1f}")
    print(f"  Medal:      {medal_emoji} {medal_name}")

    # Show weather if available
    if outcome.weather:
        print(f"\n  Weather:    {outcome.weather.name or 'Clear'}")
        if outcome.weather.description:
            print(f"             {outcome.weather.description}")

    # Show missions and results if assigned
    if outcome.mission_assignment and outcome.mission_assignment.mission_ids:
        mission_ids = outcome.mission_assignment.mission_ids
        print(f"\n  Missions:   {', '.join(mission_ids)}")

        # Show detailed mission results
        for mr in outcome.mission_results:
            status = "✅" if mr.completed else "❌"
            reward_str = f" (+{mr.reward} credits)" if mr.reward else ""
            print(f"    {status} {mr.mission_id}{reward_str}: {mr.explanation}")


def play():
    """Run one game session."""
    print("\n  ╔═══════════════════════════════════════════════╗")
    print("  ║           🎈 BALLOON FRONTIER 🎈             ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("  Pick your balloon, gas, and payload!  (q to quit)\n")

    # 1. Balloon size
    balloon_key = show_balloon_menu()
    if balloon_key is None:
        return
    balloon = CATALOG.balloon(balloon_key)
    print(f"  Selected: {balloon.name} latex balloon")

    # 2. Gas type
    gas_type = show_gas_menu()
    if gas_type is None:
        return

    # 3. Fill mode selection with presets + computed mass display
    fill_mode, gas_mass = show_fill_presets(balloon_key, gas_type)
    if gas_mass is None:
        return

    # 4. Payloads
    payloads = show_payloads_menu()

    # 5. Launch site
    site_key = show_site_menu()
    if site_key is None:
        return

    # Safety warning (only for manual mode)
    if fill_mode == FillMode.MANUAL:
        fill_range = balloon.fill_range_g
        if gas_mass * 1000 > fill_range[1]:
            print(f"\n  ⚠️  WARNING: {gas_mass*1000:.0f}g exceeds safe fill ({fill_range[1]}g)!")
        if gas_mass * 1000 < fill_range[0]:
            print(f"\n  💡 TIP: {gas_mass*1000:.0f}g is below the typical fill range.")

    # Review
    print("\n  ─────────────────────────────────────────────────")
    print("  CONFIGURATION")
    print("  ─────────────────────────────────────────────────")
    print(f"  Balloon:  {balloon.name} latex")
    print(f"  Gas:      {gas_type} ({format_mass_kg(gas_mass)})")

    payload_names = []
    has_valve = False
    for pid in payloads:
        if pid == "none":
            continue
        p = CATALOG.payload(pid)
        payload_names.append(p.name)
        if p.has_valve:
            has_valve = True

    valve_note = " 🛡️ Valve equipped" if has_valve else ""
    print(f"  Payloads: {', '.join(payload_names)}{valve_note}")

    site = CATALOG.site(site_key)
    print(f"  Site:     {site.name}")
    print("  ─────────────────────────────────────────────────")

    resp = input("  Ready to launch? (y/n) > ").strip().lower()
    if resp not in ("y", "yes"):
        print("  See you next time!")
        return

    print("\n  🚀 Launching...\n")

    # Build LaunchRequest and run via FlightService
    launch_request = LaunchRequest(
        gas_id=gas_type,
        envelope_id="latex",  # Default envelope; overridden by balloon_size
        balloon_size=balloon_key,
        payload_ids=tuple(payloads),
        launch_site_id=site_key,
        fill_mode=fill_mode,
        manual_gas_mass_kg=gas_mass if fill_mode == FillMode.MANUAL else None,
    )

    try:
        outcome = flight_service.run(launch_request)
    except Exception as e:
        print(f"\n  ❌ Flight simulation failed: {e}")
        return

    show_results(outcome, balloon_key, gas_type, gas_mass, payloads)


def main():
    print("Welcome to Balloon Frontier! 🎈")
    print("Type 'q' at any prompt to exit.\n")
    play()
    while True:
        resp = input("  Play again? (y/n) > ").strip().lower()
        if resp in ("n", "no", "q", "quit", "exit"):
            print("Thanks for playing Balloon Frontier! 🎈\n")
            break
        play()


if __name__ == "__main__":
    main()