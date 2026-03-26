"""
Unit tests for the calculator module.
"""

import unittest
from calculator import add, subtract, multiply, divide


class TestCalculator(unittest.TestCase):
    """Test cases for calculator functions."""

    def test_add(self):
        """Test the add function."""
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)
        self.assertEqual(add(0, 0), 0)
        self.assertEqual(add(1.5, 2.5), 4.0)

    def test_subtract(self):
        """Test the subtract function."""
        self.assertEqual(subtract(5, 3), 2)
        self.assertEqual(subtract(-1, 1), -2)
        self.assertEqual(subtract(0, 0), 0)
        self.assertEqual(subtract(5.5, 2.5), 3.0)

    def test_multiply(self):
        """Test the multiply function."""
        self.assertEqual(multiply(2, 3), 6)
        self.assertEqual(multiply(-2, 3), -6)
        self.assertEqual(multiply(0, 5), 0)
        self.assertEqual(multiply(1.5, 2), 3.0)

    def test_divide(self):
        """Test the divide function."""
        self.assertEqual(divide(6, 3), 2)
        self.assertEqual(divide(-6, 3), -2)
        self.assertEqual(divide(5, 2), 2.5)

    def test_divide_by_zero(self):
        """Test that division by zero raises ValueError."""
        with self.assertRaises(ValueError) as context:
            divide(5, 0)
        self.assertEqual(str(context.exception), "Cannot divide by zero")


if __name__ == "__main__":
    unittest.main()
