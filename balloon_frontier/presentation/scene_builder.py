"""Build the shared 34-column Balloon Frontier scene."""

from .assets import BALLOON, CLOUDS, GROUND, STARS
from .canvas import Canvas, Cell
from .flight_moment import FlightEvent, FlightPhase, RenderFrame
from .palette import Color


class FlightSceneBuilder:
    WIDTH = 34
    HEIGHT = 18

    def build(self, frame: RenderFrame) -> Canvas:
        canvas = Canvas(self.WIDTH, self.HEIGHT)
        self._border(canvas)
        moment = frame.moment
        if moment.altitude_m >= 12000:
            canvas.write(2, 3, STARS[frame.star_phase % len(STARS)][:30], foreground=Color.WHITE)
        elif moment.altitude_m < 1500:
            canvas.write(7, 12, CLOUDS, foreground=Color.CYAN)
        else:
            canvas.write(5 + frame.cloud_offset_x, 12, CLOUDS, foreground=Color.CYAN)
        if moment.phase in {FlightPhase.LANDED, FlightPhase.CRASHED, FlightPhase.COMPLETE}:
            canvas.write(6, 12, GROUND, foreground=Color.GREEN)
        balloon_x = 12 + frame.balloon_offset_x
        balloon_y = 5 if moment.phase not in {FlightPhase.LANDED, FlightPhase.CRASHED} else 7
        color = Color.RED if moment.phase in {FlightPhase.BURST, FlightPhase.CRASHED} else Color.WHITE
        canvas.draw_lines(balloon_x, balloon_y, BALLOON, foreground=color, bold=True)
        altitude = self._format_altitude(moment.altitude_m)
        velocity = f"{moment.velocity_mps:+.1f}m/s"
        canvas.write(2, 14, f"ALT {altitude:<7} V/S {velocity:>8}"[:30], foreground=Color.CYAN, bold=True)
        status, status_color = self._status(frame)
        canvas.write(2, 15, status[:30].center(30), foreground=status_color, bold=True)
        canvas.write(2, 16, f"T+ {self._format_time(moment.time_s)}".ljust(30), foreground=Color.WHITE)
        return canvas

    def _border(self, canvas: Canvas) -> None:
        canvas.write(0, 0, "+" + "-" * 32 + "+", foreground=Color.MAGENTA, bold=True)
        canvas.write(0, 1, "|" + "BALLOON FRONTIER".center(32) + "|", foreground=Color.MAGENTA, bold=True)
        canvas.write(0, 2, "+" + "-" * 32 + "+", foreground=Color.MAGENTA, bold=True)
        for y in range(3, 17):
            canvas.put(0, y, Cell("|", Color.MAGENTA, bold=True))
            canvas.put(33, y, Cell("|", Color.MAGENTA, bold=True))
        canvas.write(0, 13, "+" + "-" * 32 + "+", foreground=Color.MAGENTA, bold=True)
        canvas.write(0, 17, "+" + "-" * 32 + "+", foreground=Color.MAGENTA, bold=True)

    @staticmethod
    def _format_altitude(altitude_m: float) -> str:
        return f"{altitude_m / 1000:.1f}km" if altitude_m >= 1000 else f"{altitude_m:.0f}m"

    @staticmethod
    def _format_time(time_s: float) -> str:
        total = max(0, int(time_s)); hours, remainder = divmod(total, 3600); minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"

    @staticmethod
    def _status(frame: RenderFrame) -> tuple[str, Color]:
        moment = frame.moment
        if moment.phase == FlightPhase.CRASHED: return "IMPACT - FLIGHT LOST", Color.RED
        if moment.phase == FlightPhase.LANDED: return "RECOVERY COMPLETE", Color.GREEN
        if moment.phase == FlightPhase.BURST: return "ENVELOPE BURST", Color.RED
        if moment.phase == FlightPhase.APOGEE: return "APOGEE", Color.YELLOW
        if moment.event == FlightEvent.ENTER_STRATOSPHERE: return "ENTERING STRATOSPHERE", Color.MAGENTA
        if moment.event == FlightEvent.CLOUD_ENTRY: return "CLOUD LAYER", Color.CYAN
        if moment.event == FlightEvent.LIFTOFF: return "LIFTOFF", Color.GREEN
        if moment.phase == FlightPhase.DESCENT: return "DESCENT", Color.YELLOW
        if moment.phase == FlightPhase.PRELAUNCH: return "READY FOR RELEASE", Color.YELLOW
        return "ASCENT", Color.GREEN
