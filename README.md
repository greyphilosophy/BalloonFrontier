# Balloon Frontier

A real-physics balloon engineering, exploration, and mission simulation game.

## Overview

Balloon Frontier lets players design lighter-than-air vehicles, select lifting gases, launch from varied environments, ride atmospheric wind layers, operate payloads, and complete missions. The game uses physically plausible, inspectable models rather than scripted outcomes.

## Architecture

- **Python physics engine** (`balloon_frontier/`) — Deterministic physics calculations
- **Godot 4.x game** (`scenes/`) — Visual simulation and UI
- **Tests** (`tests/`) — Comprehensive pytest coverage for every equation

## Quick Start

```bash
# Install dependencies
pip install -e ".[test]"

# Run physics tests
python -m pytest tests/ -v

# Launch Godot
godot --headless --run_main_scene
```

## Milestones

- **M0:** Project bootstrap ✓
- **M1:** Deterministic fixed-step vertical balloon sandbox
- **M2:** Workshop (vehicle builder)
- **M3:** Mission system, launch sites
- **M4:** Thermal model, propulsion, wind-layer navigation
- **M5:** Polished UI, save/load, replay

## Tests

All 37 physics tests pass:
```
tests/test_physics.py::test_g_value PASSED
tests/test_physics.py::test_r_universal PASSED
tests/test_physics.py::test_r_air PASSED
tests/test_physics.py::TestAtmosphereModel::test_sea_level_temperature PASSED
... (37 total)
```

## License

MIT
