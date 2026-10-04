# Stratospheric communications: from relay to flying cell tower

The player builds a service that stays useful while its vehicle moves through
real weather. Coverage, endurance, capacity, and operating cost become separate
engineering goals. This extends the existing hobby-to-commercial progression
without imposing a particular gas or aircraft recipe.

## Inspiration and evidence

Sceye reported that its 2026 Service Test 1 demonstrated connections to ordinary
phones, drone communications, and onboard computing over Japan. It operated at
16.5–17 km and reported station keeping within a radius as small as 5 km. Its
reported 68 ms processing round trip is a measured system result, not simply
radio propagation time. [Sceye's September 9 release][st1]

Sceye describes daytime solar generation and batteries for nighttime operation
as part of its platform design. [Platform description][platform]

The later optical experiment demonstrated tracking and reflected laser ranging.
It supports future optical communications development; it did not demonstrate
laser power delivery or an operational satellite-to-airship optical network.
[Sceye's September 23 release][laser]

The [New Atlas article][article] provided the starting point. Its "500 towers"
comparison concerns coverage area, not equivalent simultaneous-user capacity.

## Implemented first step: Sky Relay

`data/missions/sky_relay.json` joins the ordinary Scenario mission pool. Launch
from Open Field with the Radio Repeater and Battery Pack to make it eligible;
the existing deterministic selection chooses the mission set. The briefing
states a service goal, and the player chooses the vehicle freely.

- Operate at or above 16 km above sea level.
- Cover the whole community: a 10 km radius centered on the launch field.
- Deliver a total of 30 minutes of connected service, with gaps excluded.
- Receive 8,000 credits on completion; see connected minutes, longest connection,
  and causes of service gaps in the ordinary CLI/Discord mission report.

The shared powered simulation supplies radio activity, battery energy, and
coverage radius. The mission evaluator uses timestamped telemetry, requiring
both ends of each credited interval to meet every condition. It does not infer
coverage from a high peak or a long flight. Legacy telemetry without radio
activity cannot complete this objective.

This is a generic relay prototype. It does not simulate a cellular base station,
mobile-core registration, internet access, subscriber capacity, or backhaul.
The larger Story chapter remains planned; the current early chapters retain
their order.

### Model assumptions

| Quantity | Current model |
|---|---|
| Repeater electrical load | 20 W while the shared battery supplies power |
| Maximum slant range | 100 km |
| Minimum receiver elevation angle | 10 degrees |
| Ground geometry | Spherical Earth, radius 6,371 km; targets at launch-site elevation |
| Position | Existing one-dimensional horizontal drift |
| Coverage | The entire target must fit inside the geometric footprint |
| Interruptions | Power loss, insufficient altitude, range/drift, burst, landing, crash |
| Timing | Conservative endpoint scoring at the recorded sampling interval |

These are explicit gameplay assumptions, **not Sceye hardware specifications**.
The footprint is the smaller of the elevation-limited and range-limited surface
radii. Increasing altitude initially increases reach; near the range limit the
footprint shrinks. Beyond that limit even a receiver directly underneath is
unreachable. Terrain masking, buildings, refraction, antenna patterns, and
interference are deferred.

`provide_coverage` accepts `minimum_altitude_m`, `target_x_m`, `target_radius_m`,
and a positive `minimum_duration_s`. Radio activity is required independently
of the mission's equipment list. Missing telemetry defaults to offline.

The existing Battery Pack supplies 500 Wh. Radio loads share that energy with
other modeled equipment. Solar Panel and Propeller Pod remain unavailable until
their actual generation and propulsion behavior exists; no free station keeping
or perpetual power is implied.

## Proposed campaign progression

| Stage | Service problem | New engineering decision |
|---|---|---|
| Emergency relay | Restore communications to separated ground teams | Altitude, drift, radio coverage, battery endurance |
| Night shift | Maintain service through sunset and dawn | Solar area and mass, storage, reserve, payload duty cycle |
| Persistent cell | Keep an assigned region connected for several days | Wind-layer planning, gas retention, thermal cycling, propulsion power |
| Rural network | Meet demand across multiple communities | Antenna gain and beams, spectrum, backhaul, capacity, handoffs |
| Disaster fleet | Replace failed ground infrastructure and connect drones | Redundancy, relocation, maintenance, fleet rotation |
| Edge platform | Process urgent local data without a remote round trip | Compute mass, power, cooling, latency, backhaul independence |
| Optical backbone | Move data between ground, platforms, and satellites | Pointing, tracking, clouds, RF fallback, link availability |

Implement each as a small extension of the shared simulation with repeatable
weather, observed telemetry, and explainable scoring. Aircraft without propulsion
continue to drift with the wind; later powered craft must pay the mass and energy
cost of station keeping. A 5 km station-keeping contract should remain a future
benchmark until that control loop is actually available.

Coverage and capacity must remain separate. A broad footprint can include many
customers while lacking the bandwidth or backhaul to serve them. Future contract
revenue should depend on delivered service, outages, capacity, and operating cost,
not a fixed bonus for flying over a large area.

## Implementation sequence

1. **Done:** powered repeater, inspectable footprint, connected-time objective,
   Scenario mission, shared results, and regression tests.
2. **Next:** solar charging and day/night battery balance using the existing
   weather/thermal clock, with a repeatable overnight endurance scenario.
3. Add density-dependent propulsion and station-keeping control to the unified
   vehicle model; then introduce persistent-platform Story contracts.
4. Add explicit radio links and backhaul before assigning throughput, subscribers,
   internet availability, or network revenue.
5. Add multiple platforms, edge computing, and optical links as separately tested
   capabilities. Radio links and power-beaming concepts remain separate systems.

[article]: https://newatlas.com/aircraft/sceye-flying-cell-tower-beams-phone-signal-stratosphere/
[st1]: https://sceye.com/press-releases/sceye-completes-record-us-japan-stratospheric-flight/
[platform]: https://sceye.com/platform/
[laser]: https://sceye.com/press-releases/sceye-softbank-demonstrate-world-first-laser-ranging-tracking-haps-from-ground/
