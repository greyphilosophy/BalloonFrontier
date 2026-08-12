"""Shared flight presentation primitives for image, ANSI, and plain output."""

from .ansi_image import ImageAnsiRenderer
from .canvas import Canvas, Cell
from .flight_moment import FlightEvent, FlightMoment, FlightPhase, RenderFrame
from .image_scene import GraphicFlightSceneRenderer
from .palette import Color
from .scene_builder import FlightSceneBuilder
from .serializers import DiscordAnsiSerializer, PlainTextSerializer, TerminalAnsiSerializer
from .timeline import build_flight_moments

__all__ = [
    "Canvas",
    "Cell",
    "Color",
    "DiscordAnsiSerializer",
    "FlightEvent",
    "FlightMoment",
    "FlightPhase",
    "FlightSceneBuilder",
    "GraphicFlightSceneRenderer",
    "ImageAnsiRenderer",
    "PlainTextSerializer",
    "RenderFrame",
    "TerminalAnsiSerializer",
    "build_flight_moments",
]
