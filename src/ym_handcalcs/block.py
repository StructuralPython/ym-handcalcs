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

Like ``_py``, the source runs in the document's ``_vars``, so it can use
values from ``_vars`` and earlier blocks, and later blocks can use its results.
ymprint registers this block itself when ym_handcalcs is installed
(``pip install ymprint[hc]``).
"""
from __future__ import annotations

from typing import Any

from handcalcs import HandCalcs, get_option
from handcalcs.parsing import line_values

from .renderer import ReportLabRenderer

BLOCK_CODE = "_hc"
OPTIONS = {"source", "theme_color", "base_size"}


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
    return block_value


def run_source(source: str, namespace: dict):
    """Run 'source' in 'namespace'; returns the recorded line values (or None)."""
    if not get_option("line_values", True):
        exec(source, namespace)
        return None
    return line_values.run(source, namespace)


def convert_hc_block(block_key: str, block_value: Any, context: dict) -> list:
    options = block_options(block_key, block_value)
    source = options["source"]
    namespace = context["vars"]
    try:
        values = run_source(source, namespace)
    except Exception as e:
        # The author's own code raised: report it like a failing _py block.
        from ymprint.errors import PythonBlockError

        raise PythonBlockError(block_key, source, e) from e
    renderer = ReportLabRenderer(
        theme_color=options.get("theme_color"),
        base_size=options.get("base_size", context["styles"]["ymprint"].body.size),
    )
    result = HandCalcs(renderer=renderer).render_run(source, namespace, values)
    return list(result["story"])
