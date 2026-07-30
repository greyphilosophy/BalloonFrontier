"""Fixed-width styled character canvas."""

from dataclasses import dataclass
from typing import Iterable

from .palette import Color


@dataclass(frozen=True)
class Cell:
    character: str = " "
    foreground: Color | None = None
    background: Color | None = None
    bold: bool = False

    def __post_init__(self) -> None:
        if len(self.character) != 1:
            raise ValueError("Cell.character must contain exactly one code point")


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("Canvas dimensions must be positive")
        self.width = width
        self.height = height
        self._rows = [[Cell() for _ in range(width)] for _ in range(height)]

    def put(self, x: int, y: int, cell: Cell) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._rows[y][x] = cell

    def write(self, x: int, y: int, text: str, *, foreground: Color | None = None,
              background: Color | None = None, bold: bool = False) -> None:
        if not 0 <= y < self.height:
            return
        for offset, character in enumerate(text):
            self.put(x + offset, y, Cell(character, foreground, background, bold))

    def draw_lines(self, x: int, y: int, lines: Iterable[str], *,
                   foreground: Color | None = None, bold: bool = False) -> None:
        for row_offset, line in enumerate(lines):
            self.write(x, y + row_offset, line, foreground=foreground, bold=bold)

    def rows(self) -> tuple[tuple[Cell, ...], ...]:
        return tuple(tuple(row) for row in self._rows)
