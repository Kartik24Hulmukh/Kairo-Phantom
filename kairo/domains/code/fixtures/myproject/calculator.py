# PROVENANCE: original | fixture project for code domain oracle tests
"""Calculator module — a self-contained stdlib-only Python project for code domain fixtures."""


def add(a: int, b: int) -> int:
    """Return the sum of a and b."""
    return a + b


def subtract(a: int, b: int) -> int:
    """Return the difference of a and b."""
    return a - b


def multiply(a: int, b: int) -> int:
    """Return the product of a and b."""
    return a * b


def divide(a: int, b: int) -> float:
    """Return the quotient of a divided by b.

    Raises:
        ZeroDivisionError: If b is 0.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def factorial(n: int) -> int:
    """Return the factorial of n.

    Raises:
        ValueError: If n is negative.
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    if n <= 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
