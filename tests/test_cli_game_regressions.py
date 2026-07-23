import cli_game


def test_show_balloon_menu_excludes_s21_and_s29(monkeypatch, capsys):
    monkeypatch.setattr(cli_game, "get_balloon_choice", lambda: None)

    cli_game.show_balloon_menu()
    output = capsys.readouterr().out

    assert '21"' not in output
    assert '29"' not in output
    assert '36"' in output
    assert '150"' in output


def test_get_balloon_choice_uses_playable_list(monkeypatch):
    monkeypatch.setattr(cli_game, "get_choice", lambda *args, **kwargs: 0)

    choice = cli_game.get_balloon_choice()

    assert choice == cli_game.BALLOON_LIST[0]
    assert choice not in {"s21", "s29"}


def test_show_fill_presets_uses_configured_gas_density(monkeypatch):
    captured_densities = []

    def fake_calculate_max_safe_gas_mass(*args, **kwargs):
        captured_densities.append(kwargs["gas_density"])
        return 0.123

    monkeypatch.setattr(cli_game, "calculate_max_safe_gas_mass", fake_calculate_max_safe_gas_mass)
    monkeypatch.setattr(cli_game, "get_choice", lambda *args, **kwargs: 0)

    mode, mass = cli_game.show_fill_presets("s36", "methane")

    assert mode == cli_game.FillMode.AUTO
    assert mass == 0.123
    assert captured_densities
    assert all(d == cli_game.GAS_OPTIONS["methane"][1] for d in captured_densities)


def test_run_flight_uses_peak_for_medal_emoji(monkeypatch):
    def fake_run_simulation(*args, **kwargs):
        return [
            {
                "time_s": 0.1,
                "altitude_m": 12.5,
                "velocity_mps": 0.0,
                "burst": False,
                "landed": True,
                "crashed": False,
            }
        ]

    monkeypatch.setattr(cli_game, "run_simulation", fake_run_simulation)

    telemetry, summary = cli_game.run_flight(
        "helium",
        0.5,
        cli_game.BALLOON_SIZES["s36"],
        [],
        "field",
    )

    assert telemetry
    assert summary["peak_altitude"] == 12.5
    assert summary["medal_emoji"]
