from types import SimpleNamespace

import pytest

from balloon_frontier.game_modes import GameMode
from balloon_frontier.game_session import SessionState
from balloon_frontier import session_adapters as adapters


@pytest.fixture(autouse=True)
def no_real_missions(monkeypatch):
    monkeypatch.setattr(adapters, "plan_session", _fake_plan_session)


def _fake_plan_session(mode, configuration, *, player_id=None, context=None):
    from balloon_frontier.session_controller import ModePolicy, SessionPlan
    from balloon_frontier.game_session import GameSession

    parsed = mode if isinstance(mode, GameMode) else GameMode(str(mode).replace(" ", "_"))
    if parsed is GameMode.TUTORIAL:
        parsed = GameMode.STORY
    session = GameSession(parsed, player_id=player_id)
    session.set_configuration(configuration)
    session.mark_ready()
    policy = ModePolicy(
        parsed,
        parsed is not GameMode.FREE_PLAY,
        parsed is GameMode.STORY,
        parsed is GameMode.FREE_PLAY,
        0,
        "test",
    )
    return SessionPlan(
        session,
        policy,
        ("mission",) if policy.requires_missions else (),
        context or {},
    )


def test_cli_adapter_translates_legacy_tutorial_to_story():
    request = SimpleNamespace(
        gas_id="helium",
        envelope_id="latex",
        balloon_size="s36",
        payload_ids=("camera",),
        launch_site_id="field",
        fill_mode=SimpleNamespace(value="auto"),
        manual_gas_mass_kg=None,
    )

    plan = adapters.prepare_cli_session("tutorial", request, player_id="cli-player")

    assert plan.session.mode is GameMode.STORY
    assert plan.session.configuration["payloads"] == ("camera",)
    assert plan.context == {"ui": "cli"}


def test_discord_adapter_supports_dm_and_isolates_players():
    adapter = adapters.DiscordSessionAdapter.create()
    state = {
        "gas": "helium",
        "envelope": "latex",
        "payloads": ["camera"],
        "site": "field",
    }

    alice = adapter.start("alice", "story", state, channel_kind="dm")
    bob = adapter.start("bob", "free play", state, channel_kind="guild")

    assert alice is not bob
    assert alice.context["channel"] == "dm"
    assert bob.context["channel"] == "guild"
    assert adapter.registry.get("alice") is alice
    assert adapter.registry.get("bob") is bob


def test_discord_restart_cancels_previous_session():
    adapter = adapters.DiscordSessionAdapter.create()
    state = {"gas": "helium", "payloads": [], "site": "field"}
    first = adapter.start("player", "tutorial", state)
    second = adapter.start("player", "scenario", state)

    assert first.session.state is SessionState.CANCELLED
    assert first.session.mode is GameMode.STORY
    assert adapter.registry.get("player") is second


def test_discord_lifecycle_and_interruption():
    adapter = adapters.DiscordSessionAdapter.create()
    state = {"gas": "helium", "payloads": [], "site": "field"}
    plan = adapter.start("player", "free play", state)

    adapter.launch("player")
    assert plan.session.state is SessionState.IN_FLIGHT
    adapter.complete("player", {"peak_altitude_m": 1000})
    assert plan.session.state is SessionState.COMPLETED

    assert adapter.cancel("player")
    assert adapter.registry.get("player") is None
    with pytest.raises(ValueError, match="no active session"):
        adapter.launch("player")
