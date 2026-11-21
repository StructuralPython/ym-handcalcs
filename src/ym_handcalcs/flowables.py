"""Custom flowables used by the ReportLab renderer."""
from __future__ import annotations

import re

from reportlab.lib.colors import HexColor
from reportlab.platypus import Flowable, Paragraph, Table

from .breaking import NBSP
from .markers import MATRIX_CLOSE, MATRIX_OPEN, Fraction


# ``# hc: --boxed``: the result is set between two ``<onDraw>`` marks (see
# ``box_marks``). ReportLab calls the callback at each mark while it draws the
# text, with the text position; the closing mark draws the box. ``BoxTable``
# registers the callback on the canvas, so every table of calc cells can draw it.
BOX_CALLBACK = "hcBox"


def box_marks(color: str) -> tuple[str, str]:
    """The markup put around a boxed result, drawing a box in ``color``."""
    return (
        f'<onDraw name="{BOX_CALLBACK}" label="open"/>',
        f'<onDraw name="{BOX_CALLBACK}" label="close {color}"/>',
    )


def draw_box(canv, kind: str, label: str) -> None:
    """The ``<onDraw>`` callback of ``box_marks``."""
    info = canv._curr_tx_info
    x, y, tx = info["cur_x"], info["cur_y"], info["tx"]
    if label == "open":
        canv._hc_box_start = (x, y)
        return
    start = getattr(canv, "_hc_box_start", None)
    canv._hc_box_start = None
    if start is None:
        return
    # A result that wrapped is boxed on its last line, from the line's start.
    x0 = start[0] if start[1] == y else tx._x0
    size = tx._fontsize or info["xs"].style.fontSize
    leading = info["leading"]
    # Just outside the band a result's highlight fills (one leading tall, its
    # top a font size above the baseline), which is painted after this box.
    pad, gap = 0.25 * size, 0.6
    canv.saveState()
    canv.setStrokeColor(HexColor(label.partition(" ")[2] or "#000000"))
    canv.setLineWidth(0.6)
    canv.rect(x0 - pad, y + size - leading - gap, x - x0 + 2 * pad, leading + 2 * gap,
              stroke=1, fill=0)
    canv.restoreState()


class BoxTable(Table):
    """A table whose cells may hold boxed results (``box_marks``); its split parts are too."""

    def draw(self):
        self.canv.setNamedCB(BOX_CALLBACK, draw_box)
        super().draw()


def natural_width(paragraph: Paragraph) -> float:
    """Width of the widest line of ``paragraph`` when it is not wrapped."""
    paragraph.wrap(1e6, 1e6)
    return max(paragraph.getActualLineWidths0() or [0.0])


def fits_width(paragraph: Paragraph, width: float) -> bool:
    """
    True if ``paragraph`` wrapped at ``width`` has no line wider than the space
    that line has (the first line is offset by ``firstLineIndent``).
    """
    style = paragraph.style
    paragraph.wrap(width, 1e6)
    widths = paragraph.getActualLineWidths0() or [0.0]
    for idx, line_width in enumerate(widths):
        indent = style.leftIndent + (style.firstLineIndent if idx == 0 else 0)
        if line_width > width - indent - style.rightIndent + 0.01:
            return False
    return True


class Chip(Flowable):
    """
    A paragraph on a rounded background that is only as wide as its text (up to
    the frame width, where it wraps). Used for imports.
    """

    def __init__(self, paragraph: Paragraph, background, radius: float = 2.5, pad: tuple[float, float] = (3.0, 2.0)):
        super().__init__()
        self.paragraph = paragraph
        self.background = background
        self.radius = radius
        self.pad_x, self.pad_y = pad
        style = paragraph.style
        self.spaceBefore = style.spaceBefore
        self.spaceAfter = style.spaceAfter

    def wrap(self, avail_width, avail_height):
        inner = min(natural_width(self.paragraph) + 0.5, avail_width - 2 * self.pad_x)
        self._inner_width, self._inner_height = self.paragraph.wrap(inner, avail_height)
        self.width = self._inner_width + 2 * self.pad_x
        self.height = self._inner_height + 2 * self.pad_y
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(self.background)
        canvas.roundRect(0, 0, self.width, self.height, self.radius, stroke=0, fill=1)
        canvas.restoreState()
        self.paragraph.drawOn(canvas, self.pad_x, self.pad_y)


class DepthGuides(Flowable):
    """
    Indent ``content`` by ``depth`` levels and draw one thin vertical guide per
    enclosing level in the left margin, like the indent guides of a code
    editor. Each guide also runs through the content's ``spaceBefore`` and
    ``spaceAfter``, so the guides of consecutive lines join into one line.

    The story stays flat (no nested tables), so nested blocks still split across
    pages: ``split`` splits the content and wraps each part again.
    """

    def __init__(self, content: Flowable, depth: int, indent: float, colors: list, line_width: float = 0.8):
        super().__init__()
        self.content = content
        self.depth = depth
        self.indent = indent
        self.colors = colors
        self.line_width = line_width
        self.keepWithNext = content.getKeepWithNext()

    @property
    def offset(self) -> float:
        return self.depth * self.indent

    def _canvas(self):
        return getattr(self, "canv", None)

    def wrap(self, avail_width, avail_height):
        canvas = self._canvas()
        inner = avail_width - self.offset
        if canvas is not None:
            width, height = self.content.wrapOn(canvas, inner, avail_height)
        else:
            width, height = self.content.wrap(inner, avail_height)
        self.width, self.height = width + self.offset, height
        return self.width, self.height

    def split(self, avail_width, avail_height):
        canvas = self._canvas()
        inner = avail_width - self.offset
        if canvas is not None:
            parts = self.content.splitOn(canvas, inner, avail_height)
        else:
            parts = self.content.split(inner, avail_height)
        return [DepthGuides(part, self.depth, self.indent, self.colors, self.line_width) for part in parts]

    def getSpaceBefore(self):
        return self.content.getSpaceBefore()

    def getSpaceAfter(self):
        return self.content.getSpaceAfter()

    def draw(self):
        canvas = self.canv
        bottom = -self.content.getSpaceAfter()
        top = self.height + self.content.getSpaceBefore()
        canvas.saveState()
        canvas.setLineWidth(self.line_width)
        for level in range(1, self.depth + 1):
            x = (level - 1) * self.indent + self.indent * 0.35
            canvas.setStrokeColor(self.colors[(level - 1) % len(self.colors)])
            canvas.line(x, bottom, x, top)
        canvas.restoreState()
        self.content.drawOn(canvas, self.offset, 0)


class _TableHost(Flowable):
    """
    Base for flowables that build a ``Table`` in ``wrap`` (when the frame width
    is known), then draw, split and space as that table.
    """

    align = "LEFT"

    def __init__(self, space_before: float = 0.0, space_after: float = 0.0):
        super().__init__()
        # The frame aligns a flowable by its ``hAlign`` (an instance attribute
        # set by ``Flowable.__init__``, so it must be set after it).
        self.hAlign = self.align
        self.spaceBefore = space_before
        self.spaceAfter = space_after
        self._table: Table | None = None

    def build_table(self, avail_width: float) -> Table:
        raise NotImplementedError

    def wrap(self, avail_width, avail_height):
        self._table = self.build_table(avail_width)
        self.width, self.height = self._table.wrap(avail_width, avail_height)
        return self.width, self.height

    def split(self, avail_width, avail_height):
        table = self.build_table(avail_width)
        return table.split(avail_width, avail_height)

    def draw(self):
        self._table.drawOn(self.canv, 0, 0)


def _column_widths(rows: list[list[Paragraph]], pad: float) -> list[float]:
    ncols = max((len(row) for row in rows), default=0)
    return [
        max((natural_width(row[c]) for row in rows if c < len(row)), default=0.0) + 2 * pad + 0.5
        for c in range(ncols)
    ]


class ParamGrid(_TableHost):
    """
    A params grid: ``id = value [comment]`` groups aligned on ``=``, centred.

    ``rows`` are handcalcs' grid rows (``None`` pads a short row). The grid keeps
    them: a ``;`` grid has the rows of its source, a ``# hc: -g`` grid rows of
    ``param_cols``. When the grid is too wide it steps down to fewer groups per row,
    to 1: a uniform grid (every row but the last as long as the first) reflows as a
    whole, and an uneven one splits each long row in place, so its rows stay apart.
    """

    align = "CENTER"

    def __init__(self, rows: list, styles: dict, table_style, gap: float,
                 pad: float, zebra=None, space_before: float = 0.0, space_after: float = 0.0,
                 matrices: dict | None = None):
        super().__init__(space_before, space_after)
        self.matrices = matrices
        self.rows = [[cell for cell in row if cell is not None] for row in rows]
        self.rows = [row for row in self.rows if row]
        self.cells = [cell for row in self.rows for cell in row]
        self.cols = max((len(row) for row in self.rows), default=1)
        self.uniform = all(len(row) == self.cols for row in self.rows[:-1])
        self.styles = styles
        self.table_style = table_style
        self.gap = gap
        self.pad = pad
        self.zebra = zebra
        self.with_comments = any(len(cell) > 3 and cell[3] for cell in self.cells)
        self.cols_used = self.cols

    def _cell_paragraphs(self, cell) -> list[Flowable]:
        parts = [str(part) for part in cell] + ["", "", "", ""]
        ident, eq, val, comment = parts[:4]
        paras = [
            Paragraph(ident, self.styles["right"]),
            Paragraph(eq, self.styles["center"]),
            value_cell(val, self.styles["left"], self.matrices),
        ]
        if self.with_comments:
            paras.append(Paragraph(comment, self.styles["comment"]))
        return paras

    def groups(self, cols: int) -> list[list]:
        """The cells of each table row, at no more than ``cols`` groups per row."""
        source = [self.cells] if self.uniform else self.rows
        return [row[k:k + cols] for row in source for k in range(0, len(row), cols)]

    def _table_for(self, cols: int) -> Table:
        per_cell = 4 if self.with_comments else 3
        groups = self.groups(cols)
        rows = []
        for group in groups:
            row: list = []
            for idx in range(cols):
                if idx:
                    row.append("")  # spacer column between groups
                if idx < len(group):
                    row.extend(self._cell_paragraphs(group[idx]))
                else:
                    row.extend([""] * per_cell)
            rows.append(row)
        para_rows = [[c if isinstance(c, Flowable) else Paragraph("", self.styles["left"]) for c in r] for r in rows]
        widths = _column_widths(para_rows, self.pad)
        spacer_cols = [idx * (per_cell + 1) - 1 for idx in range(1, cols)]
        for col in spacer_cols:
            widths[col] = self.gap
        commands = list(self.table_style.getCommands())
        if self.zebra is not None and len(rows) > 2:
            commands.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [None, self.zebra]))
        return BoxTable(rows, colWidths=widths, style=commands, hAlign=self.align)

    def build_table(self, avail_width: float) -> Table:
        for cols in range(min(self.cols, max(1, len(self.cells))), 0, -1):
            table = self._table_for(cols)
            width, _ = table.wrap(avail_width, 1e6)
            if width <= avail_width + 0.01 or cols == 1:
                self.cols_used = cols
                return table
        raise AssertionError("unreachable")


def _scaled(style, scale: float):
    if scale == 1:
        return style
    return style.clone(
        f"{style.name}@{scale:g}",
        fontSize=style.fontSize * scale,
        leading=style.leading * scale,
        leftIndent=style.leftIndent * scale,
        firstLineIndent=style.firstLineIndent * scale,
    )


class BreakingParagraph(Flowable):
    """
    A paragraph that wraps only at its best-ranked break points
    (``breaking.ranked_breaks``), allowing worse ones only when a piece between
    breaks is still wider than the frame. Used for block headers, which it can
    also set on a rounded ``background`` (drawn here rather than with the
    style's ``backColor`` so a hanging indent stays inside the box).
    """

    def __init__(self, markup: str, style, background=None, radius: float = 3.0,
                 pad: tuple[float, float] = (4.0, 2.5)):
        super().__init__()
        self.markup = markup
        self.style = style
        self.background = background
        self.radius = radius
        self.pad_x, self.pad_y = pad if background is not None else (0.0, 0.0)
        self.spaceBefore = style.spaceBefore
        self.spaceAfter = style.spaceAfter
        self.keepWithNext = getattr(style, "keepWithNext", 0)
        self._paragraph: Paragraph | None = None

    def _choose(self, inner_width: float) -> Paragraph:
        from .breaking import max_rank, with_breaks

        for rank in range(0, max_rank(self.markup) + 1):
            paragraph = Paragraph(with_breaks(self.markup, rank), self.style)
            if fits_width(paragraph, inner_width):
                return paragraph
        return Paragraph(self.markup, self.style)

    def wrap(self, avail_width, avail_height):
        inner = avail_width - 2 * self.pad_x
        self._paragraph = self._choose(inner)
        _, height = self._paragraph.wrap(inner, avail_height)
        self.width, self.height = avail_width, height + 2 * self.pad_y
        return self.width, self.height

    def split(self, avail_width, avail_height):
        if self.background is not None:
            return []  # a callout header is short; keep it whole
        return self._choose(avail_width).split(avail_width, avail_height)

    def draw(self):
        if self.background is not None:
            canvas = self.canv
            canvas.saveState()
            canvas.setFillColor(self.background)
            canvas.roundRect(0, 0, self.width, self.height, self.radius, stroke=0, fill=1)
            canvas.restoreState()
        self._paragraph.drawOn(self.canv, self.pad_x, self.pad_y)


class CalcLine(Flowable):
    """
    One calc line, laid out as rows of a three-column table aligned on ``=``:
    ``target | = | value``. A line picks its layout when it learns the frame
    width; inside a ``CalcBlock`` it shares the target column width with the
    other lines of its run, so their ``=`` signs line up.

    ``columns`` are ``[target, sym, num, result]`` (or fewer) as paragraph
    markup; ``comment`` is the styled inline comment or None. It always ends
    the line's last row, so it never reads as part of the next line. The
    layouts are tried in order and the first that fits is kept:

    1. ``line``: one row, ``target = sym = num = result`` (skipped when
       ``forced_grid``, i.e. ``# hc: -m``);
    2. ``grid``: one row per value, each starting with ``=``, no wrapping;
    3. ``grid:breakN``: wrap value cells at break points up to rank N;
       then ``stack`` / ``stack:breakN``: the same with the target on a row of
       its own (for a target too wide for the target column);
    4. ``grid:elided``: long collections shortened around an ellipsis;
    5. ``shrink``: the above at ``min_scale`` font size;
    6. ``overflow``: the last attempt, wider than the frame.

    The numeric substitution row is never dropped here; that is the author's
    call, per line, with ``# hc: mode="no_num"``.

    ``layout`` records the choice (for the overflow report and tests). On its
    own (outside a block) the line wraps and draws its rows as a table.
    """

    def __init__(self, columns: list[str], comment, *, forced_grid: bool, styles: dict,
                 result_markup, table_style, pad: float,
                 min_scale: float = 0.85, matrices: dict | None = None):
        super().__init__()
        self.columns = list(columns)
        # Rows of cell markup for the matrix tokens in ``columns`` (see ``MathRow``).
        self.matrices = matrices
        self.comment = comment or ""
        self.forced_grid = forced_grid
        self.styles = styles
        self.result_markup = result_markup
        self.table_style = table_style
        self.pad = pad
        self.min_scale = min_scale
        self.has_result = len(self.columns) >= 3
        line_style = styles["line"]
        self.spaceBefore = line_style.spaceBefore
        self.spaceAfter = line_style.spaceAfter
        self.layout = ""
        self._table = None
        self._cache: dict = {}

    # -- markup ---------------------------------------------------------

    def _values(self, columns: list[str], transform) -> list[str]:
        values = [transform(col) for col in columns]
        if self.has_result and len(values) >= 3:
            values[-1] = self.result_markup(values[-1])
        return values

    # -- column widths ----------------------------------------------------

    def target_width(self) -> float:
        """Natural width of the target cell, padding included (0 without a target)."""
        if len(self.columns) < 2:
            return 0.0
        target = self._values(self.columns, lambda m: m)[0]
        return natural_width(Paragraph(target, self.styles["right"])) + 2 * self.pad + 0.5

    def eq_width(self) -> float:
        return natural_width(Paragraph("=", self.styles["center"])) + 2 * self.pad + 0.5

    # -- layouts ----------------------------------------------------------

    def _rows(self, avail_width: float, id_width: float, columns: list[str], transform,
              kind: str, scale: float = 1.0):
        """
        The cells of one layout and whether it fits. ``kind`` is ``line``,
        ``grid`` or ``stack`` (the target on a row of its own). Returns ``(cells, commands, fits)``; ``commands`` are extra table
        commands with row numbers relative to this line.
        """
        right = _scaled(self.styles["right"], scale)
        center = _scaled(self.styles["center"], scale)
        value_style = _scaled(self.styles["value"], scale)
        values = self._values(columns, transform)
        if len(values) == 1:
            rows = [["", "", values[0]]]
        elif kind == "line":
            rows = [[values[0], "=", " = ".join(values[1:])]]
        elif kind == "stack":
            rows = [[values[0], "", ""]] + [["", "=", value] for value in values[1:]]
        else:
            rows = [[values[0], "=", values[1]]] + [["", "=", value] for value in values[2:]]
        if self.comment:
            rows[-1][2] = f"{rows[-1][2]} {self.comment}"
        cells = [
            [Paragraph(i, right) if i else "", Paragraph(e, center) if e else "",
             value_cell(v, value_style, self.matrices)]
            for i, e, v in rows
        ]
        commands = []
        value_rows = cells
        eq_width = self.eq_width()
        inner = avail_width - id_width - eq_width - 2 * self.pad
        if kind == "stack":
            cells[0] = [Paragraph(rows[0][0], value_style), "", ""]
            commands.append(("SPAN", (0, 0), (-1, 0)))
            target_fits = fits_width(cells[0][0], avail_width - 2 * self.pad)
            value_rows = cells[1:]
        elif isinstance(cells[0][0], Paragraph):
            target_fits = natural_width(cells[0][0]) <= id_width - 2 * self.pad + 0.01
        else:
            target_fits = True
        # A row holding a matrix is centred on it, so its target and '=' sit at
        # the matrix's middle, level with the text around the matrix.
        for idx, row in enumerate(cells):
            if isinstance(row[2], MathRow):
                commands.append(("VALIGN", (0, idx), (-1, idx), "MIDDLE"))
        if kind == "line":
            # A one-row layout must fit without wrapping at all.
            fits = target_fits and inner > 0 and natural_width(value_rows[0][2]) <= inner + 0.01
        else:
            fits = target_fits and inner > 0 and all(fits_width(row[2], inner) for row in value_rows)
        return cells, commands, fits

    def _attempts(self, avail_width: float, id_width: float):
        from .breaking import elide_collections, max_rank, unbreakable, with_breaks

        if not self.forced_grid:
            yield "line", lambda s: self._rows(avail_width, id_width, self.columns, unbreakable, "line", s)
        column_sets = [("", self.columns)]
        elided = [elide_collections(col) for col in self.columns]
        if elided != self.columns:
            column_sets.append((":elided", elided))
        # Stacked fractions never wrap: a value too wide for them writes them inline.
        # First only in the values that do not fit on a row of their own (often the
        # numeric substitution), then everywhere.
        if any(has_fraction(col, self.matrices) for col in self.columns):
            flat = [inline_fractions(col, self.matrices) for col in self.columns]
            inner = avail_width - id_width - self.eq_width() - 2 * self.pad
            mixed = [
                col if idx == 0 or self._stacked_fits(col, inner) else flat[idx]
                for idx, col in enumerate(self.columns)
            ]
            if mixed != self.columns and mixed != flat:
                column_sets.append((":mixed", mixed))
            column_sets.append((":inline", flat))
            flat_elided = [elide_collections(col) for col in flat]
            if flat_elided != flat:
                column_sets.append((":inline:elided", flat_elided))
        for suffix, columns in column_sets:
            top = max((max_rank(col) for col in columns), default=0)
            for kind in ("grid", "stack"):
                if kind == "stack" and len(columns) < 2:
                    continue
                name = f"{kind}{suffix}"
                yield name, lambda s, c=columns, k=kind: self._rows(avail_width, id_width, c, unbreakable, k, s)
                for rank in range(0, top + 1):
                    yield (
                        f"{name}:break{rank}",
                        lambda s, c=columns, r=rank, k=kind: self._rows(
                            avail_width, id_width, c, lambda m: with_breaks(m, r), k, s
                        ),
                    )

    def _stacked_fits(self, markup: str, inner: float) -> bool:
        """True if ``markup`` with its fractions stacked fits in a value cell ``inner`` wide."""
        return natural_width(value_cell(markup, self.styles["value"], self.matrices)) <= inner + 0.01

    def choose(self, avail_width: float, id_width: float):
        """``(layout, cells, commands)`` for this frame width and target column width."""
        key = (round(avail_width, 2), round(id_width, 2))
        if key in self._cache:
            self.layout = self._cache[key][0]
            return self._cache[key]
        attempts = list(self._attempts(avail_width, id_width))
        choice = None
        for name, build in attempts:
            cells, commands, fits = build(1.0)
            if fits:
                choice = (name, cells, commands)
                break
        if choice is None:
            for name, build in attempts:
                cells, commands, fits = build(self.min_scale)
                if fits:
                    choice = (f"shrink:{name}", cells, commands)
                    break
        if choice is None:
            name, build = attempts[-1]
            cells, commands, _ = build(self.min_scale)
            choice = (f"overflow:{name}", cells, commands)
        self._cache[key] = choice
        self.layout = choice[0]
        return choice

    # -- standalone flowable ------------------------------------------------

    def _build(self, avail_width: float) -> Table:
        block = CalcBlock([self], gap=0.0)
        return block.build_table(avail_width)

    def wrap(self, avail_width, avail_height):
        self._table = self._build(avail_width)
        self.width, self.height = self._table.wrap(avail_width, avail_height)
        return self.width, self.height

    # A calc line with this many rows or fewer is never split across pages.
    keep_rows = 4

    def split(self, avail_width, avail_height):
        table = self._build(avail_width)
        if len(table._cellvalues) <= self.keep_rows:
            return []
        return table.split(avail_width, avail_height)

    def draw(self):
        self._table.drawOn(self.canv, 0, 0)


class CalcBlock(Flowable):
    """
    A run of consecutive calc lines at one depth, drawn as one table aligned on
    the first ``=``: every line shares the target column, so the ``=`` signs
    of the whole run line up. Each line still picks its own layout (see
    ``CalcLine``).

    Lines are separated by an empty spacer row of height ``gap``, so a line's
    rows are exactly its own: the accent rule (the table style's
    ``LINEBEFORE``) is applied per line and never runs through the gaps.
    With ``rule_single_lines`` off (the default), only lines laid out over
    more than one ``=`` row get it: ``# hc: -m`` lines and long lines that fell
    back to a grid. With it on, the style's rule runs down the whole block.

    The target column is as wide as the widest target, ignoring targets wider
    than ``max_target`` of the frame; those lines stack their target on a row
    of its own. A block splits across pages between lines, never inside one;
    both parts keep the original target column width, so the ``=`` signs stay
    aligned across the break. A line taller than ``CalcLine.keep_rows`` that
    cannot start on the page splits by rows.
    """

    max_target = 0.4
    rule_single_lines = False

    def __init__(self, lines: list[CalcLine], gap: float | None = None,
                 fixed_id_width: float | None = None):
        super().__init__()
        self.lines = list(lines)
        first, last = self.lines[0], self.lines[-1]
        self.table_style = first.table_style
        self.pad = first.pad
        # The spacer between lines, standing in for the paragraph spacing the
        # lines had as separate flowables.
        self.gap = first.spaceBefore if gap is None else gap
        self.fixed_id_width = fixed_id_width
        self.spaceBefore = first.spaceBefore
        self.spaceAfter = last.spaceAfter
        self._table = None
        # ``(first_row, end_row)`` of each line's own rows (gap rows excluded).
        self.spans: list[tuple[int, int]] = []

    def id_width(self, avail_width: float) -> float:
        if self.fixed_id_width is not None:
            return self.fixed_id_width
        cap = avail_width * self.max_target
        widths = [w for w in (line.target_width() for line in self.lines) if w <= cap]
        return max(widths, default=2 * self.pad + 0.5)

    def build_table(self, avail_width: float) -> Table:
        id_width = self.id_width(avail_width)
        eq_width = max(line.eq_width() for line in self.lines)
        style = list(self.table_style.getCommands())
        rules = [c for c in style if c[0] == "LINEBEFORE"]
        commands = style if self.rule_single_lines else [c for c in style if c[0] != "LINEBEFORE"]
        cells: list = []
        heights: list = []
        self.spans = []
        for idx, line in enumerate(self.lines):
            if idx and self.gap:
                gap_row = len(cells)
                cells.append(["", "", ""])
                heights.append(self.gap)
                commands.append(("TOPPADDING", (0, gap_row), (-1, gap_row), 0))
                commands.append(("BOTTOMPADDING", (0, gap_row), (-1, gap_row), 0))
            layout, line_cells, line_commands = line.choose(avail_width, id_width)
            first = len(cells)
            for cmd, (c0, r0), (c1, r1), *rest in line_commands:
                commands.append((cmd, (c0, r0 + first), (c1, r1 + first), *rest))
            cells.extend(line_cells)
            heights.extend([None] * len(line_cells))
            self.spans.append((first, len(cells)))
            if not self.rule_single_lines and _is_multirow(line, layout):
                for cmd, _, _, *rest in rules:
                    commands.append((cmd, (0, first), (0, len(cells) - 1), *rest))
        val_width = max(avail_width - id_width - eq_width, 4 * self.pad)
        return BoxTable(cells, colWidths=[id_width, eq_width, val_width], rowHeights=heights,
                     style=commands, hAlign="LEFT")

    def wrap(self, avail_width, avail_height):
        self._table = self.build_table(avail_width)
        self.width, self.height = self._table.wrap(avail_width, avail_height)
        return self.width, self.height

    def split(self, avail_width, avail_height):
        id_width = self.id_width(avail_width)
        table = self.build_table(avail_width)
        table.wrap(avail_width, avail_height)
        heights = table._rowHeights
        used, fitting, previous_end = 0.0, 0, 0
        for first, end in self.spans:
            # A line's height includes the gap row above it (``previous_end``
            # is where the previous line's rows stopped).
            line_height = sum(heights[previous_end:end])
            if used + line_height > avail_height + 0.01:
                break
            used += line_height
            previous_end = end
            fitting += 1
        # ``split`` is only called when the block does not fit, so at least the
        # last line must move on (the frame's spacing is not counted above).
        fitting = min(fitting, len(self.lines) - 1)
        if fitting == 0:
            first, end = self.spans[0]
            if end - first <= CalcLine.keep_rows:
                return []
            if len(self.lines) == 1:
                return table.split(avail_width, avail_height)
            # A tall first line goes on its own, so it can split by rows.
            fitting = 1
        head = CalcBlock(self.lines[:fitting], gap=self.gap, fixed_id_width=id_width)
        tail = CalcBlock(self.lines[fitting:], gap=self.gap, fixed_id_width=id_width)
        head.spaceAfter = 0
        return [head, tail]

    def draw(self):
        self._table.drawOn(self.canv, 0, 0)


def _is_multirow(line: CalcLine, layout: str) -> bool:
    """True for a line laid out over several ``=`` rows (not a one-row line)."""
    base = layout.split(":", 1)[1] if layout.startswith(("shrink:", "overflow:")) else layout
    return line.forced_grid or not base.startswith("line")


## MATRICES

_MARKUP = re.compile(rf"<(/?)([a-zA-Z]+)[^>]*?(/?)>|{MATRIX_OPEN}(\d+){MATRIX_CLOSE}|([()])")
_TOKEN = re.compile(rf"{MATRIX_OPEN}(\d+){MATRIX_CLOSE}")
# Tags whose content is raised or lowered: brackets inside them are never stretched.
_SCRIPTS = ("sup", "sub", "super")


def has_matrix(markup: str) -> bool:
    return MATRIX_OPEN in markup


def matrix_segments(markup: str, brackets: bool = False) -> list[tuple[str, str]]:
    """
    Split ``markup`` at its matrix tokens into ``("text", markup)`` and
    ``("matrix", id)`` pieces. Tags open across a token are closed before it and
    reopened after it, so every text piece is balanced; each matrix piece also
    carries the tags open around it (``("matrix", id, open, close)``), so a
    matrix result keeps the result's colour and weight. With ``brackets``,
    every ``(`` and ``)`` outside a superscript or subscript is a piece of its
    own too (``("bracket", char, open, close)``), so it can be stretched.
    """
    pieces: list = []
    stack: list[tuple[str, str]] = []
    current = ""
    position = 0

    def opening() -> str:
        return "".join(tag for _, tag in stack)

    def closing() -> str:
        return "".join(f"</{name}>" for name, _ in reversed(stack))

    for match in _MARKUP.finditer(markup):
        current += markup[position:match.start()]
        position = match.end()
        if match.group(4) is not None:
            pieces.append(("text", current + closing()))
            pieces.append(("matrix", match.group(4), opening(), closing()))
            current = opening()
            continue
        if match.group(5) is not None:
            if brackets and not any(name in _SCRIPTS for name, _ in stack):
                pieces.append(("text", current + closing()))
                pieces.append(("bracket", match.group(5), opening(), closing()))
                current = opening()
            else:
                current += match.group(5)
            continue
        current += match.group(0)
        is_close, name, self_closing = match.group(1), match.group(2), match.group(3)
        if self_closing:
            continue
        if is_close:
            if stack and stack[-1][0] == name:
                stack.pop()
        else:
            stack.append((name, match.group(0)))
    pieces.append(("text", current + markup[position:]))
    return [p for p in pieces if p[0] != "text" or re.sub(r"<[^>]+>", "", p[1])]


def inline_matrices(markup: str, matrices: dict) -> str:
    """
    ``markup`` with each matrix token written out inline, ``[[1, 2], [3, 4]]``,
    and each fraction as an inline division, ``(a + b) / c``.
    """
    def inline(match: re.Match) -> str:
        value = matrices[match.group(1)]
        if isinstance(value, Fraction):
            return inline_fraction(value, matrices)
        return "[" + ", ".join("[" + ", ".join(row) + "]" for row in value) + "]"

    return _TOKEN.sub(inline, markup)


def inline_fraction(fraction: Fraction, matrices: dict) -> str:
    numerator = inline_matrices(fraction.numerator, matrices)
    denominator = inline_matrices(fraction.denominator, matrices)
    if fraction.numerator_brackets:
        numerator = f"{fraction.lpar}{numerator}{fraction.rpar}"
    if fraction.denominator_brackets:
        denominator = f"{fraction.lpar}{denominator}{fraction.rpar}"
    return f"{numerator} {'//' if fraction.floor else '/'} {denominator}"


def inline_fractions(markup: str, matrices: dict) -> str:
    """``markup`` with its fractions written inline and its matrices kept."""
    def inline(match: re.Match) -> str:
        value = matrices[match.group(1)]
        return inline_fraction(value, matrices) if isinstance(value, Fraction) else match.group(0)

    previous = None
    while previous != markup:  # a fraction's operands may hold fractions
        previous, markup = markup, _TOKEN.sub(inline, markup)
    return markup


def has_fraction(markup: str, matrices: dict | None) -> bool:
    return bool(matrices) and any(
        isinstance(matrices.get(key), Fraction) for key in _TOKEN.findall(markup)
    )


def _flat(style, name: str, **kwargs):
    """``style`` with no indents or paragraph spacing, for a piece of a ``MathRow``."""
    return style.clone(f"{style.name}{name}", leftIndent=0, firstLineIndent=0,
                       rightIndent=0, spaceBefore=0, spaceAfter=0, **kwargs)


_BACK_COLOR = re.compile(r'\s+backColor="([^"]*)"')

# The maths axis (where a fraction bar and the middle of a minus sign sit), as a
# fraction of the font size above the baseline.
AXIS = 0.3


def text_axis(paragraph: Paragraph) -> float:
    """Height of the maths axis above the bottom of a one-line ``paragraph`` (wrapped)."""
    style = paragraph.style
    # ReportLab sets the first baseline a font size below the paragraph's top.
    return paragraph.height - style.fontSize + AXIS * style.fontSize


def axis_of(part: Flowable) -> float:
    if isinstance(part, Paragraph):
        return text_axis(part)
    return getattr(part, "axis", part.height / 2)


class Matrix(Flowable):
    """
    A 2-D array: cells right-aligned in columns, between square brackets. A
    ``backColor`` in the tags around it (the result highlight) is drawn once,
    behind the whole matrix, rather than behind each cell.
    """

    def __init__(self, rows: list[list[str]], style, open_tags: str = "", close_tags: str = ""):
        super().__init__()
        background = _BACK_COLOR.search(open_tags)
        self.background = background.group(1) if background else None
        open_tags = _BACK_COLOR.sub("", open_tags)
        cell_style = _flat(style, "@matrix")
        self.cells = [
            [Paragraph(f"{open_tags}{cell}{close_tags}", cell_style) for cell in row] for row in rows
        ]
        self.color = style.textColor
        size = style.fontSize
        self.col_gap = size * 0.6
        self.inset = size * 0.3  # between a bracket and the cells
        self.tick = size * 0.25  # the bracket's top and bottom serifs
        self.line_width = max(0.5, size * 0.06)

    def _measure(self) -> None:
        ncols = max((len(row) for row in self.cells), default=0)
        self.col_widths = [
            max((natural_width(row[c]) for row in self.cells if c < len(row)), default=0.0)
            for c in range(ncols)
        ]
        self.row_heights = [
            max((cell.wrap(1e6, 1e6)[1] for cell in row), default=0.0) for row in self.cells
        ]

    def wrap(self, avail_width, avail_height):
        self._measure()
        content = sum(self.col_widths) + self.col_gap * max(0, len(self.col_widths) - 1)
        self.width = content + 2 * self.inset
        self.height = sum(self.row_heights)
        self.axis = self.height / 2
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        if self.background is not None:
            canvas.saveState()
            canvas.setFillColor(HexColor(self.background))
            canvas.roundRect(0, 0, self.width, self.height, 3, stroke=0, fill=1)
            canvas.restoreState()
        y = self.height
        for row, height in zip(self.cells, self.row_heights):
            y -= height
            x = self.inset
            for cell, col_width in zip(row, self.col_widths):
                cell.wrap(1e6, 1e6)
                cell.drawOn(canvas, x + col_width - natural_width(cell), y)
                x += col_width + self.col_gap
        canvas.saveState()
        canvas.setStrokeColor(self.color)
        canvas.setLineWidth(self.line_width)
        for x, tick in ((0, self.tick), (self.width, -self.tick)):
            path = canvas.beginPath()
            path.moveTo(x + tick, self.height)
            path.lineTo(x, self.height)
            path.lineTo(x, 0)
            path.lineTo(x + tick, 0)
            canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()


# A fraction's operands are set this much smaller than the text around it, and
# smaller again in a fraction inside an operand.
FRACTION_SCALE = (1.0, 0.85)


class FractionFlowable(Flowable):
    """
    A stacked fraction: its numerator centred over its denominator, the bar on
    the maths axis of the text beside it. Each operand is a ``value_cell`` of its
    own, so it can hold another fraction or a matrix. Like ``Matrix``, a
    ``backColor`` in the tags around it is drawn once, behind the whole fraction.
    """

    def __init__(self, fraction: Fraction, style, open_tags: str, close_tags: str,
                 matrices: dict, level: int = 0):
        super().__init__()
        background = _BACK_COLOR.search(open_tags)
        self.background = background.group(1) if background else None
        open_tags = _BACK_COLOR.sub("", open_tags)
        scale = FRACTION_SCALE[min(level, len(FRACTION_SCALE) - 1)]
        operand_style = _scaled(_flat(style, f"@frac{level}"), scale)
        self.numerator = value_cell(f"{open_tags}{fraction.numerator}{close_tags}", operand_style,
                                    matrices, level + 1)
        self.denominator = value_cell(f"{open_tags}{fraction.denominator}{close_tags}", operand_style,
                                      matrices, level + 1)
        self.color = style.textColor
        size = style.fontSize
        self.size = size
        self.bar = max(0.5, size * 0.055)
        self.gap = size * 0.08  # between the bar and each operand's box
        self.overhang = size * 0.12  # the bar past the wider operand

    def wrap(self, avail_width, avail_height):
        self._num = _measure(self.numerator)
        self._den = _measure(self.denominator)
        self.width = max(self._num[0], self._den[0]) + 2 * self.overhang
        self.height = self._num[1] + self._den[1] + 2 * self.gap + self.bar
        self.axis = self._den[1] + self.gap + self.bar / 2
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        if self.background is not None:
            canvas.saveState()
            canvas.setFillColor(HexColor(self.background))
            canvas.roundRect(0, 0, self.width, self.height, 3, stroke=0, fill=1)
            canvas.restoreState()
        (nw, nh), (dw, dh) = self._num, self._den
        # Numerator first, so text copied from the PDF reads top to bottom.
        self.numerator.drawOn(canvas, (self.width - nw) / 2, self.height - nh)
        self.denominator.drawOn(canvas, (self.width - dw) / 2, 0)
        canvas.saveState()
        canvas.setStrokeColor(self.color)
        canvas.setLineWidth(self.bar)
        canvas.line(self.overhang * 0.5, self.axis, self.width - self.overhang * 0.5, self.axis)
        canvas.restoreState()


class Bracket(Flowable):
    """A ``(`` or ``)`` drawn as a curve, stretched to the fraction it encloses."""

    def __init__(self, char: str, style, open_tags: str = ""):
        super().__init__()
        self.char = char
        color = re.search(r'color="([^"]*)"', _BACK_COLOR.sub("", open_tags))
        self.color = HexColor(color.group(1)) if color else style.textColor
        self.size = style.fontSize
        self.above = self.below = 0.0  # extent from the axis, set by ``MathRow``

    def wrap(self, avail_width, avail_height):
        self.width = self.size * 0.42
        self.height = self.above + self.below
        self.axis = self.below
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        w, h = self.width, self.height
        inner, outer = (w * 0.85, w * 0.2) if self.char == "(" else (w * 0.15, w * 0.8)
        canvas.saveState()
        canvas.setStrokeColor(self.color)
        canvas.setLineWidth(max(0.5, self.size * 0.065))
        path = canvas.beginPath()
        path.moveTo(inner, h)
        path.curveTo(outer, h * 0.78, outer, h * 0.22, inner, 0)
        canvas.drawPath(path, stroke=1, fill=0)
        canvas.restoreState()


def _measure(part: Flowable) -> tuple[float, float]:
    if isinstance(part, Paragraph):
        width = natural_width(part)
        _, height = part.wrap(width + 0.01, 1e6)
        return width, height
    return part.wrap(1e6, 1e6)


class MathRow(Flowable):
    """
    Value markup that contains matrices or fractions: its text pieces and
    ``Matrix`` / ``FractionFlowable`` pieces side by side on one row, each piece
    on the row's maths axis. Brackets around a fraction are stretched to its
    height. It never wraps; like a paragraph it reports its line widths (one
    line), so ``natural_width`` and ``fits_width`` measure it and a calc line
    falls back to another layout when it is too wide.

    At the top ``level`` the row is padded so that its middle is where the middle
    of a plain line of text would be, so a table cell centred on it (the target
    and ``=``) sits on its axis.
    """

    def __init__(self, markup: str, style, matrices: dict, level: int = 0):
        super().__init__()
        self.style = style
        self.level = level
        text_style = _flat(style, "@row")
        self.parts: list[Flowable] = []
        pieces = matrix_segments(markup, brackets=has_fraction(markup, matrices))
        tall = _tall_brackets(pieces, matrices)
        stretched = {i for pair in tall.items() for i in pair}
        part_of: dict[int, int] = {}  # piece index -> part index
        for idx, piece in enumerate(pieces):
            part_of[idx] = len(self.parts)
            if piece[0] == "text":
                # A paragraph drops the spaces at its ends; keep the ones that
                # separate this piece from a matrix (`` = ``, `` @ ``).
                text = re.sub(r"^((?:<[^>]+>)*) ", rf"\1{NBSP}", piece[1])
                text = re.sub(r" ((?:<[^>]+>)*)$", rf"{NBSP}\1", text)
                self.parts.append(Paragraph(text, text_style))
            elif piece[0] == "bracket":
                _, char, open_tags, close_tags = piece
                if idx in stretched:
                    self.parts.append(Bracket(char, style, open_tags))
                else:
                    self.parts.append(Paragraph(f"{open_tags}{char}{close_tags}", text_style))
            else:
                _, key, open_tags, close_tags = piece
                value = matrices[key]
                if isinstance(value, Fraction):
                    fraction = FractionFlowable(value, style, open_tags, close_tags, matrices, level)
                    if value.floor:
                        self.parts.extend([
                            Paragraph(f"{open_tags}⌊{close_tags}", text_style), fraction,
                            Paragraph(f"{open_tags}⌋{close_tags}", text_style),
                        ])
                    else:
                        self.parts.append(fraction)
                else:
                    self.parts.append(Matrix(value, style, open_tags, close_tags))
        # Stretched bracket parts: opening part index -> closing part index.
        self.pairs = {part_of[o]: part_of[c] for o, c in tall.items()}
        reference = Paragraph("x", text_style)
        reference.wrap(1e6, 1e6)
        # How far the middle of a line of text is above its maths axis.
        self._text_offset = reference.height / 2 - text_axis(reference)
        self._sizes: list[tuple[float, float]] = []

    def wrap(self, avail_width, avail_height):
        brackets = {i for pair in self.pairs.items() for i in pair}
        self._sizes = [(0.0, 0.0)] * len(self.parts)
        for idx, part in enumerate(self.parts):
            if idx not in brackets:
                self._sizes[idx] = _measure(part)
        # Each pair of tall brackets reaches past the tallest piece between them;
        # inner pairs close first, so an outer pair reaches past them too.
        pad = self.style.fontSize * 0.03
        for open_idx, close_idx in sorted(self.pairs.items(), key=lambda pair: pair[1]):
            inside = range(open_idx + 1, close_idx)
            above = max((self._sizes[i][1] - axis_of(self.parts[i]) for i in inside), default=0.0)
            below = max((axis_of(self.parts[i]) for i in inside), default=0.0)
            for i in (open_idx, close_idx):
                self.parts[i].above, self.parts[i].below = above + pad, below + pad
                self._sizes[i] = self.parts[i].wrap(1e6, 1e6)
        axes = [axis_of(part) for part in self.parts]
        below = max(axes, default=0.0)
        above = max((h - a for (_, h), a in zip(self._sizes, axes)), default=0.0)
        self._offset = 0.0
        if self.level == 0:
            offset = self._text_offset
            half = max(above - offset, below + offset)
            self._offset = half - offset - below  # lifts the content to centre it
            self.height = 2 * half
        else:
            self.height = above + below
        self.axis = below + self._offset
        self.width = sum(w for w, _ in self._sizes)
        return self.width, self.height

    def getActualLineWidths0(self) -> list[float]:
        return [self.width]

    def draw(self):
        x = 0.0
        for part, (width, _) in zip(self.parts, self._sizes):
            part.drawOn(self.canv, x, self.axis - axis_of(part))
            x += width


def _tall_brackets(pieces: list, matrices: dict) -> dict[int, int]:
    """Matched bracket pieces (opening index -> closing index) that enclose a fraction."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for idx, piece in enumerate(pieces):
        if piece[0] != "bracket":
            continue
        if piece[1] == "(":
            stack.append(idx)
        elif stack:
            open_idx = stack.pop()
            if any(p[0] == "matrix" and isinstance(matrices[p[1]], Fraction)
                   for p in pieces[open_idx + 1:idx]):
                pairs[open_idx] = idx
    return pairs


def value_cell(markup: str, style, matrices: dict | None = None, level: int = 0) -> Flowable:
    """A ``Paragraph`` for ``markup``, or a ``MathRow`` when it holds a matrix or fraction."""
    if matrices and has_matrix(markup):
        return MathRow(markup, style, matrices, level)
    return Paragraph(markup, style)
