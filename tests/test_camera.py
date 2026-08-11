"""The camera. Mostly one rule: never show past the edge of the level."""

from __future__ import annotations

import pytest

from hack_and_slash.core.vec2 import Vec2
from hack_and_slash.render.camera import Camera

VIEW_W, VIEW_H = 384, 188
LEVEL_W, LEVEL_H = 640, 384


def camera() -> Camera:
    return Camera(LEVEL_W, LEVEL_H, VIEW_W, VIEW_H)


def test_snapping_centres_the_target() -> None:
    cam = camera()
    cam.snap_to(Vec2(320, 192))
    assert cam.x == pytest.approx(320 - VIEW_W / 2)
    assert cam.y == pytest.approx(192 - VIEW_H / 2)


def test_the_view_never_runs_past_the_edge_of_the_level() -> None:
    """The failure this prevents is a strip of void along one wall."""
    cam = camera()
    for target in (Vec2(0, 0), Vec2(LEVEL_W, LEVEL_H), Vec2(-500, -500), Vec2(9999, 9999)):
        cam.snap_to(target)
        assert 0 <= cam.x <= LEVEL_W - VIEW_W
        assert 0 <= cam.y <= LEVEL_H - VIEW_H


def test_a_level_smaller_than_the_view_is_centred() -> None:
    # Rather than drifting against one edge and leaving a band on the other.
    cam = Camera(200, 100, VIEW_W, VIEW_H)
    cam.snap_to(Vec2(100, 50))
    assert cam.x == pytest.approx(-(VIEW_W - 200) / 2)
    assert cam.y == pytest.approx(-(VIEW_H - 100) / 2)


def test_following_eases_toward_the_target_rather_than_snapping() -> None:
    """A camera locked to the hero yanks the whole world sideways on every
    dodge. Easing is what keeps a fast game legible."""
    cam = camera()
    cam.snap_to(Vec2(100, 192))
    before = cam.x

    cam.follow(Vec2(400, 192))
    assert before < cam.x, "did not move toward the target"
    assert cam.x < 400 - VIEW_W / 2, "snapped instead of easing"


def test_following_converges_on_the_target_eventually() -> None:
    cam = camera()
    cam.snap_to(Vec2(100, 192))
    for _ in range(120):
        cam.follow(Vec2(400, 192))
    assert cam.x == pytest.approx(400 - VIEW_W / 2, abs=1.0)


def test_look_ahead_leans_toward_where_you_are_aiming() -> None:
    centred = camera()
    leaning = camera()
    centred.snap_to(Vec2(320, 192))
    leaning.snap_to(Vec2(320, 192), Vec2(1, 0))
    assert leaning.x > centred.x


def test_screen_coordinates_are_whole_pixels() -> None:
    """A sprite blitted at a fractional offset lands on a half pixel, and the
    integer upscale turns that into a visible wobble."""
    cam = camera()
    cam.x, cam.y = 10.4, 20.7
    sx, sy = cam.to_screen(Vec2(100.6, 200.2))
    assert isinstance(sx, int) and isinstance(sy, int)


def test_to_world_is_the_inverse_of_to_screen() -> None:
    cam = camera()
    cam.snap_to(Vec2(320, 192))
    original = Vec2(300, 180)
    sx, sy = cam.to_screen(original)
    back = cam.to_world(sx, sy)
    assert back.x == pytest.approx(original.x, abs=1.0)
    assert back.y == pytest.approx(original.y, abs=1.0)


def test_visible_tiles_covers_the_whole_viewport() -> None:
    cam = camera()
    cam.snap_to(Vec2(320, 192))
    x0, y0, x1, y1 = cam.visible_tiles(16)
    assert x0 <= cam.x / 16
    assert x1 >= (cam.x + VIEW_W) / 16
    assert y0 <= cam.y / 16
    assert y1 >= (cam.y + VIEW_H) / 16


def test_offscreen_things_are_reported_offscreen() -> None:
    cam = camera()
    cam.snap_to(Vec2(320, 192))
    assert cam.is_on_screen(Vec2(320, 192))
    assert not cam.is_on_screen(Vec2(320, 192 + VIEW_H))
