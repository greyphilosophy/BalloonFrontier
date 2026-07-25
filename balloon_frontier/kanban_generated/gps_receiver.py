from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Literal, Optional, Sequence, Tuple


EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True, slots=True)
class GPSFix:
    """A single GPS position fix.

    Attributes
    ----------
    latitude_deg / longitude_deg:
        WGS84 coordinates in degrees.
    timestamp_s:
        Simulation time in seconds. Used for ordering + accuracy matching.
    horizontal_accuracy_m:
        Optional reported horizontal accuracy (1-sigma-ish). If provided,
        consumers may incorporate it into weighting.
    """

    latitude_deg: float
    longitude_deg: float
    timestamp_s: float
    horizontal_accuracy_m: Optional[float] = None

    def __post_init__(self) -> None:
        if not (-90.0 <= self.latitude_deg <= 90.0):
            raise ValueError("latitude_deg must be within [-90, 90]")
        if not (-180.0 <= self.longitude_deg <= 180.0):
            raise ValueError("longitude_deg must be within [-180, 180]")
        if self.horizontal_accuracy_m is not None and self.horizontal_accuracy_m < 0:
            raise ValueError("horizontal_accuracy_m must be non-negative")


def haversine_distance_m(
    a: GPSFix | Tuple[float, float],
    b: GPSFix | Tuple[float, float],
    *,
    earth_radius_m: float = EARTH_RADIUS_M,
) -> float:
    """Great-circle distance between two points.

    Parameters
    ----------
    a, b:
        Either :class:`GPSFix` or ``(lat_deg, lon_deg)`` tuples.

    Returns
    -------
    float
        Distance in meters.
    """

    if earth_radius_m <= 0:
        raise ValueError("earth_radius_m must be positive")

    if isinstance(a, GPSFix):
        lat1, lon1 = a.latitude_deg, a.longitude_deg
    else:
        lat1, lon1 = a

    if isinstance(b, GPSFix):
        lat2, lon2 = b.latitude_deg, b.longitude_deg
    else:
        lat2, lon2 = b

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    sin_dphi = math.sin(dphi / 2.0)
    sin_dlambda = math.sin(dlambda / 2.0)

    h = sin_dphi * sin_dphi + math.cos(phi1) * math.cos(phi2) * sin_dlambda * sin_dlambda
    # Numerical safety: h should be in [0, 1]
    h = min(1.0, max(0.0, h))

    return 2.0 * earth_radius_m * math.asin(math.sqrt(h))


def _mean(values: Sequence[float]) -> float:
    return 0.0 if not values else sum(values) / float(len(values))


def _rmse(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / float(len(values)))


@dataclass(frozen=True, slots=True)
class GPSAccuracyReport:
    """Summary statistics for GPS accuracy vs ground truth."""

    n_matches: int
    mean_error_m: float
    rmse_error_m: float
    max_error_m: float

    # Often useful in UI/debugging.
    errors_m: Tuple[float, ...] = ()


class GPSReceiver:
    """In-memory GPS receiver.

    Responsibilities
    ----------------
    - Log fixes as they arrive.
    - Provide route representations for visualization.
    - Compute horizontal accuracy vs ground truth fixes.

    Notes
    -----
    This module does *not* parse NMEA strings and does *not* depend on
    external GPS hardware. It’s a deterministic, simulation-friendly
    computation layer.
    """

    def __init__(self, *, max_samples: int = 50_000) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self._max_samples = max_samples
        self._fixes: List[GPSFix] = []

    def log_position(self, fix: GPSFix) -> None:
        """Add a new GPS fix to the log."""

        if len(self._fixes) >= self._max_samples:
            # Drop oldest to preserve bounded memory.
            self._fixes.pop(0)
        self._fixes.append(fix)

    @property
    def fixes(self) -> Tuple[GPSFix, ...]:
        return tuple(self._fixes)

    def latest_fix(self) -> Optional[GPSFix]:
        return self._fixes[-1] if self._fixes else None

    def route_points(
        self,
        *,
        order: Literal["insertion", "timestamp"] = "timestamp",
    ) -> Tuple[GPSFix, ...]:
        """Return the logged points for route visualization."""

        if not self._fixes:
            return ()
        if order == "insertion":
            return tuple(self._fixes)
        if order == "timestamp":
            return tuple(sorted(self._fixes, key=lambda f: f.timestamp_s))
        raise ValueError("order must be 'insertion' or 'timestamp'")

    def route_coordinates(
        self,
        *,
        order: Literal["insertion", "timestamp"] = "timestamp",
        as_lon_lat: bool = True,
    ) -> List[Tuple[float, float]]:
        """Return route coordinates.

        By default returns coordinates in GeoJSON order: ``(lon, lat)``.
        Set ``as_lon_lat=False`` to get ``(lat, lon)``.
        """

        pts = self.route_points(order=order)
        if as_lon_lat:
            return [(p.longitude_deg, p.latitude_deg) for p in pts]
        return [(p.latitude_deg, p.longitude_deg) for p in pts]

    def route_length_m(
        self,
        *,
        order: Literal["insertion", "timestamp"] = "timestamp",
    ) -> float:
        """Total path length along the logged route."""

        pts = self.route_points(order=order)
        if len(pts) < 2:
            return 0.0
        total = 0.0
        for prev, cur in zip(pts, pts[1:]):
            total += haversine_distance_m(prev, cur)
        return total

    def route_geojson(self, *, order: Literal["insertion", "timestamp"] = "timestamp") -> dict:
        """Return a lightweight GeoJSON representation of the route.

        Shape
        -----
        {
          "type": "FeatureCollection",
          "features": [
            {"type":"Feature", "geometry": {"type":"Point", "coordinates": [lon,lat]}, ...},
            ...,
            {"type":"Feature", "properties": {"kind":"route"}, "geometry": {"type":"LineString", "coordinates": [[lon,lat],...]}}
          ]
        }
        """

        pts = self.route_points(order=order)
        if not pts:
            return {"type": "FeatureCollection", "features": []}

        point_features = [
            {
                "type": "Feature",
                "properties": {
                    "kind": "fix",
                    "timestamp_s": p.timestamp_s,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [p.longitude_deg, p.latitude_deg],
                },
            }
            for p in pts
        ]

        line_feature = {
            "type": "Feature",
            "properties": {"kind": "route"},
            "geometry": {
                "type": "LineString",
                "coordinates": [[p.longitude_deg, p.latitude_deg] for p in pts],
            },
        }

        return {
            "type": "FeatureCollection",
            "features": [*point_features, line_feature],
        }

    def accuracy_report(
        self,
        ground_truth: Sequence[GPSFix],
        *,
        match_mode: Literal["nearest_timestamp", "by_index"] = "nearest_timestamp",
        max_time_delta_s: float = 2.0,
    ) -> GPSAccuracyReport:
        """Compute horizontal accuracy vs ground truth.

        Parameters
        ----------
        ground_truth:
            The reference set of GPS fixes.
        match_mode:
            - ``nearest_timestamp``: for each receiver fix, match the
              ground-truth fix with the closest timestamp (within
              ``max_time_delta_s``).
            - ``by_index``: compare receiver and ground truth in order.

        Returns
        -------
        GPSAccuracyReport
            Includes mean, RMSE, max and the list of matched error samples.
        """

        if not ground_truth:
            return GPSAccuracyReport(
                n_matches=0,
                mean_error_m=0.0,
                rmse_error_m=0.0,
                max_error_m=0.0,
                errors_m=(),
            )

        recv = list(self.route_points(order="timestamp"))
        truth = list(sorted(ground_truth, key=lambda f: f.timestamp_s))

        if match_mode == "by_index":
            n = min(len(recv), len(truth))
            errors: List[float] = []
            for i in range(n):
                errors.append(haversine_distance_m(recv[i], truth[i]))
        elif match_mode == "nearest_timestamp":
            if not recv:
                errors = []
            else:
                errors = []
                for r in recv:
                    # Find nearest truth fix by timestamp.
                    best: Optional[GPSFix] = None
                    best_dt = float("inf")
                    for t in truth:
                        dt = abs(t.timestamp_s - r.timestamp_s)
                        if dt < best_dt:
                            best_dt = dt
                            best = t
                    if best is not None and best_dt <= max_time_delta_s:
                        errors.append(haversine_distance_m(r, best))
        else:
            raise ValueError("match_mode must be 'nearest_timestamp' or 'by_index'")

        n_matches = len(errors)
        mean_err = _mean(errors)
        rmse_err = _rmse(errors)
        max_err = max(errors) if errors else 0.0

        return GPSAccuracyReport(
            n_matches=n_matches,
            mean_error_m=mean_err,
            rmse_error_m=rmse_err,
            max_error_m=max_err,
            errors_m=tuple(errors),
        )


__all__ = [
    "GPSFix",
    "GPSAccuracyReport",
    "GPSReceiver",
    "haversine_distance_m",
]
