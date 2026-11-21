"""Decimal helpers shared by recipe expansion and warehouse allocation.

Kept free of third-party imports so the allocation rules stay testable
with the standard library alone.
"""

from decimal import Decimal, localcontext

ZERO = Decimal(0)


def text_of(number):
    """Format a Decimal as plain decimal text without trailing zeros."""
    fixed = format(number, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def allocate(demand, declared, remaining):
    """Occupiable quantity for one batch.

    A batch occupies at most what it needs (demand), what its own stock
    fill declared (declared) and what the shared warehouse still has
    (remaining); never below zero.
    """
    return max(min(demand, declared, remaining), ZERO)


def shortage(demand, occupied):
    """Purchase gap: the part of demand not covered by actual occupation."""
    return max(demand - occupied, ZERO)


def packages(gap, pack):
    """Whole packages needed to cover the gap, and the order quantity."""
    with localcontext() as context:
        context.prec = 60
        count, remainder = divmod(gap, pack)
        count = int(count) + int(remainder > 0)
        return count, count * pack
