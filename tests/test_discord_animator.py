import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image

from balloon_frontier.discord_ui.animator import DiscordFlightAnimator
from balloon_frontier.presentation import build_flight_moments


class FakeInteraction:
    def __init__(self):
        self.followup = SimpleNamespace(send=AsyncMock())
        self.edit_original_response = AsyncMock()


def moments():
    return build_flight_moments(
        [
            {"time": 0, "alt": 0, "vel": 0},
            {"time": 5, "alt": 20, "vel": 4},
            {"time": 100, "alt": 900, "vel": 6},
            {"time": 800, "alt": 13000, "vel": 7},
            {"time": 1600, "alt": 30000, "vel": 1, "burst": True},
            {"time": 1900, "alt": 8000, "vel": -12},
            {"time": 2400, "alt": 0, "vel": 0, "landed": True},
        ]
    )


def test_animator_sends_one_gif_without_explicit_message_edit():
    interaction = FakeInteraction()
    animator = DiscordFlightAnimator(duration_s=10)

    gif = asyncio.run(
        animator.play(
            interaction,
            moments(),
            envelope_id="latex",
            payload_ids=("camera",),
        )
    )

    assert gif.startswith(b"GIF")
    # Keep comfortably below Discord's baseline upload allowance even before any
    # account/server-specific file-size increases are considered.
    assert len(gif) < 8 * 1024 * 1024
    interaction.edit_original_response.assert_not_awaited()
    interaction.followup.send.assert_awaited_once()
    sent = interaction.followup.send.await_args.kwargs
    assert sent["content"] == "🎈 **Flight playback**"
    assert sent["file"].filename == "balloon-flight.gif"

    with Image.open(BytesIO(gif)) as image:
        assert image.is_animated
        assert image.n_frames == len(moments()) * animator.ticks_per_moment


def test_duration_is_longer_clamped_and_empty_moments_do_not_send():
    assert DiscordFlightAnimator(duration_s=0).duration_s == 8
    assert DiscordFlightAnimator(duration_s=99).duration_s == 15
    interaction = FakeInteraction()
    assert asyncio.run(DiscordFlightAnimator().play(interaction, [])) is None
    interaction.followup.send.assert_not_awaited()
    interaction.edit_original_response.assert_not_awaited()


def test_frame_durations_cover_requested_animation_time():
    animator = DiscordFlightAnimator(duration_s=10)
    durations = animator._frame_durations(14)
    assert len(durations) == 14
    assert sum(durations) == 10000
    assert durations[-1] > durations[0]
