"""Metrology verdict recomputation following ISO/IEC 17025 principles.

Implements Section 6.2 of docs/PLAN.md:
Sign convention:
  e = as-found error = reading - true value
  true = reading - e
  x' = x - e
  Interval: [x' - U, x' + U]

Decision rule:
  pass          if [x' - U, x' + U] is inside [lo, hi]
  fail          if [x' - U, x' + U] is disjoint from [lo, hi]
  indeterminate otherwise (guard-band overlap)
"""

from decimal import Decimal as D
from typing import Tuple, Union


def recompute_verdict(
    value: Union[float, int, str, D],
    lo: Union[float, int, str, D],
    hi: Union[float, int, str, D],
    e: Union[float, int, str, D],
    U: Union[float, int, str, D],
) -> str:
    """Recomputes a measurement pass/fail/indeterminate verdict under error e and uncertainty U.

    Uses Decimal conversion to prevent floating point inaccuracies at boundary limits.
    """
    x = D(str(value)) - D(str(e))
    u = D(str(U))
    lo_dec = D(str(lo))
    hi_dec = D(str(hi))

    low = x - u
    high = x + u

    # Completely inside tolerance interval [lo, hi]
    if low >= lo_dec and high <= hi_dec:
        return "pass"

    # Disjoint from tolerance interval [lo, hi]
    if high < lo_dec or low > hi_dec:
        return "fail"

    # Overlaps tolerance boundary
    return "indeterminate"


def get_corrected_interval(
    value: Union[float, int, str, D],
    e: Union[float, int, str, D],
    U: Union[float, int, str, D],
) -> Tuple[float, float]:
    """Returns the corrected (low, high) measurement interval [x' - U, x' + U] as floats."""
    x = D(str(value)) - D(str(e))
    u = D(str(U))
    return float(x - u), float(x + u)

