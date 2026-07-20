# 🎈 Balloon Frontier

A playable balloon building simulator with realistic physics, CLI game interface, and Discord bot integration.

## Features

- **Realistic Physics Engine**: Ideal gas law, US Standard Atmosphere model, semi-implicit Euler integration
- **CLI Game**: Interactive terminal game for testing balloon configurations
- **Discord Bot**: Select-menu UI for configuring and launching balloon flights
- **Modular Architecture**: Physics, simulation, thermal, wind, valves, and fuel subsystems

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
1. **Select Balloon Size**: 21" to 150" latex weather balloons
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
| 36"  | 60g  | 3.5m³      | 30–500        |
| 45"  | 85g  | 6.0m³      | 50–1000       |
| 55"  | 110g | 10.0m³     | 80–1500       |
| 70"  | 200g | 25.0m³     | 150–3000      |
| 100" | 400g | 75.0m³     | 400–7000      |
| 150" | 700g | 250.0m³    | 1000–15000    |

### Payloads

- Camera (1.5 kg)
- Radio Repeater (2.0 kg)
- Weather Sensor (0.8 kg)
- Battery Pack (3.0 kg)
- Heater (2.5 kg)
- Ballast - Sand (15.0 kg)
- Parachute (2.0 kg)
- Flight Computer (1.2 kg)

### Launch Sites

- **Open Field**: 288.15K, sea level
- **Mountain Ridge**: 283.15K, elevated
- **Urban Rooftop**: 291.15K, warm microclimate

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

- `/launch` — Open the balloon configurator with select menus
- `/physics` — View the physics equations
- `/help` — List available commands

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
| Hot Air | ~0.22 kg | 0.02897 |
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
├── wind.py         — Wind models
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
```
