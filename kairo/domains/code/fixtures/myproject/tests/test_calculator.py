# PROVENANCE: original | fixture project tests for code domain oracle
"""Tests for the calculator module — used by the code domain oracle."""

import sys
import os

# Add parent dir to path so we can import calculator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculator import add, subtract, multiply, divide, factorial


class TestAdd:
    def test_add_positive(self):
        assert add(2, 3) == 5

    def test_add_negative(self):
        assert add(-1, -1) == -2

    def test_add_zero(self):
        assert add(0, 0) == 0


class TestSubtract:
    def test_subtract_positive(self):
        assert subtract(5, 3) == 2

    def test_subtract_negative(self):
        assert subtract(-1, -1) == 0


class TestMultiply:
    def test_multiply_positive(self):
        assert multiply(3, 4) == 12

    def test_multiply_zero(self):
        assert multiply(5, 0) == 0


class TestDivide:
    def test_divide_exact(self):
        assert divide(10, 2) == 5.0

    def test_divide_by_zero(self):
        import pytest

        with pytest.raises(ZeroDivisionError):
            divide(1, 0)


class TestFactorial:
    def test_factorial_zero(self):
        assert factorial(0) == 1

    def test_factorial_one(self):
        assert factorial(1) == 1

    def test_factorial_five(self):
        assert factorial(5) == 120

    def test_factorial_negative(self):
        import pytest

        with pytest.raises(ValueError):
            factorial(-1)
