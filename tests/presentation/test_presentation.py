from balloon_frontier.presentation import (
    DiscordAnsiSerializer,
    FlightEvent,
    FlightPhase,
    FlightSceneBuilder,
    PlainTextSerializer,
    RenderFrame,
    TerminalAnsiSerializer,
    build_flight_moments,
)


def telemetry(*, burst=False, landed=True, crashed=False):
    return [
        {"time": 0, "alt": 0, "vel": 0},
        {"time": 5, "alt": 20, "vel": 4},
        {"time": 100, "alt": 900, "vel": 6},
        {"time": 800, "alt": 13000, "vel": 7},
        {"time": 1600, "alt": 30000, "vel": 1, "burst": burst},
        {"time": 1900, "alt": 8000, "vel": -12},
        {"time": 2400, "alt": 0, "vel": 0, "landed": landed, "crashed": crashed},
    ]


def test_default_timeline_is_seven_frames_and_deterministic():
    first = build_flight_moments(telemetry())
    second = build_flight_moments(telemetry())
    assert first == second and len(first) == 7
    assert first[0].phase == FlightPhase.PRELAUNCH
    assert first[-1].phase == FlightPhase.LANDED
    assert sum(moment.phase == FlightPhase.APOGEE for moment in first) == 1


def test_burst_at_apogee_and_crash_are_preserved():
    moments = build_flight_moments(
        telemetry(burst=True, landed=False, crashed=True)
    )
    phases = [moment.phase for moment in moments]
    assert FlightPhase.APOGEE in phases and FlightPhase.BURST in phases
    assert phases.index(FlightPhase.APOGEE) < phases.index(FlightPhase.BURST)
    assert phases[-1] == FlightPhase.CRASHED


def test_flat_telemetry_does_not_invent_liftoff_or_apogee():
    moments = build_flight_moments(
        [
            {"time": 0, "alt": 0, "vel": 0},
            {"time": 5, "alt": 0, "vel": 0},
            {"time": 10, "alt": 0, "vel": 0, "landed": True},
        ],
        max_frames=18,
    )

    assert [moment.phase for moment in moments] == [
        FlightPhase.PRELAUNCH,
        FlightPhase.LANDED,
    ]
    assert all(moment.event is not FlightEvent.LIFTOFF for moment in moments)
    assert all(moment.phase is not FlightPhase.APOGEE for moment in moments)


def test_empty_telemetry_returns_safe_frame():
    assert build_flight_moments([])[0].phase == FlightPhase.COMPLETE


def test_scene_is_exactly_34_columns_and_fits_discord():
    moment = build_flight_moments(telemetry())[3]
    canvas = FlightSceneBuilder().build(RenderFrame(moment))
    plain = PlainTextSerializer().serialize(canvas)
    assert len(plain.splitlines()) == 18
    assert all(len(line) == 34 for line in plain.splitlines())
    assert "\x1b" not in plain
    body = DiscordAnsiSerializer().serialize(canvas)
    assert len(f"```ansi\n{body}\n```") < 2000


def test_ansi_serializers_reset_every_line():
    canvas = FlightSceneBuilder().build(
        RenderFrame(build_flight_moments(telemetry())[3])
    )
    for serializer in (DiscordAnsiSerializer(), TerminalAnsiSerializer()):
        assert all(
            line.endswith("\x1b[0m")
            for line in serializer.serialize(canvas).splitlines()
        )


def test_requested_frame_count_never_exceeds_twenty_four():
    dense = [
        {
            "time": index * 5,
            "alt": min(index, 30 - index) * 1000,
            "vel": 4,
        }
        for index in range(31)
    ]
    assert len(build_flight_moments(dense, max_frames=999)) <= 24
