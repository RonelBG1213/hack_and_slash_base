"""Collision maths. Pure functions over plain numbers -- no world, no pygame.

Three shapes of problem live here:

* **Bodies against walls.** A circle against a tile grid, resolved by pushing out
  along the contact normal. Sliding along a wall is not a special case; it is
  what falls out of pushing along the normal and leaving the tangent alone.
* **Bodies against each other.** Circle overlap, and the symmetric push that
  stops two enemies occupying one spot.
* **Swings against bodies.** The cone test: reach plus arc.

The subtle part is *internal edges*. A wall three tiles wide is three AABBs, and
the seams between them are not real surfaces -- a circle sliding along the wall
must not catch on them. Every contact here is culled if the neighbouring tile in
the direction of the push is also solid, which is what makes a tiled wall behave
like one flat surface.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, NamedTuple

from .vec2 import EPSILON, Vec2, angle_difference

#: `is_solid(tile_x, tile_y) -> bool`. Anything outside the map must answer True,
#: so the arena is closed without ringing it in explicit wall tiles.
SolidFn = Callable[[int, int], bool]

#: A push-out is abandoned after this many passes. Reached only in genuinely
#: pathological geometry (a body wedged in a one-tile slot narrower than itself);
#: bailing keeps a bad level from hanging the sim.
MAX_RESOLVE_PASSES = 4


class Contact(NamedTuple):
    normal: Vec2  # unit vector pointing out of the surface, toward the body
    depth: float  # how far the body must travel along `normal` to be clear


# --- circle vs circle --------------------------------------------------------
def circles_overlap(a: Vec2, radius_a: float, b: Vec2, radius_b: float) -> bool:
    reach = radius_a + radius_b
    return a.distance_sq_to(b) < reach * reach


def circle_separation(a: Vec2, radius_a: float, b: Vec2, radius_b: float) -> Vec2:
    """Offset that moves `a` clear of `b`. ZERO when they are already apart.

    Two bodies stacked exactly on top of each other have no direction to
    separate along, so one is nudged along +x. Arbitrary, but deterministic --
    which matters more than which way it picks, because the sim must replay.
    """
    delta = a - b
    reach = radius_a + radius_b
    distance_sq = delta.length_sq()
    if distance_sq >= reach * reach:
        return Vec2(0.0, 0.0)
    if distance_sq < EPSILON * EPSILON:
        return Vec2(reach, 0.0)
    distance = math.sqrt(distance_sq)
    return delta * ((reach - distance) / distance)


# --- circle vs tiles ---------------------------------------------------------
def _overlapping_tiles(pos: Vec2, radius: float, tile: int) -> Iterable[tuple[int, int]]:
    """Tile coordinates whose cells the circle's bounding box touches."""
    x0 = math.floor((pos.x - radius) / tile)
    x1 = math.floor((pos.x + radius) / tile)
    y0 = math.floor((pos.y - radius) / tile)
    y1 = math.floor((pos.y + radius) / tile)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            yield tx, ty


def _tile_contact(
    pos: Vec2, radius: float, tx: int, ty: int, tile: int, is_solid: SolidFn
) -> Contact | None:
    """Contact between a circle and one solid tile, or None.

    Returns None for contacts on internal edges -- faces and corners that face
    into the rest of the wall. Those are the seams; treating them as surfaces is
    what makes a body snag while sliding along an otherwise flat wall.
    """
    left, top = tx * tile, ty * tile
    right, bottom = left + tile, top + tile

    closest_x = min(max(pos.x, left), right)
    closest_y = min(max(pos.y, top), bottom)
    delta = Vec2(pos.x - closest_x, pos.y - closest_y)
    distance_sq = delta.length_sq()

    if distance_sq >= radius * radius:
        return None

    if distance_sq < EPSILON * EPSILON:
        # Centre is inside the tile: there is no outward direction to read off
        # the geometry. Escape through the nearest face that does not lead
        # further into the wall.
        return _escape_from_inside(pos, radius, tx, ty, tile, is_solid)

    distance = math.sqrt(distance_sq)
    normal = delta / distance

    # Which neighbours does this contact push toward? A face contact has one
    # zero component and names a single neighbour; a corner contact names two,
    # and either one being solid means the neighbour owns this region.
    on_vertical_face = abs(delta.x) > EPSILON
    on_horizontal_face = abs(delta.y) > EPSILON

    if on_vertical_face and is_solid(tx + (1 if delta.x > 0 else -1), ty):
        return None
    if on_horizontal_face and is_solid(tx, ty + (1 if delta.y > 0 else -1)):
        return None

    return Contact(normal, radius - distance)


def _escape_from_inside(
    pos: Vec2, radius: float, tx: int, ty: int, tile: int, is_solid: SolidFn
) -> Contact | None:
    """Shortest way out for a centre that is already inside a solid tile.

    Only reachable when something spawned or teleported into a wall. Each of the
    four faces is scored by how far the body must travel to clear it, and faces
    backing onto more wall are not offered at all.
    """
    left, top = tx * tile, ty * tile
    right, bottom = left + tile, top + tile

    candidates = [
        (Vec2(-1.0, 0.0), pos.x - left + radius, (tx - 1, ty)),
        (Vec2(1.0, 0.0), right - pos.x + radius, (tx + 1, ty)),
        (Vec2(0.0, -1.0), pos.y - top + radius, (tx, ty - 1)),
        (Vec2(0.0, 1.0), bottom - pos.y + radius, (tx, ty + 1)),
    ]
    open_faces = [
        (normal, depth) for normal, depth, neighbour in candidates if not is_solid(*neighbour)
    ]
    if not open_faces:
        # Entombed. Nothing sensible to do; leave the body where it is rather
        # than shoving it into an equally solid neighbour.
        return None
    normal, depth = min(open_faces, key=lambda pair: pair[1])
    return Contact(normal, depth)


def resolve_circle_vs_tiles(
    pos: Vec2, radius: float, is_solid: SolidFn, tile: int
) -> Vec2:
    """Nearest position at which the circle touches no solid tile.

    Resolves the deepest contact first and re-tests, because pushing out of one
    tile can press the body into another. Position is returned, never mutated.
    """
    for _ in range(MAX_RESOLVE_PASSES):
        deepest: Contact | None = None
        for tx, ty in _overlapping_tiles(pos, radius, tile):
            if not is_solid(tx, ty):
                continue
            contact = _tile_contact(pos, radius, tx, ty, tile, is_solid)
            if contact is not None and (deepest is None or contact.depth > deepest.depth):
                deepest = contact
        if deepest is None:
            break
        pos = pos + deepest.normal * deepest.depth
    return pos


def move_and_collide(
    pos: Vec2, radius: float, delta: Vec2, is_solid: SolidFn, tile: int
) -> Vec2:
    """Move a body by `delta` and push it back out of anything it entered.

    Two things are going on.

    The two axes are stepped separately, which is what produces sliding: running
    diagonally into a horizontal wall loses the vertical component and keeps the
    horizontal one, instead of stopping dead the way a single combined step does.

    And a long `delta` is walked in substeps. Push-out only sees where a body
    *landed*, not where it travelled, so a single large step can hop clean over
    a wall and resolve happily on the far side. A dash covers real distance in
    one tick, so this is not hypothetical -- it is the difference between a dodge
    that ends against a wall and one that ends outside the arena.
    """
    steps = max(1, math.ceil(delta.length() / max(radius, 1.0)))
    step = delta / steps
    for _ in range(steps):
        pos = resolve_circle_vs_tiles(Vec2(pos.x + step.x, pos.y), radius, is_solid, tile)
        pos = resolve_circle_vs_tiles(Vec2(pos.x, pos.y + step.y), radius, is_solid, tile)
    return pos


def path_is_clear(a: Vec2, b: Vec2, is_solid: SolidFn, tile: int) -> bool:
    """True when no solid tile lies anywhere on the segment from `a` to `b`.

    A *swept* test, and that is the whole point of it. Checking only where
    something ended up is the same mistake `move_and_collide` substeps to avoid:
    both endpoints of a long jump can sit on open floor with a wall in between.
    Anything that moves further than a tile in one tick needs this rather than a
    look at its destination.

    Sampled at half-tile steps rather than walked with a DDA. The step count
    grows with the distance, so a long path is not sampled more thinly than a
    short one -- a fixed number of samples would let walls leak through at range.
    """
    delta = b - a
    distance = delta.length()
    if distance < EPSILON:
        return not is_solid(int(math.floor(a.x / tile)), int(math.floor(a.y / tile)))

    steps = max(1, int(distance / (tile * 0.5)))
    for i in range(steps + 1):
        point = a + delta * (i / steps)
        if is_solid(int(math.floor(point.x / tile)), int(math.floor(point.y / tile))):
            return False
    return True


def closest_point_on_segment(point: Vec2, a: Vec2, b: Vec2) -> Vec2:
    """The nearest point to `point` that lies on the segment `a`..`b`.

    The *segment*, not the infinite line through it, and the clamp below is the
    whole of the difference: a blade that has swept past you is behind you, not
    still beside you, and an unclamped projection says otherwise.

    A degenerate segment (`a == b` -- a spike, or a blade at the end of its
    travel turning around) returns `a`. That case is reached constantly rather
    than pathologically, which is why it is an early return and not a guard.
    """
    span = b - a
    length_sq = span.length_sq()
    if length_sq < EPSILON:
        return a

    # How far along the segment the perpendicular foot lands, as a fraction,
    # clamped into 0..1 so the answer is on the segment itself.
    t = (point - a).dot(span) / length_sq
    return a + span * max(0.0, min(1.0, t))


def segment_distance(point: Vec2, a: Vec2, b: Vec2) -> float:
    """Shortest distance from a point to the segment `a`..`b`.

    Written for a swept hazard test -- where a body sits relative to the arc a
    blade travelled this tick -- which is the same shape of question
    `path_is_clear` asks of a wall, from the other end. That one asks whether a
    segment met the grid; this asks how near it came to one body.
    """
    return point.distance_to(closest_point_on_segment(point, a, b))


def line_of_sight(a: Vec2, b: Vec2, is_solid: SolidFn, tile: int) -> bool:
    """True when nothing solid stands between two points.

    The same test as `path_is_clear`, under the name that reads correctly where
    it is used: an archer asks whether it can see you, an arrow asks whether its
    path is clear. Same geometry, different question.
    """
    return path_is_clear(a, b, is_solid, tile)


# --- swings ------------------------------------------------------------------
def cone_hits(
    origin: Vec2,
    facing: float,
    arc: float,
    reach: float,
    target: Vec2,
    target_radius: float,
) -> bool:
    """Does a swing of half-angle `arc / 2` and length `reach` catch a body?

    Two tests, both accounting for the target's size rather than treating it as a
    point. A body is in reach if its *near edge* is within `reach`, and inside the
    arc if any part of it is -- a wide enemy clipping the edge of the swing reads
    as a hit to the player, so it should be one.

    A target overlapping the origin always hits: at zero distance there is no
    meaningful angle, and "the enemy is standing on me" should never be a miss.
    """
    delta = target - origin
    distance = delta.length()

    if distance <= target_radius:
        return True
    if distance - target_radius > reach:
        return False

    # Half-width of the target as seen from the origin. asin is safe here --
    # the distance > target_radius case above keeps the ratio under 1.
    angular_radius = math.asin(min(1.0, target_radius / distance))
    offset = abs(angle_difference(facing, delta.angle()))
    return offset - angular_radius <= arc * 0.5
