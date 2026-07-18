# Balloon Frontier — Development Plan

## Phase 1: Fuel & Descent System
- Fuel consumption model (gas permeability, heater fuel, battery drain)
- Descent mechanics: hot air burns fuel for soft landing; parachute exhausts fuel then drops
- Landing score based on altitude, velocity, payload mass
- Tests: fuel consumption, landing scenarios, edge cases

## Phase 2: Valve Variants
- Lightweight (0.3kg, 2.0x stretch), Standard (0.5kg, 2.5x), Heavy (1.0kg, 3.0x)
- Trade-off testing: valve mass vs altitude vs survival
- Tests: valve mass impact on peak altitude, burst timing

## Phase 3: Weather & Time-of-Day
- Diurnal temperature curve (GDD §6.7)
- Wind layer variation by hour of day (GDD §14.3)
- Cloud layers (visibility bonus for photo missions)
- Tests: temperature curve, wind variation, cloud detection

## Phase 4: Mission Evaluation
- Mission scoring: altitude targets, photo quality, data recovery, landing
- Budget efficiency scoring
- Tests: each objective type, scoring edge cases

## Phase 5: Progression System
- Budget per mission, unlock envelopes, reputation scoring
- Tests: budget calculations, unlock thresholds, progression path

## Phase 6: Discord UI Polish
- Mission selection with dropdowns
- Player state tracking
- Leaderboards
- Tests: state persistence, leaderboard updates
