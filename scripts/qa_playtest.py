#!/usr/bin/env python3
"""Automated playtest: feeds random choices through cli_game.py.

Detects failures: 0m peak altitude = balloon never rose (too heavy).
"""
import subprocess
import sys
import os
import random

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLI = os.path.join(REPO, "cli_game.py")


def make_inputs():
    """Generate random choices for a complete playthrough."""
    return {
        "balloon": str(random.randint(1, 6)),
        "gas": str(random.randint(1, 3)),
        "fill": str(random.randint(1, 4)),  # Auto/Light/Normal/Heavy
        "payload": str(random.randint(1, 9)),
        "site": str(random.randint(1, 3)),
    }


def run_playthrough(n_runs=3):
    results = []
    for run_num in range(n_runs):
        choices = make_inputs()
        inputs = [
            choices["balloon"],
            choices["gas"],
            choices["fill"],
            choices["payload"],
            "done",
            choices["site"],
            "y",
            "n",
        ]
        inp = "\n".join(inputs) + "\n"
        try:
            proc = subprocess.run(
                [sys.executable, CLI],
                input=inp, capture_output=True, text=True,
                cwd=REPO, timeout=30,
                env={**os.environ, "PYTHONPATH": REPO},
            )
            if "Peak Altitude:" in proc.stdout:
                import re
                peak_match = re.search(r"Peak Altitude:\s+([\d,\.]+)", proc.stdout)
                peak = float(peak_match.group(1).replace(",", "")) if peak_match else 0
                if peak == 0:
                    results.append({
                        "status": "TOO_HEAVY",
                        "peak": 0,
                        "choices": choices,
                    })
                else:
                    results.append({
                        "status": "PASS",
                        "peak": peak,
                        "choices": choices,
                    })
            elif "TOO HEAVY" in proc.stdout:
                results.append({
                    "status": "TOO_HEAVY",
                    "peak": 0,
                    "choices": choices,
                })
            else:
                results.append({"status": "CRASH", "peak": 0, "choices": choices})
        except subprocess.TimeoutExpired:
            results.append({"status": "TIMEOUT", "peak": 0, "choices": choices})
    return results


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results = run_playthrough(n)
    passed = sum(1 for r in results if r["status"] == "PASS")
    heavy = sum(1 for r in results if r["status"] == "TOO_HEAVY")
    for r in results:
        c = r["choices"]
        if r["status"] == "TOO_HEAVY":
            print(f"Run: TOO HEAVY (never rose) — {c}")
        elif r["status"] == "PASS":
            print(f"Run: FLEW (peak {r['peak']:.0f}m) — {c}")
        else:
            print(f"Run: {r['status']} — {c}")
    print(f"\nSUMMARY: {n} runs, {passed} flew, {heavy} too heavy")