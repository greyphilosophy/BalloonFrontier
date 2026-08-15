#!/usr/bin/env python3
"""Balloon Frontier CLI game with shared graphical-to-ANSI launch playback."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.aerostat import fill_mass_for_configuration
from balloon_frontier.atmosphere_profile import atmosphere_profiles
from balloon_frontier.career_prologue import (
    FIRST_FLIGHT_FILL_OPTIONS,
    FIRST_FLIGHT_HEAT_SOURCES,
    FIRST_FLIGHT_OPTION_KEYS,
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
    FIRST_FLIGHT_SITE_NAME,
    first_flight_balloon_choices,
    first_flight_payload_keys,
    with_required_first_flight_payloads,
)
from balloon_frontier.catalog import CATALOG
from balloon_frontier.cli_ui.animator import TerminalFlightAnimator
from balloon_frontier.discord_ui.configurator import (
    ENVELOPE_OPTIONS,
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
)
from balloon_frontier.flight_service import FlightOutcome, flight_service
from balloon_frontier.game_modes import GameMode, list_game_modes
from balloon_frontier.how_to_play import how_to_play_text
from balloon_frontier.launch_result import FillMode, LaunchRequest
from balloon_frontier.physics import (
    atmosphere_density,
    atmosphere_pressure,
    atmosphere_temperature,
    gas_density,
)
from balloon_frontier.power import (
    gas_mass_for_supported_fraction_kg,
    maximum_capacity_gas_mass_kg,
)
from balloon_frontier.presentation import build_flight_moments
from balloon_frontier.progression import PlayerRegistry, get_envelope
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.story import (
    FIRST_FLIGHT_MISSION_ID,
    format_atmosphere_profile,
    story_chapter_for_mission,
    story_chapter_intro,
)
from balloon_frontier.story_mission_select import story_mission_choices

DEFAULT_CLI_PLAYER_ID = "cli-player"


def format_mass_kg(mass_kg):
    if mass_kg < 1.0:
        return f"{mass_kg * 1000:.1f}g"
    if mass_kg < 100:
        return f"{mass_kg:.3f} kg"
    return f"{mass_kg:.2f} kg"


def get_choice(max_val, prompt):
    while True:
        raw = input(f"  {prompt} (1-{max_val}, q to quit) > ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        try:
            value = int(raw)
            if 1 <= value <= max_val:
                return value - 1
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {max_val}")


def _terminal_markdown(text: str) -> str:
    return str(text).replace("**", "").replace("*", "")


def show_how_to_play():
    print("\n" + _terminal_markdown(how_to_play_text()))


def show_game_mode_menu():
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
        else:
            return modes[idx]


def show_story_mission_menu(player_id: str):
    choices = story_mission_choices(player_id)
    if not choices:
        return None
    print("\n  📖 Story Missions\n  " + "─" * 45)
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {'Replay' if choice.completed else 'Next'}: {choice.chapter.title}")
        print(f"     {choice.chapter.season}")
    idx = get_choice(len(choices), f"Mission (1-{len(choices)})")
    return choices[idx].mission_id if idx is not None else None


def show_story_briefing(mission_id: str, *, player_id: str | None = None):
    chapter = story_chapter_for_mission(mission_id)
    content = story_chapter_intro(chapter, player_id=player_id, include_disclaimer=True)
    if player_id and mission_id != FIRST_FLIGHT_MISSION_ID:
        profile = atmosphere_profiles.get(str(player_id))
        if profile is not None:
            content += "\n\n" + format_atmosphere_profile(profile)
    print("\n" + _terminal_markdown(content) + "\n")


def get_balloon_choice(balloons):
    idx = get_choice(len(balloons), f"Balloon (1-{len(balloons)})")
    return balloons[idx].id if idx is not None else None


def show_balloon_menu():
    balloons = [b for b in CATALOG.all_balloons() if b.id not in ("s21", "s29")]
    print("\n  Balloon size:\n  " + "─" * 45)
    for i, balloon in enumerate(balloons, 1):
        print(
            f"  {i}. {balloon.name} ({balloon.max_volume_m3:.1f}m³, "
            f"burst@{balloon.burst_volume_m3:.1f}m³, {balloon.mass_kg * 1000}g)"
        )
    return get_balloon_choice(balloons)


def show_gas_menu(gas_ids=None):
    gases = [CATALOG.gas(g) for g in gas_ids] if gas_ids is not None else CATALOG.all_gases()
    print("\n  Gas type:\n  " + "─" * 45)
    for i, gas in enumerate(gases, 1):
        print(f"  {i}. {gas.name} (molar mass={gas.molar_mass:.4f} kg/mol, {gas.gas_behavior})")
    idx = get_choice(len(gases), f"Gas (1-{len(gases)})")
    return gases[idx].id if idx is not None else None


def show_envelope_menu(envelope_ids=None, *, player_id: str | None = None):
    ids = tuple(envelope_ids or ENVELOPE_OPTIONS.keys())
    envelopes = [CATALOG.envelope(eid) for eid in ids]
    player = PlayerRegistry.get_or_create(str(player_id)) if player_id is not None else None
    print("\n  Envelope:\n  " + "─" * 45)
    for i, envelope in enumerate(envelopes, 1):
        locked = player is not None and not player.is_envelope_unlocked(envelope.id)
        print(
            f"  {i}. {envelope.name} ({envelope.max_volume_m3:g}m³, "
            f"{envelope.mass_kg:g}kg){' 🔒' if locked else ''}"
        )
    while True:
        idx = get_choice(len(envelopes), f"Envelope (1-{len(envelopes)})")
        if idx is None:
            return None
        envelope = envelopes[idx]
        if player is None or player.is_envelope_unlocked(envelope.id):
            return envelope.id
        prog_env = get_envelope(envelope.id)
        print(
            f"  🔒 {prog_env.name} is locked. Unlock by reaching "
            f"{prog_env.min_reputation} reputation OR {prog_env.cost} credits."
        )


def show_first_flight_balloon_menu(gas_id: str):
    """Show only physically coherent balloons for the selected gas."""
    choices = first_flight_balloon_choices(gas_id)
    if not choices:
        return None
    print("\n  Balloon:\n  " + "─" * 45)
    for i, choice in enumerate(choices, 1):
        envelope = CATALOG.envelope(choice.envelope_id)
        if choice.balloon_size:
            balloon = CATALOG.balloon(choice.balloon_size)
            name = f'{balloon.name} Latex Weather Balloon'
            mass_kg = balloon.mass_kg
            burst_volume = balloon.burst_volume_m3
        else:
            name = envelope.name
            mass_kg = envelope.mass_kg
            burst_volume = envelope.burst_volume_m3
        print(f"  {i}. {name}")
        print(f"     {mass_kg * 1000:.0f}g • ${choice.cost} • {burst_volume:.1f}m³ before burst")
    if gas_id == "helium":
        print(
            "     Smaller balloons are lighter and cheaper. Larger balloons have "
            "more room to expand, so they can climb higher before bursting."
        )
    else:
        print(
            "     Heated air needs an open hot-air envelope; sealed latex weather "
            "balloons are not offered for this gas."
        )
    idx = get_choice(len(choices), f"Balloon (1-{len(choices)})")
    return choices[idx] if idx is not None else None


def show_fill_presets(balloon_key, gas_type):
    while True:
        print("\n  Fill mode:\n  " + "─" * 45)
        for i, mode in enumerate(FillMode, 1):
            if mode == FillMode.MANUAL:
                mass_str = "You choose"
            else:
                request = LaunchRequest(
                    gas_id=gas_type,
                    envelope_id="latex",
                    balloon_size=balloon_key,
                    launch_site_id="field",
                    fill_mode=mode,
                )
                mass_str = format_mass_kg(request.gas_mass_kg)
            print(f"  {i}. {mode.label}: {mode.description} ({mass_str})")
        idx = get_choice(len(FillMode), f"Fill mode (1-{len(FillMode)})")
        if idx is None:
            return None, None
        mode = list(FillMode)[idx]
        if mode != FillMode.MANUAL:
            request = LaunchRequest(
                gas_id=gas_type,
                envelope_id="latex",
                balloon_size=balloon_key,
                launch_site_id="field",
                fill_mode=mode,
            )
            return mode, request.gas_mass_kg
        raw = input("  Mass (g) > ").strip()
        if raw.lower() in ("q", "quit"):
            return None, None
        try:
            return mode, float(raw) / 1000.0
        except ValueError:
            print("  Invalid input. Try again.")


def show_story_fill_mode(envelope_id, gas_type):
    modes = list(FillMode)
    print("\n  Fill mode:\n  " + "─" * 45)
    for i, mode in enumerate(modes, 1):
        print(f"  {i}. {mode.label}: {mode.description}")
    idx = get_choice(len(modes), f"Fill mode (1-{len(modes)})")
    if idx is None:
        return None, None
    mode = modes[idx]
    if mode != FillMode.MANUAL:
        return mode, None
    while True:
        raw = input("  Mass (g) > ").strip()
        if raw.lower() in ("q", "quit"):
            return None, None
        try:
            return mode, float(raw) / 1000.0
        except ValueError:
            print("  Invalid input. Try again.")


def show_payloads_menu(payload_ids=None):
    payloads = CATALOG.all_payloads() if payload_ids is None else [CATALOG.payload(p) for p in payload_ids]
    print("\n  Select payloads (space-separated numbers, or 'done'):\n  " + "─" * 45)
    for i, payload in enumerate(payloads, 1):
        print(f"  {i}. {payload.name} ({payload.mass_kg} kg){' 🛡️' if payload.has_valve else ''}")
    print(f"  {len(payloads) + 1}. None")
    while True:
        raw = input("  Payloads > ").strip()
        if raw in ("", "done") or raw.lower() in ("q", "quit"):
            return ["none"]
        chosen = []
        for value in raw.split():
            try:
                idx = int(value) - 1
            except ValueError:
                continue
            if 0 <= idx < len(payloads):
                chosen.append(payloads[idx].id)
            elif idx == len(payloads):
                return ["none"]
        if chosen:
            return list(dict.fromkeys(chosen))
        print("  Invalid selection. Try again.")


def show_site_menu(site_ids=None, *, first_flight=False):
    ids = tuple(site_ids or SITE_OPTIONS.keys())
    sites = [CATALOG.site(site_id) for site_id in ids]
    print("\n  Launch site:\n  " + "─" * 45)
    for i, site in enumerate(sites, 1):
        name = FIRST_FLIGHT_SITE_NAME if first_flight and site.id == "field" else site.name
        print(f"  {i}. {name}")
        if site.description:
            print(f"     {site.description}")
    idx = get_choice(len(sites), f"Launch site (1-{len(sites)})")
    return sites[idx].id if idx is not None else None


def _first_flight_fill_mass(
    *, gas_id, envelope_id, payload_ids, site_id, fill_key, balloon_size=None
):
    envelope = CATALOG.envelope(envelope_id)
    balloon = CATALOG.balloon(balloon_size) if balloon_size else None
    max_volume = balloon.max_volume_m3 if balloon else envelope.max_volume_m3
    vehicle_mass = balloon.mass_kg if balloon else envelope.mass_kg
    site = CATALOG.site(site_id)
    payloads = with_required_first_flight_payloads(tuple(payload_ids or ()))
    payload_mass = sum(CATALOG.payload(pid).mass_kg for pid in payloads)
    pressure = atmosphere_pressure(site.altitude_m)
    temperature = (
        site.gas_temperature_k
        if site.gas_temperature_k is not None
        else atmosphere_temperature(site.altitude_m) + site.temperature_offset_k
    )
    ambient_density = atmosphere_density(site.altitude_m)
    lifting_density = gas_density(gas_id, temperature, pressure)
    if fill_key == "maximum":
        return maximum_capacity_gas_mass_kg(
            lifting_gas_density_kg_m3=lifting_density,
            max_volume_m3=max_volume,
        )
    return gas_mass_for_supported_fraction_kg(
        non_gas_mass_kg=vehicle_mass + payload_mass,
        ambient_density_kg_m3=ambient_density,
        lifting_gas_density_kg_m3=lifting_density,
        max_volume_m3=max_volume,
        support_fraction=FIRST_FLIGHT_FILL_OPTIONS[fill_key]["support_fraction"],
    )


def show_first_flight_optional_payloads(gas_id: str):
    keys = first_flight_payload_keys(gas_id)
    real_keys = tuple(key for key in keys if key != "none")
    print("\n  Payloads:\n  " + "─" * 45)
    print("  Essential payloads (provided):")
    for pid in FIRST_FLIGHT_PROVIDED_PAYLOADS:
        payload = CATALOG.payload(pid)
        print(f"    • {payload.name} ({payload.mass_kg}kg)")
    print("\n  Optional additions (space-separated numbers; blank for none):")
    for i, pid in enumerate(real_keys, 1):
        payload = CATALOG.payload(pid)
        print(f"  {i}. {payload.name} ({payload.mass_kg}kg, ${payload.cost})")
    if gas_id == "air":
        print("     Air requires exactly one heat source: tea light or electric heater.")
    while True:
        raw = input("  Optional payloads > ").strip()
        if not raw or raw.lower() in ("done", "none"):
            if gas_id == "air":
                print("  Air needs a heat source. Choose the tea light or electric heater.")
                continue
            return list(FIRST_FLIGHT_PROVIDED_PAYLOADS)
        if raw.lower() in ("q", "quit", "exit"):
            return None
        selected = []
        valid = True
        for value in raw.split():
            try:
                idx = int(value) - 1
            except ValueError:
                valid = False
                break
            if not 0 <= idx < len(real_keys):
                valid = False
                break
            selected.append(real_keys[idx])
        if not valid:
            print("  Invalid selection. Try again.")
            continue
        selected = list(dict.fromkeys(selected))
        heaters = [pid for pid in selected if pid in FIRST_FLIGHT_HEAT_SOURCES]
        if gas_id == "air" and len(heaters) != 1:
            print("  Choose exactly one heat source for the hot-air envelope.")
            continue
        return list(with_required_first_flight_payloads(tuple(selected)))


def show_first_flight_fill_menu(
    gas_id, envelope_id, payload_ids, site_id, *, balloon_size=None
):
    options = []
    for key in FIRST_FLIGHT_OPTION_KEYS[2]:
        try:
            mass = round(
                _first_flight_fill_mass(
                    gas_id=gas_id,
                    envelope_id=envelope_id,
                    payload_ids=payload_ids,
                    site_id=site_id,
                    fill_key=key,
                    balloon_size=balloon_size,
                ),
                3,
            )
        except ValueError:
            continue
        options.append((key, FIRST_FLIGHT_FILL_OPTIONS[key], mass))
    print("\n  Fill mode:\n  " + "─" * 45)
    for i, (_, option, mass) in enumerate(options, 1):
        print(f"  {i}. {option['label']} — {format_mass_kg(mass)}")
        print(f"     {option['description']}")
    idx = get_choice(len(options), f"Fill mode (1-{len(options)})")
    if idx is None:
        return None
    key, option, mass = options[idx]
    return key, option["label"], mass


def build_first_flight_request(player_id: str):
    print("\n  🔧 Balloon Configuration")
    player = PlayerRegistry.get_or_create(player_id)
    print(f"  ⚡ You have {player.reputation} reputation and ${player.budget} budget.")

    print("\n  Step 1/6: Gas Type")
    gas_id = show_gas_menu(FIRST_FLIGHT_OPTION_KEYS[0])
    if gas_id is None:
        return None
    print("\n  Step 2/6: Balloon")
    choice = show_first_flight_balloon_menu(gas_id)
    if choice is None:
        return None
    print("\n  Step 3/6: Payloads")
    payload_ids = show_first_flight_optional_payloads(gas_id)
    if payload_ids is None:
        return None
    print("\n  Step 4/6: Launch Site")
    site_id = show_site_menu(FIRST_FLIGHT_OPTION_KEYS[4], first_flight=True)
    if site_id is None:
        return None
    print("\n  Step 5/6: Fill Mode")
    fill = show_first_flight_fill_menu(
        gas_id,
        choice.envelope_id,
        payload_ids,
        site_id,
        balloon_size=choice.balloon_size,
    )
    if fill is None:
        return None
    _, fill_label, gas_mass = fill
    request = LaunchRequest(
        gas_id=gas_id,
        envelope_id=choice.envelope_id,
        balloon_size=choice.balloon_size,
        payload_ids=tuple(payload_ids),
        launch_site_id=site_id,
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=gas_mass,
        player_id=player_id,
    )
    if choice.balloon_size:
        balloon = CATALOG.balloon(choice.balloon_size)
        name, mass, burst = (
            f'{balloon.name} Latex Weather Balloon',
            balloon.mass_kg,
            balloon.burst_volume_m3,
        )
    else:
        envelope = CATALOG.envelope(choice.envelope_id)
        name, mass, burst = envelope.name, envelope.mass_kg, envelope.burst_volume_m3
    print("\n  Step 6/6: Review & Launch\n  " + "─" * 45)
    print(f"  Gas:       {CATALOG.gas(gas_id).name}")
    print(f"  Fill:      {fill_label} → {format_mass_kg(gas_mass)}")
    print(f"  Balloon:   {name}")
    print(f"  Weight:    {mass * 1000:.0f}g")
    print(f"  Cost:      ${choice.cost}")
    print(f"  Burst cap: {burst:.1f}m³")
    print("  Payloads:  " + ", ".join(CATALOG.payload(pid).name for pid in payload_ids))
    print(f"  Site:      {FIRST_FLIGHT_SITE_NAME}")
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return request


def _offer_recorded_atmosphere(player_id: str) -> None:
    profile = atmosphere_profiles.get(str(player_id))
    if profile is None:
        return
    if input("  Use recorded atmosphere for this launch? (y/n) > ").strip().lower() in ("y", "yes"):
        atmosphere_profiles.lock_for_next_flight(str(player_id))
        print("  🔒 Measured conditions selected for the next launch.")


def build_standard_story_request(player_id: str):
    gas_id = show_gas_menu(tuple(GAS_OPTIONS.keys()))
    if gas_id is None:
        return None
    envelope_id = show_envelope_menu(tuple(ENVELOPE_OPTIONS.keys()), player_id=player_id)
    if envelope_id is None:
        return None
    fill_mode, manual_mass = show_story_fill_mode(envelope_id, gas_id)
    if fill_mode is None:
        return None
    payload_ids = show_payloads_menu(tuple(key for key in PAYLOAD_OPTIONS if key != "none"))
    site_id = show_site_menu(tuple(SITE_OPTIONS.keys()))
    if site_id is None:
        return None
    request = LaunchRequest(
        gas_id=gas_id,
        envelope_id=envelope_id,
        payload_ids=tuple(payload_ids),
        launch_site_id=site_id,
        fill_mode=fill_mode,
        manual_gas_mass_kg=manual_mass,
        player_id=player_id,
    )
    resolved_mass = fill_mass_for_configuration(
        gas_id=gas_id,
        envelope_id=envelope_id,
        launch_site_id=site_id,
        fill_mode=fill_mode,
        manual_gas_mass_kg=manual_mass,
    )
    print("\n  Review & Launch\n  " + "─" * 45)
    print(f"  Gas:       {CATALOG.gas(gas_id).name}")
    print(f"  Fill:      {fill_mode.label} → {format_mass_kg(resolved_mass)}")
    print(f"  Envelope:  {CATALOG.envelope(envelope_id).name}")
    names = [CATALOG.payload(pid).name for pid in payload_ids if pid != "none"]
    print(f"  Payloads:  {', '.join(names) or 'None'}")
    print(f"  Site:      {CATALOG.site(site_id).name}")
    _offer_recorded_atmosphere(player_id)
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return request


def _legacy_request(player_id: str | None = None):
    balloon = show_balloon_menu()
    if balloon is None:
        return None
    gas = show_gas_menu()
    if gas is None:
        return None
    fill_mode, gas_mass = show_fill_presets(balloon, gas)
    if gas_mass is None:
        return None
    payloads = show_payloads_menu()
    site = show_site_menu()
    if site is None or input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return LaunchRequest(
        gas_id=gas,
        envelope_id="latex",
        balloon_size=balloon,
        payload_ids=tuple(payloads),
        launch_site_id=site,
        fill_mode=fill_mode,
        manual_gas_mass_kg=gas_mass if fill_mode == FillMode.MANUAL else None,
        player_id=player_id,
    )


def show_results(outcome: FlightOutcome, balloon_key=None, gas_type=None, gas_mass=None, payloads=None):
    result = outcome.result
    request = result.launch_request
    vehicle = (
        f"{CATALOG.balloon(request.balloon_size).name} latex"
        if request.balloon_size
        else CATALOG.envelope(request.envelope_id).name
    )
    resolved_mass = fill_mass_for_configuration(
        gas_id=request.gas_id,
        envelope_id=request.envelope_id,
        launch_site_id=request.launch_site_id,
        fill_mode=request.fill_mode,
        manual_gas_mass_kg=request.manual_gas_mass_kg,
        balloon_size=request.balloon_size,
        gas_temperature_delta_k=request.gas_temperature_delta_k,
    )
    names = [CATALOG.payload(pid).name for pid in request.payload_ids if pid != "none"]
    print("\n  +-----------------------------------------------+")
    print("  |              FLIGHT RESULTS                  |")
    print("  +-----------------------------------------------+")
    print(f"  Vehicle:     {vehicle}")
    print(f"  Gas:         {CATALOG.gas(request.gas_id).name} ({format_mass_kg(resolved_mass)})")
    print(f"  Payloads:    {', '.join(names) or 'None'}")
    print(f"  Peak Alt:    {result.peak_altitude_m:.1f}m")
    print(f"  Flight Time: {result.duration_s:.1f}s")
    state = "CRASHED" if result.crashed else "BURST" if result.burst else "LANDED" if result.landed else "COMPLETE"
    print(f"  Result:      {state}")
    print(f"  Score:       {outcome.score:.1f}")
    print(f"  Medal:       {outcome.medal_emoji} {outcome.medal_name}")
    if outcome.safety_notes:
        print("\n  Safety factors:")
        for note in outcome.safety_notes:
            print(f"    ⚠ {note}")
    if outcome.weather:
        print(f"\n  Weather:     {outcome.weather.name or 'Clear'}")
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
            player_id=DEFAULT_CLI_PLAYER_ID,
        )
    player_id = str(getattr(args, "player_id", DEFAULT_CLI_PLAYER_ID))
    print("\n  +-----------------------------------------------+")
    print("  |             BALLOON FRONTIER                  |")
    print("  +-----------------------------------------------+")
    mode = show_game_mode_menu()
    if mode is None:
        return
    story_mission_id = None
    if mode is GameMode.STORY:
        story_mission_id = show_story_mission_menu(player_id)
        if story_mission_id is None:
            return
        show_story_briefing(story_mission_id, player_id=player_id)
        request = (
            build_first_flight_request(player_id)
            if story_mission_id == FIRST_FLIGHT_MISSION_ID
            else build_standard_story_request(player_id)
        )
    else:
        request = _legacy_request(player_id)
    if request is None:
        return
    service = SessionAwareFlightService(
        flight_service,
        mode,
        ui="cli",
        story_player_id=player_id if mode is GameMode.STORY else None,
        story_mission_id=story_mission_id,
    )
    print("\n  Launching...\n")
    try:
        outcome = service.run(request)
    except Exception as exc:
        print(f"\n  Flight simulation failed: {exc}")
        return
    TerminalFlightAnimator().play(
        build_flight_moments(outcome.result.telemetry, max_frames=18),
        speed=args.animation_speed,
        no_animation=args.no_animation,
        no_color=args.no_color,
        envelope_id=request.envelope_id,
        payload_ids=tuple(request.payload_ids),
    )
    show_results(outcome)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Balloon Frontier CLI")
    parser.add_argument("--no-animation", action="store_true", help="show one static launch frame")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--animation-speed", type=float, default=1.0, metavar="MULTIPLIER")
    parser.add_argument(
        "--player-id",
        default=DEFAULT_CLI_PLAYER_ID,
        help="persistent Story profile identifier (default: cli-player)",
    )
    args = parser.parse_args(argv)
    if args.animation_speed <= 0:
        parser.error("--animation-speed must be greater than zero")
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
