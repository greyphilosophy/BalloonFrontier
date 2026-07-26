from dataclasses import dataclass

import pytest

from balloon_frontier.atmosphere import AtmosphereSample
from balloon_frontier.catalog import FillMode
from balloon_frontier.flight_service import FlightService
from balloon_frontier.launch_result import LaunchRequest
from balloon_frontier.weather_column import WeatherColumn


def _request():
    return LaunchRequest(
        gas_id="helium",
        envelope_id="latex",
        payload_ids=(),
        launch_site_id="field",
        fill_mode=FillMode.NORMAL,
    )


def test_prepare_assigns_a_deterministic_weather_column():
    service = FlightService(default_sim_time=0.2)

    first = service.prepare(_request())
    second = service.prepare(_request())

    assert isinstance(first.atmosphere_provider, WeatherColumn)
    assert first.atmosphere_provider == second.atmosphere_provider
    assert first.atmosphere_provider.ceiling_m == 50000.0


def test_run_reports_the_column_that_drove_physics():
    outcome = FlightService(default_sim_time=0.2).run(_request())

    assert isinstance(outcome.atmosphere_provider, WeatherColumn)
    first = outcome.result.telemetry[0]
    expected = outcome.atmosphere_provider.sample(first.altitude_m, time_s=first.time_s)
    assert first.ambient_temperature_k == pytest.approx(expected.temperature_k, abs=0.1)
    assert first.ambient_pressure_pa == pytest.approx(expected.pressure_pa, abs=50.0)


@dataclass(frozen=True)
class _FixedAtmosphere:
    def sample(self, altitude_m: float, *, time_s: float = 0.0) -> AtmosphereSample:
        del time_s
        return AtmosphereSample(
            altitude_m=max(0.0, altitude_m),
            temperature_k=250.0,
            pressure_pa=70000.0,
            wind_x_mps=12.0,
            wind_y_mps=0.0,
        )


def test_explicit_provider_overrides_generated_column():
    provider = _FixedAtmosphere()
    outcome = FlightService(
        default_sim_time=0.2,
        atmosphere_provider=provider,
    ).run(_request())

    assert outcome.atmosphere_provider is provider
    first = outcome.result.telemetry[0]
    assert first.ambient_temperature_k == pytest.approx(250.0, abs=0.1)
    assert first.ambient_pressure_pa == pytest.approx(70000.0, abs=50.0)
