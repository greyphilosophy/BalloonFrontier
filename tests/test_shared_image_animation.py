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


def test_graphical_scene_changes_for_selected_payload_and_burst():
    renderer = GraphicFlightSceneRenderer()
    ordinary = renderer.render(
        RenderFrame(moments()[2]),
        payload_ids=("camera",),
    )
    quadcopter = renderer.render(
        RenderFrame(moments()[2]),
        payload_ids=("small_quadcopter",),
    )

    assert ordinary.tobytes() != quadcopter.tobytes()
