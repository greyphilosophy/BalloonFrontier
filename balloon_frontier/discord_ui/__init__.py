"""Balloon Frontier — Discord UI package.

Exports the configurator wizard, Discord UI components, launch handling,
and result rendering used by the root ``discord_bot.py`` bootstrap layer.
"""

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
from balloon_frontier.discord_ui.modals import _ManualGasMassButton, _ManualGasMassModal
from balloon_frontier.discord_ui.launch_handler import run_simulation
from balloon_frontier.discord_ui.result_renderer import format_score_breakdown, make_result_embed

__all__ = [
    # Configurator / game data
    "_Step",
    "BalloonConfigurator",
    "GAS_OPTIONS",
    "ENVELOPE_OPTIONS",
    "PAYLOAD_OPTIONS",
    "SITE_OPTIONS",
    "FILL_MODES",
    # Views (buttons)
    "_OptionButton",
    "_BackButton",
    "_NextButton",
    # Modals
    "_ManualGasMassButton",
    "_ManualGasMassModal",
    # Launch
    "run_simulation",
    # Rendering
    "format_score_breakdown",
    "make_result_embed",
]
