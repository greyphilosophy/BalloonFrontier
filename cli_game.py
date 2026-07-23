#!/usr/bin/env python3
"""Balloon Frontier — CLI Game

Playable balloon building simulator with realistic sizing.

Usage:
    python3 cli_game.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from balloon_frontier.simulation import SimulationState, EnvelopeConfig, run_simulation
from balloon_frontier.flight_score import calculate_flight_score
from balloon_frontier.medal_tier import get_medal_tier, get_medal_emoji, medal_tier_to_string
from balloon_frontier.fill import calculate_optimal_fill, apply_fill_mode, FillMode, calculate_max_safe_gas_mass
from balloon_frontier.fill import MULTIPLIER_LIGHT, MULTIPLIER_NORMAL, MULTIPLIER_HEAVY
from balloon_frontier.launch_sites import LaunchSiteInfo

# ── Latex Balloon Sizes ──────────────────────────────────
# Realistic weather balloon data (Great Balloon / Scott Balloons)
BALLOON_SIZES = {
    "s21":  {"name": '21"',   "mass_kg": 0.025,  "max_vol": 0.6,  "burst": 2.3, "fill_g": (10, 120)},
    "s29":  {"name": '29"',   "mass_kg": 0.040,  "max_vol": 1.5,  "burst": 2.3, "fill_g": (20, 250)},
    "s36":  {"name": '36"',   "mass_kg": 0.060,  "max_vol": 3.5,  "burst": 2.3, "fill_g": (30, 1158)},
    "s45":  {"name": '45"',   "mass_kg": 0.085,  "max_vol": 6.0,  "burst": 2.2, "fill_g": (50, 1163)},
    "s55":  {"name": '55"',   "mass_kg": 0.110,  "max_vol": 10.0, "burst": 2.2, "fill_g": (80, 1500)},
    "s70":  {"name": '70"',   "mass_kg": 0.200,  "max_vol": 25.0, "burst": 2.2, "fill_g": (150, 3000)},
    "s100": {"name": '100"',  "mass_kg": 0.400,  "max_vol": 75.0, "burst": 2.1, "fill_g": (400, 7000)},
    "s150": {"name": '150"',  "mass_kg": 0.700,  "max_vol": 250.0,"burst": 2.0, "fill_g": (1000, 15000)},
}


# Balloon list exposed for tests
# s21 and s29 are excluded as too small for practical gameplay
_SMALL_BALLOONS = {"s21", "s29"}
BALLOON_LIST = [k for k in BALLOON_SIZES.keys() if k not in _SMALL_BALLOONS]
PLAYABLE_BALLOON_LIST = list(BALLOON_LIST)  # All listed balloons are playable



PAYLOADS = {
    "camera":      ("Camera",          1.5, False),
    "radio":       ("Radio Repeater",  2.0, False),
    "weather_sens":("Weather Sensor",  0.8, False),
    "battery":     ("Battery Pack",    3.0, False),
    "heater":      ("Heater",          2.5, False),
    "ballast":     ("Ballast (Sand)",  15.0, False),
    "parachute":   ("Parachute",       2.0, False),
    "flight_comp": ("Flight Computer", 1.2, False),
    "valve":       ("Pressure Valve",  0.3, True),   # Prevents bursting by venting gas
    "none":        ("None",             1.0, False),
}

SITES = {
    "field": LaunchSiteInfo(
        name="Open Field",
        altitude_m=0.0,
        gas_temperature_k=288.15,
        temperature_offset_k=0.0,
        wind_strength=2.0,
        description="Flat terrain, mild crosswind",
    ),
    "mountain": LaunchSiteInfo(
        name="Mountain Ridge",
        altitude_m=1500.0,
        gas_temperature_k=278.15,
        temperature_offset_k=-5.0,
        wind_strength=4.0,
        description="Elevated, colder, stronger wind",
    ),
    "rooftop": LaunchSiteInfo(
        name="Urban Rooftop",
        altitude_m=50.0,
        gas_temperature_k=291.15,
        temperature_offset_k=3.0,
        wind_strength=3.0,
        description="Warm microclimate, moderate wind",
    ),
}

# ── Gas Types ─────────────────────────────────────────────
GAS_OPTIONS = {
    "helium":      ("Helium",      0.0040026, "lighter"),
    "hydrogen":    ("Hydrogen",    0.002016,  "lighter"),
    "hot_air":     ("Hot Air",     0.028965,  "neutral"),
    "methane":     ("Methane",     0.01604,   "lighter"),
}

# ── Payload list for menu ordering ──────────────────────────
PAYLOAD_LIST = list(PAYLOADS.keys())

# ── Fill mode presets ──────────────────────────────────────

FILL_PRESETS = [
    {"mode": FillMode.AUTO,   "label": "Auto",   "desc": "Optimal fill, safe burst margin"},
    {"mode": FillMode.LIGHT,  "label": "Light",  "desc": "20% less gas — slower ascent"},
    {"mode": FillMode.NORMAL, "label": "Normal", "desc": "Baseline optimal fill"},
    {"mode": FillMode.HEAVY, "label": "Heavy",  "desc": "20% more gas — faster ascent"},
    {"mode": FillMode.MANUAL, "label": "Manual", "desc": "Specify exact gas mass"},
]


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


def _validate_envelope_params(balloon_spec):
    """Validate and extract envelope parameters from the balloon spec.
    
    Validates that the required fields exist and are numeric, returning
    a dict of envelope parameters ready for the shared calculation.
    
    Raises:
        ValueError: If required fields are missing or malformed.
    """
    if "max_vol" not in balloon_spec:
        raise ValueError(f"Missing 'max_vol' in balloon spec for {balloon_spec.get('name', 'unknown')}")
    if "burst" not in balloon_spec:
        raise ValueError(f"Missing 'burst' in balloon spec for {balloon_spec.get('name', 'unknown')}")
    if not isinstance(balloon_spec["max_vol"], (int, float)):
        raise ValueError(f"'max_vol' must be numeric, got {balloon_spec['max_vol']!r}")
    if not isinstance(balloon_spec["burst"], (int, float)):
        raise ValueError(f"'burst' must be numeric, got {balloon_spec['burst']!r}")
    if balloon_spec["max_vol"] <= 0:
        raise ValueError(f"'max_vol' must be positive, got {balloon_spec['max_vol']}")
    if balloon_spec["burst"] <= 0:
        raise ValueError(f"'burst' must be positive, got {balloon_spec['burst']}")
    return {
        "max_vol": balloon_spec["max_vol"],
        "burst_stretch_ratio": balloon_spec["burst"],
    }


def show_fill_presets(balloon_key, gas_type):
    """Show fill mode selection UI with presets and auto option.

    Displays all fill presets with their calculated masses using envelope
    parameters passed to the shared calculate_max_safe_gas_mass() function.
    Returns the selected FillMode and computed mass.
    UI state persists across screen transitions via returned mode.

    Acceptance:
    - Selecting any option immediately updates displayed mass
    - Shows computed mass value next to each option
    - Passes burst_stretch_ratio from envelope spec to shared calculation
    """
    
    balloon_spec = BALLOON_SIZES[balloon_key]
    envelope_params = _validate_envelope_params(balloon_spec)
    
    gas_density = gas_type in ("helium", "hydrogen") and 0.004 or 0.028965  # simplified
    
    while True:
        print("\n  Fill mode:")
        print("  ─────────────────────────────────────────────")
        for preset in FILL_PRESETS:
            mode = preset["mode"]
            label = preset["label"]
            desc = preset["desc"]
            
            try:
                mass_kg = calculate_max_safe_gas_mass(
                    max_volume=envelope_params["max_vol"],
                    burst_stretch_ratio=envelope_params["burst_stretch_ratio"],
                    fill_mode=mode,
                    gas_density=gas_density,
                )
                mass_str = format_mass_kg(mass_kg)
                print(f"  {label}: {desc} ({mass_str})")
            except Exception as e:
                print(f"  {label}: {desc} (error: {e})")
        
        print()
        idx = get_choice(len(FILL_PRESETS), "Fill mode (1-5)")
        if idx is None:
            return None, None
        
        selected_mode = FILL_PRESETS[idx]["mode"]
        
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
        else:
            # Auto-calculate mass
            mass_kg = calculate_max_safe_gas_mass(
                max_volume=envelope_params["max_vol"],
                burst_stretch_ratio=envelope_params["burst_stretch_ratio"],
                fill_mode=selected_mode,
                gas_density=gas_density,
            )
            gas_mass_kg = mass_kg
            print(f"\n  Selected {selected_mode.value} fill: {format_mass_kg(gas_mass_kg)}")
        
        return selected_mode, gas_mass_kg


def show_balloon_menu():
    """Display balloon selection menu and return the chosen balloon key."""
    print("\n  Balloon size:")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(BALLOON_SIZES):
        v = BALLOON_SIZES[key]
        print(f"  {i+1}. {v['name']} ({v['max_vol']:.1f}m³, burst@{v['burst'] * v['max_vol']:.1f}m³, {v['mass_kg']*1000}g)")
    print()
    return get_balloon_choice()


def get_balloon_choice():
    """Prompt user for balloon size selection."""
    idx = get_choice(len(BALLOON_SIZES), "Balloon (1-8)")
    keys = list(BALLOON_SIZES.keys())
    return keys[idx] if idx is not None else None


def show_gas_menu():
    """Display gas type selection menu and return the chosen gas type."""
    print("\n  Gas type:")
    print("  ─────────────────────────────────────────────")
    for i, (key, (name, density, behavior)) in enumerate(GAS_OPTIONS.items()):
        print(f"  {i+1}. {name} (density={density:.4f} kg/m³, {behavior})")
    print()
    idx = get_choice(len(GAS_OPTIONS), "Gas (1-4)")
    keys = list(GAS_OPTIONS.keys())
    return keys[idx] if idx is not None else None


def show_payloads_menu():
    """Display payload selection menu and return chosen payload IDs."""
    print("\n  Select payloads (space-separated numbers, or 'done'):")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(PAYLOAD_LIST):
        v = PAYLOADS[key]
        has_valve = v[2]
        valve_note = " 🛡️" if has_valve else ""
        print(f"  {i+1}. {v[0]}  ({v[1]} kg){valve_note}")
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
                if 0 <= idx < len(PAYLOAD_LIST):
                    chosen.append(PAYLOAD_LIST[idx])
            except ValueError:
                pass
        if not chosen:
            print("  Invalid selection. Try again.")
        else:
            return chosen


def show_site_menu():
    print("\n  Launch site:")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(SITE_LIST):
        v = SITES[key]
        print(f"  {i+1}. {v.name}")
    print()
    idx = get_choice(len(SITE_LIST), "Launch site (1-3)")
    return SITE_LIST[idx] if idx is not None else None


SITE_LIST = ["field", "mountain", "rooftop"]


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


# ── Simulation ───────────────────────────────────────────

def run_flight(gas_type, gas_mass, envelope_spec, payload_ids, site_key):
    site_info = SITES[site_key]
    site_temp_k = site_info.gas_temperature_at_launch()
    terrain_offset_m = site_info.altitude_m

    env_config = EnvelopeConfig(
        max_volume_m3=envelope_spec["max_vol"],
        burst_stretch_ratio=envelope_spec["burst"],
        drag_coefficient=0.47,
        permeability=0.001,
        mass_kg=envelope_spec["mass_kg"],
        contained_gas=True,
    )
    payload_mass = sum(PAYLOADS[p][1] for p in payload_ids)
    has_valve = any(PAYLOADS[p][2] for p in payload_ids)  # Check if valve is equipped
    
    state = SimulationState(
        gas_type=gas_type,
        gas_mass_kg=gas_mass,
        payload_mass_kg=payload_mass,
        envelope=env_config,
        # alt is absolute above sea level; for an elevated launch site,
        # start the balloon at the site's ground elevation.
        altitude_m=terrain_offset_m,
        # This tells the physics engine what "ground" is when deciding
        # landing/crash events.
        terrain_base_altitude_offset_m=terrain_offset_m,
        gas_temperature_k=site_temp_k,
        # Pass valve information to the simulation
        has_pressure_valve=has_valve,
    )
    initial_altitude_m = state.altitude_m
    tel = run_simulation(state, dt=0.1, total_time_s=300, max_steps=5000)
    if not tel:
        return [], {
            "peak_altitude": 0, "burst": True, "landed": False,
            "crashed": False, "time_of_flight": 0, "final_alt": 0,
            "initial_altitude_m": initial_altitude_m,
            "payload_count": len(payload_ids), "score": 0, "medal": "None",
            "medal_emoji": "⚪",
        }
    last = tel[-1]
    peak = max(t["altitude_m"] for t in tel)
    time_of_flight = last["time_s"]
    payload_count = len(payload_ids)
    score = calculate_flight_score(peak, payload_count, time_of_flight)
    tier = get_medal_tier(peak)
    return tel, {
        "peak_altitude": peak, "burst": last["burst"],
        "landed": last["landed"], "crashed": last["crashed"],
        "time_of_flight": time_of_flight, "final_alt": last["altitude_m"],
        "initial_altitude_m": initial_altitude_m,
        "payload_count": payload_count, "score": score,
        "medal": tier, "medal_emoji": get_medal_emoji(summary["peak_altitude"]),
        "has_pressure_valve": has_valve,
    }


def show_results(balloon_spec, gas_type, gas_mass, payloads, summary):
    """Display flight results with medal and stats."""
    valve_note = " 🛡️" if summary.get("has_pressure_valve") else ""
    print("\n  ╔═══════════════════════════════════════════════╗")
    print("  ║              🎈 FLIGHT RESULTS 🎈             ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print(f"  Balloon:    {balloon_spec['name']} latex")
    print(f"  Gas:        {gas_type} ({format_mass_kg(gas_mass)})")
    payload_names = [PAYLOADS[p][0] for p in payloads]
    print(f"  Payloads:   {', '.join(payload_names)}{valve_note}")
    print(f"  Peak Alt:   {summary['peak_altitude']:.1f}m")
    print(f"  Flight Time: {summary['time_of_flight']:.1f}s")
    if summary["burst"]:
        print(f"  Result:     💥 BURST")
    elif summary["landed"]:
        print(f"  Result:     ✅ LANDED")
    if summary["crashed"]:
        print(f"  Status:     💥 CRASHED!")
    print(f"  Score:      {summary['score']:.1f}")
    print(f"  Medal:      {summary['medal_emoji']} {summary['medal']}")


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
    balloon_spec = BALLOON_SIZES[balloon_key]
    print(f"  Selected: {balloon_spec['name']} latex balloon")

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
        fill_range = balloon_spec["fill_g"]
        if gas_mass * 1000 > fill_range[1]:
            print(f"\n  ⚠️  WARNING: {gas_mass*1000:.0f}g exceeds safe fill ({fill_range[1]}g)!")
        if gas_mass * 1000 < fill_range[0]:
            print(f"\n  💡 TIP: {gas_mass*1000:.0f}g is below the typical fill range.")

    # Review
    print("\n  ─────────────────────────────────────────────────")
    print("  CONFIGURATION")
    print("  ─────────────────────────────────────────────────")
    print(f"  Balloon:  {balloon_spec['name']} latex")
    print(f"  Gas:      {gas_type} ({format_mass_kg(gas_mass)})")
    payload_names = [PAYLOADS[p][0] for p in payloads]
    has_valve = any(PAYLOADS[p][2] for p in payloads)
    valve_note = " 🛡️ Valve equipped" if has_valve else ""
    print(f"  Payloads: {', '.join(payload_names)}{valve_note}")
    print(f"  Site:     {SITES[site_key].name}")
    print("  ─────────────────────────────────────────────────")

    resp = input("  Ready to launch? (y/n) > ").strip().lower()
    if resp not in ("y", "yes"):
        print("  See you next time!")
        return

    print("\n  🚀 Launching...\n")
    tel, summary = run_flight(gas_type, gas_mass, balloon_spec, payloads, site_key)
    show_results(balloon_spec, gas_type, gas_mass, payloads, summary)


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