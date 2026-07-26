import pytest

from balloon_frontier.noaa_igra import (
    IgraStation,
    nearest_stations,
    parse_station_list,
    period_of_record_archive_url,
    recent_archive_url,
)


def _station_line(
    station_id="USM00072797",
    latitude=47.6833,
    longitude=-117.6333,
    elevation=721.0,
    state="WA",
    name="SPOKANE INTL AP",
    first_year=1948,
    last_year=2026,
    observations=50000,
):
    return (
        f"{station_id:<11} {latitude:8.4f} {longitude:9.4f} {elevation:6.1f} "
        f"{state:<2} {name:<30} {first_year:4d} {last_year:4d} {observations:6d}"
    )


def test_parse_station_list_uses_official_fixed_width_columns():
    station = parse_station_list(_station_line())[0]

    assert station.station_id == "USM00072797"
    assert station.latitude_deg == pytest.approx(47.6833)
    assert station.longitude_deg == pytest.approx(-117.6333)
    assert station.elevation_m == pytest.approx(721.0)
    assert station.state_code == "WA"
    assert station.name == "SPOKANE INTL AP"
    assert station.first_year == 1948
    assert station.last_year == 2026
    assert station.observation_count == 50000


def test_missing_elevation_and_malformed_rows_are_tolerated():
    text = "bad row\n" + _station_line(elevation=-999.9)

    station = parse_station_list(text)[0]

    assert station.elevation_m is None


def test_nearest_stations_filters_mobile_and_record_year():
    near = IgraStation("USM00000001", 47.0, -122.0, 10.0, "WA", "Near", 2000, 2026, 10)
    far = IgraStation("USM00000002", 45.0, -120.0, 10.0, "OR", "Far", 1900, 2026, 10)
    old = IgraStation("USM00000003", 46.9, -122.0, 10.0, "WA", "Old", 1900, 1990, 10)
    mobile = IgraStation("ZZV00000001", -98.8888, -998.8888, None, None, "Mobile", 2000, 2026, 10)

    result = nearest_stations(
        (far, mobile, old, near),
        47.1,
        -122.0,
        limit=3,
        active_in_year=2026,
    )

    assert result == (near, far)


def test_archive_urls_are_stable_and_validate_station_ids():
    assert recent_archive_url("usm00072797", beginning_year=2026).endswith(
        "/USM00072797-data-beg2026.txt.zip"
    )
    assert period_of_record_archive_url("USM00072797").endswith(
        "/USM00072797-data.txt.zip"
    )
    with pytest.raises(ValueError, match="station_id"):
        period_of_record_archive_url("../../bad")
