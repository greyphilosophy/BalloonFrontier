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
from balloon_frontier.fill import calculate_optimal_fill, apply_fill_mode, FillMode
from balloon_frontier.fill import MULTIPLIER_LIGHT, MULTIPLIER_NORMAL, MULTIPLIER_HEAVY

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

PAYLOADS = {
    "camera":      ("Camera",          1.5),
    "radio":       ("Radio Repeater",  2.0),
    "weather_sens":("Weather Sensor",  0.8),
    "battery":     ("Battery Pack",    3.0),
    "heater":      ("Heater",          2.5),
    "ballast":     ("Ballast (Sand)", 15.0),
    "parachute":   ("Parachute",       2.0),
    "flight_comp": ("Flight Computer", 1.2),
    "none":        ("None",             1.0),
}

SITES = {
    "field":   ("Open Field",    288.15, 0.0),
    "mountain":("Mountain Ridge", 283.15, 500.0),
    "rooftop": ("Urban Rooftop", 291.15, 0.0),
}

# Playable roster (small set calibration update): exclude 21" and 29" from play
# while keeping them available in BALLOON_SIZES for other uses/debug.
PLAYABLE_BALLOON_LIST = [k for k in BALLOON_SIZES.keys() if k not in ("s21", "s29")]
BALLOON_LIST = PLAYABLE_BALLOON_LIST
PAYLOAD_LIST = list(PAYLOADS.keys())
SITE_LIST = list(SITES.keys())


# ── Input Helpers ────────────────────────────────────────

def get_choice(count, prompt="Choose"):
    """Get a numeric menu choice (1-indexed). Returns 0-based index or None."""
    while True:
        raw = input(f"  {prompt} > ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        try:
            n = int(raw)
            if 1 <= n <= count:
                return n - 1  # return 0-based
        except (ValueError, TypeError):
            pass

def get_number(prompt, default, min_val=0.01):
    """Get a numeric input. Returns float or None."""
    while True:
        raw = input(f"  {prompt} > ").strip()
        if raw.lower() in ("q", "quit", "exit"):
            return None
        if raw == "":
            return default
        try:
            val = float(raw)
            if val >= min_val:
                return val
        except ValueError:
            pass

# ── Fill Mode Presets ──────────────────────────────────────

FILL_PRESETS = [
    {"mode": FillMode.AUTO,   "label": "Auto",   "desc": "Optimal fill, safe burst margin"},
    {"mode": FillMode.LIGHT,  "label": "Light",  "desc": "20% less gas — faster climb"},
    {"mode": FillMode.NORMAL, "label": "Normal", "desc": "Baseline optimal fill"},
    {"mode": FillMode.HEAVY, "label": "Heavy",  "desc": "20% more gas — longer float"},
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


def show_fill_presets(balloon_key, gas_type):
    """Show fill mode selection UI with presets and auto option.
    
    Displays all fill presets with their calculated masses.
    Returns the selected FillMode and computed mass.
    UI state persists across screen transitions via returned mode.
    
    Acceptance:
    - Selecting any option immediately updates displayed mass
    - Shows computed mass value next to each option
    """
    balloon_spec = BALLOON_SIZES[balloon_key]
    max_vol = balloon_spec["max_vol"]
    
    # Calculate masses for all presets
    base_mass = calculate_optimal_fill(max_vol, gas_type)
    preset_masses = {}
    for preset in FILL_PRESETS:
        if preset["mode"] == FillMode.MANUAL:
            preset_masses[preset["mode"]] = None
        else:
            preset_masses[preset["mode"]] = apply_fill_mode(max_vol, gas_type, preset["mode"])
    
    print("\n  Fill Mode Selection")
    print("  ─────────────────────────────────────────────")
    print(f"  Envelope: {balloon_spec['name']} ({max_vol:.1f}m³ max)")
    print(f"  Gas type: {gas_type.replace('_', ' ').title()}")
    print()
    
    for i, preset in enumerate(FILL_PRESETS, 1):
        mode = preset["mode"]
        mass = preset_masses[mode]
        mass_str = format_mass_kg(mass) if mass else "You choose"
        print(f"  {i}. {preset['label']:<8s} {mass_str:<12s} {preset['desc']}")
    
    print()
    
    while True:
        raw = input("  Select fill mode (1-5) > ").strip()
        
        if raw.lower() in ("q", "quit", "exit"):
            return None, None
        
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(FILL_PRESETS):
                selected = FILL_PRESETS[idx]

                if selected["mode"] == FillMode.MANUAL:
                    fill_range = balloon_spec["fill_g"]
                    safe_mid = (fill_range[0] + fill_range[1]) / 2 / 1000

                    g_low, g_high = fill_range
                    kg_low = g_low / 1000
                    kg_high = g_high / 1000

                    print(
                        f"  Safe fill: {g_low}–{g_high}g "
                        f"({format_kg_compact(kg_low)}–{format_kg_compact(kg_high)} kg)"
                    )

                    print("  Preset masses for reference:")
                    for ref in FILL_PRESETS:
                        if ref["mode"] != FillMode.MANUAL:
                            ref_mass = preset_masses[ref["mode"]]
                            print(f"    {ref['label']}: {format_mass_kg(ref_mass)}")

                    gas_mass = get_number(
                        f"Gas mass (kg) [default {safe_mid:.3f}]",
                        safe_mid,
                        min_val=0.001,
                    )
                    if gas_mass is None:
                        return None, None
                    return FillMode.MANUAL, gas_mass
                else:
                    mass = apply_fill_mode(max_vol, gas_type, selected["mode"])
                    print(f"  Selected: {selected['label']} → {format_mass_kg(mass)}")
                    return selected["mode"], mass
            else:
                print(f"  Invalid: choose 1-{len(FILL_PRESETS)}")
        except ValueError:
            print("  Enter a number from 1 to 5")


def show_balloon_menu():
    print("\n  Select your balloon size:")
    print("  ─────────────────────────────────────────────")
    print("  Size   Mass   Max Vol  Safe Fill (g)")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(BALLOON_LIST):
        s = BALLOON_SIZES[key]
        low, high = s["fill_g"]
        print(f"  {i+1}. {s['name']:<10s} {s['mass_kg']*1000:>5.0f}g  {s['max_vol']:>6.1f}m³  {low:>5}-{high:>5}g")
    print()
    idx = get_choice(len(BALLOON_LIST), f"Balloon size (1-{len(BALLOON_LIST)})")
    return BALLOON_LIST[idx] if idx is not None else None


def show_gas_menu():
    print("\n  Gas type:")
    print("  ─────────────────────────────────────────────")
    print("  1. Helium (stable, moderate lift)")
    print("  2. Hydrogen (best lift, flammable)")
    print("  3. Hot Air (needs heat source)")
    print()
    idx = get_choice(3, "Gas type (1-3)")
    return ["helium", "hydrogen", "hot_air"][idx] if idx is not None else None


def show_payloads_menu():
    print("\n  Select payloads (space-separated numbers, or 'done'):")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(PAYLOAD_LIST):
        v = PAYLOADS[key]
        print(f"  {i+1}. {v[0]}  ({v[1]} kg)")
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
        if chosen:
            selected = chosen


def show_site_menu():
    print("\n  Launch site:")
    print("  ─────────────────────────────────────────────")
    for i, key in enumerate(SITE_LIST):
        v = SITES[key]
        print(f"  {i+1}. {v[0]}")
    print()
    idx = get_choice(len(SITE_LIST), "Launch site (1-3)")
    return SITE_LIST[idx] if idx is not None else None


# ── Simulation ───────────────────────────────────────────

def run_flight(gas_type, gas_mass, envelope_spec, payload_ids, site_key):
    site_info = SITES[site_key]
    site_temp_k = site_info[1]
    terrain_offset_m = site_info[2]

    env_config = EnvelopeConfig(
        max_volume_m3=envelope_spec["max_vol"],
        burst_stretch_ratio=envelope_spec["burst"],
        drag_coefficient=0.47,
        permeability=0.001,
        mass_kg=envelope_spec["mass_kg"],
        contained_gas=True,
    )
    payload_mass = sum(PAYLOADS[p][1] for p in payload_ids)
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
        "medal": tier.name, "medal_emoji": get_medal_emoji(peak),
    }


def show_results(envelope_spec, gas_type, gas_mass, payload_ids, summary):
    print("\n  ════════════════════════════════════════════════════")
    print("  🎈 FLIGHT RESULTS")
    print("  ════════════════════════════════════════════════════")
    peak = summary.get("peak_altitude", 0)
    target = 30000
    if peak >= target:
        status = "🟢 TARGET REACHED"
    elif peak >= target * 0.7:
        status = "🟡 CLOSE"
    else:
        status = "🔵 KEEPING GOING"
    print(f"  Peak Altitude: {peak:>10,.0f} m  ({status})")
    print(f"  Target:        {target:>10,} m")
    initial_altitude_m = summary.get("initial_altitude_m", 0)
    print(f"  Initial Alt:  {initial_altitude_m:>10,.0f} m")

    time_of_flight = summary.get("time_of_flight", 0)
    print(f"  Time:          {time_of_flight:>6.1f} s")

    # ── Medal ───────────────────────────────────────────
    medal = summary.get("medal", "None")
    medal_emoji = summary.get("medal_emoji", "⚪")
    print(f"  Medal:         {medal_emoji} {medal}")

    # ── Score ───────────────────────────────────────────
    score = summary.get("score", 0)
    payload_count = summary.get("payload_count", 0)
    print(f"  Score:         {score:>.2f}")
    print(f"  (Alt: {peak:,.0f} × 1.0 + {payload_count} payloads × 500 + time)")
    burst = summary.get("burst", False)
    crashed = summary.get("crashed", False)
    landed = summary.get("landed", False)

    if burst:
        print("  💥 BURST — envelope burst!")
    elif crashed:
        print("  🏁 Landed — CRASHED")
    elif landed:
        print("  🏁 Landed safely!")
    else:
        print("  📈 Still climbing after 5 minutes!")
    print()


# ── Game Flow ────────────────────────────────────────────

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
    print(f"  Payloads: {', '.join(PAYLOADS[p][0] for p in payloads)}")
    print(f"  Site:     {SITES[site_key][0]}")
    print("  ─────────────────────────────────────────────────")

    resp = input("  Ready to launch? (y/n) > ").strip().lower()
    if resp not in ("y", "yes"):
        print("  See you next time!")
        return

    print("\n  🚀 Launching...\n")
    tel, summary = run_flight(gas_type, gas_mass, balloon_spec, payloads)
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
