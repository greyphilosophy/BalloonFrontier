import pytest

from balloon_frontier.atmosphere import (
    AtmosphereProvider,
    AtmosphereSample,
    StandardAtmosphereProvider,
)
from balloon_frontier.physics import atmosphere_pressure, atmosphere_temperature


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
        "balloon_frontier.atmosphere.wind_vector",
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
