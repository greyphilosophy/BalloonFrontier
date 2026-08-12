import asyncio
from io import BytesIO

from PIL import Image

from balloon_frontier.discord_ui.animator import DiscordFlightAnimator
from balloon_frontier.presentation import build_flight_moments


class FakeInteraction:
    def __init__(self):
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


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


def test_animator_uploads_one_gif_instead_of_editing_every_frame():
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
    assert len(interaction.edits) == 1
    edit = interaction.edits[0]
    assert edit["content"] == "🎈 **Flight playback**"
    assert edit["view"] is None
    assert len(edit["attachments"]) == 1
    assert edit["attachments"][0].filename == "balloon-flight.gif"

    with Image.open(BytesIO(gif)) as image:
        assert image.is_animated
        assert image.n_frames == len(moments()) * animator.ticks_per_moment


def test_duration_is_longer_clamped_and_empty_moments_do_not_edit():
    assert DiscordFlightAnimator(duration_s=0).duration_s == 8
    assert DiscordFlightAnimator(duration_s=99).duration_s == 15
    interaction = FakeInteraction()
    assert asyncio.run(DiscordFlightAnimator().play(interaction, [])) is None
    assert interaction.edits == []


def test_frame_durations_cover_requested_animation_time():
    animator = DiscordFlightAnimator(duration_s=10)
    durations = animator._frame_durations(14)
    assert len(durations) == 14
    assert sum(durations) == 10000
    assert durations[-1] > durations[0]
