---
title: "Drone altitude tutorial"
section: "Core: Altitude management + Pressure + Burst prevention"
task_id: t_542e1efd
---

# Drone altitude tutorial

This tutorial teaches how to manage altitude safely by understanding:
- how atmospheric pressure drops with height
- how that pressure drop drives gas expansion (and internal pressure)
- how to prevent burst events with careful ascent + pressure-valve strategy

By the end, you’ll be able to:
1) Estimate pressure at a target altitude (or read it from telemetry).
2) Predict the “risk zone” where expansion can exceed the envelope’s safe limits.
3) Choose an ascent plan (rate + staging) that avoids runaway pressure.
4) Use a pressure valve correctly (venting reduces burst risk but costs lift).

---

## 1) The mental model (what actually causes a burst)

A high-altitude drone/balloon fails when the envelope can’t accommodate the gas expansion driven by the atmosphere.

Key loop:
- As altitude increases, ambient pressure decreases.
- The gas wants to expand.
- If the envelope volume (and/or allowable pressure differential) is exceeded, you get a burst.

So altitude management is really “expansion management.”

---

## 2) Pressure vs altitude (how the outside world changes)

### 2.1 Quick estimation: exponential drop (good enough in-game)
A fast approximation for atmospheric pressure is:

P(h) ≈ P0 · exp(-h / H)

Where:
- h is altitude above sea level (m)
- P0 is surface pressure (≈ 101,322 Pa)
- H is the scale height (≈ 8,400 m, depends on assumptions)

Practical intuition:
- when pressure halves, gas volume tends to double (see next section)

### 2.2 In the game: read telemetry if available
Many simulations expose something like:
- ambient_pressure_pa
- altitude_m
- gas_volume_m3

If your HUD/telemetry already gives ambient pressure, prefer that over estimation: it matches the simulation’s atmosphere model.

---

## 3) How expansion changes with altitude (the part you can predict)

### 3.1 Ideal-gas relationship (the “why”) 
For the same amount of gas (no venting), the core rule is:

P · V = n · R · T

If we hold temperature T roughly constant during a short altitude change:
- V is approximately inversely proportional to P

So:

V(h) ≈ V0 · P0 / P(h)

Example intuition:
- If ambient pressure drops to 0.5×, then V roughly doubles.
- If your envelope’s safe/max volume is only 1.3× higher than V0, you’ve created a burst problem.

### 3.2 What “safe” means in practice
Your envelope typically has a maximum safe volume (or an equivalent burst stretch/limit parameter).

Safe policy:
- Keep the expected gas expansion below the envelope’s max-safe volume.

If the simulation gives:
- max_volume_m3 (or equivalent)
- burst condition flags
Then your safest workflow is:
- preflight compute expansion at the target altitude
- then choose an ascent profile that delays/avoids hitting that target pressure too early

---

## 4) Internal pressure vs ambient pressure (what the valve is for)

In a simplified quasi-equilibrium view, internal gas pressure trends with ambient pressure while the envelope elastically expands.

But in a “burst prevention” view, what matters is the system reaching a geometry/pressure state the envelope can’t withstand.

### 4.1 Pressure valve strategy (prevent burst by trading lift)
If you have a pressure valve:
- it should vent gas when internal pressure would otherwise exceed the burst condition
- venting reduces the gas quantity (n), which reduces future expansion

Trade-off:
- Less gas = less lift (you may stall, land early, or become marginal)
- More venting = lower burst risk but potentially more mission risk in the “low lift” dimension

So the valve is a “safety net,” not a free lunch.

---

## 5) Altitude management playbook (what to do in-game)

### 5.1 Choose a target altitude that stays out of the expansion risk zone
Preflight steps:
1) Pick your mission’s target altitude (or the highest altitude you’ll reach).
2) Estimate ambient pressure at that altitude (or read ambient_pressure_pa).
3) Predict expansion factor: f ≈ P0 / P(h_target).
4) Check whether V0 · f approaches/exceeds the envelope’s max-safe volume.

If you’re near the limit:
- you need either slower ascent, staging (stop/hold), more redundancy (bigger envelope / better materials), or the valve

### 5.2 Use slower ascent near the danger boundary
Even if the valve exists, a fast climb can:
- push the system into an overpressure state before the valve can do its job (or before the simulation allows stabilization)

In-game policy:
- climb “normally” when far from the boundary
- reduce ascent rate as you enter the final approach band

### 5.3 Stage the climb (mini-checkpoints)
Instead of a continuous climb:
- climb to a checkpoint
- watch gas_volume / pressure trend
- only proceed if the trend stays within safe bounds

This turns a single hard failure risk into a controllable sequence of smaller decisions.

---

## 6) Burst prevention checklist (copy/paste mental rules)

Before launch:
- [ ] You know the envelope’s max safe volume (or equivalent burst limit).
- [ ] You can observe ambient_pressure_pa and gas_volume_m3 (telemetry) OR you’ve estimated P(h).
- [ ] If using a valve: understand the cost (reduced lift) and your landing/mission tolerance.

During ascent:
- [ ] Monitor pressure/volume trend (don’t just watch altitude).
- [ ] Slow down if the trend steepens.
- [ ] If valve vents: expect lift reduction; compensate with net-lift (ballast/payload choices) if your mission needs it.

---

## 7) Mission practice (3 drills that build intuition)

### Drill A — “Pressure drop → expansion” drill
Goal: build a direct feel for how fast expansion ramps.
Steps:
1) Choose a build with no valve (or valve disabled if possible).
2) Run two flights with the same starting conditions but different maximum altitude targets.
3) Compare gas_volume trend vs altitude.

Expected learning:
- the nearer you get to a halving/doubling of ambient pressure, the more rapidly volume grows.

---

### Drill B — Valve on vs valve off
Goal: see burst prevention in action and quantify the lift penalty.
Steps:
1) Pick one borderline build (where “no valve” is close to risky).
2) Run with valve disabled (expect failure or near-failure depending on difficulty).
3) Run with valve enabled.
4) Compare: burst occurrence, max altitude, and whether you still completed the mission objectives.

Expected learning:
- the valve shifts the failure mode (from burst to “lift margin / mission outcome”).

---

### Drill C — Ascent-rate safety drill
Goal: confirm that ascent rate matters operationally.
Steps:
1) Use the same build and same final target altitude.
2) Run two ascent profiles: “fast climb” and “slow climb.”
3) Compare burst events and the time spent near max volume.

Expected learning:
- slower climb gives the system more opportunity to stay within limits and reduces runaway pressure risk.

---

## 8) Quick quiz

1) Atmospheric pressure decreases with altitude, so gas volume tends to:
- A) decrease
- B) increase
- C) stay constant

2) A pressure valve usually prevents burst by:
- A) adding lift
- B) venting gas to reduce expansion
- C) increasing envelope stiffness without side effects

3) If you’re close to the envelope’s max safe volume, the best first adjustment is usually:
- A) climb faster
- B) slow down or stage your climb
- C) ignore pressure and watch only altitude

Answer key:
1) B
2) B
3) B

---

## 9) In-game summary (actionable rules)
- Treat altitude as pressure risk: higher altitude = lower ambient pressure = more expansion.
- Predict expansion using pressure ratios (or read ambient_pressure_pa if you have it).
- Stay below the envelope’s max safe volume by managing ascent rate and staging.
- Use a pressure valve to avoid burst, but expect reduced lift margin afterward.
