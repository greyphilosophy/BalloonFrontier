"""Shared multi-balloon support for launch requests and menu-driven UIs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import discord

from balloon_frontier.launch_result import LaunchRequest


MIN_BALLOON_COUNT = 1
MAX_BALLOON_COUNT = 100


@dataclass(frozen=True, slots=True)
class ClusteredLaunchRequest(LaunchRequest):
    """A launch request whose identical envelopes are flown as a cluster."""

    balloon_count: int = 1

    def __post_init__(self) -> None:
        # ``dataclass(slots=True)`` creates a replacement class object, which can
        # invalidate zero-argument ``super()`` closures. Dispatch explicitly to
        # the base dataclass so validation remains reliable on all supported
        # Python versions.
        LaunchRequest.__post_init__(self)
        if isinstance(self.balloon_count, bool) or not isinstance(self.balloon_count, int):
            raise ValueError("balloon_count must be an integer")
        if not MIN_BALLOON_COUNT <= self.balloon_count <= MAX_BALLOON_COUNT:
            raise ValueError(
                f"balloon_count must be between {MIN_BALLOON_COUNT} and {MAX_BALLOON_COUNT}"
            )

    @property
    def gas_mass_kg(self) -> float:
        """Return total gas mass for the complete cluster.

        Automatic presets are calculated per envelope and multiplied by quantity.
        Manual gas mass remains an explicit total chosen by the player.
        """

        base_property = LaunchRequest.gas_mass_kg
        assert base_property.fget is not None
        base_mass = base_property.fget(self)
        if self.fill_mode.value == "manual":
            return base_mass
        return base_mass * self.balloon_count

    def to_simulation_state(self):
        """Represent the cluster as one equivalent envelope in the physics engine."""

        state = LaunchRequest.to_simulation_state(self)
        envelope = replace(
            state.envelope,
            max_volume_m3=state.envelope.max_volume_m3 * self.balloon_count,
            mass_kg=state.envelope.mass_kg * self.balloon_count,
        )
        return replace(state, envelope=envelope, gas_mass_kg=self.gas_mass_kg)


class BalloonClusterFlightService:
    """Convert ordinary UI requests into quantity-aware launch requests.

    Unknown attributes are delegated to the wrapped service so this adapter remains
    transparent to existing callers that inspect session metadata such as ``mode``
    or ``on_finished``.
    """

    def __init__(self, service: Any, balloon_count: int = 1) -> None:
        self.service = service
        self.balloon_count = balloon_count

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)

    def run(self, request: LaunchRequest):
        clustered = ClusteredLaunchRequest(
            gas_id=request.gas_id,
            envelope_id=request.envelope_id,
            payload_ids=request.payload_ids,
            launch_site_id=request.launch_site_id,
            fill_mode=request.fill_mode,
            manual_gas_mass_kg=request.manual_gas_mass_kg,
            player_id=request.player_id,
            balloon_size=request.balloon_size,
            gas_temperature_delta_k=request.gas_temperature_delta_k,
            balloon_count=self.balloon_count,
        )
        return self.service.run(clustered)


class _BalloonCountButton(discord.ui.Button):
    def __init__(self, parent: "BalloonClusterConfiguratorMixin", delta: int) -> None:
        label = "＋ Balloon" if delta > 0 else "− Balloon"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            custom_id=f"cfg_balloon_count_{'plus' if delta > 0 else 'minus'}",
        )
        self.parent_view = parent
        self.delta = delta

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.parent_view._change_balloon_count(interaction, self.delta)


class BalloonClusterConfiguratorMixin:
    """Add envelope quantity controls without creating a separate configurator."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state.setdefault("balloon_count", 1)
        self._sync_balloon_count()
        self.build_buttons()

    def _sync_balloon_count(self) -> None:
        if hasattr(self._service, "balloon_count"):
            self._service.balloon_count = self.state["balloon_count"]

    async def _change_balloon_count(self, interaction, delta: int) -> None:
        current = int(self.state.get("balloon_count", 1))
        self.state["balloon_count"] = min(
            MAX_BALLOON_COUNT,
            max(MIN_BALLOON_COUNT, current + delta),
        )
        self._sync_balloon_count()
        self.state["gas_mass"] = self._compute_gas_mass()
        self.build_buttons()
        await self._send_step(interaction)

    def _compute_gas_mass(self):
        per_balloon = super()._compute_gas_mass()
        if self.state.get("fill_mode") == "manual":
            return per_balloon
        return round(per_balloon * int(self.state.get("balloon_count", 1)), 3)

    def _step_content(self) -> str:
        content = super()._step_content()
        if self._current_step in (1, 2, 5):
            count = int(self.state.get("balloon_count", 1))
            content += f"\n\n🎈 Balloon quantity: **×{count}**"
        return content

    def _build_config_text(self) -> str:
        text = super()._build_config_text()
        count = int(self.state.get("balloon_count", 1))
        if count > 1:
            text = text.replace("Envelope: ", f"Envelope cluster (×{count}): ", 1)
        return text

    def build_buttons(self):
        super().build_buttons()
        if self._current_step == 2:
            self.add_item(_BalloonCountButton(self, -1))
            self.add_item(_BalloonCountButton(self, 1))
