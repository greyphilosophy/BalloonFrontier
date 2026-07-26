#!/usr/bin/env python3
"""Balloon Frontier — CLI Game."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.catalog import CATALOG
from balloon_frontier.flight_service import FlightOutcome, flight_service
from balloon_frontier.game_modes import list_game_modes
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.session_adapters import SessionAwareFlightService


def format_mass_kg(mass_kg):
    if mass_kg < 1.0:
        return f"{mass_kg * 1000:.1f}g"
    if mass_kg < 100:
        return f"{mass_kg:.3f} kg"
    return f"{mass_kg:.2f} kg"


def format_kg_compact(mass_kg: float) -> str:
    abs_val = abs(mass_kg)
    if abs_val < 0.1:
        value = f"{mass_kg:.2f}"
    elif abs_val < 1.0:
        value = f"{mass_kg:.1f}"
    else:
        value = f"{mass_kg:.2f}"
    return value.rstrip("0").rstrip(".")


def show_game_mode_menu():
    print("\n  Game mode:")
    print("  ─────────────────────────────────────────────")
    modes = list_game_modes()
    for i, mode in enumerate(modes, start=1):
        print(f"  {i}. {mode.label}: {mode.description}")
    print()
    idx = get_choice(len(modes), f"Game mode (1-{len(modes)})")
    return modes[idx] if idx is not None else None


def show_fill_presets(balloon_key, gas_type):
    balloon = CATALOG.balloon(balloon_key)
    while True:
        print("\n  Fill mode:")
        print("  ─────────────────────────────────────────────")
        for i, mode in enumerate(FillMode, start=1):
            try:
                if mode == FillMode.MANUAL:
                    mass_str = "You choose"
                else:
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
                print(f"  {i}. {mode.label}: {mode.description} ({mass_str})")
            except Exception as exc:
                print(f"  {i}. {mode.label}: {mode.description} (error: {exc})")
        print()
        idx = get_choice(len(FillMode), f"Fill mode (1-{len(FillMode)})")
        if idx is None:
            return None, None
        selected_mode = list(FillMode)[idx]
        if selected_mode == FillMode.MANUAL:
            raw = input("  Mass (g) > ").strip()
            if raw.lower() in ("q", "quit"):
                return None, None
            try:
                gas_mass_kg = float(raw) / 1000.0
            except ValueError:
                print("  Invalid input. Try again.")
                continue
            print(f"\n  Selected manual fill: {format_mass_kg(gas_mass_kg)}")
            return selected_mode, gas_mass_kg
        request = LaunchRequest(
            gas_id=gas_type,
            envelope_id="latex",
            balloon_size=balloon_key,
            payload_ids=tuple(),
            launch_site_id="field",
            fill_mode=selected_mode,
            manual_gas_mass_kg=None,
        )
        gas_mass_kg = request.gas_mass_kg
        print(f"\n  Selected {selected_mode.value} fill: {format_mass_kg(gas_mass_kg)}")
        return selected_mode, gas_mass_kg


def show_balloon_menu():
    print("\n  Balloon size:")
    print("  ─────────────────────────────────────────────")
    balloons = [b for b in CATALOG.all_balloons() if b.id not in ("s21", "s29")]
    for i, balloon in enumerate(balloons):
        print(f"  {i+1}. {balloon.name} ({balloon.max_volume_m3:.1f}m³, burst@{balloon.burst_volume_m3:.1f}m³, {balloon.mass_kg*1000}g)")
    print()
    return get_balloon_choice(balloons)


def get_balloon_choice(balloons):
    idx = get_choice(len(balloons), f"Balloon (1-{len(balloons)})")
    return balloons[idx].id if idx is not None else None


def show_gas_menu():
    print("\n  Gas type:")
    print("  ─────────────────────────────────────────────")
    gases = CATALOG.all_gases()
    for i, gas in enumerate(gases):
        print(f"  {i+1}. {gas.name} (molar mass={gas.molar_mass:.4f} kg/mol, {gas.gas_behavior})")
    print()
    idx = get_choice(len(gases), "Gas (1-4)")
    return gases[idx].id if idx is not None else None


def show_payloads_menu():
    print("\n  Select payloads (space-separated numbers, or 'done'):")
    print("  ─────────────────────────────────────────────")
    payloads = CATALOG.all_payloads()
    for i, payload in enumerate(payloads):
        valve_note = " 🛡️" if payload.has_valve else ""
        print(f"  {i+1}. {payload.name}  ({payload.mass_kg} kg){valve_note}")
    print(f"  {len(payloads)+1}. None\n")
    selected = []
    while True:
        raw = input("  Payloads > ").strip()
        if raw == "done" or raw == "":
            return selected if selected else ["none"]
        if raw.lower() in ("q", "quit"):
            return ["none"]
        chosen = []
        for value in raw.split():
            try:
                idx = int(value) - 1
                if 0 <= idx < len(payloads):
                    chosen.append(payloads[idx].id)
                elif idx == len(payloads) and value == str(len(payloads) + 1):
                    return ["none"]
            except ValueError:
                pass
        if chosen:
            return chosen
        print("  Invalid selection. Try again.")


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
    while True:
        raw = input(f"  {prompt} (1-{max_val}, q to quit) > ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        try:
            val = int(raw)
            if 1 <= val <= max_val:
                return val - 1
            print(f"  Please enter a number between 1 and {max_val}")
        except ValueError:
            print("  Invalid input. Try again.")


def show_results(outcome: FlightOutcome, balloon_key, gas_type, gas_mass, payloads):
    result = outcome.result
    has_valve = any(pid == "valve" for pid in payloads if pid != "none")
    valve_note = " 🛡️" if has_valve else ""
    print("\n  ╔═══════════════════════════════════════════════╗")
    print("  ║              🎈 FLIGHT RESULTS 🎈             ║")
    print("  ╚═══════════════════════════════════════════════╝")
    balloon = CATALOG.balloon(balloon_key)
    gas = CATALOG.gas(gas_type)
    print(f"  Balloon:    {balloon.name} latex")
    print(f"  Gas:        {gas.name} ({format_mass_kg(gas_mass)})")
    payload_names = [CATALOG.payload(pid).name for pid in payloads if pid != "none"]
    print(f"  Payloads:   {', '.join(payload_names)}{valve_note}")
    print(f"  Peak Alt:   {result.peak_altitude_m:.1f}m")
    print(f"  Flight Time: {result.duration_s:.1f}s")
    if result.burst:
        print("  Result:     💥 BURST")
    elif result.landed:
        print("  Result:     ✅ LANDED")
    if result.crashed:
        print("  Status:     💥 CRASHED!")
    print(f"  Score:      {outcome.score:.1f}")
    print(f"  Medal:      {outcome.medal_emoji} {outcome.medal_name}")
    if outcome.weather:
        print(f"\n  Weather:    {outcome.weather.name or 'Clear'}")
        if outcome.weather.description:
            print(f"             {outcome.weather.description}")
    if outcome.mission_assignment and outcome.mission_assignment.mission_ids:
        print(f"\n  Missions:   {', '.join(outcome.mission_assignment.mission_ids)}")
        for mission_result in outcome.mission_results:
            status = "✅" if mission_result.completed else "❌"
            reward = f" (+{mission_result.reward} credits)" if mission_result.reward else ""
            print(f"    {status} {mission_result.mission_id}{reward}: {mission_result.explanation}")


def play():
    print("\n  ╔═══════════════════════════════════════════════╗")
    print("  ║           🎈 BALLOON FRONTIER 🎈             ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("  Pick your mode, balloon, gas, and payload!  (q to quit)\n")

    mode = show_game_mode_menu()
    if mode is None:
        return
    print(f"  Selected mode: {mode.label} — {mode.description}")

    balloon_key = show_balloon_menu()
    if balloon_key is None:
        return
    balloon = CATALOG.balloon(balloon_key)
    print(f"  Selected: {balloon.name} latex balloon")

    gas_type = show_gas_menu()
    if gas_type is None:
        return
    fill_mode, gas_mass = show_fill_presets(balloon_key, gas_type)
    if gas_mass is None:
        return
    payloads = show_payloads_menu()
    site_key = show_site_menu()
    if site_key is None:
        return

    if fill_mode == FillMode.MANUAL:
        fill_range = balloon.fill_range_g
        if gas_mass * 1000 > fill_range[1]:
            print(f"\n  ⚠️  WARNING: {gas_mass*1000:.0f}g exceeds safe fill ({fill_range[1]}g)!")
        if gas_mass * 1000 < fill_range[0]:
            print(f"\n  💡 TIP: {gas_mass*1000:.0f}g is below the typical fill range.")

    print("\n  ─────────────────────────────────────────────────")
    print("  CONFIGURATION")
    print("  ─────────────────────────────────────────────────")
    print(f"  Mode:     {mode.label}")
    print(f"  Balloon:  {balloon.name} latex")
    print(f"  Gas:      {gas_type} ({format_mass_kg(gas_mass)})")
    payload_names = []
    has_valve = False
    for pid in payloads:
        if pid == "none":
            continue
        payload = CATALOG.payload(pid)
        payload_names.append(payload.name)
        has_valve = has_valve or payload.has_valve
    valve_note = " 🛡️ Valve equipped" if has_valve else ""
    print(f"  Payloads: {', '.join(payload_names)}{valve_note}")
    site = CATALOG.site(site_key)
    print(f"  Site:     {site.name}")
    print("  ─────────────────────────────────────────────────")

    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        print("  See you next time!")
        return

    launch_request = LaunchRequest(
        gas_id=gas_type,
        envelope_id="latex",
        balloon_size=balloon_key,
        payload_ids=tuple(payloads),
        launch_site_id=site_key,
        fill_mode=fill_mode,
        manual_gas_mass_kg=gas_mass if fill_mode == FillMode.MANUAL else None,
    )
    session_service = SessionAwareFlightService(flight_service, mode, ui="cli")
    print("\n  🚀 Launching...\n")
    try:
        outcome = session_service.run(launch_request)
    except Exception as exc:
        print(f"\n  ❌ Flight simulation failed: {exc}")
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
