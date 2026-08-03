"""Keep the restored tutorial wizard state aligned with the effective request."""

from __future__ import annotations

from functools import wraps


def install_tutorial_state_guard() -> None:
    from balloon_frontier.discord_ui import launch_handler

    current = launch_handler.run_launch
    if getattr(current, "_balloon_frontier_effective_state", False):
        return

    @wraps(current)
    async def run(configurator, interaction, service):
        result = await current(configurator, interaction, service)

        from balloon_frontier.game_modes import GameMode
        from balloon_frontier.launch_result import FillMode, LaunchRequest
        from balloon_frontier.tutorial_catalog import TUTORIAL_ENVELOPE_ID

        context = getattr(configurator, "_game_entry_context", None) or {}
        state = configurator.state
        if (
            context.get("mode") is GameMode.TUTORIAL
            and state.get("envelope") == "mylar"
        ):
            effective = LaunchRequest(
                gas_id=state["gas"],
                envelope_id=TUTORIAL_ENVELOPE_ID,
                payload_ids=tuple(state.get("payloads") or ()),
                launch_site_id=state["site"],
                fill_mode=FillMode(state.get("fill_mode", "auto")),
                manual_gas_mass_kg=state.get("manual_gas_mass"),
                player_id=str(interaction.user.id),
                balloon_size=None,
            )
            state["gas_mass"] = effective.gas_mass_kg
        return result

    run._balloon_frontier_effective_state = True
    launch_handler.run_launch = run
