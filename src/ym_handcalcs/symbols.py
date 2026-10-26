"""
Inline rules for the ReportLab renderer: how names, operators and function
calls read inside paragraph markup.

ReportLab paragraphs take a small XML dialect (``<sub>``, ``<sup>``, ``<font>``,
``<b>``, ``<i>``) plus XML entities, so every rule here emits that dialect
directly. Nothing is borrowed from another renderer: a change to the HTML or
LaTeX output can never leak into a PDF.

Identifiers are parsed with handcalcs' shared identifier rules
(``handcalcs.renderers.identifiers``), so they follow the same conventions as
every other renderer.

``register_symbol_rules`` attaches the rules to a renderer class. Rules on one
node type run in registration order, so the order below matters.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from handcalcs.parsing.nodes import Constant, Name, Subscript
from handcalcs.parsing.inline_nodes import FunctionCall
from handcalcs.parsing.operator_nodes import HcBinOp, HcCompOp, PowOp
from handcalcs.renderers.base import (
    OP_PRECEDENCE,
    ROOT_SYMBOLS,
    BaseRenderContext,
    math_call_name,
    postfix_factorial,
    render_constant,
    render_subscript as render_bracketed_subscript,
    subscript_value,
)
from handcalcs.renderers.identifiers import (
    GREEK_UNICODE,
    Symbol,
    identifier_options,
    indexed_symbol,
    is_identifier,
    parse_identifier,
)

from .breaking import unbreakable

BRC = BaseRenderContext

# What an accent component adds after the symbol it decorates.
ACCENT_MARKS = {"hat": "\u0302", "bar": "\u0305", "dot": "\u0307", "ddot": "\u0308"}
PRIME_MARK = "\u2032"

# Comparison symbols as paragraph markup. ``<`` and ``>`` must be entities.
COMPARISONS = {"<": "&lt;", "<=": "&le;", ">": "&gt;", ">=": "&ge;", "!=": "≠"}


## NAMES (symbolic column only: the numeric column shows values)

def rl_symbol(symbol: Symbol, space: str = " ") -> str:
    """
    A parsed ``Symbol`` as paragraph markup: Greek letters, combining accents,
    primes, ``<sup>`` and ``<sub>`` (sibling subscripts separated by commas).
    """
    markup = space.join(
        "".join(GREEK_UNICODE[text] if is_greek else escape(text) for is_greek, text in pieces)
        for pieces in symbol.words
    )
    markup += "".join(ACCENT_MARKS[accent] for accent in symbol.accents)
    markup += PRIME_MARK * symbol.primes
    if symbol.superscripts:
        markup += f"<sup>{','.join(rl_symbol(sup, space) for sup in symbol.superscripts)}</sup>"
    if symbol.subscripts:
        markup += f"<sub>{','.join(rl_symbol(sub, space) for sub in symbol.subscripts)}</sub>"
    return markup


def swap_identifier(renderer, node: Name, base_context: BRC) -> Name:
    """
    Typeset an identifier from its parsed ``Symbol`` (handcalcs' shared
    identifier rules): ``sigma_max`` -> ``σ<sub>max</sub>``, ``N_pl_Rd`` ->
    ``N<sub>pl,Rd</sub>`` (nested with the ``subscripts`` option), ``DeltaH``
    -> ``ΔH``, ``x_hat`` -> x̂, ``M_star`` -> ``M<sup>*</sup>``; ``__`` is a
    space and ``___`` an underscore. An identifier in the ``symbols`` option is
    typeset from its spec. Text that is not an identifier (markup from another
    rule) is left alone.
    """
    options = identifier_options(renderer, base_context)
    identifier = node.identifier
    if identifier in options.symbols or is_identifier(identifier):
        node.identifier = rl_symbol(parse_identifier(identifier, options), base_context.current.space)
    return node


def render_subscript(renderer, node: Subscript, base_context: BRC) -> str:
    """
    An index or key lookup. A name indexed by integers, short strings or names
    shows each index as a subscript (``xs[0]`` -> ``xs<sub>0</sub>``); any
    other lookup is shown in brackets. The numeric column shows the element.
    """
    value = subscript_value(renderer, node, base_context)
    if value is not None:
        return value
    if node.labels is None:
        return render_bracketed_subscript(renderer, node, base_context)
    options = identifier_options(renderer, base_context)
    symbol = indexed_symbol(node.container.identifier, node.labels, options)
    return rl_symbol(symbol, base_context.current.space)


## OPERATORS

def swap_mult_symbol(renderer, node: HcBinOp, base_context: BRC) -> HcBinOp:
    """``*`` shows as a centred dot (idempotent across the two render passes)."""
    node.symbol = "·"
    return node


def render_pow_op(renderer, node: HcBinOp, base_context: BRC) -> str:
    """
    Every exponent is a superscript: ``a<sup>2</sup>``, ``a<sup>b + 1</sup>``.
    The raised position groups the exponent, so it needs no brackets. The base
    is bracketed when it binds looser than a power (``(a + b)<sup>2</sup>``,
    ``(a<sup>b</sup>)<sup>c</sup>``) or renders with a sign (a negative value
    substituted in the numeric column). The exponent's spaces are made
    non-breaking so a line never wraps inside a superscript.
    """
    context = base_context.current
    base = renderer.render_node(node.left, base_context)
    if (
        OP_PRECEDENCE.get(type(node.left), float("inf")) <= OP_PRECEDENCE[PowOp]
        or base.lstrip().startswith(("-", "+"))
    ):
        base = f"{context.lpar}{base}{context.rpar}"
    exponent = unbreakable(renderer.render_node(node.right, base_context))
    return f"{base}<sup>{exponent}</sup>"


def swap_comparison(renderer, node: HcCompOp, base_context: BRC) -> HcCompOp:
    node.symbol = COMPARISONS.get(node.symbol, node.symbol)
    return node


def space_comparison(renderer, rendered: str, node: HcCompOp, base_context: BRC) -> str:
    # Space comparisons like the arithmetic operators (``a &lt; b``, not
    # ``a&lt;b``). ``breaking`` treats them as relations.
    return f" {rendered} "


## MATHS MODULES

# Functions and constants of these modules read as plain maths, so their module
# prefix is dropped: ``math.sqrt(x)`` shows as ``√(x)`` and ``math.pi`` as ``π``.
# numpy also holds array functions (``np.linspace``), so only its elementwise
# maths functions lose the prefix. A module is recognised by its real name (via
# the render context's ``global_ns``, so ``import math as m`` works) or, when no
# namespace was supplied, by the conventional alias.
MATH_MODULES = {"math": "math", "cmath": "cmath", "numpy": "numpy", "np": "numpy"}
NUMPY_MATH_FUNCTIONS = {
    "sqrt", "cbrt", "exp", "log", "log2", "log10", "abs", "sin", "cos", "tan",
    "arcsin", "arccos", "arctan", "arctan2", "sinh", "cosh", "tanh", "degrees",
    "radians", "deg2rad", "rad2deg", "floor", "ceil", "hypot",
}
MATH_CONSTANTS = {"pi": "π", "tau": "τ", "e": "e", "inf": "∞"}


def math_module(alias: str, base_context: BRC):
    """The maths module ('math', 'cmath' or 'numpy') that ``alias`` names, or None."""
    global_ns = getattr(base_context.current, "global_ns", None) or {}
    return MATH_MODULES.get(getattr(global_ns.get(alias), "__name__", alias))


def drop_math_namespace(renderer, node: FunctionCall, base_context: BRC) -> FunctionCall:
    """
    ``math.sin(x)`` -> ``sin(x)``. Registered before ``swap_roots``. Clearing the namespace is idempotent, and an
    empty namespace renders as nothing.
    """
    namespace = getattr(node.namespace, "identifier", None)
    if not isinstance(namespace, str):
        return node
    module = math_module(namespace, base_context)
    name = getattr(node.function_name, "identifier", None)
    if module in ("math", "cmath") or (module == "numpy" and name in NUMPY_MATH_FUNCTIONS):
        node.namespace = None
    return node


def swap_math_constant(renderer, node, base_context: BRC):
    """``math.pi`` -> ``π`` in the symbolic column; the numeric column shows the value."""
    if node.identifier in MATH_CONSTANTS and math_module(node.namespace or "", base_context):
        node.namespace = ""
        node.identifier = MATH_CONSTANTS[node.identifier]
    return node


## FUNCTION CALLS

def swap_roots(renderer, node: FunctionCall, base_context: BRC) -> FunctionCall:
    """
    Arguments sit in round brackets; ``sqrt(x)`` shows as ``√(x)``,
    ``cbrt(x)`` as ``∛(x)`` and ``factorial(n)`` as ``n!`` (``(n + 1)!``).
    """
    name = math_call_name(node)
    if name == "":  # already set in its own notation (a factorial)
        return node
    node.pre = "("
    node.post = ")"
    if name == "factorial":
        return postfix_factorial(node, "(", ")")
    if name in ROOT_SYMBOLS:
        node.function_name.identifier = ROOT_SYMBOLS[name]
        node.function_name.value = ROOT_SYMBOLS[name]
    return node


## VALUES

def quote_string(renderer, node: Constant, base_context: BRC):
    """A string value is shown in curly quotes, “W310x39”; ``escape_value`` escapes it."""
    if isinstance(node.value, str) and (node.calculated or node.source_text):
        return f"“{node.value}”"
    return render_constant(renderer, node, base_context)


def register_symbol_rules(cls) -> None:
    cls.register("name:sym")(swap_identifier)
    cls.register("subscript")(render_subscript)
    cls.register("mult_op:pre")(swap_mult_symbol)
    cls.register("pow_op")(render_pow_op)
    for op in ("gt_op", "lt_op", "gte_op", "lte_op", "eq_op", "neq_op"):
        cls.register(f"{op}:pre")(swap_comparison)
        cls.register(f"{op}:post")(space_comparison)
    cls.register("function_call:pre")(drop_math_namespace)
    cls.register("function_call:pre")(swap_roots)
    cls.register("constant")(quote_string)
    cls.register("attribute:sym")(swap_math_constant)
