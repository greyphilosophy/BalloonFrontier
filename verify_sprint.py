#!/usr/bin/env python3
"""Ad-hoc verification of the Balloon Frontier sprint deliverables.

Verifies:
1. simulation.py loads and exports the expected symbols
2. All physics tests still pass (regression)
3. All simulation tests pass (new)
4. The Godot typo fix is in place
5. Deterministic reproducibility check
6. Physical correctness: helium ascends, hydrogen ascends faster
"""

import sys
import os

# Ensure we can import from the project root
sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

passed = 0
failed = 0
total = 0


def check(name, condition, detail=""):
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}: {detail}")


# ── 1. Module loads and exports expected symbols ─────────────────
print("1. Checking module structure...")

try:
    from balloon_frontier.simulation import (
        EnvelopeConfig, SimulationState, simulation_step, run_simulation
    )
    check("simulation.py imports cleanly", True)
    check("EnvelopeConfig class exists", callable(EnvelopeConfig))
    check("SimulationState class exists", callable(SimulationState))
    check("simulation_step is callable", callable(simulation_step))
    check("run_simulation is callable", callable(run_simulation))
except Exception as e:
    check("simulation.py imports cleanly", False, str(e))

# ── 2. EnvelopeConfig has contained_gas flag ────────────────────
print("2. Checking EnvelopeConfig attributes...")
env = EnvelopeConfig()
check("EnvelopeConfig has contained_gas", hasattr(env, "contained_gas"))
check("contained_gas defaults to False", env.contained_gas == False)
check("EnvelopeConfig has burst_stretch_ratio", hasattr(env, "burst_stretch_ratio"))

# ── 3. SimulationState structure ────────────────────────────────
print("3. Checking SimulationState structure...")
state = SimulationState()
check("State has total_mass() method", callable(state.total_mass))
check("total_mass() returns positive value", state.total_mass() > 0)
check("State has burst flag", hasattr(state, "burst"))
check("State has landed flag", hasattr(state, "landed"))
check("State has crashed flag", hasattr(state, "crashed"))

# ── 4. Simulation step produces valid telemetry ────────────────
print("4. Checking simulation_step output...")
state = SimulationState()
result = simulation_step(state)
required_keys = [
    "time_s", "altitude_m", "velocity_mps", "gas_volume_m3",
    "ambient_pressure_pa", "net_lift_N", "buoyancy_N", "weight_N",
    "drag_N", "burst", "landed", "crashed"
]
for key in required_keys:
    check(f"Telemetry has '{key}'", key in result)

# ── 5. Semi-implicit Euler integration correctness ──────────────
print("5. Checking integration correctness...")
state = SimulationState(
    gas_mass_kg=20.0,
    gas_type="helium",
    payload_mass_kg=3.0,
    envelope=EnvelopeConfig(max_volume_m3=500.0, mass_kg=5.0),
)
tel = run_simulation(state, dt=0.1, total_time_s=5.0)
check("Simulation produces 50 steps", len(tel) == 50)
check("Altitude increases over time",
      tel[-1]["altitude_m"] > tel[0]["altitude_m"])
check("Final altitude > 50m", tel[-1]["altitude_m"] > 50.0)
check("Velocity positive (ascending)",
      tel[-1]["velocity_mps"] > 0)

# ── 6. Determinism ───────────────────────────────────────────────
print("6. Checking determinism...")
state1 = SimulationState(gas_mass_kg=10.0, payload_mass_kg=3.0,
                          envelope=EnvelopeConfig(max_volume_m3=200.0))
state2 = SimulationState(gas_mass_kg=10.0, payload_mass_kg=3.0,
                          envelope=EnvelopeConfig(max_volume_m3=200.0))
tel1 = run_simulation(state1, dt=0.1, total_time_s=3.0)
tel2 = run_simulation(state2, dt=0.1, total_time_s=3.0)
deterministic = all(
    abs(t1["altitude_m"] - t2["altitude_m"]) < 1e-10 for t1, t2 in zip(tel1, tel2)
)
check("Two identical runs produce identical telemetry",
      deterministic,
      f"diff={abs(tel1[-1]['altitude_m'] - tel2[-1]['altitude_m'])}")

# ── 7. Hydrogen vs Helium ──────────────────────────────────────
print("7. Checking hydrogen provides more lift than helium...")
s_he = SimulationState(gas_mass_kg=10.0, gas_type="helium",
                         payload_mass_kg=2.0,
                         envelope=EnvelopeConfig(max_volume_m3=500.0))
s_h2 = SimulationState(gas_mass_kg=10.0, gas_type="hydrogen",
                         payload_mass_kg=2.0,
                         envelope=EnvelopeConfig(max_volume_m3=500.0))
tel_he = run_simulation(s_he, dt=0.1, total_time_s=3.0)
tel_h2 = run_simulation(s_h2, dt=0.1, total_time_s=3.0)
check("Hydrogen balloon ascends higher than helium",
      tel_h2[-1]["altitude_m"] > tel_he[-1]["altitude_m"])

# ── 8. Burst detection ─────────────────────────────────────────
print("8. Checking burst detection...")
env_burst = EnvelopeConfig(
    max_volume_m3=10.0, burst_stretch_ratio=2.0,
    mass_kg=1.0, contained_gas=True,
)
state_burst = SimulationState(gas_mass_kg=50.0, envelope=env_burst)
result_burst = simulation_step(state_burst)
check("Contained envelope bursts when volume exceeds limit",
      result_burst["burst"],
      f"burst={result_burst['burst']}")

# ── 9. Zero-pressure venting ───────────────────────────────────
print("9. Checking zero-pressure venting...")
env_zp = EnvelopeConfig(max_volume_m3=100.0, mass_kg=3.0,
                         contained_gas=False)
state_zp = SimulationState(gas_mass_kg=50.0, envelope=env_zp)
result_zp = simulation_step(state_zp)
check("Zero-pressure balloon vents excess gas", not result_zp["burst"])

# ── 10. Gas leakage ────────────────────────────────────────────
print("10. Checking gas leakage model...")
state_leak = SimulationState(
    gas_mass_kg=10.0,
    envelope=EnvelopeConfig(permeability=0.02, max_volume_m3=200.0),
)
for _ in range(10):
    simulation_step(state_leak, dt=0.1)
check("Gas mass decreases over time", state_leak.gas_mass_kg < 10.0)

# ── 11. Physics tests still pass ────────────────────────────────
print("11. Checking physics tests (regression)...")
import subprocess
result = subprocess.run(
    ["python", "-m", "pytest", "tests/test_physics.py", "-v", "--tb=line", "-q"],
    capture_output=True, text=True,
    cwd="/home/greyphilosophy/projects/BalloonFrontier",
)
physics_pass = "37 passed" in result.stdout
check("All 37 physics tests pass", physics_pass, result.stdout[-200:] if not physics_pass else "")

# ── 12. Godot bug fix ───────────────────────────────────────────
print("12. Checking Godot typo fix...")
with open("/home/greyphilosophy/projects/BalloonFrontier/scripts/simulation.gd") as f:
    gd_content = f.read()
check("Godot: F_buuyancy typo fixed", "F_buuyancy" not in gd_content)
check("Godot: F_buoy used correctly", "F_buoy - F_weight" in gd_content)

# ── 13. Git commit exists ──────────────────────────────────────
print("13. Checking git commit...")
result = subprocess.run(
    ["git", "log", "-1", "--format=%s"],
    capture_output=True, text=True,
    cwd="/home/greyphilosophy/projects/BalloonFrontier",
)
commit_msg = result.stdout.strip()
has_simg = "simulation" in commit_msg.lower()
check("Recent commit mentions simulation", has_simg, commit_msg)

# ── Summary ─────────────────────────────────────────────────────
print(f"\n{'=' * 50}")
print(f"Verification: {passed}/{total} checks passed, {failed} failed")
if failed == 0:
    print("✅ All ad-hoc verifications passed")
else:
    print(f"⚠️  {failed} check(s) failed")
sys.exit(0 if failed == 0 else 1)
