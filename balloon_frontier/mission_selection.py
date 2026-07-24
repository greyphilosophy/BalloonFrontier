"""Mission selection (GDD §14.2 / §17).

This module selects mission IDs from the mission pool for each flight.

Acceptance covered:
- Select N missions per flight (N clamped to 1–3 and derived from payload count).
- No duplicates within a single flight.
- Deterministic selection with an explicit seed.
- Store chosen mission IDs (returned as a list and usable as flight/session state).
- Graceful fallback when selection fails or the mission pool is empty.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import List, Optional

from .missions import MISSIONS, list_missions, load_mission_directory


DEFAULT_MISSION_COUNT_RANGE = (1, 3)


def ensure_missions_loaded(mission_dir: Optional[str] = None) -> None:
    """Ensure the global mission registry is populated.

    The Discord bot/game runtime historically didn't load missions automatically.
    For selection, we lazily load from data/missions/ the first time needed.
    """

    if MISSIONS:
        return

    if mission_dir is None:
        # balloon_frontier/mission_selection.py -> ../data/missions
        here = os.path.dirname(os.path.abspath(__file__))
        mission_dir = os.path.join(os.path.dirname(here), "data", "missions")

    load_mission_directory(mission_dir)


def choose_mission_count(payload_count: int) -> int:
    """Decide how many missions to assign to a flight.

    Current game flow allows selecting up to 3 payloads, so we map payload_count
    to 1–3 missions.
    """

    if payload_count is None:
        payload_count = 0

    n = int(payload_count)
    n = max(DEFAULT_MISSION_COUNT_RANGE[0], min(DEFAULT_MISSION_COUNT_RANGE[1], n))
    if n < 1:
        n = DEFAULT_MISSION_COUNT_RANGE[0]
    return n


def fallback_mission_ids() -> List[str]:
    """Safe default mission list.

    If there are no missions, return an empty list.
    Otherwise, return the first mission by deterministic (sorted) ID.
    """

    ids = sorted(MISSIONS.keys())
    if not ids:
        return []
    return [ids[0]]


def _stable_seed_from_string(s: str) -> int:
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    # take 32 bits
    return int.from_bytes(digest[:4], "big", signed=False)


def select_missions(
    mission_count: int,
    seed: Optional[int] = None,
    mission_dir: Optional[str] = None,
    selected_payloads: Optional[List[str]] = None,
    launch_site: Optional[str] = None,
) -> List[str]:
    """Select mission IDs from the mission pool.

    Args:
        mission_count: Desired number of missions for the flight. Clamped to 1–3
            and to the pool size.
        seed: Optional deterministic seed.
        mission_dir: Optional mission directory override for lazy loading.
        selected_payloads: Payload keys the player selected (e.g. ["camera", "battery"]).
            Only missions whose required_payloads are a subset of these are eligible.
        launch_site: The site the player is launching from (e.g. "field", "mountain", "rooftop").
            Only missions whose launch_site is None or matches this site are eligible.

    Returns:
        A list of selected mission IDs (unique, length <= mission_count).
    """

    try:
        ensure_missions_loaded(mission_dir)

        pool_ids = sorted(MISSIONS.keys())
        if not pool_ids:
            return fallback_mission_ids()

        # Filter by launch_site and required_payloads compatibility.
        eligible_ids = []
        for mid in pool_ids:
            m = MISSIONS[mid]
            # Site check: None means any site; otherwise must match.
            if m.launch_site is not None and m.launch_site != launch_site:
                continue
            # Payload check: all required_payloads must be subset of selected_payloads.
            req = m.required_payloads if m.required_payloads else []
            if selected_payloads and not set(req).issubset(set(selected_payloads)):
                continue
            eligible_ids.append(mid)

        # If filtering eliminated all missions, fall back to full pool.
        if not eligible_ids:
            eligible_ids = pool_ids

        n_raw = int(mission_count)
        if n_raw < 1:
            return fallback_mission_ids()
        n = max(DEFAULT_MISSION_COUNT_RANGE[0], min(DEFAULT_MISSION_COUNT_RANGE[1], n_raw))
        n = min(n, len(eligible_ids))

        if seed is None:
            rng = random.Random()
        else:
            rng = random.Random(int(seed))

        # random.sample guarantees uniqueness.
        return rng.sample(eligible_ids, n)

    except Exception:
        # Any selection error should not crash flight start.
        return fallback_mission_ids()


def seed_from_game_state(
    gas: str,
    envelope: str,
    payloads: List[str],
    site: str,
) -> int:
    """Helper to create a deterministic mission seed from player selections."""

    payload_part = ",".join(payloads)
    return _stable_seed_from_string(f"{gas}|{envelope}|{payload_part}|{site}")


def assign_missions_to_flight(
    payload_count: int,
    seed: Optional[int] = None,
    mission_count: Optional[int] = None,
    selected_payloads: Optional[List[str]] = None,
    launch_site: Optional[str] = None,
) -> dict:
    """Convenience wrapper returning a flight/session-friendly mission assignment.

    Filters the mission pool by compatibility (launch_site and required_payloads)
    so players cannot receive missions they cannot perform.
    """
    if mission_count is None:
        mission_count = choose_mission_count(payload_count)

    mission_ids = select_missions(
        mission_count=mission_count,
        seed=seed,
        selected_payloads=selected_payloads,
        launch_site=launch_site,
    )

    return {
        "mission_count": len(mission_ids),
        "missions": mission_ids,
        "seed": seed,
    }
