"""Convert graphical flight frames to terminal-friendly ANSI or ASCII.

This renderer deliberately consumes Pillow images rather than separate terminal
sprites.  The CLI therefore shows a downsampled version of the same scene that
Discord encodes as a GIF.
"""

from __future__ import annotations

from PIL import Image

_RESET = "\x1b[0m"
_ASCII_RAMP = " .:-=+*#%@"


class ImageAnsiRenderer:
    """Render a Pillow image using half-block true color or grayscale ASCII."""

    def __init__(self, *, columns: int = 48) -> None:
        self.columns = max(20, int(columns))

    def render(self, image: Image.Image, *, color: bool = True) -> str:
        rgb = image.convert("RGB")
        target_width = self.columns
        # Terminal cells are roughly twice as tall as they are wide.  In color
        # mode each cell also represents two vertical source pixels via ▀.
        aspect = rgb.height / max(1, rgb.width)
        if color:
            target_height = max(2, round(target_width * aspect))
            if target_height % 2:
                target_height += 1
            resized = rgb.resize((target_width, target_height), Image.Resampling.LANCZOS)
            return self._truecolor_half_blocks(resized)

        target_height = max(1, round(target_width * aspect * 0.5))
        resized = rgb.resize((target_width, target_height), Image.Resampling.LANCZOS)
        return self._ascii_luminance(resized)

    @staticmethod
    def _truecolor_half_blocks(image: Image.Image) -> str:
        pixels = image.load()
        lines: list[str] = []
        for y in range(0, image.height, 2):
            chunks: list[str] = []
            active: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None
            for x in range(image.width):
                foreground = pixels[x, y]
                background = pixels[x, min(y + 1, image.height - 1)]
                style = (foreground, background)
                if style != active:
                    fr, fg, fb = foreground
                    br, bg, bb = background
                    chunks.append(
                        f"\x1b[38;2;{fr};{fg};{fb};48;2;{br};{bg};{bb}m"
                    )
                    active = style
                chunks.append("▀")
            chunks.append(_RESET)
            lines.append("".join(chunks))
        return "\n".join(lines)

    @staticmethod
    def _ascii_luminance(image: Image.Image) -> str:
        pixels = image.load()
        lines: list[str] = []
        last_index = len(_ASCII_RAMP) - 1
        for y in range(image.height):
            characters = []
            for x in range(image.width):
                r, g, b = pixels[x, y]
                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                characters.append(_ASCII_RAMP[round((luminance / 255.0) * last_index)])
            lines.append("".join(characters))
        return "\n".join(lines)
