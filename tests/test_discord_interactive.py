"""Interactive walkthrough tests for BalloonConfigurator.

Exercises the full Discord UI interaction path -- selecting options, navigating
back and forth, submitting modals, toggling payloads, and verifying that each
step renders the correct buttons and content.

All tests use fully mocked ``discord.Interaction`` / ``discord.ui.Modal`` objects
so nothing hits a real Discord connection.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── helpers ──────────────────────────────────────────────────────────────

def _make_interaction(**kwargs):
    """Return a minimal mocked Discord Interaction."""
    m = MagicMock()
    resp = kwargs.get("response")
    if resp is None:
        resp = MagicMock()
        resp.edit_message = AsyncMock(return_value=None)
        resp.send_message = AsyncMock(return_value=None)  # for modal submit responses
        m.response = resp
    user = kwargs.get("user")
    if user is None:
        user = MagicMock()
        user.id = 123456789  # integer ID for player state lookups
    m.user = user
    msg = kwargs.get("message")
    if msg is not None:
        m.message = msg
    else:
        m.message = MagicMock()
        m.message.author = MagicMock()
        m.message.author.id = user.id  # same integer ID so _get_player_state() matches
    return m


# ─── fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture()
def configurator():
    """Fresh BalloonConfigurator instance with full equipment unlocks.

    UI tests need all items available to test button counts, navigation,
    and state transitions independently of progression gating.
    """
    from discord_bot import BalloonConfigurator
    from balloon_frontier.progression import ENVELOPES, PAYLOAD_UNLOCKS, SITES, PlayerRegistry
    c = BalloonConfigurator()

    # Unlock all players in the shared registry — the fixture creates one
    # via _get_player_state() (ID "anonymous"), but test interactions use
    # user.id=123456789 which creates a *different* PlayerState.
    for player in PlayerRegistry._players.values():
        player.unlocked_envelopes = [e.id for e in ENVELOPES]
        player.unlocked_payloads = [p.id for p in PAYLOAD_UNLOCKS]
        player.unlocked_sites = [s.id for s in SITES]

    # Also unlock the "anonymous" player created by BalloonConfigurator
    # in case it's a different instance from the registry lookup
    for pid in ["anonymous", "123456789"]:
        ps = PlayerRegistry.get_or_create(pid)
        ps.unlocked_envelopes = [e.id for e in ENVELOPES]
        ps.unlocked_payloads = [p.id for p in PAYLOAD_UNLOCKS]
        ps.unlocked_sites = [s.id for s in SITES]

    return c


# ─── helper coroutine runner (works with sync event loops too) ───────────

def _await(coro):
    """Run *coro* on a fresh or existing event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and not loop.is_closed():
        return loop.run_until_complete(coro)
    return asyncio.run(coro)


def _is_back(btn):
    from discord_bot import _BackButton
    return isinstance(btn, _BackButton)


# ─── helper click-routines (advance + await) ─────────────────────────────

def _full_path_to(cfg, target_step, interaction):
    """Advance config through steps up to *target_step*.

    Uses index 2 (middle-ish) for selections where applicable.
    For payloads, also invokes Next so we can reach CHOOSE_SITE+.
    """
    from discord_bot import _Step

    # Gas → envelope
    i1 = _make_interaction()
    cfg._current_step = _Step.CHOOSE_GAS
    _await(cfg._on_gas(i1, 2))  # hydrogen

    # Envelope → fill
    i2 = _make_interaction()
    cfg._current_step = _Step.CHOOSE_ENVELOPE
    _await(cfg._on_envelope(i2, 2))  # latex

    if target_step <= _Step.CHOOSE_FILL:
        return cfg

    # Fill → payloads
    i3 = _make_interaction()
    cfg._current_step = _Step.CHOOSE_FILL
    _await(cfg._on_fill(i3, 2))  # light

    if target_step <= _Step.CHOOSE_PAYLOADS:
        return cfg

    # Payloads → site (select camera then Next)
    i4a = _make_interaction()
    cfg._current_step = _Step.CHOOSE_PAYLOADS
    _await(cfg._on_payload(i4a, 1))  # camera

    if target_step == _Step.CHOOSE_PAYLOADS:
        return cfg

    i4b = _make_interaction()
    _await(cfg._advance(i4b))  # Next button logic

    if target_step <= _Step.CHOOSE_SITE:
        return cfg

    # Site → review
    i5 = _make_interaction()
    cfg._current_step = _Step.CHOOSE_SITE
    _await(cfg._on_site(i5, 2))  # rooftop

    return cfg


def _click_cfg_option(cfg, callback_factory, index, step_val):
    """Generic helper: set step, call callback, await it."""
    cfg._current_step = step_val
    cb = callback_factory(interaction=_make_interaction(), index=index)
    return _await(cb)


# ══════════════════════════════════════════════════════════════════════════
#  Test classes
# ══════════════════════════════════════════════════════════════════════════

# ─── 1. Initial state & first-step rendering ─────────────────────────────

class TestInitialState:
    def test_starts_on_gas_step(self, configurator):
        from discord_bot import _Step
        assert configurator._current_step == _Step.CHOOSE_GAS

    def test_initial_state_defaults(self, configurator):
        s = configurator.state
        assert s["gas"] == "helium"
        assert s["envelope"] == "latex"
        assert s["payloads"] == ["none"]
        assert s["site"] == "field"
        assert s["fill_mode"] == "auto"
        assert s["gas_mass"] is not None

    def test_step_content_at_gas_contains_options(self, configurator):
        content = configurator._step_content()
        assert "Gas Type" in content or "Step 1" in content
        assert "Helium" in content
        assert "Hydrogen" in content
        assert "Hot Air" in content
        assert "Methane" in content

    def test_back_is_disabled_at_step_1(self, configurator):
        """At CHOOSE_GAS the Back button exists but is effectively hidden;
        the BackButton class does NOT set disabled=True itself, so we verify
        the logical gate in _prev_step returns False rather than checking text."""
        from discord_bot import _Step, _BackButton
        # Verify _prev_step blocks at step 1.
        result = configurator._prev_step()
        assert result is False
        assert configurator._current_step == _Step.CHOOSE_GAS


# ─── 2. Full forward path ────────────────────────────────────────────────

class TestFullPath:
    def test_choose_gas_advances(self, configurator):
        from discord_bot import _Step
        interaction = _make_interaction()
        _await(configurator._on_gas(interaction, 1))
        assert configurator._current_step == _Step.CHOOSE_ENVELOPE
        interaction.response.edit_message.assert_awaited_once()

    def test_full_path_completes_to_review(self, configurator):
        """End-to-end: Gas→Envelope→Fill→Payload+Next→Site→Review."""
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        assert configurator._current_step == _Step.REVIEW_LAUNCH
        assert configurator.state["gas"] != ""
        assert configurator.state["envelope"] != ""
        assert configurator.state["site"] != ""

    def test_chosen_gas_survives_all_steps(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        # _full_path_to selects index 2 (hydrogen)
        assert configurator.state["gas"] == "hydrogen"

    def test_chosen_envelope_survives_all_steps(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        assert configurator.state["envelope"] == "latex"  # index 2 → latex

    def test_chosen_fill_survives_all_steps(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        assert configurator.state["fill_mode"] == "light"  # index 2

    def test_payload_select_survives(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        assert "camera" in configurator.state["payloads"]


# ─── 3. Button verification per step ─────────────────────────────────────

class TestButtonsPerStep:
    def _non_back_labels(self, cfg):
        return [b.label for b in cfg.children if not _is_back(b)]

    def _non_back_count(self, cfg):
        return sum(1 for b in cfg.children if not _is_back(b))

    def test_gas_has_4_options(self, configurator):
        configurator.build_buttons()
        labels = self._non_back_labels(configurator)
        assert len(labels) == 4

    def test_envelope_has_4_options(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_ENVELOPE
        configurator.build_buttons()
        assert self._non_back_count(configurator) == 4

    def test_fill_has_6_buttons(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_FILL
        configurator.build_buttons()
        assert self._non_back_count(configurator) == 6  # 5 fills + manual

    def test_fill_has_manual_button(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_FILL
        configurator.build_buttons()
        assert "Edit Gas Mass" in self._non_back_labels(configurator)

    def test_payload_has_toggle_buttons_plus_next(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_PAYLOADS
        configurator.build_buttons()
        labels = self._non_back_labels(configurator)
        assert "Next >" in labels or "Next \u25b6" in labels

    def test_site_has_3_options(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_SITE
        configurator.build_buttons()
        assert self._non_back_count(configurator) == 3

    def test_review_has_launch_only(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.REVIEW_LAUNCH
        configurator.build_buttons()
        labels = self._non_back_labels(configurator)
        assert "Launch" in labels[0]

    def test_no_launch_before_review(self, configurator):
        """Launch only appears on REVIEW_LAUNCH."""
        from discord_bot import _Step
        for si in range(_Step.REVIEW_LAUNCH):
            configurator._current_step = si
            configurator.build_buttons()
            for btn in configurator.children:
                assert "Launch" not in btn.label

    def test_next_only_on_payload(self, configurator):
        from discord_bot import _Step
        for si in list(range(_Step.CHOOSE_PAYLOADS)) + [_Step.CHOOSE_SITE, _Step.REVIEW_LAUNCH]:
            configurator._current_step = si
            configurator.build_buttons()
            has_next = any(n in btn.label for btn in configurator.children
                           for n in ("Next", "\u25b6"))
            assert not has_next


# ─── 4. Back navigation ──────────────────────────────────────────────────

class TestBackNavigation:
    def test_back_from_gas_stays(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_GAS
        result = configurator._prev_step()
        assert result is False
        assert configurator._current_step == _Step.CHOOSE_GAS

    def test_back_from_envelope_returns_gas(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_ENVELOPE
        configurator._prev_step()
        assert configurator._current_step == _Step.CHOOSE_GAS

    def test_back_from_fill_reaches_gas(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_FILL
        configurator._prev_step()  # → envelope
        configurator._prev_step()  # → gas
        assert configurator._current_step == _Step.CHOOSE_GAS

    def test_back_from_review_reaches_gas(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.REVIEW_LAUNCH
        for _ in range(5):
            configurator._prev_step()
        assert configurator._current_step == _Step.CHOOSE_GAS

    def test_back_triggers_edit_message(self, configurator):
        from discord_bot import _Step
        interaction = _make_interaction()
        configurator._current_step = _Step.CHOOSE_FILL
        _await(configurator._on_back(interaction))
        assert configurator._current_step == _Step.CHOOSE_ENVELOPE
        interaction.response.edit_message.assert_awaited_once()


# ─── 5. Payload toggling & sentinel ──────────────────────────────────────

class TestPayloadToggling:
    def test_first_payload_adds_camera(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 1))  # camera
        assert "camera" in configurator.state["payloads"]
        assert "none" not in configurator.state["payloads"]

    def test_deselecting_removes_and_resets_sentinel(self, configurator):
        """Select camera, deselect → back to ['none']."""
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 1))  # add camera
        assert "camera" in configurator.state["payloads"]
        _await(configurator._on_payload(inter, 1))  # remove camera
        assert configurator.state["payloads"] == ["none"]

    def test_selecting_none_clears_real_payloads(self, configurator):
        """'none' selected while real payloads present → clear to ['none']."""
        from discord_bot import _Step, PAYLOAD_OPTIONS
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 1))  # add camera
        assert configurator.state["payloads"] == ["camera"]

        # Find none index.
        keys = list(PAYLOAD_OPTIONS.keys())
        none_idx = keys.index("none") + 1  # 1-based
        _await(configurator._on_payload(inter, none_idx))
        assert configurator.state["payloads"] == ["none"]

    def test_real_payload_removes_none(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 2))  # radio
        assert "radio" in configurator.state["payloads"]
        assert "none" not in configurator.state["payloads"]

    def test_multiple_selections(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 1))  # camera
        _await(configurator._on_payload(inter, 2))  # radio
        _await(configurator._on_payload(inter, 5))  # heater
        assert set(configurator.state["payloads"]) == {"camera", "radio", "heater"}

    def test_payload_does_not_autoforward(self, configurator):
        """Payload selection does NOT auto-advance to next step."""
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        before = configurator._current_step
        _await(configurator._on_payload(inter, 1))
        assert configurator._current_step == before

    def test_payload_change_affects_gas_mass(self, configurator):
        initial = configurator.state["gas_mass"]
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_PAYLOADS, inter)
        _await(configurator._on_payload(inter, 1))  # camera (+1.5 kg)
        assert configurator.state["gas_mass"] != initial


# ─── 6. Manual gas mass modal ────────────────────────────────────────────

class TestManualGasMassModal:
    def test_manual_button_present_on_fill_step(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_FILL
        configurator.build_buttons()
        labels = [b.label for b in configurator.children]
        assert "Edit Gas Mass" in labels

    def test_modal_submit_valid_number(self):
        """Mocked modal submission writes valid float to state."""
        from discord_bot import _ManualGasMassModal, BalloonConfigurator

        cfg = BalloonConfigurator()
        cfg.state["fill_mode"] = "manual"
        cfg.state["manual_gas_mass"] = None

        modal = _ManualGasMassModal(cfg)

        # Override the mock input value so reading it returns our test string.
        original_value = modal.mass_input.value
        type(modal.mass_input).value = PropertyMock(return_value="7.25")

        interaction = _make_interaction()
        _await(modal.on_submit(interaction))

        assert cfg.state["manual_gas_mass"] == 7.25

        # Restore so teardown does not clobber other tests.
        type(modal.mass_input).value = PropertyMock(return_value=original_value)

    def test_modal_submit_invalid_sends_error(self):
        from discord_bot import _ManualGasMassModal, BalloonConfigurator

        cfg = BalloonConfigurator()
        modal = _ManualGasMassModal(cfg)
        type(modal.mass_input).value = PropertyMock(return_value="abc")

        interaction = _make_interaction()
        _await(modal.on_submit(interaction))

        interaction.response.send_message.assert_called_once()

    def test_modal_submit_clamps_negative(self):
        from discord_bot import _ManualGasMassModal, BalloonConfigurator

        cfg = BalloonConfigurator()
        cfg.state["fill_mode"] = "manual"
        modal = _ManualGasMassModal(cfg)
        type(modal.mass_input).value = PropertyMock(return_value="-5.0")

        interaction = _make_interaction()
        _await(modal.on_submit(interaction))

        assert cfg.state["manual_gas_mass"] == 0.001


# ─── 7. Content verification ─────────────────────────────────────────────

class TestContentVerification:
    def test_review_text_includes_gas(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        configurator.state["gas"] = "hydrogen"
        configurator.state["envelope"] = "mylar"
        configurator.state["site"] = "mountain"
        configurator.state["fill_mode"] = "heavy"
        configurator.state["payloads"] = ["camera", "radio"]
        content = configurator._build_config_text()
        assert "Hydrogen" in content
        assert "Heavy" in content.lower() or "heavy" in content.lower()

    def test_fill_step_lists_modes(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_FILL
        content = configurator._step_content()
        assert "Auto" in content
        assert "Light" in content
        assert "Normal" in content

    def test_payload_step_lists_options(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.CHOOSE_PAYLOADS
        content = configurator._step_content()
        assert "Camera" in content
        assert "Radio" in content


# ─── 8. State persistence across steps ──────────────────────────────────

class TestStatePersistence:
    def test_gas_choice_survives_navigation(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.CHOOSE_FILL, inter)
        # _full_path_to selects index 2 (hydrogen)
        assert configurator.state["gas"] == "hydrogen"

    def test_gas_mass_always_positive(self, configurator):
        from discord_bot import _Step
        inter = _make_interaction()
        _full_path_to(configurator, _Step.REVIEW_LAUNCH, inter)
        assert configurator.state["gas_mass"] is not None
        assert configurator.state["gas_mass"] > 0

    def test_individual_select_updates_state(self, configurator):
        from discord_bot import _Step
        inter1 = _make_interaction()
        _await(configurator._on_gas(inter1, 2))  # hydrogen
        assert configurator.state["gas"] == "hydrogen"

        inter2 = _make_interaction()
        _await(configurator._on_envelope(inter2, 1))  # mylar
        assert configurator.state["envelope"] == "mylar"


# ─── 9. _advance edge cases ──────────────────────────────────────────────

class TestAdvanceEdgeCases:
    def test_advance_beyond_last_clips_to_review(self, configurator):
        from discord_bot import _Step
        configurator._current_step = _Step.REVIEW_LAUNCH
        configurator._current_step += 1  # 6  (past max)
        interaction = _make_interaction()
        _await(configurator._advance(interaction))
        assert configurator._current_step == _Step.REVIEW_LAUNCH

    def test_build_before_edit_sequence(self, configurator):
        """_advance must rebuild buttons before editing message."""
        from discord_bot import _Step
        inter = _make_interaction()
        order = []
        old_build = configurator.build_buttons

        def traced(*args, **kw):
            order.append("build")
            return old_build(*args, **kw)

        configurator.build_buttons = traced
        configurator._current_step = _Step.CHOOSE_GAS
        _await(configurator._advance(inter))
        assert order[0] == "build"


# ─── 10. STEP_LABELS / STEPS consistency ─────────────────────────────────

class TestConsistency:
    def test_lengths_match(self):
        from discord_bot import BalloonConfigurator
        assert len(BalloonConfigurator.STEPS) == len(BalloonConfigurator.STEP_LABELS)
        assert len(BalloonConfigurator.STEPS) == 6

    def test_all_labels_non_empty(self):
        from discord_bot import BalloonConfigurator
        for label in BalloonConfigurator.STEP_LABELS:
            assert isinstance(label, str)
            assert len(label) > 0

    def test_consecutive_indices(self):
        from discord_bot import _Step
        assert _Step.CHOOSE_GAS == 0
        assert _Step.CHOOSE_ENVELOPE == 1
        assert _Step.CHOOSE_FILL == 2
        assert _Step.CHOOSE_PAYLOADS == 3
        assert _Step.CHOOSE_SITE == 4
        assert _Step.REVIEW_LAUNCH == 5