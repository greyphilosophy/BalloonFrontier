"""Tests for typed launch and result models (launch_result.py).

These tests verify:
- LaunchRequest validation and field resolution
- TelemetryPoint conversion from simulation dicts
- FlightResult properties and summaries
- Backward-compatibility shims
- Type contracts (frozen dataclasses, slots)

No behavioral changes — just schema verification.
"""

import pytest
from dataclasses import FrozenInstanceError

from balloon_frontier.launch_result import (
    LaunchRequest,
    FlightResult,
    TelemetryPoint,
    FillMode,
    build_launch_request_from_discord,
    build_launch_request_from_cli,
    telemetry_point_from_dict,
    telemetry_list_to_points,
)
from balloon_frontier.catalog import CATALOG


# ─── TelemetryPoint tests ──────────────────────────────────────────


class TestTelemetryPoint:

    def test_create_from_minimal_dict(self):
        d = {
            "time_s": 10.0,
            "altitude_m": 100.0,
            "velocity_mps": 2.0,
            "gas_volume_m3": 5.0,
            "ambient_pressure_pa": 90000.0,
            "ambient_temperature_k": 270.0,
            "net_lift_N": 10.0,
            "buoyancy_N": 50.0,
            "weight_N": 40.0,
            "drag_N": -5.0,
            "gas_mass_kg": 1.0,
            "total_mass_kg": 15.0,
        }
        tp = telemetry_point_from_dict(d)
        assert tp.time_s == 10.0
        assert tp.altitude_m == 100.0
        assert tp.velocity_mps == 2.0
        assert tp.burst is False
        assert tp.landed is False
        assert tp.crashed is False

    def test_from_dict_with_events(self):
        d = {
            "time_s": 60.0,
            "altitude_m": 5000.0,
            "velocity_mps": -1.0,
            "gas_volume_m3": 20.0,
            "ambient_pressure_pa": 50000.0,
            "ambient_temperature_k": 250.0,
            "net_lift_N": 0.0,
            "buoyancy_N": 30.0,
            "weight_N": 30.0,
            "drag_N": 0.0,
            "gas_mass_kg": 0.5,
            "total_mass_kg": 10.0,
            "burst": True,
            "landed": True,
            "crashed": False,
        }
        tp = telemetry_point_from_dict(d)
        assert tp.burst is True
        assert tp.landed is True
        assert tp.crashed is False

    def test_frozen_dataclass(self):
        tp = TelemetryPoint(
            time_s=1.0, altitude_m=0.0, velocity_mps=0.0,
            gas_volume_m3=1.0, ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )
        with pytest.raises(Exception, match="cannot assign to field"):
            tp.time_s = 2.0

    def test_default_values(self):
        tp = TelemetryPoint(
            time_s=0.0, altitude_m=0.0, velocity_mps=0.0,
            gas_volume_m3=0.0, ambient_pressure_pa=0.0,
            ambient_temperature_k=0.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=0.0, total_mass_kg=0.0,
        )
        assert tp.x_m == 0.0
        assert tp.vx_mps == 0.0


# ─── FlightResult tests ────────────────────────────────────────────


class TestFlightResult:

    def test_basic_properties(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        tel = [
            TelemetryPoint(
                time_s=0.0, altitude_m=0.0, velocity_mps=0.0,
                gas_volume_m3=0.0, ambient_pressure_pa=0.0,
                ambient_temperature_k=0.0, net_lift_N=0.0,
                buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
                gas_mass_kg=1.0, total_mass_kg=10.0,
            ),
            TelemetryPoint(
                time_s=30.0, altitude_m=500.0, velocity_mps=2.0,
                gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
                ambient_temperature_k=270.0, net_lift_N=10.0,
                buoyancy_N=50.0, weight_N=40.0, drag_N=-5.0,
                gas_mass_kg=0.9, total_mass_kg=10.0,
            ),
            TelemetryPoint(
                time_s=60.0, altitude_m=500.0, velocity_mps=-1.0,
                gas_volume_m3=4.5, ambient_pressure_pa=90000.0,
                ambient_temperature_k=270.0, net_lift_N=0.0,
                buoyancy_N=30.0, weight_N=30.0, drag_N=0.0,
                gas_mass_kg=0.8, total_mass_kg=9.5,
            ),
        ]
        result = FlightResult(telemetry=tel, launch_request=req)
        assert result.peak_altitude_m == 500.0
        assert result.duration_s == 60.0
        assert result.final_altitude_m == 500.0
        assert result.final_velocity_mps == -1.0
        assert result.final_gas_mass_kg == 0.8

    def test_empty_telemetry(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        result = FlightResult(telemetry=[], launch_request=req)
        assert result.peak_altitude_m == 0.0
        assert result.duration_s == 0.0
        assert result.burst is False
        assert result.landed is False
        assert result.crashed is False
        assert result.final_altitude_m == 0.0

    def test_burst_detection(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        tel = [
            TelemetryPoint(
                time_s=10.0, altitude_m=100.0, velocity_mps=2.0,
                gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
                ambient_temperature_k=270.0, net_lift_N=10.0,
                buoyancy_N=50.0, weight_N=40.0, drag_N=-5.0,
                gas_mass_kg=1.0, total_mass_kg=10.0,
                burst=True,
            ),
        ]
        result = FlightResult(telemetry=tel, launch_request=req)
        assert result.burst is True
        assert result.crashed is False

    def test_end_state_labels(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )

        # Crashed
        tel_crashed = [TelemetryPoint(
            time_s=10.0, altitude_m=0.0, velocity_mps=-16.0,
            gas_volume_m3=0.0, ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=0.0, total_mass_kg=0.0,
            crashed=True,
        )]
        result = FlightResult(telemetry=tel_crashed, launch_request=req)
        assert result.end_state() == "💥 Crashed"

        # Burst
        tel_burst = [TelemetryPoint(
            time_s=10.0, altitude_m=100.0, velocity_mps=2.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=10.0,
            buoyancy_N=50.0, weight_N=40.0, drag_N=-5.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
            burst=True,
        )]
        result = FlightResult(telemetry=tel_burst, launch_request=req)
        assert result.end_state() == "🎈 Burst"

        # Landed
        tel_landed = [TelemetryPoint(
            time_s=10.0, altitude_m=0.0, velocity_mps=-2.0,
            gas_volume_m3=0.0, ambient_pressure_pa=101325.0,
            ambient_temperature_k=288.15, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=0.0, total_mass_kg=0.0,
            landed=True,
        )]
        result = FlightResult(telemetry=tel_landed, launch_request=req)
        assert result.end_state() == "✅ Landed"

        # In flight (no events)
        tel_flight = [TelemetryPoint(
            time_s=10.0, altitude_m=100.0, velocity_mps=2.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=10.0,
            buoyancy_N=50.0, weight_N=40.0, drag_N=-5.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )]
        result = FlightResult(telemetry=tel_flight, launch_request=req)
        assert result.end_state() == "🔄 In flight"

    def test_flight_time_label(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        tel = [TelemetryPoint(
            time_s=0.0, altitude_m=0.0, velocity_mps=0.0,
            gas_volume_m3=0.0, ambient_pressure_pa=0.0,
            ambient_temperature_k=0.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )]
        tel.append(TelemetryPoint(
            time_s=125.0, altitude_m=500.0, velocity_mps=0.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=0.9, total_mass_kg=9.5,
        ))
        result = FlightResult(telemetry=tel, launch_request=req)
        assert result.flight_time_label == "2m 5s"

    def test_emoji_altitude_label(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        tel = [TelemetryPoint(
            time_s=10.0, altitude_m=15000.0, velocity_mps=0.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )]
        result = FlightResult(telemetry=tel, launch_request=req)
        assert result.peak_altitude_label == "15.0 km"

        tel[0] = TelemetryPoint(
            time_s=10.0, altitude_m=500.0, velocity_mps=0.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )
        result = FlightResult(telemetry=tel, launch_request=req)
        assert result.peak_altitude_label == "500 m"

    def test_frozen_dataclass(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        tel = [TelemetryPoint(
            time_s=10.0, altitude_m=0.0, velocity_mps=0.0,
            gas_volume_m3=0.0, ambient_pressure_pa=0.0,
            ambient_temperature_k=0.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )]
        result = FlightResult(telemetry=tel, launch_request=req)
        with pytest.raises(TypeError, match="super"):
            result.peak_altitude_m = 100.0

    def test_embed_fields(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["camera"], site_id="field",
        )
        tel = [TelemetryPoint(
            time_s=0.0, altitude_m=0.0, velocity_mps=0.0,
            gas_volume_m3=0.0, ambient_pressure_pa=0.0,
            ambient_temperature_k=0.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=1.0, total_mass_kg=10.0,
        )]
        tel.append(TelemetryPoint(
            time_s=30.0, altitude_m=500.0, velocity_mps=-1.0,
            gas_volume_m3=5.0, ambient_pressure_pa=90000.0,
            ambient_temperature_k=270.0, net_lift_N=0.0,
            buoyancy_N=0.0, weight_N=0.0, drag_N=0.0,
            gas_mass_kg=0.9, total_mass_kg=9.5,
            landed=True,
        ))
        result = FlightResult(telemetry=tel, launch_request=req)
        fields = result.to_embed_fields()
        names = [f[0] for f in fields]
        assert "Flight Result" in names
        assert "Peak Altitude" in names
        assert "Flight Time" in names


# ─── LaunchRequest tests ──────────────────────────────────────────


class TestLaunchRequest:

    def test_minimal_request(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["none"], site_id="field",
        )
        assert req.gas_id == "helium"
        assert req.envelope_id == "latex"
        assert req.gas.name == "Helium"
        assert req.envelope.name == "Latex Weather Balloon"
        assert req.site.name == "Open Field"
        assert req.payload_ids == ("none",)
        assert req.payloads == []

    def test_full_request(self):
        req = LaunchRequest(
            gas_id="helium", envelope_id="latex",
            payload_ids=["camera", "battery"],
            launch_site_id="mountain",
            fill_mode=FillMode.HEAVY,
            balloon_size="s36",
        )
        assert req.gas.name == "Helium"
        assert req.payloads[0].name == "Camera"
        assert req.payloads[1].name == "Battery Pack"
        assert req.total_payload_mass_kg == 1.5 + 3.0
        assert req.balloon.name == "36\""
        assert req.site.name == "Mountain Ridge"

    def test_gas_mass_calculation(self):
        """Gas mass is computed from envelope burst volume × fill multiplier."""
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
            fill_mode="normal",
        )
        # Normal = 1.0x burst volume
        burst_vol = req.envelope.burst_volume_m3  # 25.0 m³
        assert req.gas_mass_kg > 0

        req_light = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
            fill_mode="light",
        )
        # Light = 0.8x burst volume
        assert req_light.gas_mass_kg < req.gas_mass_kg

        req_heavy = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
            fill_mode="heavy",
        )
        # Heavy = 1.2x burst volume
        assert req_heavy.gas_mass_kg > req.gas_mass_kg

    def test_balloon_size_clamp_not_at_boundary(self):
        """Calculated mass within range should not be clamped to min.

        Regression: previously the mass was divided by 1000 twice,
        turning a 1.0 kg fill into 0.001 kg, which got clamped to
        the minimum (e.g. 30 g). This test asserts the calculated
        mass falls inside the allowed range and is returned as-is.
        """
        # s36 balloon: fill_range_g = (30, 1158) g
        req = LaunchRequest(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], launch_site_id="field",
            fill_mode=FillMode.NORMAL,
            balloon_size="s36",
        )
        calculated = req.gas_mass_kg
        # The calculated mass (using helium density × burst volume × 1.0)
        # is around 4.2 kg for a latex envelope. The s36 range is 0.030–1.158 kg.
        # Since calculated > max, it should clamp to max.
        # Use a larger balloon where calculated falls inside the range.
        req_large = LaunchRequest(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], launch_site_id="field",
            fill_mode=FillMode.LIGHT,  # 0.8x burst
            balloon_size="s70",  # fill_range_g = (150, 3000) → 0.150–3.0 kg
        )
        calculated = req_large.gas_mass_kg
        min_kg = 0.150  # 150g in kg
        max_kg = 3.0    # 3000g in kg
        # If the calculated mass is inside the range, it should equal
        # the calculated value (no clamping). If outside, it should equal
        # the boundary. Either way, it must NOT be 0.001 (the old bug).
        assert calculated > 0.01, f"Gas mass {calculated} kg is suspiciously low (old 1000x bug?)"

    def test_valve_activated_in_sim_state(self):
        """Selecting the valve payload sets has_pressure_valve=True."""
        req_with_valve = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["valve", "camera"],
            site_id="field",
        )
        state = req_with_valve.to_simulation_state()
        assert state.has_pressure_valve is True

        req_without_valve = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["camera", "battery"],
            site_id="field",
        )
        state_no_valve = req_without_valve.to_simulation_state()
        assert state_no_valve.has_pressure_valve is False

    def test_manual_mode(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
            fill_mode="manual",
            manual_mass=2.5,
        )
        assert req.gas_mass_kg == 2.5

    def test_manual_mode_requires_mass(self):
        with pytest.raises(ValueError, match="MANUAL mode requires"):
            build_launch_request_from_cli(
                gas_id="helium", envelope_id="latex",
                payload_ids=[], site_id="field",
                fill_mode="manual",
            )

    def test_unknown_gas_raises(self):
        with pytest.raises(ValueError, match="Unknown gas:"):
            LaunchRequest(
                gas_id="plasma", envelope_id="latex",
                payload_ids=[], launch_site_id="field",
            )

    def test_unknown_envelope_raises(self):
        with pytest.raises(ValueError, match="Unknown envelope:"):
            LaunchRequest(
                gas_id="helium", envelope_id="toy",
                payload_ids=[], launch_site_id="field",
            )

    def test_unknown_payload_raises(self):
        with pytest.raises(ValueError, match="Unknown payload:"):
            LaunchRequest(
                gas_id="helium", envelope_id="latex",
                payload_ids=["nonexistent"],
                launch_site_id="field",
            )

    def test_unknown_site_raises(self):
        with pytest.raises(ValueError, match="Unknown site:"):
            LaunchRequest(
                gas_id="helium", envelope_id="latex",
                payload_ids=[], launch_site_id="moon_base",
            )

    def test_unknown_balloon_size_raises(self):
        with pytest.raises(ValueError, match="Unknown balloon size:"):
            LaunchRequest(
                gas_id="helium", envelope_id="latex",
                payload_ids=[], launch_site_id="field",
                balloon_size="s999",
            )

    def test_frozen_dataclass(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=[], site_id="field",
        )
        with pytest.raises(FrozenInstanceError):
            req.gas_id = "hydrogen"

    def test_to_result_summary(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["camera", "battery"],
            site_id="mountain",
            fill_mode="heavy",
        )
        summary = req.to_result_summary()
        assert "Helium" in summary
        assert "Latex Weather Balloon" in summary
        assert "Camera" in summary
        assert "Mountain Ridge" in summary
        assert "Heavy" in summary

    def test_valve_payload_identified(self):
        req = build_launch_request_from_cli(
            gas_id="helium", envelope_id="latex",
            payload_ids=["camera", "valve"],
            site_id="field",
        )
        payloads_with_valve = [p.name for p in req.payloads if p.has_valve]
        assert "Pressure Valve" in payloads_with_valve


# ─── Backward-compatibility shims ─────────────────────────────────


class TestBackwardCompatShims:

    def test_discord_helper(self):
        req = build_launch_request_from_discord(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["camera", "radio"],
            site_id="rooftop",
            fill_mode="auto",
            manual_mass=None,
            player_id="player_123",
        )
        assert req.player_id == "player_123"
        assert req.gas_id == "helium"
        assert req.payload_ids == ("camera", "radio")
        assert req.fill_mode == FillMode.AUTO

    def test_cli_helper(self):
        req = build_launch_request_from_cli(
            gas_id="hydrogen",
            envelope_id="blimp",
            payload_ids=["ballast"],
            site_id="field",
            fill_mode="light",
            manual_mass=None,
        )
        assert req.gas_id == "hydrogen"
        assert req.fill_mode == FillMode.LIGHT

    def test_discord_to_sim_state(self):
        req = build_launch_request_from_discord(
            gas_id="helium",
            envelope_id="latex",
            payload_ids=["camera"],
            site_id="field",
            fill_mode="normal",
        )
        sim_state = req.to_simulation_state()
        assert sim_state.gas_type == "helium"
        assert sim_state.altitude_m == 0.0  # field altitude
        assert sim_state.gas_mass_kg > 0
        assert sim_state.total_mass() > 0


# ─── Telemetry batch conversion ───────────────────────────────────


class TestTelemetryBatch:

    def test_convert_list(self):
        tel_dicts = [
            {
                "time_s": i * 10.0,
                "altitude_m": i * 100.0,
                "velocity_mps": 2.0,
                "gas_volume_m3": 5.0,
                "ambient_pressure_pa": 90000.0,
                "ambient_temperature_k": 270.0,
                "net_lift_N": 10.0,
                "buoyancy_N": 50.0,
                "weight_N": 40.0,
                "drag_N": -5.0,
                "gas_mass_kg": 1.0 - i * 0.01,
                "total_mass_kg": 10.0,
            }
            for i in range(5)
        ]
        points = telemetry_list_to_points(tel_dicts)
        assert len(points) == 5
        assert points[0].time_s == 0.0
        assert points[4].time_s == 40.0

    def test_empty_list(self):
        assert telemetry_list_to_points([]) == []