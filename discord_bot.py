"""Balloon Frontier — Discord Bot Bootstrap

This file is now a thin composition layer. All Discord UI logic lives in
the ``balloon_frontier.discord_ui`` package and is re-exported here so
that existing imports from ``discord_bot`` remain valid.

Responsibilities:
- Bot construction (discord.ext.commands.Bot)
- Command registration (/launch, /physics, /help, /profile)
- Startup/shutdown (run_bot)
- Top-level error handling
"""

import asyncio
import logging
import os
from typing import List, Optional

import discord
from discord.ext import commands

from balloon_frontier.flight_service import FlightServiceError

# ─── Re-export everything the tests expect ────────────────────────────

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

# Compatibility: _LaunchButton was previously in discord_bot.py;
# tests reference it.  Re-export from modals where it lives now.
from balloon_frontier.discord_ui.modals import _LaunchButton  # noqa: F401
# Compatibility: format_discord_results was previously in discord_bot.py
from balloon_frontier.narrative_result import format_discord_results  # noqa: F401

logger = logging.getLogger(__name__)

# ─── Bot ──────────────────────────────────────────────────────────────

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


# ─── Commands ─────────────────────────────────────────────────────────

@bot.command(name="launch")
async def cmd_launch(ctx):
    """Open the balloon configurator wizard."""
    view = BalloonConfigurator()
    content = view._build_config_text()
    msg = await ctx.send(content, view=view)
    view._msg = msg


@bot.command(name="physics")
async def cmd_physics(ctx):
    """Show the physics model equations."""
    content = (
        "\u2699\ufe0f **Physics Model**\n\n"
        "\u2022 \u03c1 = P / (R_air \u00d7 T)\n"
        "\u2022 F_buoy = \u03c1_air \u00d7 g \u00d7 V\n"
        "\u2022 F_drag = 0.5 \u00d7 \u03c1 \u00d7 v\u00b2 \u00d7 C_d \u00d7 A\n"
        "\u2022 PV = nRT\n"
        "\u2022 Fixed-step Euler: \u0394t = 0.5s"
    )
    await ctx.send(content)


@bot.command(name="help")
async def cmd_help(ctx):
    """Show help text."""
    content = (
        "\U0001f388 **Balloon Frontier**\n\n"
        "\u2022 `/launch` \u2014 Open the balloon configurator\n"
        "\u2022 `/physics` \u2014 View the physics equations\n"
        "\u2022 `/help` \u2014 This message"
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
        await ctx.send("\\u26a0\\ufe0f Unable to load player profile.")
        return

    lines = [
        f"\u26a1 **{user_id}'s Profile**",
        f"  Reputation: {player.reputation}",
        f"  Budget: ${player.budget}",
        f"  Flights: {player.total_flights} ({player.successful_flights} successful)",
        "",
        "=== ENVELOPES ===",
    ]

    for env in PROGRESSION_ENVELOPES:
        unlocked = player.is_envelope_unlocked(env.id)
        mark = "\u2705" if unlocked else "\U0001f512"
        detail = ""
        if not unlocked:
            rep_ok = player.reputation >= env.min_reputation
            budget_ok = player.budget >= env.cost
            if rep_ok and budget_ok:
                pass  # should be unlocked \u2014 race condition; treat as unlocked
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
        mark = "\u2705" if unlocked else "\U0001f512"
        if unlocked:
            continue  # Hide already-unlocked basic payloads
        # Show locked advanced payloads only
        if p.min_reputation > 0 or p.cost > 0:
            advanced_unseen = True
            rep_needed = max(0, p.min_reputation - player.reputation)
            cr_needed = max(0, p.cost - player.budget)
            lines.append(f"{mark} {p.name} \u2014 {p.description}")
            if rep_needed == 0:
                lines.append(f"   Needs {cr_needed} more credits")
            elif cr_needed == 0:
                lines.append(f"   Needs {rep_needed} more reputation")
            else:
                lines.append(f"   Needs {min(rep_needed, cr_needed)} of either rep/credits to progress")
    if not advanced_unseen:
        lines.append("\u2705 All payload types unlocked!")

    lines.append("")
    lines.append("=== SITES ===")
    for s in SITES:
        unlocked = player.is_site_unlocked(s.id)
        mark = "\u2705" if unlocked else "\U0001f512"
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


# ─── Entry point ─────────────────────────────────────────────────────

def run_bot():
    """Start the Discord bot."""
    token = os.environ.get("DISCORD_BF_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
