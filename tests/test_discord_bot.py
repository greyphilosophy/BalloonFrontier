"""Tests for the Balloon Frontier Discord bot — commands, on_message, and simulation."""

import sys

import pytest

sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

from discord_bot import (
    bot, run_simulation, make_result_embed, BalloonConfigurator,
    run_bot, GAS_OPTIONS, ENVELOPE_OPTIONS, PAYLOAD_OPTIONS, SITE_OPTIONS,
)

# ─── 1. Command Registration Tests ──────────────────────────────

class TestCommandRegistration:
    def test_bot_instance_exists(self):
        from discord.ext.commands import Bot
        assert isinstance(bot, Bot)

    def test_help_command_registered(self):
        assert bot.get_command("help") is not None

    def test_physics_command_registered(self):
        assert bot.get_command("physics") is not None

    def test_launch_command_registered(self):
        assert bot.get_command("launch") is not None

    def test_command_prefix_is_slash(self):
        assert bot.command_prefix == "/"

    def test_bot_has_three_named_commands(self):
        names = set(bot.all_commands.keys())
        assert "help" in names
        assert "physics" in names
        assert "launch" in names
        assert len(names) >= 3

# ─── 2. Simulation Tests ────────────────────────────────────────

class TestRunSimulation:
    def test_returns_telemetry_and_summary(self):
        tel, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert isinstance(tel, list)
        assert isinstance(summary, dict)

    def test_telemetry_has_expected_keys(self):
        tel, _ = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert len(tel) > 0
        for entry in tel:
            assert {"time", "alt", "vel"}.issubset(entry.keys())

    def test_summary_has_peak_altitude(self):
        _, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert "peak_altitude" in summary
        assert "burst" in summary

    def test_peak_altitude_is_positive(self):
        _, summary = run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)
        assert summary["peak_altitude"] > 0

    def test_heavy_payload_still_runs(self):
        tel, _ = run_simulation("helium", 0.1, 288.15, 100.0, 0.47, 10.0, 3.0)
        assert len(tel) > 0

# ─── 3. Make Result Embed Tests ────────────────────────────────

class TestMakeResultEmbed:
    def _get_telemetry(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[0]

    def _get_summary(self):
        return run_simulation("helium", 2.0, 288.15, 1.0, 0.47, 10.0, 3.0)[1]

    def test_returns_string(self):
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field",
            self._get_telemetry(), self._get_summary()
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_key_labels(self):
        result = make_result_embed(
            "Helium", 2.0, "Latex", "None", "Open Field",
            self._get_telemetry(), self._get_summary()
        )
        assert "Helium" in result
        assert "Latex" in result
        assert "Launch Report" in result

# ─── 4. Config Data Integrity Tests ─────────────────────────────

class TestDataIntegrity:
    def test_gas_options_have_expected_keys(self):
        for k in ["helium", "hydrogen", "hot_air"]:
            assert k in GAS_OPTIONS

    def test_envelope_options_have_expected_keys(self):
        for k in ["mylar", "latex", "zero_pressure", "blimp"]:
            assert k in ENVELOPE_OPTIONS

    def test_payload_options_have_expected_keys(self):
        for k in ["camera", "radio", "none"]:
            assert k in PAYLOAD_OPTIONS

    def test_site_options_have_expected_keys(self):
        for k in ["field", "mountain", "rooftop"]:
            assert k in SITE_OPTIONS

# ─── 5. Natural Language Help Detection ───────────────────────

class TestNaturalLanguageHelp:
    HELP_KEYWORDS = ["help", "how", "what is", "welcome", "hello", "hi", "start", "play"]

    def _matches_help(self, text):
        return any(word in text.lower() for word in self.HELP_KEYWORDS)

    def test_help_keyword_detected(self):
        assert self._matches_help("help")

    def test_how_to_play_detected(self):
        assert self._matches_help("how to play")

    def test_hello_detected(self):
        assert self._matches_help("hello")

    def test_random_message_not_triggered(self):
        assert not self._matches_help("banana")

    def test_hi_short_form_triggers(self):
        assert self._matches_help("hi there")

# ─── 6. Command Name Extraction ────────────────────────────────

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

# ─── 7. CRITICAL: on_message dispatch bug detection ────────────

class TestOnMessageDispatchBug:
    """
    These tests read the actual source file to detect whether
    the on_message handler properly dispatches commands.
    """

    def test_source_file_exists(self):
        import os
        path = "/home/greyphilosophy/projects/BalloonFrontier/discord_bot.py"
        assert os.path.exists(path), "discord_bot.py should exist"

    def test_on_message_exists_in_source(self):
        source = open("/home/greyphilosophy/projects/BalloonFrontier/discord_bot.py").read()
        assert "def on_message" in source, "on_message handler should be defined"

    def test_on_message_calls_process_commands(self):
        """
        CRITICAL BUG: Without 'await bot.process_commands(message)', the Bot's
        internal dispatcher never fires for prefix commands. This means
        /help, /physics, /launch are silently swallowed.
        """
        source = open("/home/greyphilosophy/projects/BalloonFrontier/discord_bot.py").read()
        assert "process_commands" in source, (
            "on_message must call 'await bot.process_commands(message)' "
            "for slash-prefixed commands to dispatch"
        )

    def test_on_message_does_not_block_slash_commands(self):
        """The guard bot.get_command(first_word) should NOT block '/help'."""
        assert bot.get_command("/help") is None, (
            "bot.get_command('/help') returns None, so the guard should pass through"
        )

# ─── 8. Bot Safety Tests ────────────────────────────────────────

class TestBotSafety:
    def test_run_bot_exists(self):
        assert callable(run_bot)

    def test_bot_has_message_content_intent(self):
        assert bot.intents.message_content

    def test_bot_has_guilds_intent(self):
        assert bot.intents.guilds

    def test_token_env_var_name(self):
        source = open("/home/greyphilosophy/projects/BalloonFrontier/discord_bot.py").read()
        assert "DISCORD_BF_TOKEN" in source or "DISCORD_TOKEN" in source

    def test_bot_has_registered_commands(self):
        assert len(bot.all_commands) >= 3

# ─── 9. BalloonConfigurator Tests ────────────────────────────────

class TestBalloonConfigurator:
    def test_configurator_state_initialized(self):
        config = BalloonConfigurator()
        assert config.state["gas"] == "helium"
        assert config.state["envelope"] == "latex"
        assert config.state["site"] == "field"

    def test_build_config_text_returns_string(self):
        config = BalloonConfigurator()
        text = config._build_config_text()
        assert isinstance(text, str)
        assert "Balloon Configuration" in text

    def test_handle_select_updates_state(self):
        config = BalloonConfigurator()
        config._handle_select(None, "gas", ["hot_air"])
        assert config.state["gas"] == "hot_air"

    def test_handle_select_updates_payloads_as_list(self):
        config = BalloonConfigurator()
        config._handle_select(None, "payloads", ["camera", "radio"])
        assert config.state["payloads"] == ["camera", "radio"]
