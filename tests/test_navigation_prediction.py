import pytest

from balloon_frontier.atmosphere_profile import AtmosphereLayer, AtmosphereProfile
from balloon_frontier.navigation_prediction import predict_landing_offset
from balloon_frontier.weather_event import WeatherEvent


def _weather():
    return WeatherEvent(1.0, 0.0, 0.0, 0.0, 0.0, "Recorded", "", "normal")


def test_constant_east_wind_matches_time_integral():
    profile = AtmosphereProfile(
        layers=(
            AtmosphereLayer(0.0, 288.0, 101325.0, wind_x_mps=10.0),
            AtmosphereLayer(1000.0, 280.0, 90000.0, wind_x_mps=10.0),
        ),
        weather=_weather(),
        wind_measurements_available=True,
    )
    prediction = predict_landing_offset(
        profile,
        target_altitude_m=1000.0,
        ascent_rate_mps=5.0,
        descent_rate_mps=10.0,
        altitude_step_m=200.0,
    )
    assert prediction.flight_time_s == pytest.approx(300.0)
    assert prediction.east_m == pytest.approx(3000.0)
    assert prediction.north_m == pytest.approx(0.0)
    assert prediction.distance_m == pytest.approx(3000.0)


def test_opposing_layers_can_cancel_drift():
    profile = AtmosphereProfile(
        layers=(
            AtmosphereLayer(0.0, 288.0, 101325.0, wind_x_mps=-10.0),
            AtmosphereLayer(500.0, 284.0, 95000.0, wind_x_mps=0.0),
            AtmosphereLayer(1000.0, 280.0, 90000.0, wind_x_mps=10.0),
        ),
        weather=_weather(),
        wind_measurements_available=True,
    )
    prediction = predict_landing_offset(
        profile,
        target_altitude_m=1000.0,
        ascent_rate_mps=5.0,
        descent_rate_mps=5.0,
        altitude_step_m=100.0,
    )
    assert prediction.east_m == pytest.approx(0.0, abs=1e-9)


def test_prediction_rejects_profile_without_measured_wind():
    profile = AtmosphereProfile(
        layers=(AtmosphereLayer(0.0, 288.0, 101325.0),),
        weather=_weather(),
        wind_measurements_available=False,
    )
    with pytest.raises(ValueError, match="measured wind"):
        predict_landing_offset(profile, target_altitude_m=1000.0)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"target_altitude_m": 0.0}, "target_altitude_m"),
        ({"target_altitude_m": 1000.0, "ascent_rate_mps": 0.0}, "vertical rates"),
        ({"target_altitude_m": 1000.0, "descent_rate_mps": -1.0}, "vertical rates"),
        ({"target_altitude_m": 1000.0, "altitude_step_m": 0.0}, "altitude_step_m"),
    ],
)
def test_prediction_rejects_invalid_inputs(kwargs, message):
    profile = AtmosphereProfile(
        layers=(AtmosphereLayer(0.0, 288.0, 101325.0),),
        weather=_weather(),
        wind_measurements_available=True,
    )
    with pytest.raises(ValueError, match=message):
        predict_landing_offset(profile, **kwargs)
