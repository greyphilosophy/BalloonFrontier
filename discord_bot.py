"""Balloon Frontier Discord transport.

Discord is a menu-driven way to access the same game flow as the CLI. Any
ordinary message opens the player's current game view: idle players receive the
game-mode menu, while active players receive a fresh copy of the wizard at the
step where they left off. ``/play`` remains the explicit reset path.
``/launch`` is retained only as an undocumented compatibility alias.
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

# ``_engaged_players`` remains for compatibility with existing callers/tests.
# ``_active_views`` is the source of truth for resumable Discord UI state.
_engaged_players: set[str] = set()
_active_views: dict[str, discord.ui.View] = {}


def _channel_kind(channel) -> str:
    return "dm" if isinstance(channel, discord.DMChannel) else "guild"


def _remember_active_view(player_id: str | int, view: discord.ui.View) -> None:
    """Record the live view whose mutable state represents a player's session."""
    key = str(player_id)
    _engaged_players.add(key)
    _active_views[key] = view


def _finish_session(player_id: str | int) -> None:
    """Forget a completed/resettable session."""
    key = str(player_id)
    _engaged_players.discard(key)
    _active_views.pop(key, None)


def _resume_content(view: discord.ui.View) -> str:
    """Render the current content for a remembered view."""
    content = getattr(view, "_resume_content", None)
    if callable(content):
        return str(content())
    if isinstance(content, str):
        return content

    step_content = getattr(view, "_step_content", None)
    if callable(step_content):
        return str(step_content())

    if isinstance(view, GameModeView):
        return game_mode_prompt()

    return "🎈 **Balloon Frontier**\n\nYour current game is ready."


async def resume_game(destination, *, player_id: str | int):
    """Send a fresh message containing the player's current live view."""
    key = str(player_id)
    view = _active_views.get(key)
    if view is None:
        return None

    msg = await destination.send(_resume_content(view), view=view)
    if hasattr(view, "_msg"):
        view._msg = msg
    return msg


async def send_game_menu(destination, *, player_id: str | int, channel_kind: str, reset: bool = False):
    """Start a new game menu or resume the player's current Discord view."""
    from balloon_frontier.flight_service import flight_service

    key = str(player_id)
    if not reset and key in _active_views:
        return await resume_game(destination, player_id=key)

    if reset:
        old_view = _active_views.get(key)
        if old_view is not None:
            old_view.stop()
        _finish_session(key)

    on_view_changed = lambda view: _remember_active_view(key, view)
    view = GameModeView(
        player_id=key,
        channel_kind=channel_kind,
        service=flight_service,
        on_finished=lambda: _finish_session(key),
        on_view_changed=on_view_changed,
    )
    _remember_active_view(key, view)
    msg = await destination.send(game_mode_prompt(), view=view)
    view._msg = msg
    return msg


@bot.event
async def on_ready():
    logger.info("Balloon Frontier online as %s (%s)", bot.user, bot.user.id)


@bot.event
async def on_message(message):
    """Start idle players and resume active players from any ordinary message."""
    if getattr(message.author, "bot", False):
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
    """Explicitly restart the menu-driven game from the mode menu."""
    await send_game_menu(
        ctx,
        player_id=ctx.author.id if ctx.author else "anonymous",
        channel_kind=_channel_kind(ctx.channel),
        reset=True,
    )


@bot.command(name="launch", hidden=True)
async def cmd_launch_compat(ctx):
    """Deprecated compatibility alias for older clients; use /play."""
    await cmd_play(ctx)


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
        "Send any message to begin or resume your current game.\n\n"
        "• `/play` — Restart from the game-mode menu\n"
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
