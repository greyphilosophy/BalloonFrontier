# Tutorial Mission: Spring-Break Yearbook Flight

## Story

It is spring break of senior year. The yearbook staff still needs aerial photographs of the school before the final layout is sent to print.

The player has a small camera-equipped quadcopter. The quadcopter is the aircraft: it supplies propulsion, steering, camera control, and landing capability. A balloon is attached above it only to offset part of the vehicle's weight and reduce the rotor power needed to remain airborne.

The complete vehicle is intentionally heavier than air.

## Objective

1. Launch from the school field.
2. Climb to at least 30 metres.
3. Remain at or above photo altitude for at least 45 seconds so the yearbook shots can be captured.
4. Return and land without bursting or crashing.

The nominal photo route takes 210 seconds.

## Buoyancy-assisted endurance model

The general balloon simulation currently treats payloads as passive mass, so the tutorial adds a narrow powered-flight assessment when that passive model reports an immediate safe ground contact.

The assessment uses the actual first telemetry point from the selected configuration:

- measured vehicle weight,
- measured balloon buoyancy,
- measured gas volume,
- selected envelope drag coefficient,
- actual added payload mass.

The fraction of weight carried by the rotors is:

`rotor load fraction = 1 - buoyancy / weight`

The temporary endurance estimate uses induced-power scaling with a nonzero avionics and control-power floor:

`power fraction = 0.22 + 0.78 × rotor load fraction^1.5 + envelope drag penalty`

`estimated endurance = 150 seconds / power fraction`

The powered route is generated only when estimated endurance is at least 210 seconds. A real burst, crash, incomplete flight, or inadequate energy budget is never overwritten.

## Success rules

Production flights with timestamped telemetry are judged by the actual objective: camera quadcopter present, sufficient photo-altitude dwell, sufficient endurance, and safe recovery. The green choices are guidance, not a hidden requirement; another configuration may succeed if it demonstrably completes the route.

Legacy unit fixtures without timestamped route telemetry retain the older evaluator result because they cannot prove whether photographs were taken.

## Current limitation

The powered sortie remains a deterministic interim model. Rotor thrust, battery energy, camera events, and active control authority should eventually become first-class simulation state rather than a tutorial-only assessment layer.
