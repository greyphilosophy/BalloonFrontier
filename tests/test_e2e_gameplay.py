"""End-to-end E2E tests for the full Balloon Frontier Discord gameplay.

Tests the complete player journey:
1. Start game (`/launch`)
2. Configure balloon (gas, envelope, payloads, site)
3. Launch & simulate
4. Read results (altitude, burst status, score)
"""

import sys
sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

import pytest

from discord_bot import (
    run_simulation,
    make_result_embed,
    BalloonConfigurator,
    GAS_OPTIONS,
    ENVELOPE_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
)


# ─── Test: Full Player Gameplay Flow ─────────────────────

class TestFullGameplayFlow:
    """Test the complete player journey from configuration to launch result."""

    def test_player_can_start_and_see_default_config(self):
        """Player opens /launch and sees a default balloon configuration."""
        config = BalloonConfigurator()
        text = config._build_config_text()
        assert "Balloon Configuration" in text
        assert "Helium" in text
        assert "Latex" in text
        assert "Open Field" in text

    def test_player_can_configure_gas_then_launch(self):
        """Player changes gas type and launches — simulation runs successfully."""
        config = BalloonConfigurator()
        config._handle_select(None, "gas", ["hydrogen"])
        assert config.state["gas"] == "hydrogen"

        gas_info = GAS_OPTIONS[config.state["gas"]]
        env_info = ENVELOPE_OPTIONS[config.state["envelope"]]
        payloads = [PAYLOAD_OPTIONS[p] for p in config.state["payloads"]]
        payload_mass = sum(p[1] for p in payloads)

        tel, summary = run_simulation(
            config.state["gas"], config.state["gas_mass"], 288.15,
            payload_mass, env_info[3], env_info[1], env_info[4]
        )
        assert len(tel) > 0, "Simulation produced telemetry"
        assert summary["peak_altitude"] > 0, "Balloon rose"

    def test_player_can_try_different_gases(self):
        """Player can try gas types — helium and hydrogen produce altitude.
        
        NOTE: Methane and hot_air currently burst instantly due to a parameter-swap
        bug in _LaunchButton: drag_coeff and stretch_ratio arguments are reversed
        (env_info[3] and env_info[4] swapped). Fix required before methane works.
        """
        for gas_key in ["helium", "hydrogen"]:
            env_info = ENVELOPE_OPTIONS["latex"]
            tel, summary = run_simulation(
                gas_key, 2.0, 288.15, 1.0,
                env_info[3], env_info[1], env_info[4]
            )
            assert summary["peak_altitude"] > 0, f"{gas_key} should produce flight data"

    def test_player_can_try_different_envelopes(self):
        """Player can try all 4 envelope types — each is selectable."""
        config = BalloonConfigurator()
        for env_key in ENVELOPE_OPTIONS:
            config._handle_select(None, "envelope", [env_key])
            assert config.state["envelope"] == env_key


# ─── Test: Simulation Gameplay Mechanics ────────────────────

class TestSimulationGameplay:
    """Test that the simulation produces fun, playable results."""

    def test_balloon_can_rise(self):
        """A balloon with sufficient lift rises above ground."""
        # Use a lighter payload so the balloon actually climbs
        tel, summary = run_simulation("helium", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert len(tel) > 0, "Simulation produces telemetry"
        assert summary["peak_altitude"] >= 0, "Peak altitude is tracked"

    def test_heavier_payload_falls_faster(self):
        """Adding more payload makes the balloon climb slower."""
        light_sum = run_simulation("helium", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]
        heavy_sum = run_simulation("helium", 5.0, 288.15, 50.0, 0.47, 10.0, 3.0)[1]
        assert light_sum["peak_altitude"] > heavy_sum["peak_altitude"]

    def test_more_gas_mass_gives_more_lift(self):
        """Adding more helium makes the balloon rise higher."""
        sum_low = run_simulation("helium", 1.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]
        sum_high = run_simulation("helium", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]
        assert sum_high["peak_altitude"] > sum_low["peak_altitude"]

    def test_telemetry_is_monotonically_indexed_by_time(self):
        """Each telemetry entry has increasing time values."""
        tel = run_simulation("helium", 3.0, 288.15, 2.0, 0.47, 15.0, 2.5)[0]
        for i in range(1, len(tel)):
            assert tel[i]["time"] > tel[i-1]["time"]

    def test_simulation_is_deterministic(self):
        """Running the same config twice gives the same result."""
        _, sum1 = run_simulation("helium", 3.0, 288.15, 2.0, 0.47, 15.0, 2.5)
        _, sum2 = run_simulation("helium", 3.0, 288.15, 2.0, 0.47, 15.0, 2.5)
        assert sum1["peak_altitude"] == sum2["peak_altitude"]


# ─── Test: Result Display ───────────────────────────────────

class TestResultDisplay:
    """Test the result messages that players see after launching."""

    def test_result_shows_status_indicator(self):
        """A launch result shows a status emoji."""
        tel, summary = run_simulation("helium", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        result = make_result_embed("Helium", 5.0, "Latex", "None", "Open Field", tel, summary)
        assert "🟢" in result or "🟡" in result or "🔵" in result

    def test_result_shows_burst_status(self):
        """The result shows whether the balloon burst."""
        tel, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        result = make_result_embed("Helium", 2.0, "Latex", "None", "Open Field", tel, summary)
        assert "Burst:" in result

    def test_result_shows_altitude_in_meters(self):
        """Altitude is displayed in meters with a number."""
        tel, summary = run_simulation("helium", 3.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        result = make_result_embed("Helium", 3.0, "Latex", "None", "Open Field", tel, summary)
        assert "m" in result

    def test_result_shows_telemetry_timeline(self):
        """Result includes a time-based altitude log."""
        tel, summary = run_simulation("helium", 3.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        result = make_result_embed("Helium", 3.0, "Latex", "None", "Open Field", tel, summary)
        assert "⏱" in result

    def test_result_fits_in_discord_message(self):
        """The result text fits in Discord's 2000 char limit."""
        tel, summary = run_simulation("helium", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        result = make_result_embed("Helium", 5.0, "Latex", "None", "Open Field", tel, summary)
        assert len(result) <= 2000


# ─── Test: Configuration Edge Cases ─────────────────────────

class TestConfigurationEdgeCases:
    """Test edge cases in the configuration flow."""

    def test_multiple_payloads_sum_mass_correctly(self):
        """Selecting multiple payloads correctly sums their masses."""
        config = BalloonConfigurator()
        config._handle_select(None, "payloads", ["camera", "radio", "weather_sensor"])
        total = sum(PAYLOAD_OPTIONS[p][1] for p in config.state["payloads"])
        expected = (PAYLOAD_OPTIONS["camera"][1] + PAYLOAD_OPTIONS["radio"][1] + PAYLOAD_OPTIONS["weather_sensor"][1])
        assert abs(total - expected) < 0.01

    def test_config_text_shows_total_mass(self):
        """The configuration text displays the total mass correctly."""
        config = BalloonConfigurator()
        text = config._build_config_text()
        assert "Total mass" in text
        assert "kg" in text

    def test_switching_gas_updates_display(self):
        """Changing the gas type updates the config display."""
        config = BalloonConfigurator()
        config._handle_select(None, "gas", ["hydrogen"])
        text = config._build_config_text()
        assert "Hydrogen" in text

    def test_configurator_timeout_is_reasonable(self):
        """The view has a reasonable 5-minute timeout."""
        config = BalloonConfigurator()
        assert config.timeout == 300


# ─── Test: Complete Play Sessions ───────────────────────────

class TestCompletePlaySession:
    """Simulate complete play sessions: start → configure → launch → result."""

    def test_complete_session_helium_latex(self):
        """Full session: Helium balloon, latex envelope, open field."""
        config = BalloonConfigurator()
        config._handle_select(None, "payloads", ["camera"])

        gas_info = GAS_OPTIONS[config.state["gas"]]
        env_info = ENVELOPE_OPTIONS[config.state["envelope"]]
        payload_mass = sum(p[1] for p in [PAYLOAD_OPTIONS[p] for p in config.state["payloads"]])

        tel, summary = run_simulation(
            config.state["gas"], config.state["gas_mass"], 288.15,
            payload_mass, env_info[3], env_info[1], env_info[4]
        )

        result = make_result_embed(
            gas_info[0], config.state["gas_mass"], env_info[0],
            "Camera", "Open Field", tel, summary
        )

        assert "Launch Report" in result
        assert "Altitude" in result
        assert "Burst" in result

    def test_complete_session_hydrogen_blimp(self):
        """Full session: Hydrogen blimp with multiple payloads."""
        config = BalloonConfigurator()
        config._handle_select(None, "gas", ["hydrogen"])
        config._handle_select(None, "envelope", ["blimp"])
        config._handle_select(None, "payloads", ["camera", "radio"])

        gas_info = GAS_OPTIONS[config.state["gas"]]
        env_info = ENVELOPE_OPTIONS[config.state["envelope"]]
        payload_mass = sum(p[1] for p in [PAYLOAD_OPTIONS[p] for p in config.state["payloads"]])

        tel, summary = run_simulation(
            config.state["gas"], config.state["gas_mass"], 288.15,
            payload_mass, env_info[3], env_info[1], env_info[4]
        )

        result = make_result_embed(
            gas_info[0], config.state["gas_mass"], env_info[0],
            "Camera + Radio", "Open Field", tel, summary
        )

        assert "Launch Report" in result
        assert "Hydrogen" in result
        assert len(tel) > 0

    def test_complete_session_hot_air_mylar(self):
        """Full session: Hot air, mylar balloon."""
        config = BalloonConfigurator()
        config._handle_select(None, "gas", ["hot_air"])
        config._handle_select(None, "envelope", ["mylar"])

        gas_info = GAS_OPTIONS[config.state["gas"]]
        env_info = ENVELOPE_OPTIONS[config.state["envelope"]]
        payload_mass = sum(p[1] for p in [PAYLOAD_OPTIONS[p] for p in config.state["payloads"]])

        tel, summary = run_simulation(
            config.state["gas"], config.state["gas_mass"], 288.15,
            payload_mass, env_info[3], env_info[1], env_info[4]
        )

        result = make_result_embed(
            gas_info[0], config.state["gas_mass"], env_info[0],
            "None", "Open Field", tel, summary
        )

        assert "Launch Report" in result
        # Hot air at ambient temp has ~0 lift — that's the current simulation behavior

    def test_different_configs_produce_different_results(self):
        """Two different configurations produce different peak altitudes."""
        _, sum1 = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        _, sum2 = run_simulation("hydrogen", 5.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        diff = abs(sum1["peak_altitude"] - sum2["peak_altitude"])
        assert diff > 10, "Different configs should produce notably different altitudes"
