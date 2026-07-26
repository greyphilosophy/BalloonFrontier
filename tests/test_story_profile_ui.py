from balloon_frontier.atmosphere_profile import AtmosphereLayer, AtmosphereProfile
from balloon_frontier.story import format_atmosphere_profile
from balloon_frontier.weather_event import WeatherEvent


def _weather():
    return WeatherEvent(1.0, 0.0, 0.0, 0.0, 0.0, "Recorded", "", "normal")


def test_profile_table_formats_units_and_wind_direction():
    profile = AtmosphereProfile(
        layers=(
            AtmosphereLayer(0.0, 288.15, 101325.0, wind_x_mps=10.0),
            AtmosphereLayer(2000.0, 275.15, 80000.0, wind_y_mps=-5.0),
        ),
        weather=_weather(),
        wind_measured=True,
    )

    text = format_atmosphere_profile(profile)

    assert "0.0" in text
    assert "15.0" in text
    assert "101.3" in text
    assert "10.0 E" in text
    assert "5.0 S" in text
    assert "Legacy profile" not in text


def test_profile_table_limits_rows_and_labels_legacy_wind():
    profile = AtmosphereProfile(
        layers=tuple(
            AtmosphereLayer(float(index * 1000), 280.0, 90000.0)
            for index in range(5)
        ),
        weather=_weather(),
        wind_measured=False,
    )

    text = format_atmosphere_profile(profile, max_layers=2)

    assert "3 higher layers omitted" in text
    assert "Legacy profile" in text


def test_empty_profile_has_clear_message():
    profile = AtmosphereProfile(layers=(), weather=_weather(), wind_measured=False)

    assert "No measured layers" in format_atmosphere_profile(profile)
