---
title: "Weather effects tutorial"
section: "Advanced: Wind + Temperature"
task_id: t_19fcbfdd
---

# Weather effects tutorial (Advanced)

This tutorial teaches how wind, temperature, and the atmosphere itself change a balloon’s motion and *what you should do in-game* to keep missions reliable.

By the end, you’ll be able to:
1. Predict how lift changes with temperature/altitude.
2. Read wind layers (wind shear) and plan drift-aware routes.
3. Understand when the atmosphere amplifies turbulence (and when it “calms”).
4. Prevent common failure modes: low lift, slow/unstable ascent, and avoidable burst risk.

---

## 0) The mental model (the 3 forces that matter most)

Think of balloon flight as driven by:

1) Buoyancy (vertical):
- Buoyant force increases when air density increases.
- Air density increases when the air is colder and/or at higher pressure.

2) Drag (vertical + horizontal):
- Drag depends on *relative* speed between balloon and air.
- Strong wind → stronger drag during ascent (and more horizontal drift overall).

3) Your ascent rate (how quickly you move through changing air):
- If you climb quickly, you “sample” layers more aggressively.
- Wind shear (wind changing with altitude) turns a simple climb into a drift problem.

---

## 1) Wind: wind direction, wind speed, and wind shear

### 1.1 Wind direction = your horizontal “default”
In calm weather, your payload stays nearly above your launch point (modulo drift from horizontal speed of the balloon). In windy weather, your balloon will move with the wind while it’s climbing.

In-game cues:
- Look for the wind arrow / vector in the HUD (direction) and its magnitude (speed).
- Watch the difference between “balloon ground track” and “air mass flow.”

What to do:
- Plan missions so your target is reachable *within the expected drift window*.
- If you must land precisely, consider slower ascent (more time to correct) or choose a path that minimizes time spent in the strongest layer.

### 1.2 Wind shear: the part that surprises people
Wind shear is when wind changes with altitude.

Why it matters:
- Your balloon’s horizontal velocity changes as soon as it enters a new wind layer.
- Even if the launch layer seems tolerable, the next layer may blow you off course.

What to do:
- In the weather panel, check the wind profile across altitude bands.
- If the game provides “layer” summaries, treat each layer as a separate drift episode.

Rule of thumb:
- “Same average wind, different shear” can produce very different drift outcomes.

---

## 2) Temperature: it changes lift even if the envelope is unchanged

### 2.1 Cold air is denser → more lift
Buoyancy scales with air density (and your displaced volume). Colder air generally increases lift.

Practical consequences:
- On cold mornings, you often climb faster and reach higher altitudes.
- On warm afternoons, you can feel like your balloon “runs out of power” sooner.

### 2.2 Temperature also changes drag and stability
Temperature influences atmospheric structure and density, which in turn changes how strongly drag acts on your balloon.

What to do:
- If the simulation shows air density (or derived metrics), use it directly.
- Otherwise, use temperature as the proxy: warmer → lower density → less buoyancy.

---

## 3) Atmospheric layers: lapse rate, inversion, and turbulence

### 3.1 Typical lapse rate (troposphere behavior)
In many conditions, temperature decreases with altitude (the exact rate varies). This trend means air density can still support ascent but may vary smoothly.

How this feels in-game:
- Lift tends to “erode gradually” as you climb into lower-density air.

### 3.2 Temperature inversion (a reliability hazard)
An inversion is when temperature increases with altitude over some layer.

Why it matters:
- Inversions can cap vertical motion and reduce mixing.
- Wind shear + inversion layers are a classic recipe for “stuck drift” or unexpected slow progress.

What to do:
- If an inversion layer appears in the weather profile, treat it like a boundary.
- Plan around it: either give the balloon enough net lift to cross the layer, or redesign the mission so “drift while stalled” still lands you safely.

### 3.3 Turbulence indicators (how to avoid mission surprises)
Turbulence comes from instability (air wanting to mix) and from shear (air sliding past air).

Signs you should expect rough behavior:
- Strong wind shear.
- Rapid changes in temperature across altitude.
- Conditions that suggest strong convection.

What to do:
- In turbulence-prone weather, prioritize controllability: don’t run the system at the edge of viability.
- Reduce “risky” choices (heavy payload, marginal fill, or configurations that produce low net lift).

---

## 4) Burst risk and pressure/thermal stress (don’t ignore the weather)

Even if the balloon is buoyant, weather can indirectly increase failure risk:

- If wind shear drives higher relative motion, drag loads can grow.
- If temperature changes how gas/air temperatures evolve (depending on your balloon design), internal pressure dynamics can change.

In-game checklist:
1. Make sure your build passes lift viability (don’t assume “it’ll work on average”).
2. If you use a hot-air component (or any thermal management), ensure the heater/thermal system is active. A hot-air configuration without heat is often doomed in viability checks.
3. If the simulation tracks pressure valve behavior, remember that burst prevention depends on correct valve strategy under changing conditions.

---

## 5) Mission practice: 3 drills that build intuition

### Drill A — Temperature lift sensitivity
Goal: learn how ±temperature changes alter max altitude and time-to-go.

Steps:
1. Choose a stable baseline weather profile.
2. Run the mission twice, changing only the ground temperature (e.g., cold vs warm).
3. Compare: max altitude, ascent rate, and whether the balloon stalls.

Expected learning:
- Cold runs should exhibit better climb performance.
- Warm runs may fail the mission earlier unless you increase net lift.

### Drill B — Wind shear drift audit
Goal: learn drift outcomes from different wind-layer structures.

Steps:
1. Pick the same payload/build.
2. Run with similar average wind speed but different wind shear profiles.
3. Compare horizontal displacement at key altitude checkpoints.

Expected learning:
- The “worst layer” often dominates the drift outcome.

### Drill C — Inversion + shear “trap”
Goal: recognize when the atmosphere reduces your ability to climb.

Steps:
1. Enable/choose a weather setup with an inversion layer.
2. Ensure wind shear is also present.
3. Observe whether the balloon stalls or changes drift direction sharply.

Expected learning:
- Treat inversion layers as hard boundaries for mission planning.

---

## 6) Quick quiz (check your understanding)

1) If air temperature increases (all else equal), buoyancy usually:
- A) increases
- B) decreases
- C) stays constant

2) Wind shear matters because it changes:
- A) gravity
- B) the balloon’s relative speed vs air
- C) the wind your balloon experiences at each altitude

3) An inversion layer most often causes:
- A) extra vertical mixing and easy ascent
- B) reduced vertical motion and “capping” of ascent
- C) guaranteed burst

Answer key:
1) B
2) C
3) B

---

## 7) In-game summary (the actionable rules)
- Cold air → denser air → more lift.
- Wind shear → drift episode changes with altitude; plan with the whole wind profile.
- Inversions → treat as climb boundaries; avoid marginal builds.
- For reliability: don’t live at the edge of viability—weather will find your weak spot.
