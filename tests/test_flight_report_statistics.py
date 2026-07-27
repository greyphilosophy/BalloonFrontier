from balloon_frontier.narrative_result import (
    format_discord_results,
    format_flight_duration,
)


def _report(*, altitude=31842.4, duration=8045.0):
    return format_discord_results(
        peak_altitude=altitude,
        burst=True,
        landed=False,
        crashed=False,
        time_of_flight=duration,
        telemetry=[],
        gas_name="Helium",
        gas_mass=1.25,
        env_name="Latex Weather Balloon",
        payload_names="Camera",
        site_name="Open Field",
    )


def test_after_flight_report_includes_maximum_altitude_in_meters_and_kilometers():
    report = _report()

    assert "📊 **Flight Statistics**" in report
    assert "Maximum altitude: 31,842 m (31.84 km)" in report


def test_after_flight_report_includes_human_readable_duration():
    report = _report()

    assert "Flight duration: 2h 14m 05s" in report


def test_duration_formatter_handles_short_and_negative_values():
    assert format_flight_duration(42.4) == "42s"
    assert format_flight_duration(125.0) == "2m 05s"
    assert format_flight_duration(-10.0) == "0s"
