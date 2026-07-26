import pytest

from balloon_frontier.atmosphere import (
    AtmosphereProvider,
    AtmosphereSample,
    StandardAtmosphereProvider,
    current_atmosphere_provider,
    use_atmosphere,
)
from balloon_frontier.physics import atmosphere_pressure, atmosphere_temperature
from balloon_frontier.wind import wind_vector


def test_standard_provider_matches_existing_standard_atmosphere_without_wind():
    provider = StandardAtmosphereProvider(wind_enabled=False)

    sample = provider.sample(2500.0, time_s=120.0)

    assert sample.altitude_m == 2500.0
    assert sample.temperature_k == pytest.approx(atmosphere_temperature(2500.0))
    assert sample.pressure_pa == pytest.approx(atmosphere_pressure(2500.0))
    assert sample.wind_x_mps == 0.0
    assert sample.wind_y_mps == 0.0
    assert isinstance(provider, AtmosphereProvider)


def test_standard_provider_applies_composable_modifiers(monkeypatch):
    monkeypatch.setattr(
        "balloon_frontier.atmosphere._standard_wind_vector",
        lambda altitude_m, *, time_s, site_id: (4.0, -2.0),
    )
    provider = StandardAtmosphereProvider(
        site_id="mountain",
        wind_multiplier=1.5,
        pressure_multiplier=0.98,
        temperature_offset_k=-3.0,
    )

    sample = provider.sample(1000.0, time_s=30.0)

    assert sample.temperature_k == pytest.approx(atmosphere_temperature(1000.0) - 3.0)
    assert sample.pressure_pa == pytest.approx(atmosphere_pressure(1000.0) * 0.98)
    assert sample.wind_x_mps == 6.0
    assert sample.wind_y_mps == -3.0


def test_provider_clamps_below_sea_level_altitudes():
    sample = StandardAtmosphereProvider(wind_enabled=False).sample(-50.0)

    assert sample.altitude_m == 0.0
    assert sample.temperature_k == pytest.approx(atmosphere_temperature(0.0))
    assert sample.pressure_pa == pytest.approx(atmosphere_pressure(0.0))


def test_active_provider_dispatches_physics_and_wind_then_resets():
    class FixedProvider:
        def sample(self, altitude_m, *, time_s=0.0):
            return AtmosphereSample(
                altitude_m=float(altitude_m),
                temperature_k=250.0,
                pressure_pa=70000.0,
                wind_x_mps=12.0 + time_s,
                wind_y_mps=-4.0,
            )

    provider = FixedProvider()
    assert current_atmosphere_provider() is None

    with use_atmosphere(provider):
        assert current_atmosphere_provider() is provider
        assert atmosphere_temperature(5000.0) == 250.0
        assert atmosphere_pressure(5000.0) == 70000.0
        assert wind_vector(5000.0, time_s=3.0) == (15.0, -4.0)

    assert current_atmosphere_provider() is None
    assert atmosphere_temperature(5000.0) != 250.0


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"temperature_k": 0.0, "pressure_pa": 101325.0}, "temperature_k"),
        ({"temperature_k": 288.15, "pressure_pa": 0.0}, "pressure_pa"),
    ],
)
def test_atmosphere_samples_reject_nonphysical_values(kwargs, message):
    with pytest.raises(ValueError, match=message):
        AtmosphereSample(altitude_m=0.0, **kwargs)
