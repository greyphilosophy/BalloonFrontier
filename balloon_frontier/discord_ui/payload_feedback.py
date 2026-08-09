"""Shared Discord feedback for multi-select payload toggles."""

from __future__ import annotations


class PayloadFeedbackConfiguratorMixin:
    """Show the exact payload toggle action and resulting equipped loadout."""

    def _payload_feedback_options(self):
        from balloon_frontier.discord_ui.configurator import PAYLOAD_OPTIONS, _Step

        # Story chapters may intentionally expose a smaller/different payload menu.
        first_flight_options = getattr(self, "_first_flight_options", None)
        if callable(first_flight_options):
            try:
                return first_flight_options(_Step.CHOOSE_PAYLOADS)
            except (KeyError, TypeError, ValueError):
                pass

        # Legacy compatibility for the removed guided tutorial mixin.
        tutorial_options = getattr(self, "_tutorial_options", None)
        if callable(tutorial_options):
            try:
                return tutorial_options(_Step.CHOOSE_PAYLOADS)
            except (KeyError, TypeError, ValueError):
                pass
        return PAYLOAD_OPTIONS

    def _equipped_payload_summary(self) -> str:
        options = self._payload_feedback_options()
        selected = set(self.state.get("payloads") or ("none",))
        names = [
            payload[0]
            for key, payload in options.items()
            if key in selected and key != "none"
        ]
        return ", ".join(names) if names else "None"

    async def _on_payload(self, interaction, index: int):
        options = self._payload_feedback_options()
        keys = list(options)
        if index < 1 or index > len(keys):
            await interaction.response.send_message(
                "That option isn't available right now.",
                ephemeral=True,
            )
            return

        selected_key = keys[index - 1]
        selected_name = options[selected_key][0]
        current = set(self.state.get("payloads") or ("none",))
        if selected_key == "none":
            self._payload_toggle_feedback = "🧹 **Payloads cleared.**"
        elif selected_key in current:
            self._payload_toggle_feedback = f"➖ **Removed:** {selected_name}"
        else:
            self._payload_toggle_feedback = f"✅ **Added:** {selected_name}"

        await super()._on_payload(interaction, index)

    def _step_content(self) -> str:
        from balloon_frontier.discord_ui.configurator import _Step

        content = super()._step_content()
        if self._current_step != _Step.CHOOSE_PAYLOADS:
            return content

        feedback = getattr(self, "_payload_toggle_feedback", None)
        if feedback:
            content += f"\n\n{feedback}"
        content += f"\n\n**Currently equipped:** {self._equipped_payload_summary()}"
        return content

    def build_buttons(self):
        """Use payload names and distinguish the destructive clear action."""
        super().build_buttons()

        from balloon_frontier.discord_ui.configurator import _Step
        from balloon_frontier.discord_ui.views import _OptionButton

        if self._current_step != _Step.CHOOSE_PAYLOADS:
            return

        options = self._payload_feedback_options()
        keys = list(options)
        for item in self.children:
            if not isinstance(item, _OptionButton):
                continue
            index = item._index - 1
            if index < 0 or index >= len(keys):
                continue
            key = keys[index]
            item.label = (
                "Clear payloads"
                if key == "none"
                else f"Toggle {options[key][0]}"
            )

    async def _advance(self, interaction):
        from balloon_frontier.discord_ui.configurator import _Step

        if self._current_step == _Step.CHOOSE_PAYLOADS:
            self._payload_toggle_feedback = None
        await super()._advance(interaction)

    def _prev_step(self):
        self._payload_toggle_feedback = None
        return super()._prev_step()
