"""Balloon Frontier Discord transport.

Discord is a menu-driven way to access the same game flow as the CLI. Any
ordinary message from an idle player opens the game-mode menu; subsequent play
uses buttons, menus, and modals. ``/play`` remains an optional explicit reset.
"""

import logging
import os

import discord
from discord.ext import commands

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
    _LaunchButton,
)
from balloon_frontier.discord_ui.launch_handler import run_simulation
from balloon_frontier.discord_ui.result_renderer import format_score_breakdown, make_result_embed
from balloon_frontier.discord_ui.game_menu import GameModeView, game_mode_prompt
from balloon_frontier.narrative_result import format_discord_results

logger = logging.getLogger(__name__)

intents = discord.Intents(message_content=True, guilds=True, dm_messages=True)
bot = commands.Bot(command_prefix="/", intents=intents)
bot.remove_command("help")

_engaged_players: set[str] = set()


def _channel_kind(channel) -> str:
    return "dm" if isinstance(channel, discord.DMChannel) else "guild"


async def send_game_menu(destination, *, player_id: str | int, channel_kind: str, reset: bool = False):
    """Show the common game-mode menu to an idle player."""
    from balloon_frontier.flight_service import flight_service

    key = str(player_id)
    if key in _engaged_players and not reset:
        return None
    _engaged_players.add(key)
    view = GameModeView(
        player_id=key,
        channel_kind=channel_kind,
        service=flight_service,
        on_finished=lambda: _engaged_players.discard(key),
    )
    msg = await destination.send(game_mode_prompt(), view=view)
    view._msg = msg
    return msg


@bot.event
async def on_ready():
    logger.info("Balloon Frontier online as %s (%s)", bot.user, bot.user.id)


@bot.event
async def on_message(message):
    """Treat any ordinary first message as a request to start playing."""
    if message.author.bot:
        return

    context = await bot.get_context(message)
    if context.valid:
        await bot.invoke(context)
        return

    await send_game_menu(
        message.channel,
        player_id=message.author.id,
        channel_kind=_channel_kind(message.channel),
    )


@bot.command(name="play")
async def cmd_play(ctx):
    """Explicitly open or restart the menu-driven game."""
    await send_game_menu(
        ctx,
        player_id=ctx.author.id if ctx.author else "anonymous",
        channel_kind=_channel_kind(ctx.channel),
        reset=True,
    )


@bot.command(name="physics")
async def cmd_physics(ctx):
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
    content = (
        "🎈 **Balloon Frontier**\n\n"
        "Send any message to begin. Choose a mode, then play entirely through menus and buttons.\n\n"
        "• `/play` — Open or restart the game menu\n"
        "• `/physics` — View the physics equations\n"
        "• `/profile` — View progression\n"
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
        lines.append(f"{mark} {env.name}")

    lines.extend(["", "=== PAYLOADS ==="])
    locked_payloads = [p for p in PAYLOAD_UNLOCKS if not player.is_payload_unlocked(p.id)]
    if locked_payloads:
        lines.extend(f"🔒 {p.name} — {p.description}" for p in locked_payloads)
    else:
        lines.append("✅ All payload types unlocked!")

    lines.extend(["", "=== SITES ==="])
    for site in SITES:
        mark = "✅" if player.is_site_unlocked(site.id) else "🔒"
        lines.append(f"{mark} {site.name}")

    content = "\n".join(lines)
    if len(content) > 2000:
        content = content[:1997] + "..."
    await ctx.send(content)


def run_bot():
    token = os.environ.get("DISCORD_BF_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
