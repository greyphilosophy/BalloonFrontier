"""Player-facing instructions shared by Discord and CLI."""

from __future__ import annotations


HOW_TO_PLAY = (
    "📘 **How to Play Balloon Frontier**\n\n"
    "**1. Choose a flight**\n"
    "Story begins with a small first-flight menu. Later chapters introduce more "
    "equipment, locations, and decisions. Scenario offers themed missions, while "
    "Free Play is a sandbox.\n\n"
    "**2. Configure the balloon**\n"
    "Choose a lifting gas, envelope, fill, payloads, and launch site. Every choice "
    "feeds the same flight simulation—there is no special training physics.\n\n"
    "**3. Launch and read the result**\n"
    "The flight runs through the atmosphere and reports altitude, duration, landing "
    "or crash state, mission results, and a trajectory chart. If a design fails, "
    "change one choice and compare the next flight.\n\n"
    "**4. Progress through Story**\n"
    "Completing missions saves progress and moves the story forward. The available "
    "configuration choices can change as the campaign develops.\n\n"
    "Tip: `/physics` shows the equations used by the simulation."
)


def how_to_play_text() -> str:
    return HOW_TO_PLAY
