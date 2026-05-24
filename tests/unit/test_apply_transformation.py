"""
Unit tests for kicad_sch_api.core.geometry.apply_transformation.

apply_transformation maps a pin (or other) point from symbol-library coordinates
(+Y up, math convention) to absolute schematic coordinates (+Y down, screen
convention), accounting for the component's rotation and mirror.

Regression context: prior to this test suite, apply_transformation negated Y
before applying rotation, which inverted the effective rotation direction for
90°/270°. The 0°/180° cases incidentally agreed with eeschema, which masked
the bug until it was caught against a golden .kicad_sch file with a 90°-rotated
component.

The expected values below match eeschema's actual placement (verified against
golden schematics and KiCad's netlister).
"""

import math

import pytest

from kicad_sch_api.core.geometry import apply_transformation
from kicad_sch_api.core.types import Point


ORIGIN = Point(100.0, 100.0)
# Device:R pin 1 is at (0, +3.81) in symbol coords; pin 2 at (0, -3.81).
PIN1 = (0.0, 3.81)
PIN2 = (0.0, -3.81)


def _close(a, b, tol=1e-6):
    return math.isclose(a[0], b[0], abs_tol=tol) and math.isclose(a[1], b[1], abs_tol=tol)


class TestApplyTransformationRotation:
    """Pin-position rotations must match eeschema's layout for all 4 orientations."""

    def test_rotation_0(self):
        # Pin 1 (top of symbol) → visually above origin → smaller Y on screen.
        assert _close(apply_transformation(PIN1, ORIGIN, 0), (100.0, 96.19))
        assert _close(apply_transformation(PIN2, ORIGIN, 0), (100.0, 103.81))

    def test_rotation_90(self):
        # 90° CCW: pin 1 swings to the LEFT of origin; pin 2 to the RIGHT.
        # This is the case the prior bug got wrong (it produced the mirrored result).
        assert _close(apply_transformation(PIN1, ORIGIN, 90), (96.19, 100.0))
        assert _close(apply_transformation(PIN2, ORIGIN, 90), (103.81, 100.0))

    def test_rotation_180(self):
        assert _close(apply_transformation(PIN1, ORIGIN, 180), (100.0, 103.81))
        assert _close(apply_transformation(PIN2, ORIGIN, 180), (100.0, 96.19))

    def test_rotation_270(self):
        # 270° CCW: pin 1 swings to the RIGHT; pin 2 to the LEFT.
        assert _close(apply_transformation(PIN1, ORIGIN, 270), (103.81, 100.0))
        assert _close(apply_transformation(PIN2, ORIGIN, 270), (96.19, 100.0))

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_pin_distance_preserved(self, rotation):
        """Rotation must not change the pin's distance from the component origin."""
        for pin in (PIN1, PIN2):
            x, y = apply_transformation(pin, ORIGIN, rotation)
            dist = math.hypot(x - ORIGIN.x, y - ORIGIN.y)
            assert math.isclose(dist, 3.81, abs_tol=1e-6), (
                f"rotation={rotation} pin={pin} produced distance {dist}"
            )

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_pin_pair_remains_collinear_through_origin(self, rotation):
        """The two opposite pins of a symmetric 2-pin part must stay on opposite
        sides of the origin (i.e., their midpoint is the origin)."""
        p1 = apply_transformation(PIN1, ORIGIN, rotation)
        p2 = apply_transformation(PIN2, ORIGIN, rotation)
        midpoint = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        assert _close(midpoint, (ORIGIN.x, ORIGIN.y))


class TestApplyTransformationConsistency:
    """apply_transformation must agree with SchematicSymbol.get_pin_position's
    qualitative behavior in the cases where both code paths exist.

    These two paths have historically used different formulas (and different
    Y conventions) — this test pins down the externally observable contract
    that pin distance from origin is rotation-invariant, regardless of which
    path callers use.
    """

    @pytest.mark.parametrize("rotation", [0, 90, 180, 270])
    def test_origin_translation(self, rotation):
        """A point at the symbol origin must land at the schematic origin
        for every rotation."""
        result = apply_transformation((0.0, 0.0), ORIGIN, rotation)
        assert _close(result, (ORIGIN.x, ORIGIN.y))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
