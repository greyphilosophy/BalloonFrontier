"""End-to-end coverage for the first-flight Story onboarding journey."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from balloon_frontier.career_prologue import (
    DiscoveryFirstFlightConfiguratorMixin,
    first_flight_balloon_choices,
    first_flight_payload_keys,
    toggle_first_flight_optional_payload,
    toggle_payload_selection,
)
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.discord_ui.configurator import (
    ENVELOPE_OPTIONS,
    GAS_OPTIONS,
    PAYLOAD_OPTIONS,
    _Step,
)
from balloon_frontier.discord_ui.views import _OptionButton
from balloon_frontier.game_modes import GameMode
from balloon_frontier.launch_result import FillMode, LaunchRequest
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
    assert isinstance(configurator, DiscoveryFirstFlightConfiguratorMixin)
    assert configurator._game_entry_context["mode"] is GameMode.STORY
    assert configurator._game_entry_context["first_flight"] is True
    assert configurator.STEPS == (
        _Step.CHOOSE_GAS,
        _Step.CHOOSE_ENVELOPE,
        _Step.CHOOSE_PAYLOADS,
        _Step.CHOOSE_SITE,
        _Step.CHOOSE_FILL,
        _Step.REVIEW_LAUNCH,
    )

    gas_content = configurator._step_content()
    assert "Helium" in gas_content
    assert "Air" not in gas_content
    assert "Hot " "Air" not in gas_content
    assert "Hydro" "gen" not in gas_content
    assert "Meth" "ane" not in gas_content
    assert "Tutorial" not in gas_content
    assert "Helium is provided" in gas_content
    assert "School let out twenty minutes ago" in gas_content
    assert "athletic field" in gas_content
    assert "principal" in gas_content
    assert "Step 1/6" in gas_content
    assert len(_option_buttons(configurator)) == 1

    configurator._current_step = _Step.CHOOSE_ENVELOPE
    configurator.build_buttons()
    balloon_content = configurator._step_content()
    assert '45" Latex Weather Balloon' in balloon_content
    assert '55" Latex Weather Balloon' in balloon_content
    assert '70" Latex Weather Balloon' in balloon_content
    assert "Lightweight Hot-" "Air Envelope" not in balloon_content
    assert "$15" in balloon_content and "$25" in balloon_content and "$45" in balloon_content
    assert "13.2m³" in balloon_content
    assert "22.0m³" in balloon_content
    assert "55.0m³" in balloon_content
    assert "Smaller balloons are lighter and cheaper" in balloon_content
    assert "higher before bursting" in balloon_content
    assert "Step 2/6" in balloon_content
    assert len(_option_buttons(configurator)) == 3

    configurator._current_step = _Step.CHOOSE_PAYLOADS
    configurator.build_buttons()
    payload_content = configurator._step_content()
    assert "Essential payloads (provided):" in payload_content
    assert "Camera" in payload_content
    assert "Small Quad" "copter" in payload_content
    assert "Bat" "tery Pack" in payload_content
    assert "Bat" "tery energy is finite" in payload_content
    assert "Parachute" in payload_content
    assert "Tea Light Heat Source" not in payload_content
    assert "Small Electric Heater" not in payload_content
    assert "No optional payload" in payload_content
    assert "Pressure Valve" not in payload_content
    assert "hidden for helium" in payload_content
    assert "Step 3/6" in payload_content
    assert len(_option_buttons(configurator)) == 2

    configurator._current_step = _Step.CHOOSE_SITE
    configurator.build_buttons()
    site_content = configurator._step_content()
    assert "School Athletic Field" in site_content
    assert "Open Field" not in site_content
    assert "Mountain Ridge" not in site_content
    assert "Urban Rooftop" not in site_content
    assert "Step 4/6" in site_content
    assert len(_option_buttons(configurator)) == 1

    configurator._current_step = _Step.CHOOSE_FILL
    configurator.state.update(
        gas="helium",
        envelope="latex",
        balloon_size="s45",
        _first_flight_balloon_choice="s45",
        payloads=["camera", "quad" "copter", "bat" "tery"],
        site="field",
    )
    configurator.build_buttons()
    fill_content = configurator._step_content()
    assert "Almost Lighter Than Air" in fill_content
    assert "95%" in fill_content
    assert "Lighter Than Air" in fill_content
    assert "105%" in fill_content
    assert "Maximum Capacity" in fill_content
    assert "Powered Assist" not in fill_content
    assert "Light Fill" not in fill_content
    assert "Normal Fill" not in fill_content
    assert "Step 5/6" in fill_content
    assert len(_option_buttons(configurator)) == 3


def test_first_flight_balloon_options_follow_gas(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    configurator._current_step = _Step.CHOOSE_ENVELOPE

    configurator.state["gas"] = "helium"
    helium = configurator._first_flight_options()
    assert tuple(helium) == ("s45", "s55", "s70")
    assert all("Hot-Air" not in option[0] for option in helium.values())

    # Heated-air components remain modeled for later experiments, but they are
    # not an opening-mission gas choice because the existing tiny envelope cannot
    # carry the provided starter aircraft.
    configurator.state["gas"] = "air"
    air = configurator._first_flight_options()
    assert tuple(air) == ("candle_kite",)
    assert air["candle_kite"][0] == "Lightweight Hot-Air Envelope"


def test_first_flight_payload_options_follow_gas():
    assert first_flight_payload_keys("helium") == ("parachute", "none")
    assert first_flight_payload_keys("air") == (
        "parachute",
        "candle_heater",
        "electric_heater",
        "none",
    )


def test_first_flight_option_views_do_not_mutate_global_discord_catalogs(monkeypatch):
    gas_before = dict(GAS_OPTIONS)
    envelope_before = dict(ENVELOPE_OPTIONS)
    payload_before = dict(PAYLOAD_OPTIONS)

    configurator, _ = _configurator(monkeypatch)
    for step in (_Step.CHOOSE_GAS, _Step.CHOOSE_ENVELOPE, _Step.CHOOSE_PAYLOADS):
        configurator._first_flight_options(step)

    assert GAS_OPTIONS == gas_before
    assert ENVELOPE_OPTIONS == envelope_before
    assert PAYLOAD_OPTIONS == payload_before
    assert "air" not in GAS_OPTIONS
    assert "candle_" "kite" not in ENVELOPE_OPTIONS
    assert "candle_" "heater" not in PAYLOAD_OPTIONS
    assert "electric_" "heater" not in PAYLOAD_OPTIONS
    assert "quad" "copter" not in PAYLOAD_OPTIONS


def test_payload_toggle_is_pure_deterministic_and_none_exclusive():
    original = ["camera", "parachute"]
    assert toggle_payload_selection(original, "candle_" "heater") == (
        "camera",
        "parachute",
        "candle_" "heater",
    )
    assert original == ["camera", "parachute"]
    assert toggle_payload_selection(original, "camera") == ("parachute",)
    assert toggle_payload_selection(["camera"], "camera") == ("none",)
    assert toggle_payload_selection(original, "none") == ("none",)


def test_first_flight_optional_toggle_always_keeps_essential_payloads():
    assert toggle_first_flight_optional_payload([], "none") == (
        "camera",
        "quad" "copter",
        "bat" "tery",
    )
    assert toggle_first_flight_optional_payload(
        ["camera", "quad" "copter", "bat" "tery"], "parachute"
    ) == ("camera", "quad" "copter", "bat" "tery", "parachute")
    assert toggle_first_flight_optional_payload(
        ["camera", "quad" "copter", "bat" "tery", "parachute"], "parachute"
    ) == ("camera", "quad" "copter", "bat" "tery")


def test_first_flight_selected_size_reaches_standard_simulation_request(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    configurator.state.update(
        gas="helium",
        envelope="latex",
        balloon_size="s55",
        _first_flight_balloon_choice="s55",
        payloads=["camera", "quad" "copter", "bat" "tery"],
        site="field",
        fill_mode="manual",
        manual_gas_mass=0.5,
        gas_mass=0.5,
    )
    request = LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        balloon_size="s55",
        payload_ids=tuple(configurator.state["payloads"]),
        launch_site_id="field",
        fill_mode=FillMode.MANUAL,
        manual_gas_mass_kg=0.5,
    )

    _, _, max_volume, vehicle_mass, burst_ratio = configurator._first_flight_vehicle_params()
    sim = request.to_simulation_state()

    assert max_volume == sim.envelope.max_volume_m3
    assert vehicle_mass == sim.envelope.mass_kg
    assert burst_ratio == sim.envelope.burst_stretch_ratio


def test_experimental_air_fill_uses_canonical_envelope_without_global_menu_state(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    configurator.state.update(
        gas="air",
        envelope="candle_" "kite",
        balloon_size=None,
        _first_flight_balloon_choice="candle_kite",
        payloads=["camera", "quad" "copter", "bat" "tery", "candle_" "heater"],
        site="field",
        fill_mode="normal",
        manual_gas_mass=None,
        gas_mass=None,
    )

    mass = configurator._compute_gas_mass()
    assert mass > 0.0
    config_text = configurator._build_config_text()
    assert "Lightweight Hot-" "Air Envelope" in config_text
    assert "Tea Light Heat Source" in config_text
    assert "Small Quad" "copter" in config_text
    assert "Bat" "tery Pack" in config_text
    assert "School Athletic Field" in config_text
    assert "air" not in GAS_OPTIONS
    assert "candle_" "kite" not in ENVELOPE_OPTIONS


def test_air_cannot_advance_without_heat_source(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    interaction = _Interaction()
    configurator.state.update(
        gas="air",
        envelope="candle_kite",
        balloon_size=None,
        _first_flight_balloon_choice="candle_kite",
        payloads=["camera", "quadcopter", "battery"],
    )
    configurator._current_step = _Step.CHOOSE_PAYLOADS

    asyncio.run(configurator._advance(interaction))

    assert configurator._current_step == _Step.CHOOSE_PAYLOADS
    interaction.response.send_message.assert_awaited_once()
    assert "heat source" in interaction.response.send_message.await_args.args[0]


def test_first_flight_back_navigation_matches_dependency_order(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    configurator._current_step = _Step.CHOOSE_FILL

    assert configurator._prev_step() is True
    assert configurator._current_step == _Step.CHOOSE_SITE
    assert configurator._prev_step() is True
    assert configurator._current_step == _Step.CHOOSE_PAYLOADS
    assert configurator._prev_step() is True
    assert configurator._current_step == _Step.CHOOSE_ENVELOPE


def test_player_can_drive_first_flight_to_review(monkeypatch):
    configurator, _ = _configurator(monkeypatch)
    interaction = _Interaction()

    asyncio.run(configurator._on_gas(interaction, 1))
    assert configurator._current_step == _Step.CHOOSE_ENVELOPE

    asyncio.run(configurator._on_envelope(interaction, 1))
    assert configurator._current_step == _Step.CHOOSE_PAYLOADS

    asyncio.run(configurator._on_payload(interaction, 2))
    asyncio.run(configurator._advance(interaction))
    assert configurator._current_step == _Step.CHOOSE_SITE

    asyncio.run(configurator._on_site(interaction, 1))
    assert configurator._current_step == _Step.CHOOSE_FILL

    asyncio.run(configurator._on_fill(interaction, 1))
    assert configurator._current_step == _Step.REVIEW_LAUNCH

    assert configurator.state["gas"] == "helium"
    assert configurator.state["envelope"] == "latex"
    assert configurator.state["balloon_size"] == "s45"
    assert configurator.state["_first_flight_balloon_choice"] == "s45"
    assert configurator.state["fill_mode"] == "manual"
    assert configurator.state["manual_gas_mass"] > 0.0
    assert configurator.state["payloads"] == ["camera", "quad" "copter", "bat" "tery"]
    assert configurator.state["site"] == "field"
    review = configurator._step_content()
    assert "Your First Flight" in review
    assert "45\" Latex Weather Balloon" in review
    assert "$15" in review
    assert "13.2m³" in review
    assert "Almost Lighter Than Air" in review
    assert "School Athletic Field" in review
    assert "Tutorial" not in review
    interaction.response.send_message.assert_not_awaited()


def test_completing_first_flight_switches_to_broader_story_configurator(monkeypatch):
    first, player = _configurator(monkeypatch)
    first_gases = tuple(first._first_flight_options(_Step.CHOOSE_GAS))
    assert first_gases == ("helium",)

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
    assert "Summer Project: Edge of Space" in later._step_content()
    assert "air" not in GAS_OPTIONS
    assert "candle_" "kite" not in ENVELOPE_OPTIONS
    assert "candle_" "heater" not in PAYLOAD_OPTIONS


def test_helium_balloon_choice_order_is_small_to_large():
    choices = first_flight_balloon_choices("helium")
    assert tuple(choice.balloon_size for choice in choices) == ("s45", "s55", "s70")
