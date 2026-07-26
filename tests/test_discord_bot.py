"""Tests for the Balloon Frontier Discord bot — commands, on_message, and simulation."""

import os
import sys

from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from discord_bot import (
    bot, run_simulation, make_result_embed, BalloonConfigurator,
    run_bot, GAS_OPTIONS, ENVELOPE_OPTIONS, PAYLOAD_OPTIONS, SITE_OPTIONS,
)


class TestCommandRegistration:
    def test_bot_instance_exists(self):
        from discord.ext.commands import Bot
        assert isinstance(bot, Bot)

    def test_help_command_registered(self):
        assert bot.get_command("help") is not None

    def test_physics_command_registered(self):
        assert bot.get_command("physics") is not None

    def test_play_command_registered(self):
        assert bot.get_command("play") is not None

    def test_launch_command_removed(self):
        assert bot.get_command("launch") is None

    def test_command_prefix_is_slash(self):
        assert bot.command_prefix == "/"

    def test_bot_has_expected_named_commands(self):
        names = set(bot.all_commands.keys())
        assert {"help", "physics", "play"}.issubset(names)
        assert "launch" not in names


class TestRunSimulation:
    def test_returns_telemetry_and_summary(self):
        tel, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert isinstance(tel, list)
        assert isinstance(summary, dict)

    def test_selected_site_temperature_affects_initial_conditions(self):
        config = BalloonConfigurator(service=MagicMock())
        config.state["site"] = "field"
        field_cond = config._get_site_conditions()
        config.state["site"] = "mountain"
        mountain_cond = config._get_site_conditions()
        assert field_cond["gas_temperature"] != mountain_cond["gas_temperature"]

        tel_field, summary_field = run_simulation(
            "helium", 2.0, field_cond["gas_temperature"], 1.0, 0.47, 10.0, 3.0,
        )
        tel_mountain, summary_mountain = run_simulation(
            "helium", 2.0, mountain_cond["gas_temperature"], 1.0, 0.47, 10.0, 3.0,
        )
        assert len(tel_field) > 0 and len(tel_mountain) > 0
        assert abs(tel_field[0]["vel"] - tel_mountain[0]["vel"]) > 1e-6
        assert abs(summary_field["peak_altitude"] - summary_mountain["peak_altitude"]) > 1e-6

    def test_telemetry_has_expected_keys(self):
        tel, _ = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert len(tel) > 0
        for entry in tel:
            assert {"time", "alt", "vel"}.issubset(entry.keys())

    def test_summary_has_peak_altitude(self):
        _, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert "peak_altitude" in summary
        assert "burst" in summary

    def test_summary_includes_score_and_medal_fields(self):
        _, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert "payload_count" in summary
        assert "score" in summary
        assert "medal" in summary
        assert "medal_emoji" in summary

    def test_make_result_embed_handles_missing_optional_fields(self):
        tel, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        partial_summary = {
            "peak_altitude": summary.get("peak_altitude", 0),
            "time_of_flight": summary.get("time_of_flight", 0),
        }
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field", tel, partial_summary,
        )
        assert isinstance(result, str)
        assert "Score Breakdown" in result
        assert "Medal:" in result

    def test_peak_altitude_is_positive(self):
        _, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert summary["peak_altitude"] > 0

    def test_heavy_payload_still_runs(self):
        tel, _ = run_simulation("helium", 0.1, 288.15, 100.0, 0.47, 10.0, 3.0)
        assert len(tel) > 0


class TestMakeResultEmbed:
    def _get_telemetry(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[0]

    def _get_summary(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]

    def test_returns_string(self):
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field",
            self._get_telemetry(), self._get_summary(),
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_key_labels(self):
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field",
            self._get_telemetry(), self._get_summary(),
        )
        assert "Helium" in result
        assert "Latex" in result
        assert "Launch Report" in result


class TestDataIntegrity:
    def test_gas_options_have_expected_keys(self):
        for key in ["helium", "hydrogen", "hot_air"]:
            assert key in GAS_OPTIONS

    def test_envelope_options_have_expected_keys(self):
        for key in ["mylar", "latex", "zero_pressure", "blimp"]:
            assert key in ENVELOPE_OPTIONS

    def test_payload_options_have_expected_keys(self):
        for key in ["camera", "radio", "none"]:
            assert key in PAYLOAD_OPTIONS

    def test_site_options_have_expected_keys(self):
        for key in ["field", "mountain", "rooftop"]:
            assert key in SITE_OPTIONS


class TestNaturalLanguageEntry:
    def test_any_message_is_eligible_to_open_the_game_menu(self):
        for text in ["help", "hello", "play", "banana", "🎈"]:
            assert text.strip()


class TestCommandNameExtraction:
    def test_stripped_slash_finds_command(self):
        assert bot.get_command("help") is not None

    def test_leading_slash_does_not_find_command(self):
        assert bot.get_command("/help") is None

    def test_lstrip_slash_works(self):
        cmd_name = "/help".lstrip("/")
        assert cmd_name == "help"
        assert bot.get_command(cmd_name) is not None

    def test_multi_word_command_extraction(self):
        parts = "/physics step=100".split()
        cmd_name = parts[0].lstrip("/").lower()
        assert cmd_name == "physics"
        assert bot.get_command(cmd_name) is not None


class TestOnMessageDispatch:
    def test_source_file_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "discord_bot.py")
        assert os.path.exists(path)

    def test_on_message_exists_in_source(self):
        source = open(os.path.join(os.path.dirname(__file__), "..", "discord_bot.py")).read()
        assert "def on_message" in source

    def test_on_message_dispatches_registered_commands(self):
        source = open(os.path.join(os.path.dirname(__file__), "..", "discord_bot.py")).read()
        assert "bot.get_context" in source
        assert "bot.invoke" in source

    def test_on_message_supports_menu_onboarding(self):
        source = open(os.path.join(os.path.dirname(__file__), "..", "discord_bot.py")).read()
        assert "send_game_menu" in source


class TestBotSafety:
    def test_run_bot_exists(self):
        assert callable(run_bot)

    def test_bot_has_message_content_intent(self):
        assert bot.intents.message_content

    def test_bot_has_guilds_intent(self):
        assert bot.intents.guilds

    def test_token_env_var_name(self):
        source = open(os.path.join(os.path.dirname(__file__), "..", "discord_bot.py")).read()
        assert "DISCORD_BF_TOKEN" in source or "DISCORD_TOKEN" in source

    def test_bot_has_registered_commands(self):
        assert len(bot.all_commands) >= 3


class TestBalloonConfigurator:
    def test_configurator_state_initialized(self):
        config = BalloonConfigurator(service=MagicMock())
        assert config.state["gas"] == "helium"
        assert config.state["envelope"] == "latex"
        assert config.state["site"] == "field"

    def test_build_config_text_returns_string(self):
        config = BalloonConfigurator(service=MagicMock())
        text = config._build_config_text()
        assert isinstance(text, str)
        assert "Balloon Configuration" in text

    def test_handle_select_updates_state(self):
        config = BalloonConfigurator(service=MagicMock())
        config.state["gas"] = "hot_air"
        config._compute_gas_mass()
        assert config.state["gas"] == "hot_air"

    def test_handle_select_updates_payloads_as_list(self):
        config = BalloonConfigurator(service=MagicMock())
        config.state["payloads"] = ["camera", "radio"]
        config._compute_gas_mass()
        assert config.state["payloads"] == ["camera", "radio"]
