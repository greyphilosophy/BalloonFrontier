"""Graphical flight scene shared by Discord GIFs and terminal conversion.

The scene is intentionally assembled from small raster sprites generated with
Pillow rather than maintaining a second set of ASCII art.  Discord can encode
these frames directly while the CLI downsamples the exact same pixels to ANSI.
"""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFont

from .flight_moment import FlightEvent, FlightMoment, FlightPhase, RenderFrame


class GraphicFlightSceneRenderer:
    """Render a compact illustrated Balloon Frontier flight frame."""

    WIDTH = 384
    HEIGHT = 216

    def __init__(self, *, width: int = WIDTH, height: int = HEIGHT) -> None:
        self.width = int(width)
        self.height = int(height)
        if self.width < 240 or self.height < 150:
            raise ValueError("Flight scene is too small to render legibly")
        self._small_font = ImageFont.load_default(size=11)
        self._font = ImageFont.load_default(size=13)
        self._bold_font = ImageFont.load_default(size=15)

    def render(
        self,
        frame: RenderFrame,
        *,
        envelope_id: str = "latex",
        payload_ids: Sequence[str] = (),
    ) -> Image.Image:
        image = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(image)
        moment = frame.moment

        self._draw_sky(draw, moment)
        self._draw_background(draw, frame)
        self._draw_vehicle(draw, frame, envelope_id, tuple(payload_ids))
        self._draw_hud(draw, moment, frame)
        return image

    def _draw_sky(self, draw: ImageDraw.ImageDraw, moment: FlightMoment) -> None:
        altitude_fraction = min(1.0, max(0.0, moment.altitude_m / 30000.0))
        top_low = (31, 93, 154)
        top_high = (4, 9, 30)
        bottom_low = (126, 193, 232)
        bottom_high = (38, 61, 108)
        for y in range(self.height - 42):
            vertical = y / max(1, self.height - 43)
            top = _mix(top_low, top_high, altitude_fraction)
            bottom = _mix(bottom_low, bottom_high, altitude_fraction)
            draw.line((0, y, self.width, y), fill=_mix(top, bottom, vertical))

    def _draw_background(self, draw: ImageDraw.ImageDraw, frame: RenderFrame) -> None:
        moment = frame.moment
        sky_bottom = self.height - 42
        if moment.altitude_m >= 12000:
            phase = frame.star_phase % 5
            stars = (
                (29, 31), (71, 52), (114, 24), (165, 44), (216, 27),
                (265, 57), (307, 33), (351, 61), (45, 91), (329, 100),
            )
            for index, (x, y) in enumerate(stars):
                radius = 2 if (index + phase) % 4 == 0 else 1
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(244, 242, 218))
        else:
            cloud_y = 82 if moment.altitude_m < 1500 else 108
            cloud_x = 42 + frame.cloud_offset_x * 8
            self._cloud(draw, cloud_x, cloud_y, scale=1.0)
            self._cloud(draw, self.width - 104 - frame.cloud_offset_x * 5, cloud_y - 30, scale=0.7)

        if moment.phase in {FlightPhase.LANDED, FlightPhase.CRASHED, FlightPhase.COMPLETE} or moment.altitude_m < 500:
            draw.rectangle((0, sky_bottom, self.width, self.height), fill=(65, 112, 55))
            draw.polygon(
                ((0, sky_bottom + 8), (75, sky_bottom - 8), (143, sky_bottom + 5),
                 (227, sky_bottom - 14), (309, sky_bottom + 4), (self.width, sky_bottom - 6),
                 (self.width, self.height), (0, self.height)),
                fill=(52, 91, 51),
            )

    @staticmethod
    def _cloud(draw: ImageDraw.ImageDraw, x: int, y: int, *, scale: float) -> None:
        color = (231, 242, 250)
        shadow = (187, 213, 231)
        w = int(72 * scale)
        h = int(24 * scale)
        draw.ellipse((x, y, x + w, y + h), fill=shadow)
        draw.ellipse((x + int(7 * scale), y - int(9 * scale), x + int(39 * scale), y + int(18 * scale)), fill=color)
        draw.ellipse((x + int(28 * scale), y - int(14 * scale), x + int(61 * scale), y + int(18 * scale)), fill=color)
        draw.ellipse((x + int(5 * scale), y, x + w, y + h - int(4 * scale)), fill=color)

    def _draw_vehicle(
        self,
        draw: ImageDraw.ImageDraw,
        frame: RenderFrame,
        envelope_id: str,
        payload_ids: tuple[str, ...],
    ) -> None:
        moment = frame.moment
        center_x = self.width // 2 + frame.balloon_offset_x * 7
        terminal = moment.phase in {FlightPhase.LANDED, FlightPhase.CRASHED}
        center_y = 119 if terminal else 82

        if moment.phase == FlightPhase.BURST:
            self._draw_burst(draw, center_x, center_y)
            payload_top = center_y + 24
        else:
            balloon_box = (center_x - 34, center_y - 48, center_x + 34, center_y + 28)
            foil = envelope_id.lower() in {"foil", "mylar", "party", "foil_party"}
            outline = (64, 70, 88)
            fill = (224, 229, 237) if foil else (246, 104, 119)
            highlight = (255, 181, 190) if not foil else (255, 255, 255)
            draw.ellipse(balloon_box, fill=fill, outline=outline, width=2)
            draw.ellipse((center_x - 19, center_y - 37, center_x - 5, center_y - 10), fill=highlight)
            draw.polygon(
                ((center_x - 5, center_y + 25), (center_x + 5, center_y + 25), (center_x, center_y + 35)),
                fill=fill,
                outline=outline,
            )
            payload_top = center_y + 58
            draw.line((center_x - 7, center_y + 32, center_x - 11, payload_top), fill=(56, 57, 64), width=1)
            draw.line((center_x + 7, center_y + 32, center_x + 11, payload_top), fill=(56, 57, 64), width=1)

        visible_payloads = tuple(pid for pid in payload_ids if pid and pid != "none")
        if not visible_payloads:
            visible_payloads = ("payload",)
        primary = visible_payloads[0]
        if primary in {"quadcopter", "small_quadcopter", "drone"}:
            self._draw_quadcopter(draw, center_x, payload_top)
        else:
            self._draw_payload_box(draw, center_x, payload_top, primary)
        if len(visible_payloads) > 1:
            badge = f"+{len(visible_payloads) - 1}"
            draw.rounded_rectangle((center_x + 20, payload_top - 8, center_x + 43, payload_top + 9), radius=6, fill=(35, 39, 52))
            draw.text((center_x + 24, payload_top - 6), badge, font=self._small_font, fill=(255, 255, 255))

    @staticmethod
    def _draw_burst(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        fragments = (
            ((-29, -27), (-7, -8), (-36, -3)),
            ((11, -33), (30, -13), (7, -5)),
            ((-24, 8), (-4, 3), (-11, 27)),
            ((14, 4), (37, 10), (20, 29)),
        )
        for polygon in fragments:
            draw.polygon(tuple((x + dx, y + dy) for dx, dy in polygon), fill=(242, 91, 110), outline=(94, 43, 53))
        for dx, dy in ((-43, -27), (42, -22), (-42, 18), (43, 25)):
            draw.line((x + dx // 2, y + dy // 2, x + dx, y + dy), fill=(255, 208, 91), width=2)

    def _draw_payload_box(self, draw: ImageDraw.ImageDraw, x: int, top: int, payload_id: str) -> None:
        box = (x - 24, top, x + 24, top + 27)
        draw.rounded_rectangle(box, radius=4, fill=(226, 177, 67), outline=(75, 61, 40), width=2)
        draw.rectangle((x - 18, top + 5, x + 18, top + 21), fill=(46, 52, 66))
        icon = {
            "camera": "CAM",
            "radio": "RF",
            "radio_repeater": "RF",
            "weather_sensor": "WX",
            "battery": "BAT",
            "battery_pack": "BAT",
            "heater": "HOT",
            "ballast": "BAL",
            "parachute": "CHT",
            "flight_computer": "CPU",
            "pressure_valve": "VLV",
            "payload": "PAY",
        }.get(payload_id, payload_id[:3].upper() or "PAY")
        bbox = draw.textbbox((0, 0), icon, font=self._small_font)
        draw.text((x - (bbox[2] - bbox[0]) // 2, top + 6), icon, font=self._small_font, fill=(238, 244, 250))

    @staticmethod
    def _draw_quadcopter(draw: ImageDraw.ImageDraw, x: int, top: int) -> None:
        y = top + 12
        draw.line((x - 27, y, x + 27, y), fill=(44, 47, 55), width=3)
        draw.line((x - 18, y - 7, x + 18, y + 7), fill=(44, 47, 55), width=3)
        draw.rounded_rectangle((x - 12, y - 7, x + 12, y + 8), radius=4, fill=(67, 73, 86), outline=(26, 28, 34))
        for rx, ry in ((x - 29, y), (x + 29, y), (x - 18, y - 8), (x + 18, y + 8)):
            draw.ellipse((rx - 10, ry - 3, rx + 10, ry + 3), outline=(28, 30, 36), width=2)
        draw.ellipse((x - 3, y + 2, x + 3, y + 8), fill=(74, 183, 226))

    def _draw_hud(self, draw: ImageDraw.ImageDraw, moment: FlightMoment, frame: RenderFrame) -> None:
        draw.rounded_rectangle((8, 8, self.width - 8, 36), radius=7, fill=(13, 17, 31), outline=(125, 83, 171), width=2)
        draw.text((18, 14), "BALLOON FRONTIER", font=self._bold_font, fill=(226, 213, 243))
        status = self._status(frame)
        status_bbox = draw.textbbox((0, 0), status, font=self._font)
        draw.text((self.width - 18 - (status_bbox[2] - status_bbox[0]), 15), status, font=self._font, fill=self._status_color(moment))

        panel_top = self.height - 38
        draw.rectangle((0, panel_top, self.width, self.height), fill=(11, 15, 25))
        altitude = f"{moment.altitude_m / 1000:.1f} km" if moment.altitude_m >= 1000 else f"{moment.altitude_m:.0f} m"
        draw.text((14, panel_top + 6), f"ALT {altitude}", font=self._font, fill=(121, 219, 235))
        draw.text((141, panel_top + 6), f"V/S {moment.velocity_mps:+.1f} m/s", font=self._font, fill=(121, 219, 235))
        time_label = self._format_time(moment.time_s)
        draw.text((286, panel_top + 6), f"T+ {time_label}", font=self._font, fill=(235, 237, 243))
        if frame.event_emphasis and moment.event:
            event = moment.event.value.replace("_", " ").upper()
            bbox = draw.textbbox((0, 0), event, font=self._small_font)
            draw.text((self.width - 14 - (bbox[2] - bbox[0]), panel_top + 23), event, font=self._small_font, fill=(241, 201, 90))

    @staticmethod
    def _format_time(time_s: float) -> str:
        total = max(0, int(time_s))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    @staticmethod
    def _status(frame: RenderFrame) -> str:
        moment = frame.moment
        if moment.phase == FlightPhase.CRASHED:
            return "IMPACT"
        if moment.phase == FlightPhase.LANDED:
            return "RECOVERED"
        if moment.phase == FlightPhase.BURST:
            return "BURST"
        if moment.phase == FlightPhase.APOGEE:
            return "APOGEE"
        if moment.event == FlightEvent.ENTER_STRATOSPHERE:
            return "STRATOSPHERE"
        if moment.event == FlightEvent.CLOUD_ENTRY:
            return "CLOUD LAYER"
        if moment.event == FlightEvent.LIFTOFF:
            return "LIFTOFF"
        if moment.phase == FlightPhase.DESCENT:
            return "DESCENT"
        if moment.phase == FlightPhase.PRELAUNCH:
            return "READY"
        return "ASCENT"

    @staticmethod
    def _status_color(moment: FlightMoment) -> tuple[int, int, int]:
        if moment.phase in {FlightPhase.BURST, FlightPhase.CRASHED}:
            return (255, 118, 128)
        if moment.phase in {FlightPhase.APOGEE, FlightPhase.DESCENT, FlightPhase.PRELAUNCH}:
            return (243, 207, 89)
        return (113, 226, 147)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = min(1.0, max(0.0, amount))
    return tuple(round(left + (right - left) * amount) for left, right in zip(a, b))
