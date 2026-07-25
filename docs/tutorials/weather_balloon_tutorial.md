Weather Balloon Tutorial (Envelope + Gas + Fill)

Purpose
This tutorial helps you choose an envelope and lifting gas for a science-style weather balloon flight (payload ascent, burst altitude planning, and safe recovery).

It’s written to map directly to the in-game configurator flow:
Gas → Envelope → Fill → Payloads → Site → Review/Launch.

1) The basic physics (the “why” behind every choice)
A balloon’s lift is the difference between the density of the surrounding air and the density of the gas inside the envelope.

Idealized lift approximation (good for intuition):
  Lift ≈ (ρ_air − ρ_gas) × V
Where:
- ρ_air depends on pressure/temperature (atmosphere)
- ρ_gas depends on pressure/temperature and gas species
- V is the envelope’s gas volume

As the balloon rises:
- Pressure drops strongly → the gas expands → the envelope volume increases.
- Temperature generally drops → gas density changes, which partially counteracts expansion (but pressure drop usually dominates).

Burst is usually the limiting event: the envelope will burst when the internal pressure/strain exceeds its rating.

2) Envelope selection (latex vs mylar, and why it matters)
Your envelope choice controls:
- How much volume the balloon can reach before bursting
- How the balloon behaves as it expands with altitude
- How forgiving recovery is (and what you must include for safe descent)

Latex envelope (stretchy)
- Pros: can accommodate expansion with less “hard” volume behavior.
- Cons: lower tear resistance; requires correct recovery/handling equipment in the mission setup.

Mylar envelope (more rigid)
- Pros: stable shape and predictable performance (often easier to model in-game).
- Cons: less tolerant of sudden expansion; burst can happen earlier if you push fill too high.

In-game translation / safety links
- Latex is typically the one that triggers “burst-risk vs recovery equipment” style checks.
- If your envelope is latex, make sure you include a recovery element (parachute) and any required vent/valve behavior your game uses—otherwise you’ll see “risky” warnings in Review.

3) Gas choice (hydrogen vs helium)
Hydrogen
- Pros: slightly lower gas density → slightly higher lift per volume.
- Cons: flammable → higher safety risk in real-world handling.

Helium
- Pros: inert (safer handling). Also commonly modeled/used for science payloads.
- Cons: typically a bit less lift than hydrogen per unit volume.

Lift intuition (sea-level order-of-magnitude)
- Net lift of helium is about ~1.0 kg per m³ of envelope volume (minus envelope/payload mass details).
- Net lift of hydrogen is about ~1.1 kg per m³.

Takeaway
- Hydrogen gives you marginally more performance (net lift) for the same volume.
- Helium gives you safer handling and more predictable “weather balloon style” missions.
- In gameplay terms: hydrogen can make “insufficient lift” less likely, but also pushes you toward filling/presure choices that may increase burst-risk if you’re not careful.

4) Fill strategy (the lever that determines burst altitude)
Fill is where most players lose flights.

In gameplay, increasing fill % generally:
- Increases starting buoyancy
- But also increases the internal pressure/strain as the gas expands
- → which tends to lower burst altitude (or increase burst probability earlier)

Rule of thumb
- If you need more altitude/float, increase lift gradually.
- Stop increasing once Review warnings start showing “risky” for excessive fill.

Temperature + gas density note
Even with “the same fill %”, cold weather can change gas density and how the balloon evolves during ascent.
- Colder conditions can reduce lift and change how quickly you approach the envelope’s critical state.
- Your in-game site/weather profile is what makes this happen automatically.

5) Weather influences (what moves your balloon and where it bursts)
Even though your configurator focuses on gas/envelope/fill, weather controls both:
A) Trajectory
- Wind changes with altitude; that determines where you land.

B) Burst timing
- Temperature profiles affect gas density and expansion behavior.
- Pressure/temperature layers (including inversions) can change how your balloon climbs.

In practice for a weather balloon mission
- Choose a site with a forecast wind profile that supports recovery.
- Don’t only chase “max altitude”—chase “burst altitude that still allows safe descent/recovery.”

6) In-game workflow checklist (do this every time)
Step A — Choose gas
- Hydrogen if you want maximum lift and accept higher risk.
- Helium for safer handling and steadier “science balloon” behavior.

Step B — Choose envelope
- Match envelope type to your mission goal (and to what your game’s warnings expect).
- If using latex, ensure your recovery equipment assumptions match the warnings system.

Step C — Choose fill mode
- If “auto” exists: use it first, then review warnings.
- If manual fill % exists: raise fill slowly until you reach your target performance, but avoid pushing into the “excessive fill / burst-risk” zone.

Step D — Add payloads
- Heavier payload reduces the net available lift.
- In Review, a heavy payload should produce “risky” lift-margin warnings.

Step E — Pick site (weather profile)
- Your site determines pressure/temperature evolution and winds during the climb.

Step F — Review (interpret warnings)
Use these as your “survival signals”:
- Insufficient lift → ☠️ Doomed (you won’t reach your intended operating regime)
- Excessive fill → ⚠️ Risky (burst sooner than desired)
- Heavy payload → ⚠️ Risky (margin too thin)
- Latex without parachute/valve-equivalent → ⚠️ Risky (recovery not set)
- Hot-air without heater → ☠️ Doomed (if your mission uses hot air / thermal assist)
- Valve unnecessary → ✅ Info (you’re safely within the model’s burst margin)

7) Common failure modes (and the quick fix)
1) “It never climbs / floats like I expected.”
   - Likely insufficient net lift.
   - Fix: switch to a higher-lift gas (helium → hydrogen if allowed) or reduce payload mass, or adjust fill carefully.

2) “It bursts too early.”
   - Likely excessive fill or burst-margin mismatch.
   - Fix: reduce fill %; choose a more appropriate envelope; select a site with more favorable temperature/pressure evolution.

3) “I got risky warnings about latex/recovery.”
   - Fix: add parachute and/or required vent/valve equipment per the game’s assumptions.

4) “It lands in the wrong place.”
   - Fix: choose a different site (wind profile), or plan around where recovery is feasible.

8) Safety note
Weather balloons involve pressure, gas handling, and recovery operations. In the real world, follow all local regulations and standard safety practices.

This tutorial is for in-game learning and intuition—always treat real-world flight as a serious safety engineering problem.
