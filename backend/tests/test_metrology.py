"""Unit tests for validity/metrology.py.

Covers Section 6.2 and Section 14 (M2 acceptance check).
Pure deterministic Python - does not require a database connection.
"""

import pytest
from backend.app.validity.metrology import recompute_verdict, get_corrected_interval


@pytest.mark.parametrize(
    "value,lo,hi,e,U,expected_verdict,expected_low,expected_high",
    [
        # Standard worked examples for Ø32H7 (32.000 to 32.025 mm)
        # e = +0.006 mm, U = 0.002 mm
        (32.012, 32.000, 32.025, 0.006, 0.002, "pass", 32.004, 32.008),
        (32.007, 32.000, 32.025, 0.006, 0.002, "indeterminate", 31.999, 32.003),
        (32.003, 32.000, 32.025, 0.006, 0.002, "fail", 31.995, 31.999),
        # Boundary cases:
        # low == lo: x' = 32.002, low = 32.000 == lo, high = 32.004 <= hi -> pass
        (32.008, 32.000, 32.025, 0.006, 0.002, "pass", 32.000, 32.004),
        # Slightly below boundary: low = 31.9999 < lo -> indeterminate
        (32.0079, 32.000, 32.025, 0.006, 0.002, "indeterminate", 31.9999, 32.0039),
        # high == lo: touches tolerance limit from outside -> indeterminate
        (32.004, 32.000, 32.025, 0.006, 0.002, "indeterminate", 31.996, 32.000),
        # strictly below lo: high < lo -> fail
        (32.0039, 32.000, 32.025, 0.006, 0.002, "fail", 31.9959, 31.9999),
        # above hi: x' = 32.034, interval [32.032, 32.036] strictly above hi=32.025 -> fail
        (32.040, 32.000, 32.025, 0.006, 0.002, "fail", 32.032, 32.036),
        # normal inside high range: x' = 32.018, [32.016, 32.020] -> pass
        (32.024, 32.000, 32.025, 0.006, 0.002, "pass", 32.016, 32.020),
        # Negative error (gauge reads low by 0.006 mm): e = -0.006, x' = 32.002 - (-0.006) = 32.008
        # interval: [32.006, 32.010] in [32.000, 32.025] -> pass
        (32.002, 32.000, 32.025, -0.006, 0.002, "pass", 32.006, 32.010),
    ],
)
def test_recompute_verdict_table(value, lo, hi, e, U, expected_verdict, expected_low, expected_high):
    verdict = recompute_verdict(value, lo, hi, e, U)
    assert verdict == expected_verdict

    low, high = get_corrected_interval(value, e, U)
    assert pytest.approx(low, abs=1e-6) == expected_low
    assert pytest.approx(high, abs=1e-6) == expected_high


def test_upper_boundary_conditions():
    # Ø32H7: lo=32.000, hi=32.025, e=0, U=0.002
    # Upper boundary touches from inside: high == hi -> pass
    # x' = 32.023, high = 32.025 == hi, low = 32.021 >= lo -> pass
    assert recompute_verdict(32.023, 32.000, 32.025, 0.0, 0.002) == "pass"

    # Upper boundary touches from outside: low == hi -> indeterminate
    # x' = 32.027, low = 32.025 == hi, high = 32.029 -> indeterminate
    assert recompute_verdict(32.027, 32.000, 32.025, 0.0, 0.002) == "indeterminate"

    # Strictly above upper boundary: low > hi -> fail
    # x' = 32.028, low = 32.026 > 32.025 -> fail
    assert recompute_verdict(32.028, 32.000, 32.025, 0.0, 0.002) == "fail"

