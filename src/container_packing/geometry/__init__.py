"""Backend-neutral geometric calculations shared by algorithms and validators."""

from .support import SupportGeometry, evaluate_support, rectangle_union_area

__all__ = ["SupportGeometry", "evaluate_support", "rectangle_union_area"]
