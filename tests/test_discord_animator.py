import asyncio

from balloon_frontier.discord_ui.animator import DiscordFlightAnimator
from balloon_frontier.presentation import build_flight_moments


class FakeInteraction:
    def __init__(self): self.edits = []
    async def edit_original_response(self, **kwargs): self.edits.append(kwargs)


def moments():
    return build_flight_moments([
        {"time": 0, "alt": 0, "vel": 0}, {"time": 5, "alt": 20, "vel": 4},
        {"time": 100, "alt": 900, "vel": 6}, {"time": 800, "alt": 13000, "vel": 7},
        {"time": 1600, "alt": 30000, "vel": 1, "burst": True},
        {"time": 1900, "alt": 8000, "vel": -12},
        {"time": 2400, "alt": 0, "vel": 0, "landed": True},
    ])


def test_animator_edits_once_per_moment_and_keeps_final_frame():
    interaction = FakeInteraction(); delays = []
    async def fake_sleep(delay): delays.append(delay)
    final = asyncio.run(DiscordFlightAnimator(duration_s=3.5, sleep=fake_sleep).play(interaction, moments()))
    assert len(interaction.edits) == len(moments())
    assert interaction.edits[-1]["content"] == final
    assert final.startswith("```ansi\n") and final.endswith("\n```") and len(final) < 2000
    assert abs(sum(delays) - 3.5) < 1e-9


def test_duration_is_clamped_and_empty_moments_do_not_edit():
    assert DiscordFlightAnimator(duration_s=0).duration_s == 2
    assert DiscordFlightAnimator(duration_s=99).duration_s == 5
    interaction = FakeInteraction()
    assert asyncio.run(DiscordFlightAnimator().play(interaction, [])) is None
    assert interaction.edits == []
