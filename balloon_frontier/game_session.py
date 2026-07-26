"""UI-agnostic state model for a single Balloon Frontier play session."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

from balloon_frontier.game_modes import GameMode, select_game_mode


class SessionState(str, Enum):
    """Lifecycle states for a game session."""

    CONFIGURING = "configuring"
    READY = "ready"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = {SessionState.COMPLETED, SessionState.CANCELLED}


def _freeze(value: Any) -> Any:
    """Recursively copy common containers into immutable equivalents."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass
class GameSession:
    """Own the shared state and lifecycle of one play session.

    The model deliberately stores plain Python values so CLI and Discord
    adapters can use it without importing UI-specific types.
    """

    mode: GameMode | str | int
    player_id: str | int | None = None
    session_id: str = field(default_factory=lambda: uuid4().hex)
    state: SessionState = field(default=SessionState.CONFIGURING, init=False)
    _configuration: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), init=False, repr=False
    )
    launch_result: Any | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GameMode):
            self.mode = select_game_mode(self.mode)
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise ValueError("session_id must be a non-empty string")

    @property
    def configuration(self) -> Mapping[str, Any]:
        """Return the immutable session configuration."""

        return self._configuration

    @property
    def is_terminal(self) -> bool:
        """Return whether no further lifecycle transitions are allowed."""

        return self.state in _TERMINAL_STATES

    def set_configuration(self, values: Mapping[str, Any]) -> None:
        """Replace the balloon configuration while the session is editable."""

        self._require_state(SessionState.CONFIGURING)
        if not values:
            raise ValueError("configuration must not be empty")
        self._configuration = _freeze(values)

    def mark_ready(self) -> None:
        """Lock configuration and mark the session ready to launch."""

        self._require_state(SessionState.CONFIGURING)
        if not self.configuration:
            raise ValueError("a session requires configuration before it is ready")
        self.state = SessionState.READY

    def launch(self) -> None:
        """Advance a ready session into flight."""

        self._require_state(SessionState.READY)
        self.state = SessionState.IN_FLIGHT

    def complete(self, result: Any | None = None) -> None:
        """Complete an active flight and optionally retain its result."""

        self._require_state(SessionState.IN_FLIGHT)
        self.launch_result = result
        self.state = SessionState.COMPLETED

    def cancel(self) -> None:
        """Cancel a session that has not already reached a terminal state."""

        if self.is_terminal:
            raise ValueError(f"cannot cancel a {self.state.value} session")
        self.state = SessionState.CANCELLED

    def _require_state(self, expected: SessionState) -> None:
        if self.state is not expected:
            raise ValueError(
                f"operation requires state {expected.value}; current state is {self.state.value}"
            )
