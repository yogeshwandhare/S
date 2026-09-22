"""Point-in-polygon test used by zone-intrusion detection.

Standard ray-casting algorithm over a simple (possibly non-convex) polygon.
Pure Python, no external geometry library -- the polygons here are small
(an operator-drawn zone, typically under 20 vertices) so there's no
performance reason to pull in a dependency like Shapely for this.
"""

from __future__ import annotations


def point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    """Returns True if `point` lies inside `polygon` (a list of (x, y)
    vertices, in order -- either winding direction). Points exactly on an
    edge may return either True or False (standard ray-casting ambiguity);
    this is not relied on anywhere in the rule engine."""
    if len(polygon) < 3:
        return False

    x, y = point
    inside = False
    n = len(polygon)
    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        if y > min(y1, y2):
            if y <= max(y1, y2):
                if x <= max(x1, x2):
                    if y1 != y2:
                        x_intersect = (y - y1) * (x2 - x1) / (y2 - y1) + x1
                    else:
                        x_intersect = x1
                    if x1 == x2 or x <= x_intersect:
                        inside = not inside
        x1, y1 = x2, y2
    return inside


def denormalize_polygon(
    normalized_polygon: list[tuple[float, float]], frame_width: int, frame_height: int
) -> list[tuple[float, float]]:
    """Converts a zone's stored normalized (0.0-1.0) polygon into pixel
    coordinates for the current frame's actual resolution."""
    return [(x * frame_width, y * frame_height) for x, y in normalized_polygon]


def euclidean_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
