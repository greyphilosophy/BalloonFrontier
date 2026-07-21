import sys

sys.path.insert(0, "/home/greyphilosophy/projects/BalloonFrontier")

import pytest

from discord_bot import BalloonConfigurator, ENVELOPE_OPTIONS, PAYLOAD_OPTIONS, run_simulation


@pytest.mark.parametrize("envelope_key", list(ENVELOPE_OPTIONS.keys()))
@pytest.mark.parametrize("fill_mode", ["auto", "light", "normal", "heavy"])
def test_discord_presets_do_not_instantly_burst(envelope_key, fill_mode):
    cfg = BalloonConfigurator()
    cfg.state["gas"] = "helium"
    cfg.state["envelope"] = envelope_key
    cfg.state["fill_mode"] = fill_mode

    gas_mass = cfg._compute_gas_mass()
    assert gas_mass > 0

    env_info = ENVELOPE_OPTIONS[envelope_key]
    payload_mass = sum(PAYLOAD_OPTIONS[p][1] for p in cfg.state["payloads"])
    site_cond = cfg._get_site_conditions()

    _tel, summary = run_simulation(
        cfg.state["gas"],
        gas_mass,
        site_cond["gas_temperature"],
        payload_mass,
        env_info[3],
        env_info[1],
        env_info[4],
    )

    # Acceptance: preset/auto fill should not pop immediately.
    assert not (summary.get("burst") is True and summary.get("time_of_flight") == 0.0)
