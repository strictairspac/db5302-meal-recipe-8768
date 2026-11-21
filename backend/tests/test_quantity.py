"""Stdlib tests for the shared allocation rules (no third-party deps)."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils.quantity import allocate, packages, shortage, text_of


class TextOfTest(unittest.TestCase):
    def test_strips_trailing_zeros(self):
        self.assertEqual(text_of(Decimal("15.000")), "15")
        self.assertEqual(text_of(Decimal("0.150")), "0.15")
        self.assertEqual(text_of(Decimal("10.490")), "10.49")

    def test_keeps_integers_and_zero(self):
        self.assertEqual(text_of(Decimal(3)), "3")
        self.assertEqual(text_of(Decimal("0")), "0")


class AllocateTest(unittest.TestCase):
    def test_limited_by_demand_declared_and_remaining(self):
        self.assertEqual(allocate(Decimal("25.49"), Decimal(15), Decimal(20)), Decimal(15))
        self.assertEqual(allocate(Decimal("25.49"), Decimal(15), Decimal("10.5")), Decimal("10.5"))
        self.assertEqual(allocate(Decimal("4.2"), Decimal(15), Decimal(20)), Decimal("4.2"))

    def test_never_negative_when_warehouse_is_overdrawn(self):
        self.assertEqual(allocate(Decimal("25.49"), Decimal(15), Decimal("-3")), Decimal(0))

    def test_same_bag_filled_twice_does_not_double(self):
        # 两批各填 15 kg（同一袋料），仓库现存取最大可见量 15，
        # 第一批占满后第二批只能占到 0。
        on_hand = max(Decimal(15), Decimal(15))
        first = allocate(Decimal("25.49"), Decimal(15), on_hand)
        second = allocate(Decimal("19.47"), Decimal(15), on_hand - first)
        self.assertEqual((first, second), (Decimal(15), Decimal(0)))


class ShortageTest(unittest.TestCase):
    def test_gap_uses_actual_occupation(self):
        self.assertEqual(shortage(Decimal("25.49"), Decimal(15)), Decimal("10.49"))
        self.assertEqual(shortage(Decimal("25.49"), Decimal("5.5")), Decimal("19.99"))

    def test_never_negative(self):
        self.assertEqual(shortage(Decimal(3), Decimal(5)), Decimal(0))


class PackagesTest(unittest.TestCase):
    def test_rounds_up_to_whole_packs(self):
        count, quantity = packages(Decimal("10.49"), Decimal(5))
        self.assertEqual((count, quantity), (3, Decimal(15)))

    def test_zero_gap_needs_no_pack(self):
        self.assertEqual(packages(Decimal(0), Decimal(5)), (0, Decimal(0)))

    def test_exact_multiple(self):
        self.assertEqual(packages(Decimal(4), Decimal(2)), (2, Decimal(4)))


if __name__ == "__main__":
    unittest.main()
