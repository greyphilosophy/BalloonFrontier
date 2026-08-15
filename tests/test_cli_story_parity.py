"""CLI Story mode should mirror Discord Story progression and First Flight choices."""

from types import SimpleNamespace

import pytest

import cli_game
from balloon_frontier.career_prologue import FIRST_FLIGHT_PROVIDED_PAYLOADS
from balloon_frontier.discord_ui import game_menu
from balloon_frontier.game_modes import GameMode
from balloon_frontier.progression import PlayerRegistry, PlayerState
from balloon_frontier.story import EDGE_OF_SPACE_MISSION_ID, FIRST_FLIGHT_MISSION_ID


def _player(monkeypatch, completed=()):
    player = PlayerState("cli-test")
    player.missions_completed.extend(completed)
    monkeypatch.setattr(
        PlayerRegistry,
        "get_or_create",
        classmethod(lambda cls, player_id: player),
    )
    return player


def test_cli_story_mission_select_matches_story_progression(monkeypatch, capsys):
    _player(monkeypatch, completed=(FIRST_FLIGHT_MISSION_ID,))
    monkeypatch.setattr(cli_game, "get_choice", lambda *args, **kwargs: 1)

    mission_id = cli_game.show_story_mission_menu("cli-test")

    output = capsys.readouterr().out
    assert "Replay: Your First Flight" in output
    assert "Next: Summer Project: Edge of Space" in output
    assert mission_id == EDGE_OF_SPACE_MISSION_ID


def test_cli_story_briefing_uses_canonical_first_flight_copy(capsys):
    cli_game.show_story_briefing(FIRST_FLIGHT_MISSION_ID)

    output = capsys.readouterr().out
    assert "School let out twenty minutes ago" in output
    assert "principal" in output
    assert "Get an aerial photograph of the school" in output
    assert "There is no hidden training physics" not in output


def test_cli_first_flight_builds_same_reduced_configuration(monkeypatch):
    _player(monkeypatch)
    choices = iter((0, 0, 0, 0))  # gas, envelope, site, fill
    monkeypatch.setattr(cli_game, "get_choice", lambda *args, **kwargs: next(choices))
    answers = iter(("", "y"))  # no optional payloads, launch
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: next(answers))

    request = cli_game.build_first_flight_request("cli-test")

    assert request is not None
    assert request.gas_id == "helium"
    assert request.envelope_id == "latex"
    assert request.launch_site_id == "field"
    assert request.payload_ids == FIRST_FLIGHT_PROVIDED_PAYLOADS
    assert request.fill_mode.value == "manual"
    assert request.manual_gas_mass_kg is not None
    assert request.player_id == "cli-test"


def test_cli_first_flight_fill_matches_discord_calculation(monkeypatch):
    _player(monkeypatch)
    payloads = FIRST_FLIGHT_PROVIDED_PAYLOADS + ("parachute",)

    cli_mass = cli_game._first_flight_fill_mass(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=payloads,
        site_id="field",
        fill_key="almost_lta",
    )

    configurator = game_menu._configurator_for_mode(
        service=object(),
        mode=GameMode.STORY,
        player_id="cli-test",
        channel_kind="dm",
        on_finished=None,
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )
    configurator.state.update(
        gas="helium",
        envelope="latex",
        payloads=list(payloads),
        site="field",
    )
    discord_mass = configurator._first_flight_fill_mass("almost_lta")

    assert cli_mass == pytest.approx(discord_mass)


def test_cli_story_service_receives_selected_mission_and_player(monkeypatch):
    _player(monkeypatch)
    captured = {}

    request = SimpleNamespace(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=FIRST_FLIGHT_PROVIDED_PAYLOADS,
        launch_site_id="field",
        fill_mode=SimpleNamespace(value="manual"),
        manual_gas_mass_kg=0.1,
        player_id="cli-test",
        balloon_size=None,
        gas_temperature_delta_k=None,
    )

    # The session adapter itself is shared by CLI and Discord; this assertion
    # protects the CLI wiring without running a full simulation here.
    service = cli_game.SessionAwareFlightService(
        object(),
        GameMode.STORY,
        ui="cli",
        story_player_id="cli-test",
        story_mission_id=FIRST_FLIGHT_MISSION_ID,
    )

    assert service.ui == "cli"
    assert service.story_player_id == "cli-test"
    assert service.story_mission_id == FIRST_FLIGHT_MISSION_ID


def test_cli_player_id_argument_is_persistent_story_identity():
    args = cli_game.parse_args(["--player-id", "alfred", "--no-animation"])

    assert args.player_id == "alfred"
    assert args.no_animation is True
