"""Balloon Frontier — Valve Variants

Implements different pressure release valve options that players can
choose when configuring their balloon. Each variant trades mass for
burst stretch ratio.

Reference: GDD Sections 8.4, 14.1.
"""

from dataclasses import dataclass
from typing import List

@dataclass
class Valve:
    """A pressure release valve variant."""
    id: str
    name: str
    mass_kg: float
    burst_stretch_ratio: float  # How much the envelope stretches before burst
    cost: int = 0
    description: str = ""

# Valve variants
VALVES = [
    Valve("light", "Lightweight Valve", 0.3, 2.0, 300,
          "Minimal weight, but envelope bursts at 2.0x stretch"),
    Valve("standard", "Standard Valve", 0.5, 2.5, 400,
          "Balanced weight and stretch — most popular choice"),
    Valve("heavy", "Heavy-Duty Valve", 1.0, 3.0, 600,
          "Heavier but allows 3.0x stretch before burst"),
]


def get_valve(valve_id: str) -> Valve:
    """Get a valve by ID."""
    for v in VALVES:
        if v.id == valve_id:
            return v
    return VALVES[1]  # Default: standard


def list_valves() -> List[Valve]:
    """List all valve variants."""
    return list(VALVES)


def valve_tradeoff_description(valve_id: str) -> str:
    """Describe the mass vs stretch trade-off for a valve."""
    v = get_valve(valve_id)
    if v.mass_kg < 0.5:
        trade = "lighter but less stretch"
    else:
        trade = "heavier but more stretch"
    return f"{v.name}: {v.mass_kg}kg mass, {v.burst_stretch_ratio}x burst ratio — {trade}"
