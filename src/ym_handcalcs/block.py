"""
The ``_hc`` ymprint block: runs Python source in the document's variables and
renders it with handcalcs.

    _hc: |
      L = 6.0  # span
      M = w * L**2 / 8

    _hc_beam:
      source: |
        ...
      theme_color: "#0B5F66"
      base_size: 9.5
      namespace: beam

Like ``_py``, the source runs in the document's ``_vars``, so it can use
values from ``_vars`` and earlier blocks, and later blocks can use its results.
With ``namespace``, its results go in ``_vars[namespace]`` instead, leaving the
top level of ``_vars`` untouched.
ymprint registers this block itself when ym_handcalcs is installed
(``pip install ymprint[hc]``).
"""
from __future__ import annotations

import symtable
from typing import Any

from handcalcs import HandCalcs, get_option
from handcalcs.parsing import line_values

from .renderer import ReportLabRenderer

BLOCK_CODE = "_hc"
OPTIONS = {"source", "theme_color", "base_size", "namespace"}


def block_options(block_key: str, block_value: Any) -> dict:
    """The block's options as a dict; a bare string is the source."""
    if isinstance(block_value, str):
        return {"source": block_value}
    if not isinstance(block_value, dict) or "source" not in block_value:
        raise ValueError(
            f"{block_key}: expected the Python source as a string, or a mapping with a "
            f"'source' key (and optionally {', '.join(sorted(OPTIONS - {'source'}))})."
        )
    unknown = set(block_value) - OPTIONS
    if unknown:
        raise ValueError(
            f"{block_key}: unknown option(s) {', '.join(sorted(unknown))}. "
            f"Choose from: {', '.join(sorted(OPTIONS))}."
        )
    namespace = block_value.get("namespace")
    if namespace is not None and not (isinstance(namespace, str) and namespace.isidentifier()):
        raise ValueError(f"{block_key}: 'namespace' must be a Python identifier, got {namespace!r}.")
    return block_value


def run_source(source: str, namespace: dict):
    """Run 'source' in 'namespace'; returns the recorded line values (or None)."""
    if not get_option("line_values", True):
        exec(source, namespace)
        return None
    return line_values.run(source, namespace)


def bound_names(source: str) -> set[str]:
    """The names 'source' binds at its top level (comprehension variables excluded)."""
    table = symtable.symtable(source, "<handcalcs>", "exec")
    return {
        symbol.get_name()
        for symbol in table.get_symbols()
        if (symbol.is_assigned() or symbol.is_imported()) and not symbol.is_comp_iter()
    }


def namespace_results(source: str, document_vars: dict, run_vars: dict) -> dict:
    """
    The values 'source' left in 'run_vars', a copy of 'document_vars' it ran in.

    A name counts if the source binds it, even to the value it already had (``w = 3``
    when ``w`` is 3), or if its value changed some other way (a walrus in a
    comprehension, a ``global`` in a function).
    """
    assigned = bound_names(source)
    missing = object()
    return {
        name: value
        for name, value in run_vars.items()
        if not (name.startswith("__") and name.endswith("__"))
        and (name in assigned or document_vars.get(name, missing) is not value)
    }


def convert_hc_block(block_key: str, block_value: Any, context: dict) -> list:
    options = block_options(block_key, block_value)
    source = options["source"]
    # With a namespace, run in a copy of _vars (one dict, so functions defined in the
    # source can see its earlier names) and keep only the results in the namespace.
    namespace = options.get("namespace")
    run_vars = dict(context["vars"]) if namespace is not None else context["vars"]
    try:
        values = run_source(source, run_vars)
    except Exception as e:
        # The author's own code raised: report it like a failing _py block.
        from ymprint.errors import PythonBlockError

        raise PythonBlockError(block_key, source, e) from e
    if namespace is not None:
        context["vars"][namespace] = namespace_results(source, context["vars"], run_vars)
    renderer = ReportLabRenderer(
        theme_color=options.get("theme_color"),
        base_size=options.get("base_size", context["styles"]["ymprint"].body.size),
    )
    result = HandCalcs(renderer=renderer).render_run(source, run_vars, values)
    return list(result["story"])
