"""Balloon Frontier — Discord Bot Bootstrap

This file is now a thin composition layer. All Discord UI logic lives in
the ``balloon_frontier.discord_ui`` package and is re-exported here so
that existing imports from ``discord_bot`` remain valid.
"""

import logging
import os

import discord
from discord.ext import commands

from balloon_frontier.game_modes import select_game_mode
from balloon_frontier.session_adapters import SessionAwareFlightService

from balloon_frontier.discord_ui.configurator import (
    _Step,
    BalloonConfigurator,
    GAS_OPTIONS,
    ENVELOPE_OPTIONS,
    PAYLOAD_OPTIONS,
    SITE_OPTIONS,
    FILL_MODES,
)
from balloon_frontier.discord_ui.views import _OptionButton, _BackButton, _NextButton
from balloon_frontier.discord_ui.modals import (
    _ManualGasMassButton,
    _ManualGasMassModal,
)
from balloon_frontier.discord_ui.launch_handler import run_simulation
from balloon_frontier.discord_ui.result_renderer import format_score_breakdown, make_result_embed
from balloon_frontier.discord_ui.modals import _LaunchButton  # noqa: F401
from balloon_frontier.narrative_result import format_discord_results  # noqa: F401

logger = logging.getLogger(__name__)

intents = discord.Intents(message_content=True, guilds=True, dm_messages=True)
bot = commands.Bot(command_prefix="/", intents=intents)
bot.remove_command("help")


@bot.event
async def on_ready():
    logger.info(f"Balloon Frontier online as {bot.user} ({bot.user.id})")


@bot.event
async def on_message(message):
    """Process messages so prefix commands (/help, /physics, /launch) fire."""
    await bot.process_commands(message)


@bot.command(name="launch")
async def cmd_launch(ctx, mode: str = "free_play"):
    """Open the balloon configurator wizard for the requested game mode."""
    from balloon_frontier.flight_service import flight_service

    try:
        selected_mode = select_game_mode(mode)
    except ValueError:
        await ctx.send(
            "❌ Unknown mode. Use `tutorial`, `story`, `scenario`, or `free_play`."
        )
        return

    channel_kind = "dm" if getattr(ctx, "guild", None) is None else "guild"
    service = SessionAwareFlightService(
        flight_service,
        selected_mode,
        ui="discord",
        channel_kind=channel_kind,
    )
    view = BalloonConfigurator(service=service)
    view.session_mode = selected_mode
    content = (
        f"🎮 **Mode: {selected_mode.label}** — {selected_mode.description}\n\n"
        + view._build_config_text()
    )
    msg = await ctx.send(content, view=view)
    view._msg = msg


@bot.command(name="physics")
async def cmd_physics(ctx):
    """Show the physics model equations."""
    content = (
        "⚙️ **Physics Model**\n\n"
        "• ρ = P / (R_air × T)\n"
        "• F_buoy = ρ_air × g × V\n"
        "• F_drag = 0.5 × ρ × v² × C_d × A\n"
        "• PV = nRT\n"
        "• Fixed-step Euler: Δt = 0.5s"
    )
    await ctx.send(content)


@bot.command(name="help")
async def cmd_help(ctx):
    """Show help text."""
    content = (
        "🎈 **Balloon Frontier**\n\n"
        "• `/launch [mode]` — Open the configurator in tutorial, story, scenario, or free_play mode\n"
        "• `/physics` — View the physics equations\n"
        "• `/help` — This message"
    )
    await ctx.send(content)


@bot.command(name="profile")
async def cmd_profile(ctx):
    """Show player status and equipment unlock progress."""
    from balloon_frontier.progression import (
        ENVELOPES as PROGRESSION_ENVELOPES,
        PAYLOAD_UNLOCKS,
        SITES,
        PlayerRegistry,
    )
    try:
        user_id = str(ctx.author.id) if ctx.author else "anonymous"
        player = PlayerRegistry.get_or_create(user_id)
    except Exception:
        await ctx.send("⚠️ Unable to load player profile.")
        return

    lines = [
        f"⚡ **{user_id}'s Profile**",
        f"  Reputation: {player.reputation}",
        f"  Budget: ${player.budget}",
        f"  Flights: {player.total_flights} ({player.successful_flights} successful)",
        "",
        "=== ENVELOPES ===",
    ]

    for env in PROGRESSION_ENVELOPES:
        unlocked = player.is_envelope_unlocked(env.id)
        mark = "✅" if unlocked else "🔒"
        detail = ""
        if not unlocked:
            rep_ok = player.reputation >= env.min_reputation
            budget_ok = player.budget >= env.cost
            if rep_ok and budget_ok:
                pass
            elif rep_ok:
                detail = f"({env.cost - player.budget} more credits needed)"
            elif budget_ok:
                detail = f"({env.min_reputation - player.reputation} more reputation needed)"
            else:
                rep_need = env.min_reputation - player.reputation
                cost_need = env.cost - player.budget
                r_pct = (player.reputation / env.min_reputation * 100) if env.min_reputation > 0 else 100
                c_pct = (player.budget / env.cost * 100) if env.cost > 0 else 100
                closest = "reputation" if r_pct < c_pct else "credits"
                if closest == "reputation":
                    detail = f"({rep_need} rep closer, {cost_need} cr away)"
                else:
                    detail = f"({cost_need} cr closer, {rep_need} rep away)"
        lines.append(f"{mark} {env.name}{(' ' + detail) if detail else ''}")

    lines.append("")
    lines.append("=== PAYLOADS ===")
    advanced_unseen = False
    for p in PAYLOAD_UNLOCKS:
        unlocked = player.is_payload_unlocked(p.id)
        mark = "✅" if unlocked else "🔒"
        if unlocked:
            continue
        if p.min_reputation > 0 or p.cost > 0:
            advanced_unseen = True
            rep_needed = max(0, p.min_reputation - player.reputation)
            cr_needed = max(0, p.cost - player.budget)
            lines.append(f"{mark} {p.name} — {p.description}")
            if rep_needed == 0:
                lines.append(f"   Needs {cr_needed} more credits")
            elif cr_needed == 0:
                lines.append(f"   Needs {rep_needed} more reputation")
            else:
                lines.append(f"   Needs {min(rep_needed, cr_needed)} of either rep/credits to progress")
    if not advanced_unseen:
        lines.append("✅ All payload types unlocked!")

    lines.append("")
    lines.append("=== SITES ===")
    for s in SITES:
        unlocked = player.is_site_unlocked(s.id)
        mark = "✅" if unlocked else "🔒"
        detail = ""
        if not unlocked:
            rep_needed = max(0, s.min_reputation - player.reputation)
            cr_needed = max(0, s.cost - player.budget)
            if rep_needed == 0:
                detail = f"({cr_needed} more credits)"
            elif cr_needed == 0:
                detail = f"({rep_needed} more reputation)"
            else:
                detail = f"{rep_needed}/{cr_needed}"
        lines.append(f"{mark} {s.name}{(' ' + detail) if detail else ''}")

    content = "\n".join(lines)
    if len(content) > 2000:
        content = content[:1997] + "\n\n...(truncated)"
    await ctx.send(content)


def run_bot():
    """Start the Discord bot."""
    token = os.environ.get("DISCORD_BF_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
