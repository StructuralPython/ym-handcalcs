"""
Inline rules for the ReportLab renderer: how names, operators and function
calls read inside paragraph markup.

ReportLab paragraphs take a small XML dialect (``<sub>``, ``<sup>``, ``<font>``,
``<b>``, ``<i>``) plus XML entities, so every rule here emits that dialect
directly. Nothing is borrowed from another renderer: a change to the HTML or
LaTeX output can never leak into a PDF.

``register_symbol_rules`` attaches the rules to a renderer class. Rules on one
node type run in registration order, so the order below matters: Greek names
are swapped before the subscript rule splits an identifier on ``_``.
"""
from __future__ import annotations

from handcalcs.parsing.nodes import Name
from handcalcs.parsing.inline_nodes import FunctionCall
from handcalcs.parsing.operator_nodes import HcBinOp, HcCompOp, PowOp
from handcalcs.renderers.base import OP_PRECEDENCE, BaseRenderContext

from .breaking import unbreakable

BRC = BaseRenderContext

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ϵ", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lamb": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "omicron": "ο", "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ",
    "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "ϕ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Epsilon": "Ε",
    "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ", "Iota": "Ι", "Kappa": "Κ",
    "Lamb": "Λ", "Mu": "Μ", "Nu": "Ν", "Xi": "Ξ", "Omicron": "Ο", "Pi": "Π",
    "Rho": "Ρ", "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ", "Phi": "Φ",
    "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
}

# ``x_hat_`` -> x̂, ``x_prime_`` -> x′, ``x_bar_`` -> x̅, ``x_star_`` -> x*.
ACCENTS = {
    "_hat_": "̂_",
    "_prime_": "′_",
    "_star_": "<sup>*</sup>_",
    "_bar_": "̅_",
}

# Comparison symbols as paragraph markup. ``<`` and ``>`` must be entities.
COMPARISONS = {"<": "&lt;", "<=": "&le;", ">": "&gt;", ">=": "&ge;", "!=": "≠"}


## NAMES (symbolic column only: the numeric column shows values)

def swap_greek(renderer, node: Name, base_context: BRC) -> Name:
    """Replace each ``_``-separated part of an identifier that names a Greek letter."""
    parts = node.identifier.split("_")
    node.identifier = "_".join(GREEK.get(part, part) for part in parts)
    return node


def swap_accents(renderer, node: Name, base_context: BRC) -> Name:
    identifier = node.identifier
    for suffix, markup in ACCENTS.items():
        identifier = identifier.replace(suffix, markup)
    node.identifier = identifier
    return node


def swap_subscripts(renderer, node: Name, base_context: BRC) -> Name:
    """
    A single underscore starts a (nested) subscript, a double underscore is a
    space and a triple underscore is a literal underscore: ``e_f_g`` ->
    ``e<sub>f<sub>g</sub></sub>``, ``a__b`` -> ``a b``, ``c___d`` -> ``c_d``.
    """
    space = base_context.current.space
    identifier = node.identifier.replace("___", "\0").replace("__", "\1")
    depth = identifier.count("_")
    identifier = identifier.replace("_", "<sub>") + "</sub>" * depth
    node.identifier = identifier.replace("\1", space).replace("\0", "_")
    return node


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
    ``math.sin(x)`` -> ``sin(x)``. Registered before ``swap_sqrt`` so that rule
    still sees the ``sqrt`` name. Clearing the namespace is idempotent, and an
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

def swap_sqrt(renderer, node: FunctionCall, base_context: BRC) -> FunctionCall:
    """Arguments sit in round brackets; ``sqrt(x)`` shows as ``√(x)``."""
    node.pre = "("
    node.post = ")"
    if node.function_name.identifier == "sqrt":
        node.function_name.identifier = "√"
        node.function_name.value = "√"
    return node


def register_symbol_rules(cls) -> None:
    cls.register("name:sym")(swap_greek)
    cls.register("name:sym")(swap_accents)
    cls.register("name:sym")(swap_subscripts)
    cls.register("mult_op:pre")(swap_mult_symbol)
    cls.register("pow_op")(render_pow_op)
    for op in ("gt_op", "lt_op", "gte_op", "lte_op", "eq_op", "neq_op"):
        cls.register(f"{op}:pre")(swap_comparison)
        cls.register(f"{op}:post")(space_comparison)
    cls.register("function_call:pre")(drop_math_namespace)
    cls.register("function_call:pre")(swap_sqrt)
    cls.register("attribute:sym")(swap_math_constant)
