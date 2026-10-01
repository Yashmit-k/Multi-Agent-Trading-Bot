"""Deliberately illegal feature arithmetic for the scanner self-test."""

from __future__ import annotations

import math
import operator
import statistics

import numpy
import pandas

value = 1 + 2
value += 3
neg = -value
total = sum([1, 2])
magnitude = abs(-4)
lo = min(1, 2)
hi = max(1, 2)
rounded = round(1.2)
power = pow(2, 3)
q, r = divmod(7, 3)
folded = math.fsum([1.0, 2.0])
