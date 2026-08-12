#!/usr/bin/env python3
"""Balloon Frontier CLI game with shared graphical-to-ANSI launch playback."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.catalog import CATALOG
from balloon_frontier.cli_ui.animator import TerminalFlightAnimator
from balloon_frontier.flight_service import FlightOutcome, flight_service
from balloon_frontier.game_modes import list_game_modes
from balloon_frontier.how_to_play import how_to_play_text
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.presentation import build_flight_moments
from balloon_frontier.session_adapters import SessionAwareFlightService


def format_mass_kg(mass_kg):
    if mass_kg < 1.0: return f"{mass_kg * 1000:.1f}g"
    if mass_kg < 100: return f"{mass_kg:.3f} kg"
    return f"{mass_kg:.2f} kg"


def get_choice(max_val, prompt):
    while True:
        raw = input(f"  {prompt} (1-{max_val}, q to quit) > ").strip()
        if raw.lower() in ("q", "quit", "exit"): return None
        try:
            val = int(raw)
            if 1 <= val <= max_val: return val - 1
            print(f"  Please enter a number between 1 and {max_val}")
        except ValueError:
            print("  Invalid input. Try again.")


def show_how_to_play():
    print("\n" + how_to_play_text().replace("**", ""))


def show_game_mode_menu():
    """Choose a playable mode, with How to Play as a non-mode menu action."""
    modes = list_game_modes()
    while True:
        print("\n  Choose an option:\n  " + "─" * 45)
        for i, mode in enumerate(modes, 1):
            print(f"  {i}. {mode.label}: {mode.description}")
        print(f"  {len(modes) + 1}. How to Play")
        idx = get_choice(len(modes) + 1, f"Option (1-{len(modes) + 1})")
        if idx is None:
            return None
        if idx == len(modes):
            show_how_to_play()
            continue
        return modes[idx]


def get_balloon_choice(balloons):
    """Return the selected balloon id from the supplied playable list."""
    idx = get_choice(len(balloons), f"Balloon (1-{len(balloons)})")
    return balloons[idx].id if idx is not None else None


def show_balloon_menu():
    balloons = [b for b in CATALOG.all_balloons() if b.id not in ("s21", "s29")]
    print("\n  Balloon size:\n  " + "─" * 45)
    for i, b in enumerate(balloons, 1):
        print(f"  {i}. {b.name} ({b.max_volume_m3:.1f}m³, burst@{b.burst_volume_m3:.1f}m³, {b.mass_kg*1000}g)")
    return get_balloon_choice(balloons)


def show_gas_menu():
    gases = CATALOG.all_gases()
    print("\n  Gas type:\n  " + "─" * 45)
    for i, gas in enumerate(gases, 1):
        print(f"  {i}. {gas.name} (molar mass={gas.molar_mass:.4f} kg/mol, {gas.gas_behavior})")
    idx = get_choice(len(gases), f"Gas (1-{len(gases)})")
    return gases[idx].id if idx is not None else None


def show_fill_presets(balloon_key, gas_type):
    while True:
        print("\n  Fill mode:\n  " + "─" * 45)
        for i, mode in enumerate(FillMode, 1):
            if mode == FillMode.MANUAL:
                mass_str = "You choose"
            else:
                request = LaunchRequest(gas_id=gas_type, envelope_id="latex",
                    balloon_size=balloon_key, payload_ids=tuple(), launch_site_id="field",
                    fill_mode=mode, manual_gas_mass_kg=None)
                mass_str = format_mass_kg(request.gas_mass_kg)
            print(f"  {i}. {mode.label}: {mode.description} ({mass_str})")
        idx = get_choice(len(FillMode), f"Fill mode (1-{len(FillMode)})")
        if idx is None: return None, None
        mode = list(FillMode)[idx]
        if mode == FillMode.MANUAL:
            raw = input("  Mass (g) > ").strip()
            if raw.lower() in ("q", "quit"): return None, None
            try: return mode, float(raw) / 1000.0
            except ValueError:
                print("  Invalid input. Try again."); continue
        request = LaunchRequest(gas_id=gas_type, envelope_id="latex", balloon_size=balloon_key,
            payload_ids=tuple(), launch_site_id="field", fill_mode=mode, manual_gas_mass_kg=None)
        return mode, request.gas_mass_kg


def show_payloads_menu():
    payloads = CATALOG.all_payloads()
    print("\n  Select payloads (space-separated numbers, or 'done'):\n  " + "─" * 45)
    for i, p in enumerate(payloads, 1): print(f"  {i}. {p.name} ({p.mass_kg} kg){' 🛡️' if p.has_valve else ''}")
    print(f"  {len(payloads)+1}. None")
    while True:
        raw = input("  Payloads > ").strip()
        if raw in ("", "done") or raw.lower() in ("q", "quit"): return ["none"]
        chosen = []
        for value in raw.split():
            try:
                idx = int(value) - 1
                if 0 <= idx < len(payloads): chosen.append(payloads[idx].id)
                elif idx == len(payloads): return ["none"]
            except ValueError: pass
        if chosen: return chosen
        print("  Invalid selection. Try again.")


def show_site_menu():
    sites = CATALOG.all_sites()
    print("\n  Launch site:\n  " + "─" * 45)
    for i, site in enumerate(sites, 1): print(f"  {i}. {site.name}")
    idx = get_choice(len(sites), f"Launch site (1-{len(sites)})")
    return sites[idx].id if idx is not None else None


def show_results(outcome: FlightOutcome, balloon_key, gas_type, gas_mass, payloads):
    result = outcome.result
    print("\n  +-----------------------------------------------+")
    print("  |              FLIGHT RESULTS                  |")
    print("  +-----------------------------------------------+")
    print(f"  Balloon:     {CATALOG.balloon(balloon_key).name} latex")
    print(f"  Gas:         {CATALOG.gas(gas_type).name} ({format_mass_kg(gas_mass)})")
    names = [CATALOG.payload(pid).name for pid in payloads if pid != "none"]
    print(f"  Payloads:    {', '.join(names) or 'None'}")
    print(f"  Peak Alt:    {result.peak_altitude_m:.1f}m")
    print(f"  Flight Time: {result.duration_s:.1f}s")
    print(f"  Result:      {'CRASHED' if result.crashed else 'BURST' if result.burst else 'LANDED' if result.landed else 'COMPLETE'}")
    print(f"  Score:       {outcome.score:.1f}")
    print(f"  Medal:       {outcome.medal_emoji} {outcome.medal_name}")
    if outcome.weather: print(f"\n  Weather:     {outcome.weather.name or 'Clear'}")
    if outcome.mission_assignment and outcome.mission_assignment.mission_ids:
        print(f"\n  Missions:    {', '.join(outcome.mission_assignment.mission_ids)}")
        for mission in outcome.mission_results:
            reward = f" (+{mission.reward} credits)" if mission.reward else ""
            print(f"    {'PASS' if mission.completed else 'FAIL'} {mission.mission_id}{reward}: {mission.explanation}")


def play(args=None):
    if args is None:
        args = argparse.Namespace(
            no_animation=False,
            no_color=False,
            animation_speed=1.0,
        )
    print("\n  +-----------------------------------------------+")
    print("  |             BALLOON FRONTIER                  |")
    print("  +-----------------------------------------------+")
    mode = show_game_mode_menu()
    if mode is None: return
    balloon_key = show_balloon_menu()
    if balloon_key is None: return
    gas_type = show_gas_menu()
    if gas_type is None: return
    fill_mode, gas_mass = show_fill_presets(balloon_key, gas_type)
    if gas_mass is None: return
    payloads = show_payloads_menu()
    site_key = show_site_menu()
    if site_key is None: return
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"): return
    request = LaunchRequest(gas_id=gas_type, envelope_id="latex", balloon_size=balloon_key,
        payload_ids=tuple(payloads), launch_site_id=site_key, fill_mode=fill_mode,
        manual_gas_mass_kg=gas_mass if fill_mode == FillMode.MANUAL else None)
    service = SessionAwareFlightService(flight_service, mode, ui="cli")
    print("\n  Launching...\n")
    try: outcome = service.run(request)
    except Exception as exc:
        print(f"\n  Flight simulation failed: {exc}"); return
    TerminalFlightAnimator().play(
        build_flight_moments(outcome.result.telemetry, max_frames=18),
        speed=args.animation_speed,
        no_animation=args.no_animation,
        no_color=args.no_color,
        envelope_id="latex",
        payload_ids=tuple(payloads),
    )
    show_results(outcome, balloon_key, gas_type, gas_mass, payloads)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Balloon Frontier CLI")
    parser.add_argument("--no-animation", action="store_true", help="show one static launch frame")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--animation-speed", type=float, default=1.0, metavar="MULTIPLIER")
    args = parser.parse_args(argv)
    if args.animation_speed <= 0: parser.error("--animation-speed must be greater than zero")
    return args


def main(argv=None):
    args = parse_args(argv)
    print("Welcome to Balloon Frontier! Type 'q' at any prompt to exit.\n")
    play(args)
    while input("  Play again? (y/n) > ").strip().lower() not in ("n", "no", "q", "quit", "exit"):
        play(args)
    print("Thanks for playing Balloon Frontier!\n")


if __name__ == "__main__":
    main()