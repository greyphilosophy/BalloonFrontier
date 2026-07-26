"""NOAA IGRA station discovery and archive-location helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

STATION_LIST_URL = "https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt"
RECENT_DATA_ROOT = "https://www.ncei.noaa.gov/pub/data/igra/data/data-y2d"
PERIOD_OF_RECORD_ROOT = "https://www.ncei.noaa.gov/pub/data/igra/data/data-por"


@dataclass(frozen=True, slots=True)
class IgraStation:
    station_id: str
    latitude_deg: float
    longitude_deg: float
    elevation_m: float | None
    state_code: str | None
    name: str
    first_year: int
    last_year: int
    observation_count: int

    @property
    def is_mobile(self) -> bool:
        return self.latitude_deg == -98.8888 or self.longitude_deg == -998.8888

    def distance_km_to(self, latitude_deg: float, longitude_deg: float) -> float:
        if self.is_mobile:
            return math.inf
        return _haversine_km(
            self.latitude_deg,
            self.longitude_deg,
            float(latitude_deg),
            float(longitude_deg),
        )


def parse_station_list(text: str) -> tuple[IgraStation, ...]:
    """Parse NOAA's IGRA v2.2 fixed-width station list."""

    stations: list[IgraStation] = []
    for line in text.splitlines():
        if len(line) < 88:
            continue
        try:
            station_id = line[0:11].strip()
            latitude = float(line[12:20])
            longitude = float(line[21:30])
            elevation_raw = float(line[31:37])
            first_year = int(line[72:76])
            last_year = int(line[77:81])
            observation_count = int(line[82:88])
        except ValueError:
            continue
        if not station_id:
            continue
        stations.append(
            IgraStation(
                station_id=station_id,
                latitude_deg=latitude,
                longitude_deg=longitude,
                elevation_m=(
                    None if elevation_raw in {-999.9, -998.8} else elevation_raw
                ),
                state_code=line[38:40].strip() or None,
                name=line[41:71].strip(),
                first_year=first_year,
                last_year=last_year,
                observation_count=observation_count,
            )
        )
    return tuple(stations)


def nearest_stations(
    stations: Iterable[IgraStation],
    latitude_deg: float,
    longitude_deg: float,
    *,
    limit: int = 5,
    active_in_year: int | None = None,
) -> tuple[IgraStation, ...]:
    """Return nearest fixed stations, optionally filtered by record year."""

    if limit <= 0:
        return ()
    candidates = [
        station
        for station in stations
        if not station.is_mobile
        and (
            active_in_year is None
            or station.first_year <= active_in_year <= station.last_year
        )
    ]
    candidates.sort(
        key=lambda station: station.distance_km_to(latitude_deg, longitude_deg)
    )
    return tuple(candidates[:limit])


def recent_archive_url(station_id: str, *, beginning_year: int) -> str:
    identifier = _validated_station_id(station_id)
    year = int(beginning_year)
    if year < 1900 or year > 9999:
        raise ValueError("beginning_year must be a four-digit year")
    return f"{RECENT_DATA_ROOT}/{identifier}-data-beg{year}.txt.zip"


def period_of_record_archive_url(station_id: str) -> str:
    identifier = _validated_station_id(station_id)
    return f"{PERIOD_OF_RECORD_ROOT}/{identifier}-data.txt.zip"


def _validated_station_id(station_id: str) -> str:
    identifier = str(station_id).strip().upper()
    if len(identifier) != 11 or not identifier.isalnum():
        raise ValueError("IGRA station_id must contain exactly 11 letters or digits")
    return identifier


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(value)))
