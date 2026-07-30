"""Serialize styled canvases for Discord, terminals, and plain output."""

from .canvas import Canvas, Cell
from .palette import Color

_RESET = "\x1b[0m"
_FG = {Color.BLACK: 30, Color.RED: 31, Color.GREEN: 32, Color.YELLOW: 33, Color.BLUE: 34, Color.MAGENTA: 35, Color.CYAN: 36, Color.WHITE: 37}
_BG = {color: code + 10 for color, code in _FG.items()}


class PlainTextSerializer:
    def serialize(self, canvas: Canvas) -> str:
        return "\n".join("".join(cell.character for cell in row) for row in canvas.rows())


class _AnsiSerializer:
    def serialize(self, canvas: Canvas) -> str:
        return "\n".join(self._line(row) for row in canvas.rows())

    def _line(self, row: tuple[Cell, ...]) -> str:
        chunks = []
        active = None
        for cell in row:
            style = (cell.foreground, cell.background, cell.bold)
            if style != active:
                chunks.append(_RESET)
                codes = []
                if cell.bold: codes.append("1")
                if cell.foreground is not None: codes.append(str(_FG[cell.foreground]))
                if cell.background is not None: codes.append(str(_BG[cell.background]))
                if codes: chunks.append(f"\x1b[{';'.join(codes)}m")
                active = style
            chunks.append(cell.character)
        chunks.append(_RESET)
        return "".join(chunks)


class DiscordAnsiSerializer(_AnsiSerializer):
    """ANSI subset accepted inside Discord ANSI code blocks."""


class TerminalAnsiSerializer(_AnsiSerializer):
    """Portable eight-color terminal ANSI serializer."""
