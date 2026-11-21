"""
Light-weight values that render handlers put in the master list.

Handlers run before the nesting depth is known, so they return these markers
and ``ReportLabRenderer.join_item`` turns them into flowables. Each marker keeps
the shape the base renderer code expects: ``Tagged`` *is* a ``str``,
``CalcComponents`` *is* a ``list`` of ``str``, and ``Grid`` is neither (so it is
never mistaken for a line or a block).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class Tagged(str):
    """A whole-line string with a kind: 'heading', 'prose', 'import' or 'note'."""

    kind: str
    level: int

    def __new__(cls, text: str, kind: str, level: int = 0) -> "Tagged":
        obj = super().__new__(cls, text)
        obj.kind = kind
        obj.level = level
        return obj


class CalcComponents(list):
    """
    A rendered calc or expression line: ``[col, '=', col, '=', col, comment?]``.
    ``columns`` holds the value columns (target first) and ``comment`` the
    rendered inline comment, or None.
    """

    columns: list[str]
    comment: Optional[str]

    def __init__(self, components: list[str]) -> None:
        super().__init__(components)
        comps = list(components)
        # Columns interleave with the '=' sign, so the components of a line with
        # no comment always have an odd length; a trailing comment makes it even.
        self.comment = comps.pop() if len(comps) % 2 == 0 else None
        self.columns = comps[0::2]


@dataclass
class Grid:
    """A params grid ('params') or a multi-line calc grid ('calc')."""

    kind: str
    rows: list = field(default_factory=list)


# A 2-D array inside paragraph markup: ``MATRIX_OPEN + id + MATRIX_CLOSE``, where
# ``id`` keys the renderer's ``matrices`` (rows of cell markup). Paragraphs cannot
# hold a table, so value cells with a matrix are built as a ``MathRow``.
MATRIX_OPEN = ""
MATRIX_CLOSE = ""


@dataclass
class Fraction:
    """
    A stacked fraction inside paragraph markup. It shares the matrix token (the
    renderer's ``matrices`` holds either rows or a ``Fraction``), so every value
    cell that can draw a matrix can draw a fraction.
    The flags below say how to write it on one line (``a / b``, see
    ``flowables.inline_matrices``), for headers, plain lines and the layout
    used when a stacked line is too wide.
    """

    numerator: str
    denominator: str
    # Whether each operand needs brackets when the division is written inline.
    numerator_brackets: bool = False
    denominator_brackets: bool = False
    lpar: str = "("
    rpar: str = ")"
    # A floor division (``//``): drawn between floor brackets, ``⌊a/b⌋``.
    floor: bool = False
