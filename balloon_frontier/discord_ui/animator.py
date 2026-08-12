"""Discord GIF playback generated from the shared graphical flight scene."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence

import discord
from PIL import Image

from balloon_frontier.presentation import (
    FlightMoment,
    GraphicFlightSceneRenderer,
    RenderFrame,
)


class DiscordFlightAnimator:
    """Encode a complete flight montage and deliver it through the interaction webhook."""

    def __init__(self, *, duration_s: float = 10.0, ticks_per_moment: int = 2) -> None:
        self.duration_s = min(15.0, max(8.0, float(duration_s)))
        self.ticks_per_moment = min(4, max(1, int(ticks_per_moment)))
        self._renderer = GraphicFlightSceneRenderer()

    def render_frames(
        self,
        moments: Sequence[FlightMoment],
        *,
        envelope_id: str = "latex",
        payload_ids: Sequence[str] = (),
    ) -> list[Image.Image]:
        frames: list[Image.Image] = []
        for index, moment in enumerate(moments):
            for tick in range(self.ticks_per_moment):
                animation_index = index * self.ticks_per_moment + tick
                sway = (-1, 0, 1, 0)[animation_index % 4]
                cloud_sway = (-1, 0, 1)[animation_index % 3]
                frame = RenderFrame(
                    moment=moment,
                    animation_tick=tick,
                    balloon_offset_x=sway,
                    cloud_offset_x=cloud_sway,
                    star_phase=animation_index,
                    event_emphasis=True,
                )
                frames.append(
                    self._renderer.render(
                        frame,
                        envelope_id=envelope_id,
                        payload_ids=payload_ids,
                    )
                )
        return frames

    def render_gif(
        self,
        moments: Sequence[FlightMoment],
        *,
        envelope_id: str = "latex",
        payload_ids: Sequence[str] = (),
    ) -> bytes:
        frames = self.render_frames(
            moments,
            envelope_id=envelope_id,
            payload_ids=payload_ids,
        )
        if not frames:
            return b""

        palette_frames = [
            frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
            for frame in frames
        ]
        durations = self._frame_durations(len(palette_frames))
        output = io.BytesIO()
        palette_frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=palette_frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
            optimize=True,
        )
        return output.getvalue()

    def _frame_durations(self, frame_count: int) -> list[int]:
        total_ms = round(self.duration_s * 1000)
        if frame_count <= 1:
            return [total_ms]

        # Hold the completed flight slightly longer so Discord users can read the
        # terminal state before the animation loops.
        final_hold_ms = min(1400, max(700, total_ms // 6))
        remaining_ms = max(frame_count - 1, total_ms - final_hold_ms)
        base_ms, remainder = divmod(remaining_ms, frame_count - 1)
        durations = [
            base_ms + (1 if index < remainder else 0)
            for index in range(frame_count - 1)
        ]
        durations.append(max(final_hold_ms, base_ms))
        return durations

    async def play(
        self,
        interaction,
        moments: Sequence[FlightMoment],
        *,
        envelope_id: str = "latex",
        payload_ids: Sequence[str] = (),
    ) -> bytes | None:
        if not moments:
            return None

        # Rendering and GIF encoding are CPU-bound Pillow work. Keep them off the
        # Discord event loop so one launch cannot stall unrelated bot callbacks.
        gif = await asyncio.to_thread(
            self.render_gif,
            moments,
            envelope_id=envelope_id,
            payload_ids=payload_ids,
        )
        followup = getattr(interaction, "followup", None)
        if followup is None or not hasattr(followup, "send"):
            raise RuntimeError("Discord interaction does not support follow-up delivery")
        file = discord.File(io.BytesIO(gif), filename="balloon-flight.gif")
        # The launch handler defers with thinking=True. discord.py completes that
        # deferred response when the first follow-up is sent, so there is no need
        # for an explicit edit_original_response() here.
        await followup.send(
            content="🎈 **Flight playback**",
            file=file,
        )
        return gif
