# 🎈 Balloon Frontier

A playable balloon building simulator with realistic physics, CLI game interface, and Discord bot integration.

## Features

- **Realistic Physics Engine**: Ideal gas law, US Standard Atmosphere model, semi-implicit Euler integration
- **CLI Game**: Interactive terminal game for testing balloon configurations
- **Discord Bot**: Step-by-step button interface for configuring and launching flights
- **Modular Architecture**: Physics, simulation, thermal, wind, valves, and fuel subsystems
- **Fill Modes**: Auto-fill presets (Light, Normal, Heavy, Manual) for strategic gas management
- **Medal System**: Peak altitude tiers from Bronze to Platinum
- **Missions**: 17 unique missions with objectives, budgets, and difficulty ratings
- **Weather Events**: Dynamic conditions affecting flight dynamics with severity ratings

## Installation

```bash
cd BalloonFrontier
python3 -m venv venv
source venv/bin/activate
pip install pytest discord.py
```

## CLI Game

```bash
python3 cli_game.py
```

### Game Flow
1. **Select Balloon Size**: 36" to 150" latex weather balloons (21" & 29" retired from gameplay due to insufficient lift)
2. **Choose Gas Type**: Helium, Hydrogen, or Hot Air
3. **Set Gas Mass**: Enter fill weight in kg
4. **Select Payloads**: Camera, Radio, Battery Pack, etc.
5. **Pick Launch Site**: Open Field, Mountain Ridge, or Urban Rooftop
6. **Launch**: Watch your balloon climb!

### Balloon Sizes

| Size | Mass | Max Volume | Safe Fill (g) |
|------|------|------------|---------------|
| 21"  | 25g  | 0.6m³      | 10–120        |
| 29"  | 40g  | 1.5m³      | 20–250        |
| 36"  | 60g  | 3.5m³      | 30–1158       |
| 45"  | 85g  | 6.0m³      | 50–1163       |
| 55"  | 110g | 10.0m³     | 80–1500       |
| 70"  | 200g | 25.0m³     | 150–3000      |
| 100" | 400g | 75.0m³     | 400–7000      |
| 150" | 700g | 250.0m³    | 1000–15000    |

Note: 21" and 29" are excluded from the playable roster (cli_game.PLAYABLE_BALLOON_LIST) because their max lift cannot support even the light payloads required by gameplay.

### Fill Modes

Fill modes control how much lifting gas is loaded into the balloon envelope, affecting ascent rate and burst altitude. The system calculates optimal masses based on the ideal gas law at sea-level standard conditions.

| Mode   | Multiplier | Description |
|--------|-----------|-------------|
| **Auto** | 1.0x | Optimal fill — safe burst margin |
| **Light** | 0.8x | Less free lift, slower ascent, higher burst altitude |
| **Normal** | 1.0x | Baseline optimal fill |
| **Heavy** | 1.2x | More free lift, faster ascent, earlier burst |
| **Manual** | — | Player-specified gas mass, clamped to burst-safe range |

All auto-fill modes (Auto, Light, Normal, Heavy) are clamped to a dynamic burst-safe limit:
- **Safe volume** = nominal volume × burst stretch ratio × safe fill fraction (0.55–0.65 depending on envelope type)
- Envelope-specific presets: **Latex** (2.5x stretch, 0.6 safe), **Mylar** (3.0x stretch, 0.55 safe), **Zero-Pressure** (1.8x stretch, 0.65 safe), **Blimp** (2.0x stretch, 0.6 safe)

### Payloads

- Camera (1.5 kg)
- Radio Repeater (2.0 kg)
- Weather Sensor (0.8 kg)
- Battery Pack (3.0 kg)
- Heater (2.5 kg)
- Ballast - Sand (15.0 kg)
- Parachute (2.0 kg)
- Flight Computer (1.2 kg)
- Pressure Valve (0.3 kg) — vents gas at burst threshold to prevent burst

### Launch Sites

- **Open Field**: 288.15K, sea level
- **Mountain Ridge**: 283.15K, elevated
- **Urban Rooftop**: 291.15K, warm microclimate

## Medal System

Flights earn medals based on the peak altitude achieved. Medals provide quick visual feedback on flight performance.

| Medal | Altitude Threshold | Emoji |
|-------|-------------------|-------|
| ⚪ None | < 2,000m | ⚪ |
| 🟤 Bronze | ≥ 2,000m | 🟤 |
| 🟡 Silver | ≥ 4,000m | 🟡 |
| 🥇 Gold | ≥ 6,000m | 🥇 |
| 💎 Platinum | ≥ 8,000m | 💎 |

These thresholds were calibrated to match real achievable altitudes across all balloon size and gas combinations.

## Missions

Each flight can be assigned 1–3 missions selected from the mission pool. Mission selection is deterministic — the same launch configuration always produces the same missions. Missions are filtered by launch site and required payloads so the player only receives missions their balloon can perform.

**Mission format:**
- **Title** & **Description**: Narrative context for the flight
- **Objectives**: Specific goals (e.g., reach 10,000m altitude, capture a photo, recover data)
- **Launch Site**: Required launch site, when specified
- **Budget**: Currency or resource cost
- **Required Payloads**: Equipment needed for the mission
- **Difficulty**: 1–5 scale rating

**Mission pool (17 missions):**

| Mission | Difficulty | Budget |
|---------|-----------|--------|
| first_flight | 1 | 500 |
| steady_ascent | 1 | 800 |
| ocean_survey | 1 | 5000 |
| aurora_chase | 1 | 3000 |
| sounding_01 | 2 | 5000 |
| signal_drop | 2 | 4000 |
| desert_dreamer | 2 | 3500 |
| ozone_layer | 2 | 5500 |
| sky_high_competition | 2 | 8000 |
| polar_night | 3 | 3000 |
| midnight_sun | 3 | 4500 |
| crossing_winds | 3 | 7000 |
| stratospheric_dust | 3 | 6000 |
| volcanic_watch | 3 | 6500 |
| space_tourism_promo | 4 | 12000 |
| supersonic | 4 | 10000 |
| meteorology_final | 5 | 15000 |

Missions are stored as JSON files in `data/missions/` for easy content expansion.


## Weather

The atmospheric weather model supports altitude and diurnal variation. Each Discord launch also receives a deterministic site-specific weather event based on its configuration.

### Diurnal Effects

- **Temperature**: Follows a cosine curve peaking at 2 PM (12.5K swing)
- **Wind**: Peaks at noon, varies by altitude (logarithmic increase)
- **Clouds**: Layers at 800m, 2000m, 4500m, 8000m, 15000m with ±500m diurnal shift

### Weather Events

Each launch generates randomized weather conditions with four severity levels:

| Severity | Conditions | Examples |
|----------|-----------|----------|
| 🟢 Favorable | Calm, clear skies | Smooth sailing, gentle breeze |
| 🟡 Moderate | Moderate winds, some clouds | Unsettled air, temperature inversion |
| 🟠 Challenging | Strong crosswinds, pressure dips | Thermal instability, cloud ceiling |
| 🔴 Hazardous | Storm fronts, extreme conditions | Jet stream crosswinds, pressure crash |

Weather factors include:
- **Wind Gust Factor** (0.5x–2.5x): Multiplier on wind speed affecting drift
- **Temperature Anomaly** (-15K to +12K): Offset from standard atmosphere
- **Cloud Density** (0.0–0.8): Fractional sky cover affecting solar heating
- **Pressure Offset** (-800 to +500 Pa): Local pressure anomaly
- **Storm Risk** (0.0–0.4): Increases the effective risk of envelope burst

Weather is seeded deterministically from the launch configuration (gas, envelope, payloads, site) for reproducible gameplay.

## Discord Bot

```bash
python3 -m venv venv
source venv/bin/activate
pip install discord.py
python3 start_bot.py
```

Or set the environment variable:
```bash
DISCORD_BF_TOKEN="your-token-here" python3 start_bot.py
```

### Commands

- `/launch` — Open the step-by-step balloon configurator
- `/physics` — View the physics equations
- `/help` — List available commands
- `/profile` — Show player status and equipment unlock progress

## Game Mechanics

### Physics Model

The simulation uses:
- **Ideal Gas Law**: PV = nRT (helium, hydrogen, hot air, methane)
- **Buoyancy**: F_buoy = (ρ_air - ρ_gas) × g × V
- **Drag**: F_drag = 0.5 × ρ × v² × C_d × A
- **Semi-implicit Euler Integration**: Semi-implicit Euler integration with dt=0.1s
- **US Standard Atmosphere**: 3 layers with temperature gradient, pressure, and density
- **Burst Detection**: Contained (latex) envelopes burst when gas volume exceeds burst_stretch_ratio × max_volume

### Balloon Types

- **Contained Gas** (latex/superpressure): Gas expands freely, displaced = gas volume
- **Zero-Pressure**: Gas vents at max_volume, displaced = min(gas volume, max volume)

### Gas Types

| Gas | Lift per m³ | Molar Mass (kg/mol) |
|-----|-----------|-------------------|
| Helium | ~1.05 kg | 0.0040026 |
| Hydrogen | ~1.05 kg | 0.002016 |
| Hot Air | ~0.22 kg | 0.0289652068 |
| Methane | ~1.04 kg | 0.01604 |

## Tests

```bash
cd BalloonFrontier && python -m pytest tests/ -q
```

## Project Structure

```
balloon_frontier/
├── physics.py      — Core physics (atmosphere, gas law, buoyancy, drag)
├── simulation.py   — Fixed-step simulation engine
├── thermal.py      — Lumped-capacitance thermal model
├── equilibrium.py  — Equilibrium altitude calculator
├── valves.py       — Valve controls (vent, ballast)
├── fuel.py         — Fuel/battery models
├── payloads.py     — Payload definitions
├── progression.py  — Mission progression system
├── missions.py     — Mission objectives
├── evaluation.py   — Post-flight scoring
├── weather.py      — Weather conditions
├── weather_event.py — Random weather event generation
├── wind.py         — Wind models
├── fill.py         — Fill mode presets and auto-fill calculator
├── medal_tier.py   — Medal tier determination
├── mission_selection.py — Mission selection from pool
├── flight_score.py — Flight scoring
├── narrative_result.py — Narrative result formatting
├── discord_bot.py  — Discord bot integration
tests/
├── test_physics.py   — Physics engine tests
├── test_simulation.py — Simulation engine tests
├── test_thermal.py   — Thermal model tests
├── test_equilibrium.py — Equilibrium calculations
├── test_valves.py    — Valve controls
├── test_fuel.py      — Fuel models
├── test_payloads.py  — Payload system
├── test_progression.py — Mission progression
├── test_missions.py   — Mission objectives
├── test_evaluation.py — Scoring system
├── test_weather.py   — Weather conditions
├── test_wind.py      — Wind models
├── test_discord_bot.py — Discord bot tests
├── test_e2e.py       — End-to-end tests
├── test_e2e_gameplay.py — End-to-end gameplay tests
```

## License

Copyright (c) 2026 Balloon Frontier