from datetime import datetime, timezone

import pytest

from balloon_frontier.atmosphere import AtmosphereProvider
from balloon_frontier.sounding_atmosphere import (
    AtmosphericSounding,
    SoundingAtmosphereProvider,
    SoundingLevel,
)


def _sounding():
    return AtmosphericSounding.from_levels(
        (
            SoundingLevel(2000.0, 275.0, 80000.0, wind_x_mps=20.0, wind_y_mps=-4.0),
            SoundingLevel(0.0, 295.0, 100000.0, wind_x_mps=0.0, wind_y_mps=2.0),
            SoundingLevel(1000.0, 285.0, 90000.0, wind_x_mps=10.0, wind_y_mps=-1.0),
        ),
        source="test",
        station_id="TEST0000001",
        observed_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        latitude_deg=47.0,
        longitude_deg=-122.0,
    )


def test_sounding_normalizes_levels_and_exposes_coverage():
    sounding = _sounding()

    assert [level.altitude_m for level in sounding.levels] == [0.0, 1000.0, 2000.0]
    assert sounding.floor_m == 0.0
    assert sounding.ceiling_m == 2000.0
    assert sounding.source == "test"


def test_provider_satisfies_contract_and_interpolates_fields():
    provider = SoundingAtmosphereProvider(_sounding())

    assert isinstance(provider, AtmosphereProvider)
    sample = provider.sample(500.0, time_s=999.0)

    assert sample.altitude_m == 500.0
    assert sample.temperature_k == pytest.approx(290.0)
    assert sample.pressure_pa == pytest.approx((100000.0 * 90000.0) ** 0.5)
    assert sample.wind_x_mps == pytest.approx(5.0)
    assert sample.wind_y_mps == pytest.approx(0.5)


def test_provider_clamps_below_floor_but_rejects_above_ceiling():
    sounding = AtmosphericSounding(
        levels=(
            SoundingLevel(500.0, 290.0, 95000.0, wind_x_mps=3.0),
            SoundingLevel(1500.0, 280.0, 85000.0, wind_x_mps=8.0),
        )
    )
    provider = SoundingAtmosphereProvider(sounding)

    below = provider.sample(100.0)
    assert below.altitude_m == 100.0
    assert below.temperature_k == 290.0
    assert below.wind_x_mps == 3.0

    ceiling = provider.sample(1500.0)
    assert ceiling.temperature_k == 280.0

    with pytest.raises(ValueError, match="highest measured sounding level"):
        provider.sample(1500.1)


def test_invalid_levels_and_metadata_are_rejected():
    with pytest.raises(ValueError, match="strictly ascending"):
        AtmosphericSounding(
            levels=(
                SoundingLevel(1000.0, 280.0, 90000.0),
                SoundingLevel(1000.0, 275.0, 80000.0),
            )
        )
    with pytest.raises(ValueError, match="timezone"):
        AtmosphericSounding(
            levels=(SoundingLevel(0.0, 290.0, 100000.0),),
            observed_at=datetime(2026, 7, 26),
        )
    with pytest.raises(ValueError, match="supplied together"):
        AtmosphericSounding(
            levels=(SoundingLevel(0.0, 290.0, 100000.0),),
            latitude_deg=47.0,
        )
    with pytest.raises(ValueError, match="finite"):
        SoundingLevel(float("nan"), 290.0, 100000.0)
    with pytest.raises(ValueError, match="altitude_m must be finite"):
        SoundingAtmosphereProvider(_sounding()).sample(float("inf"))
