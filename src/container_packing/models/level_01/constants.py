"""Shared constants for the Level 1 formulation."""

from enum import Enum


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    FRONT = "front"
    BACK = "back"
    BELOW = "below"
    ABOVE = "above"


DIRECTIONS: tuple[Direction, ...] = tuple(Direction)
MM3_PER_M3 = 1_000_000_000.0
