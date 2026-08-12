import asyncio
from io import BytesIO
import threading
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


def production_moments():
    telemetry = [
        {
            "time": index * 60,
            "alt": index * 1500 if index <= 20 else (40 - index) * 1500,
            "vel": 6 if index <= 20 else -10,
            "landed": index == 40,
        }
        for index in range(41)
    ]
    selected = build_flight_moments(telemetry, max_frames=18)
    assert len(selected) == 18
    return selected


def test_animator_installs_production_size_gif_on_deferred_response():
    interaction = FakeInteraction()
    animator = DiscordFlightAnimator(duration_s=10)
    selected = production_moments()

    gif = asyncio.run(
        animator.play(
            interaction,
            selected,
            envelope_id="latex",
            payload_ids=("camera",),
        )
    )

    assert gif.startswith(b"GIF")
    # Exercise the same 18-moment montage production requests, not the smaller
    # legacy fixture, so this guard reflects the actual Discord upload.
    assert len(gif) < 8 * 1024 * 1024
    interaction.followup.send.assert_not_awaited()
    interaction.edit_original_response.assert_awaited_once()
    edit = interaction.edit_original_response.await_args.kwargs
    assert edit["content"] == "🎈 **Flight playback**"
    assert edit["view"] is None
    assert len(edit["attachments"]) == 1
    assert edit["attachments"][0].filename == "balloon-flight.gif"

    with Image.open(BytesIO(gif)) as image:
        assert image.is_animated
        assert image.n_frames == len(selected) * animator.ticks_per_moment


def test_gif_rendering_runs_off_the_event_loop_thread():
    interaction = FakeInteraction()
    animator = DiscordFlightAnimator(duration_s=10)
    caller_thread = threading.get_ident()
    render_threads = []
    original_render_gif = animator.render_gif

    def recording_render_gif(*args, **kwargs):
        render_threads.append(threading.get_ident())
        return original_render_gif(*args, **kwargs)

    animator.render_gif = recording_render_gif
    asyncio.run(animator.play(interaction, moments()))

    assert render_threads
    assert render_threads[0] != caller_thread


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
