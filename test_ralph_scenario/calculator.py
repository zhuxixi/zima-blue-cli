"""
Simple Calculator Module

This module provides basic arithmetic operations including
addition, subtraction, multiplication, and division.
"""


def add(a, b):
    """
    Add two numbers.

    Args:
        a (int or float): The first number.
        b (int or float): The second number.

    Returns:
        int or float: The sum of a and b.
    """
    return a + b


def subtract(a, b):
    """
    Subtract two numbers.

    Args:
        a (int or float): The first number.
        b (int or float): The second number.

    Returns:
        int or float: The difference of a and b.
    """
    return a - b


def multiply(a, b):
    """
    Multiply two numbers.

    Args:
        a (int or float): The first number.
        b (int or float): The second number.

    Returns:
        int or float: The product of a and b.
    """
    return a * b


def divide(a, b):
    """
    Divide two numbers.

    Args:
        a (int or float): The dividend.
        b (int or float): The divisor.

    Returns:
        int or float: The quotient of a and b.

    Raises:
        ValueError: If b is zero (division by zero).
    """
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
