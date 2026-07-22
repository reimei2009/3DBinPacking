"""Shared six-direction separation labels for fixed-orientation cuboids."""

from enum import Enum


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    FRONT = "front"
    BACK = "back"
    BELOW = "below"
    ABOVE = "above"


DIRECTIONS = tuple(Direction)
