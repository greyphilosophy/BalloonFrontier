#!/usr/bin/env python3
"""Balloon Frontier CLI game with shared graphical-to-ANSI launch playback."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.aerostat import fill_mass_for_configuration
from balloon_frontier.career_prologue import (
    FIRST_FLIGHT_FILL_OPTIONS,
    FIRST_FLIGHT_OPTION_KEYS,
    FIRST_FLIGHT_PROVIDED_PAYLOADS,
    FIRST_FLIGHT_SITE_NAME,
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
from balloon_frontier.progression import PlayerRegistry
from balloon_frontier.session_adapters import SessionAwareFlightService
from balloon_frontier.story import (
    FIRST_FLIGHT_MISSION_ID,
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
            val = int(raw)
            if 1 <= val <= max_val:
                return val - 1
            print(f"  Please enter a number between 1 and {max_val}")
        except ValueError:
            print("  Invalid input. Try again.")


def _terminal_markdown(text: str) -> str:
    """Make the shared Discord-flavored Story copy pleasant in a terminal."""
    return str(text).replace("**", "").replace("*", "")


def show_how_to_play():
    print("\n" + _terminal_markdown(how_to_play_text()))


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


def show_story_mission_menu(player_id: str):
    """Mirror Discord Story Mission Select: completed missions + next unlocked."""
    choices = story_mission_choices(player_id)
    if not choices:
        return None

    print("\n  📖 Story Missions\n  " + "─" * 45)
    for i, choice in enumerate(choices, 1):
        status = "Replay" if choice.completed else "Next"
        print(f"  {i}. {status}: {choice.chapter.title}")
        print(f"     {choice.chapter.season}")
    idx = get_choice(len(choices), f"Mission (1-{len(choices)})")
    return choices[idx].mission_id if idx is not None else None


def show_story_briefing(mission_id: str, *, player_id: str | None = None):
    chapter = story_chapter_for_mission(mission_id)
    content = story_chapter_intro(
        chapter,
        player_id=player_id,
        include_disclaimer=True,
    )
    print("\n" + _terminal_markdown(content) + "\n")


def get_balloon_choice(balloons):
    """Return the selected balloon id from the supplied playable list."""
    idx = get_choice(len(balloons), f"Balloon (1-{len(balloons)})")
    return balloons[idx].id if idx is not None else None


def show_balloon_menu():
    balloons = [b for b in CATALOG.all_balloons() if b.id not in ("s21", "s29")]
    print("\n  Balloon size:\n  " + "─" * 45)
    for i, b in enumerate(balloons, 1):
        print(
            f"  {i}. {b.name} ({b.max_volume_m3:.1f}m³, "
            f"burst@{b.burst_volume_m3:.1f}m³, {b.mass_kg * 1000}g)"
        )
    return get_balloon_choice(balloons)


def show_gas_menu(gas_ids=None):
    gases = (
        [CATALOG.gas(gas_id) for gas_id in gas_ids]
        if gas_ids is not None
        else CATALOG.all_gases()
    )
    print("\n  Gas type:\n  " + "─" * 45)
    for i, gas in enumerate(gases, 1):
        print(
            f"  {i}. {gas.name} (molar mass={gas.molar_mass:.4f} kg/mol, "
            f"{gas.gas_behavior})"
        )
    idx = get_choice(len(gases), f"Gas (1-{len(gases)})")
    return gases[idx].id if idx is not None else None


def show_envelope_menu(envelope_ids=None):
    ids = tuple(envelope_ids or ENVELOPE_OPTIONS.keys())
    envelopes = [CATALOG.envelope(envelope_id) for envelope_id in ids]
    print("\n  Envelope:\n  " + "─" * 45)
    for i, envelope in enumerate(envelopes, 1):
        print(
            f"  {i}. {envelope.name} "
            f"({envelope.max_volume_m3:g}m³, {envelope.mass_kg:g}kg)"
        )
    idx = get_choice(len(envelopes), f"Envelope (1-{len(envelopes)})")
    return envelopes[idx].id if idx is not None else None


def show_fill_presets(balloon_key, gas_type):
    """Legacy Scenario/Free Play weather-balloon fill selector."""
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
                    payload_ids=tuple(),
                    launch_site_id="field",
                    fill_mode=mode,
                    manual_gas_mass_kg=None,
                )
                mass_str = format_mass_kg(request.gas_mass_kg)
            print(f"  {i}. {mode.label}: {mode.description} ({mass_str})")
        idx = get_choice(len(FillMode), f"Fill mode (1-{len(FillMode)})")
        if idx is None:
            return None, None
        mode = list(FillMode)[idx]
        if mode == FillMode.MANUAL:
            raw = input("  Mass (g) > ").strip()
            if raw.lower() in ("q", "quit"):
                return None, None
            try:
                return mode, float(raw) / 1000.0
            except ValueError:
                print("  Invalid input. Try again.")
                continue
        request = LaunchRequest(
            gas_id=gas_type,
            envelope_id="latex",
            balloon_size=balloon_key,
            payload_ids=tuple(),
            launch_site_id="field",
            fill_mode=mode,
            manual_gas_mass_kg=None,
        )
        return mode, request.gas_mass_kg


def show_story_fill_mode(envelope_id, gas_type):
    """Use the same fill-mode choices as the regular Discord configuration UI."""
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
    if payload_ids is None:
        payloads = CATALOG.all_payloads()
    else:
        payloads = [CATALOG.payload(pid) for pid in payload_ids]
    print("\n  Select payloads (space-separated numbers, or 'done'):\n  " + "─" * 45)
    for i, p in enumerate(payloads, 1):
        print(f"  {i}. {p.name} ({p.mass_kg} kg){' 🛡️' if p.has_valve else ''}")
    print(f"  {len(payloads) + 1}. None")
    while True:
        raw = input("  Payloads > ").strip()
        if raw in ("", "done") or raw.lower() in ("q", "quit"):
            return ["none"]
        chosen = []
        for value in raw.split():
            try:
                idx = int(value) - 1
                if 0 <= idx < len(payloads):
                    chosen.append(payloads[idx].id)
                elif idx == len(payloads):
                    return ["none"]
            except ValueError:
                pass
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
    *,
    gas_id: str,
    envelope_id: str,
    payload_ids,
    site_id: str,
    fill_key: str,
) -> float:
    """Mirror the Discord First Flight semantic fill targets with shared equations."""
    envelope = CATALOG.envelope(envelope_id)
    site = CATALOG.site(site_id)
    payloads = with_required_first_flight_payloads(tuple(payload_ids or ()))
    payload_mass_kg = sum(CATALOG.payload(pid).mass_kg for pid in payloads)
    launch_pressure = atmosphere_pressure(site.altitude_m)
    launch_temperature = (
        site.gas_temperature_k
        if site.gas_temperature_k is not None
        else atmosphere_temperature(site.altitude_m) + site.temperature_offset_k
    )
    ambient_density = atmosphere_density(site.altitude_m)
    lifting_density = gas_density(gas_id, launch_temperature, launch_pressure)

    if fill_key == "maximum":
        return maximum_capacity_gas_mass_kg(
            lifting_gas_density_kg_m3=lifting_density,
            max_volume_m3=envelope.max_volume_m3,
        )

    option = FIRST_FLIGHT_FILL_OPTIONS[fill_key]
    return gas_mass_for_supported_fraction_kg(
        non_gas_mass_kg=envelope.mass_kg + payload_mass_kg,
        ambient_density_kg_m3=ambient_density,
        lifting_gas_density_kg_m3=lifting_density,
        max_volume_m3=envelope.max_volume_m3,
        support_fraction=option["support_fraction"],
    )


def show_first_flight_optional_payloads():
    keys = tuple(FIRST_FLIGHT_OPTION_KEYS[3])
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

    while True:
        raw = input("  Optional payloads > ").strip()
        if not raw or raw.lower() in ("done", "none"):
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
            if not (0 <= idx < len(real_keys)):
                valid = False
                break
            selected.append(real_keys[idx])
        if valid:
            return list(with_required_first_flight_payloads(tuple(selected)))
        print("  Invalid selection. Try again.")


def show_first_flight_fill_menu(gas_id, envelope_id, payload_ids, site_id):
    options = []
    for key in FIRST_FLIGHT_OPTION_KEYS[2]:
        try:
            mass = _first_flight_fill_mass(
                gas_id=gas_id,
                envelope_id=envelope_id,
                payload_ids=payload_ids,
                site_id=site_id,
                fill_key=key,
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
    """Terminal version of Discord's six-step First Flight configurator."""
    print("\n  🔧 Balloon Configuration")
    player = PlayerRegistry.get_or_create(player_id)
    print(f"  ⚡ You have {player.reputation} reputation and ${player.budget} budget.")

    print("\n  Step 1/6: Gas Type")
    gas_id = show_gas_menu(FIRST_FLIGHT_OPTION_KEYS[0])
    if gas_id is None:
        return None

    print("\n  Step 2/6: Envelope")
    envelope_id = show_envelope_menu(FIRST_FLIGHT_OPTION_KEYS[1])
    if envelope_id is None:
        return None

    print("\n  Step 3/6: Payloads")
    payload_ids = show_first_flight_optional_payloads()
    if payload_ids is None:
        return None

    print("\n  Step 4/6: Launch Site")
    site_id = show_site_menu(FIRST_FLIGHT_OPTION_KEYS[4], first_flight=True)
    if site_id is None:
        return None

    print("\n  Step 5/6: Fill Mode")
    fill = show_first_flight_fill_menu(gas_id, envelope_id, payload_ids, site_id)
    if fill is None:
        return None
    _, fill_label, gas_mass = fill

    request = LaunchRequest(
        gas_id=gas_id,
        envelope_id=envelope_id,
        payload_ids=tuple(payload_ids),
        launch_site_id=site_id,
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=gas_mass,
        player_id=player_id,
    )

    print("\n  Step 6/6: Review & Launch")
    print("  " + "─" * 45)
    print(f"  Gas:       {CATALOG.gas(gas_id).name}")
    print(f"  Fill:      {fill_label} → {format_mass_kg(gas_mass)}")
    print(f"  Envelope:  {CATALOG.envelope(envelope_id).name}")
    print(
        "  Payloads:  "
        + ", ".join(CATALOG.payload(pid).name for pid in payload_ids)
    )
    print(f"  Site:      {FIRST_FLIGHT_SITE_NAME}")
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return request


def build_standard_story_request(player_id: str):
    """Use the regular Discord Story configuration categories in the CLI."""
    gas_id = show_gas_menu(tuple(GAS_OPTIONS.keys()))
    if gas_id is None:
        return None
    envelope_id = show_envelope_menu(tuple(ENVELOPE_OPTIONS.keys()))
    if envelope_id is None:
        return None
    fill_mode, manual_mass = show_story_fill_mode(envelope_id, gas_id)
    if fill_mode is None:
        return None
    payload_ids = show_payloads_menu(
        tuple(key for key in PAYLOAD_OPTIONS.keys() if key != "none")
    )
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
    print(
        "  Payloads:  "
        + ", ".join(
            CATALOG.payload(pid).name for pid in payload_ids if pid != "none"
        )
    )
    print(f"  Site:      {CATALOG.site(site_id).name}")
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return request


def _legacy_request(player_id: str | None = None):
    balloon_key = show_balloon_menu()
    if balloon_key is None:
        return None
    gas_type = show_gas_menu()
    if gas_type is None:
        return None
    fill_mode, gas_mass = show_fill_presets(balloon_key, gas_type)
    if gas_mass is None:
        return None
    payloads = show_payloads_menu()
    site_key = show_site_menu()
    if site_key is None:
        return None
    if input("  Ready to launch? (y/n) > ").strip().lower() not in ("y", "yes"):
        return None
    return LaunchRequest(
        gas_id=gas_type,
        envelope_id="latex",
        balloon_size=balloon_key,
        payload_ids=tuple(payloads),
        launch_site_id=site_key,
        fill_mode=fill_mode,
        manual_gas_mass_kg=gas_mass if fill_mode == FillMode.MANUAL else None,
        player_id=player_id,
    )


def show_results(
    outcome: FlightOutcome,
    balloon_key=None,
    gas_type=None,
    gas_mass=None,
    payloads=None,
):
    """Render transport-neutral results; legacy parameters remain source-compatible."""
    result = outcome.result
    request = result.launch_request
    if request.balloon_size:
        vehicle = f"{CATALOG.balloon(request.balloon_size).name} latex"
    else:
        vehicle = CATALOG.envelope(request.envelope_id).name
    resolved_mass = fill_mass_for_configuration(
        gas_id=request.gas_id,
        envelope_id=request.envelope_id,
        launch_site_id=request.launch_site_id,
        fill_mode=request.fill_mode,
        manual_gas_mass_kg=request.manual_gas_mass_kg,
        balloon_size=request.balloon_size,
        gas_temperature_delta_k=request.gas_temperature_delta_k,
    )
    names = [
        CATALOG.payload(pid).name for pid in request.payload_ids if pid != "none"
    ]

    print("\n  +-----------------------------------------------+")
    print("  |              FLIGHT RESULTS                  |")
    print("  +-----------------------------------------------+")
    print(f"  Vehicle:     {vehicle}")
    print(f"  Gas:         {CATALOG.gas(request.gas_id).name} ({format_mass_kg(resolved_mass)})")
    print(f"  Payloads:    {', '.join(names) or 'None'}")
    print(f"  Peak Alt:    {result.peak_altitude_m:.1f}m")
    print(f"  Flight Time: {result.duration_s:.1f}s")
    print(
        f"  Result:      "
        f"{'CRASHED' if result.crashed else 'BURST' if result.burst else 'LANDED' if result.landed else 'COMPLETE'}"
    )
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
            print(
                f"    {'PASS' if mission.completed else 'FAIL'} "
                f"{mission.mission_id}{reward}: {mission.explanation}"
            )


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
        if story_mission_id == FIRST_FLIGHT_MISSION_ID:
            request = build_first_flight_request(player_id)
        else:
            request = build_standard_story_request(player_id)
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
    parser.add_argument(
        "--no-animation",
        action="store_true",
        help="show one static launch frame",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI colors",
    )
    parser.add_argument(
        "--animation-speed",
        type=float,
        default=1.0,
        metavar="MULTIPLIER",
    )
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
    while input("  Play again? (y/n) > ").strip().lower() not in (
        "n",
        "no",
        "q",
        "quit",
        "exit",
    ):
        play(args)
    print("Thanks for playing Balloon Frontier!\n")


if __name__ == "__main__":
    main()
