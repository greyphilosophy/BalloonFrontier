"""Tests for the Discord View _run_checks AttributeError in BalloonConfigurator.

Bug: discord.py's Item._run_checks calls self._parent._run_checks(interaction),
but discord.ui.View does NOT define _run_checks. So when a Select child on
BalloonConfigurator gets its _run_checks invoked by the View timeout handler,
the chain reaches `self._parent` (the BalloonConfigurator) which lacks
_run_checks → AttributeError → "Interaction Failed" to the user.

The fix: add _run_checks to BalloonConfigurator that delegates to interaction_check.

References:
  - journal logs: "AttributeError: 'BalloonConfigurator' object has no attribute '_run_checks'"
  - discord.py 2.7.1: Item has _run_checks, View does NOT have _run_checks
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockInteraction:
    """Minimal mock of discord.Interaction for testing."""
    user = type("User", (), {"id": 123})()


def test_parent_view_has_run_checks():
    """BalloonConfigurator must have _run_checks to avoid the AttributeError.

    When a Select child's _run_checks fires, it calls self._parent._run_checks().
    If the parent View lacks _run_checks, an AttributeError propagates and
    Discord shows "Interaction Failed".
    """
    from discord_bot import BalloonConfigurator

    config = BalloonConfigurator()
    assert hasattr(config, "_run_checks"), (
        "BalloonConfigurator needs a _run_checks method. Without it, selecting "
        "a dropdown triggers: AttributeError: 'BalloonConfigurator' object has "
        "no attribute '_run_checks'"
    )


def test_parent_run_checks_is_callable():
    """_run_checks must be a coroutine function."""
    import asyncio

    from discord_bot import BalloonConfigurator

    config = BalloonConfigurator()
    method = getattr(config, "_run_checks")
    assert asyncio.iscoroutinefunction(method), (
        "_run_checks should be an async method so Item._run_checks can await it"
    )


def test_parent_run_checks_returns_true():
    """Calling _run_checks on BalloonConfigurator should return True."""
    import asyncio

    from discord_bot import BalloonConfigurator

    config = BalloonConfigurator()
    # Run the coroutine in an event loop
    async def _run():
        return await config._run_checks(MockInteraction())

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(_run())
    except Exception:
        result = None
    finally:
        loop.close()

    assert result is True, (
        f"_run_checks should return True, got {result}"
    )


def test_view_base_lacks_run_checks():
    """Verify that the upstream bug exists: discord.ui.View lacks _run_checks.

    This is the root cause. If this assertion changes (discord.py adds _run_checks
    to View), the bug is fixed upstream and the BalloonConfigurator override
    becomes optional.
    """
    import discord.ui as ui

    assert not hasattr(ui.View, "_run_checks"), (
        "If discord.ui.View now has _run_checks, the upstream bug is fixed"
    )


def test_children_exist():
    """Ensure the configurator has Select children."""
    from discord_bot import BalloonConfigurator

    config = BalloonConfigurator()
    select_children = [
        child for child in config.children
        if child.__class__.__name__ == "_Select"
    ]
    assert len(select_children) > 0, (
        "Configurator should have at least one Select child"
    )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
