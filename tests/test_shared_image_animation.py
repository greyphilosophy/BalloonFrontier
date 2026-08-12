from balloon_frontier.presentation import (
    GraphicFlightSceneRenderer,
    ImageAnsiRenderer,
    RenderFrame,
    build_flight_moments,
)


def moments():
    return build_flight_moments(
        [
            {"time": 0, "alt": 0, "vel": 0},
            {"time": 5, "alt": 20, "vel": 4},
            {"time": 100, "alt": 900, "vel": 6},
            {"time": 800, "alt": 13000, "vel": 7},
            {"time": 1600, "alt": 30000, "vel": 1},
            {"time": 1900, "alt": 8000, "vel": -12},
            {"time": 2400, "alt": 0, "vel": 0, "landed": True},
        ]
    )


def test_same_graphical_frame_can_be_rendered_as_color_ansi_and_plain_ascii():
    moment = moments()[2]
    image = GraphicFlightSceneRenderer().render(
        RenderFrame(moment, event_emphasis=True),
        envelope_id="latex",
        payload_ids=("camera",),
    )

    assert image.size == (384, 216)
    assert image.mode == "RGB"

    serializer = ImageAnsiRenderer(columns=40)
    ansi = serializer.render(image, color=True)
    plain = serializer.render(image, color=False)

    assert "▀" in ansi
    assert "\x1b[38;2;" in ansi
    assert "\x1b" not in plain
    assert all(len(line) == 40 for line in plain.splitlines())


def test_graphical_scene_changes_for_selected_payload():
    renderer = GraphicFlightSceneRenderer()
    camera = renderer.render(
        RenderFrame(moments()[2]),
        payload_ids=("camera",),
    )
    quadcopter = renderer.render(
        RenderFrame(moments()[2]),
        payload_ids=("small_quadcopter",),
    )
    no_payload = renderer.render(
        RenderFrame(moments()[2]),
        payload_ids=("none",),
    )
    unknown_loadout = renderer.render(RenderFrame(moments()[2]))

    assert camera.tobytes() != quadcopter.tobytes()
    assert no_payload.tobytes() != camera.tobytes()
    assert no_payload.tobytes() != unknown_loadout.tobytes()


def test_landed_camera_remains_visible_above_hud():
    image = GraphicFlightSceneRenderer().render(
        RenderFrame(moments()[-1]),
        payload_ids=("camera",),
    )
    # The HUD begins at y=178. The camera lens color must remain visible above it.
    lens = (83, 153, 191)
    assert any(
        image.getpixel((x, y)) == lens
        for y in range(130, 178)
        for x in range(150, 235)
    )


def test_timeline_can_supply_more_moments_without_discord_edit_pressure():
    telemetry = [
        {
            "time": index * 10,
            "alt": index * 750 if index <= 20 else (40 - index) * 750,
            "vel": 5 if index <= 20 else -5,
            "landed": index == 40,
        }
        for index in range(41)
    ]

    selected = build_flight_moments(telemetry, max_frames=24)

    assert 18 <= len(selected) <= 24
