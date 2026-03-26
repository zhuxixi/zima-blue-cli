"""Tests for calculator module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from calculator import add, subtract, multiply, divide


def test_add():
    """Test add function."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_subtract():
    """Test subtract function."""
    assert subtract(5, 3) == 2
    assert subtract(0, 5) == -5
    assert subtract(10, 10) == 0


def test_multiply():
    """Test multiply function."""
    assert multiply(2, 3) == 6
    assert multiply(-2, 3) == -6
    assert multiply(0, 100) == 0


def test_divide():
    """Test divide function."""
    assert divide(6, 2) == 3
    assert divide(5, 2) == 2.5
    assert divide(0, 5) == 0


def test_divide_by_zero():
    """Test divide by zero raises error."""
    try:
        divide(5, 0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert str(e) == "Cannot divide by zero"


if __name__ == "__main__":
    test_add()
    test_subtract()
    test_multiply()
    test_divide()
    test_divide_by_zero()
    print("All tests passed!")
