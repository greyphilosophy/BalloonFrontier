"""Discord message-edit playback for compact ANSI flight scenes."""

import asyncio
from collections.abc import Callable, Sequence

from balloon_frontier.presentation import DiscordAnsiSerializer, FlightMoment, FlightSceneBuilder, RenderFrame


class DiscordFlightAnimator:
    def __init__(self, *, duration_s: float = 3.5, sleep: Callable = asyncio.sleep) -> None:
        self.duration_s = min(5.0, max(2.0, float(duration_s)))
        self._sleep = sleep
        self._builder = FlightSceneBuilder()
        self._serializer = DiscordAnsiSerializer()

    def render(self, moment: FlightMoment, index: int = 0) -> str:
        frame = RenderFrame(moment=moment, balloon_offset_x=(-1, 0, 1, 0)[index % 4], cloud_offset_x=(-1, 0, 1)[index % 3], star_phase=index, event_emphasis=True)
        body = self._serializer.serialize(self._builder.build(frame))
        content = f"```ansi\n{body}\n```"
        if len(content) >= 2000:
            raise ValueError("Rendered Discord frame exceeds message limit")
        return content

    async def play(self, interaction, moments: Sequence[FlightMoment]) -> str | None:
        if not moments:
            return None
        delay = self.duration_s / max(1, len(moments) - 1)
        final_content = None
        for index, moment in enumerate(moments):
            final_content = self.render(moment, index)
            await interaction.edit_original_response(content=final_content, view=None)
            if index < len(moments) - 1:
                await self._sleep(delay)
        return final_content
