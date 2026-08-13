"""End-to-end coverage for the first-flight Story onboarding journey."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    toggle_first_flight_optional_payload,
    toggle_payload_selection,
)
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import (
    BalloonConfigurator,
    ENVELOPE_OPTIONS,
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    _Step,
)
from balloon_frontier.discord_ui.views import _OptionButton
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import FIRST_FLIGHT_MISSION_ID


class _Interaction:
    def __init__(self, user_id="story-player"):
        self.user = SimpleNamespace(id=user_id)
        self.message = SimpleNamespace(author=self.user)
        self.response = SimpleNamespace(
            edit_message=AsyncMock(),
            send_message=AsyncMock(),
        )


def _configurator(monkeypatch, *, completed=False):
    player = PlayerState("story-player")
    if completed:
        player.missions_completed.append(FIRST_FLIGHT_MISSION_ID)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="story-player",
        channel_kind="dm",
        on_finished=None,
    ), player


def _option_buttons(configurator):
    return [item for item in configurator.children if isinstance(item, _OptionButton)]


def test_first_flight_limits_choices_without_tutorial_signposting(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    assert isinstance(configurator, DiscoveryFirstFlightConfiguratorMixin )
    assert configurator._game_entry_context["mode"] is GameMode.STORY
    assert configurator._game_entry_context["first_flight"] is True

    gas_content = configurator._step_content()
    assert "Helium" in gas_content
    assert "Air" in gas_content
    assert "Hot Air" not in gas_content
    assert "Hydrogen" not in gas_content
    assert "Methane" not in gas_content
    assert "Tutorial" not in gas_content
    assert "ambient temperature" in gas_content
    assert "school athletic field" in gas_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_ENVELOPE
    configurator.build_buttons()
    envelope_content = configurator._step_content()
    assert "Latex Weather Balloon" in envelope_content
    assert "Lightweight Hot-Air Envelope" in envelope_content
    assert "Mylar" not in envelope_content
    assert "Zero-Pressure" not in envelope_content
    assert "Envelope heat loss is material-dependent" not in envelope_content
    assert "stretch/inflation" not in envelope_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_FILL
    configurator.state["gas"] = "helium"
    configurator.build_buttons()
    fill_content = configurator._step_content()
    assert "Powered Assist" in fill_content
    assert "quadcopter supplies the remaining lift" in fill_content
    assert "Auto Fill" not in fill_content
    assert "Light Fill" in fill_content
    assert "Normal Fill" in fill_content
    assert len(_option_buttons(configurator)) == 3

    configurator._current_step = _Step.CHOOSE_PAYLOADS
    configurator.build_buttons()
    payload_content = configurator._step_content()
    assert "Essential payloads (provided):" in payload_content
    assert "Camera" in payload_content
    assert "Small Quadcopter" in payload_content
    assert "Battery Pack" in payload_content
    assert "Battery energy is finite" in payload_content
    assert "Parachute" in payload_content
    assert "Tea Light Heat Source" in payload_content
    assert "Small Electric Heater" in payload_content
    assert "No optional payload" in payload_content
    assert "Pressure Valve" not in payload_content
    assert "open-flame methods are flagged" in payload_content
    assert len(_option_buttons(configurator)) == 4

    configurator._current_step = _Step.CHOOSE_SITE
    configurator.build_buttons()
    site_content = configurator._step_content()
    assert "School Athletic Field" in site_content
    assert "Open Field" not in site_content
    assert "Mountain Ridge" not in site_content
    assert "Urban Rooftop" not in site_content
    assert len(_option_buttons(configurator)) == 1


def test_first_flight_option_views_do_not_mutate_global_discord_catalogs(monkeypatch):
    gas_before = dict(GAS_OPTIONS)
    envelope_before = dict(ENVELOPE_OPTIONS)
    payload_before = dict(PAYLOAD_OPTIONS)

    configurator, _ = _configurator(monkeypatch)
    for step in (
        _Step.CHOOSE_GAS,
        _Step.CHOOSE_ENVELOPE,
        _Step.CHOOSE_PAYLOADS,
    ):
        configurator._first_flight_options(step)

    assert GAS_OPTIONS == gas_before
    assert ENVELOPE_OPTIONS == envelope_before
    assert PAYLOAD_OPTIONS == payload_before
    assert "air" not in GAS_OPTIONS
    assert "candle_kite" not in ENVELOPE_OPTIONS
    assert "candle_heater" not in PAYLOAD_OPTIONS
    assert "electric_heater" not in PAYLOAD_OPTIONS
    assert "quadcopter" not in PAYLOAD_OPTIONS


def test_payload_toggle_is_pure_deterministic_and_none_exclusive():
    original = ["camera", "parachute"]
    assert toggle_payload_selection(original, "candle_heater") == (
        "camera",
        "parachute",
        "candle_heater",
    )
    assert original == ["camera", "parachute"]
    assert toggle_payload_selection(original, "camera") == ("parachute",)
    assert toggle_payload_selection(["camera"], "camera") == ("none",)
    assert toggle_payload_selection(original, "none") == ("none",)


def test_first_flight_optional_toggle_always_keeps_essential_payloads():
    assert toggle_first_flight_optional_payload([], "none") == (
        "camera",
        "quadcopter",
        "battery",
    )
    assert toggle_first_flight_optional_payload(
        ["camera", "quadcopter", "battery"], "parachute"
    ) == ("camera", "quadcopter", "battery", "parachute")
    assert toggle_first_flight_optional_payload(
        ["camera", "quadcopter", "battery", "parachute"], "parachute"
    ) == ("camera", "quadcopter", "battery")


def test_first_flight_uses_base_configurator_gas_mass_physics(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    base = BalloonConfigurator(service=object())

    state = {
        "gas": "helium",
        "envelope": "latex",
        "payloads": ["camera", "quadcopter", "battery"],
        "site": "field",
        "fill_mode": "normal",
        "manual_gas_mass": None,
        "gas_mass": None,
    }
    configurator.state.update(state)
    base.state.update(state)

    assert configurator._compute_gas_mass() == base._compute_gas_mass()
    assert configurator._get_env_params() == base._get_env_params()


def test_experimental_air_fill_uses_canonical_envelope_without_global_menu_state(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    configurator.state.update(
        gas="air",
        envelope="candle_kite",
        payloads=["camera", "quadcopter", "battery", "candle_heater"],
        site="field",
        fill_mode="normal",
        manual_gas_mass=None,
        gas_mass=None,
    )

    mass = configurator._compute_gas_mass()
    assert mass > 0.0
    config_text = configurator._build_config_text()
    assert "Lightweight Hot-Air Envelope" in config_text
    assert "Tea Light Heat Source" in config_text
    assert "Small Quadcopter" in config_text
    assert "Battery Pack" in config_text
    assert "School Athletic Field" in config_text
    assert "air" not in GAS_OPTIONS
    assert "candle_kite" not in ENVELOPE_OPTIONS


def test_player_can_drive_first_flight_to_review(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    interaction = _Interaction()

    asyncio.run(configurator._on_gas(interaction, 1))
    asyncio.run(configurator._on_envelope(interaction, 1))
    asyncio.run(configurator._on_fill(interaction, 1))
    asyncio.run(configurator._on_payload(interaction, 4))
    asyncio.run(configurator._advance(interaction))
    asyncio.run(configurator._on_site(interaction, 1))

    assert configurator._current_step == _Step.REVIEW_LAUNCH
    assert configurator.state["gas"] == "helium"
    assert configurator.state["envelope"] == "latex"
    assert configurator.state["fill_mode"] == "manual"
    assert configurator.state["manual_gas_mass"] > 0.0
    assert configurator.state["payloads"] == ["camera", "quadcopter", "battery"]
    assert configurator.state["site"] == "field"
    assert "Your First Flight" in configurator._step_content()
    assert "Powered Assist" in configurator._step_content()
    assert "School Athletic Field" in configurator._step_content()
    assert "Tutorial" not in configurator._step_content()
    interaction.response.send_message.assert_not_awaited()


def test_completing_first_flight_switches_to_broader_story_configurator(monkeypatch):
    first, player = _configurator(monkeypatch)
    first_gases = tuple(first._first_flight_options(_Step.CHOOSE_GAS))
    assert first_gases == ("helium", "air")

    player.missions_completed.append(FIRST_FLIGHT_MISSION_ID)
    later = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="story-player",
        channel_kind="dm",
        on_finished=None,
    )

    assert not isinstance(later, DiscoveryFirstFlightConfiguratorMixin)
    assert later._game_entry_context["mode"] is GameMode.STORY
    assert later._game_entry_context["first_flight"] is False
    later_content = later._step_content()
    assert "Summer Project: Edge of Space" in later_content
    assert "air" not in GAS_OPTIONS
    assert "candle_kite" not in ENVELOPE_OPTIONS
    assert "candle_heater" not in PAYLOAD_OPTIONS
