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

    _hc_column:
      path: column_calc     # a .py `_data` source, or an absolute path to a .py file

Like ``_py``, the source runs in the document's ``_vars``, so it can use
values from ``_vars`` and earlier blocks, and later blocks can use its results.
With ``namespace``, its results go in ``_vars[namespace]`` instead, leaving the
top level of ``_vars`` untouched. With ``path`` instead of ``source``, the source
is read from a ``.py`` file: the name of a ``_data`` source, or an absolute path.
ymprint registers this block itself when ym_handcalcs is installed
(``pip install ymprint[hc]``).
"""
from __future__ import annotations

import pathlib
import symtable
from typing import Any

from handcalcs import HandCalcs, get_option
from handcalcs.parsing import line_values

from .renderer import ReportLabRenderer

BLOCK_CODE = "_hc"
SOURCE_OPTIONS = {"source", "path"}
OPTIONS = SOURCE_OPTIONS | {"theme_color", "base_size", "namespace"}


def block_options(block_key: str, block_value: Any) -> dict:
    """The block's options as a dict; a bare string is the source."""
    if isinstance(block_value, str):
        return {"source": block_value}
    if not isinstance(block_value, dict) or not SOURCE_OPTIONS & set(block_value):
        raise ValueError(
            f"{block_key}: expected the Python source as a string, or a mapping with a "
            f"'source' or 'path' key (and optionally "
            f"{', '.join(sorted(OPTIONS - SOURCE_OPTIONS))})."
        )
    if SOURCE_OPTIONS <= set(block_value):
        raise ValueError(f"{block_key}: give either 'source' or 'path', not both.")
    unknown = set(block_value) - OPTIONS
    if unknown:
        raise ValueError(
            f"{block_key}: unknown option(s) {', '.join(sorted(unknown))}. "
            f"Choose from: {', '.join(sorted(OPTIONS))}."
        )
    namespace = block_value.get("namespace")
    if namespace is not None and not (isinstance(namespace, str) and namespace.isidentifier()):
        raise ValueError(f"{block_key}: 'namespace' must be a Python identifier, got {namespace!r}.")
    path = block_value.get("path")
    if "path" in block_value and not (isinstance(path, str) and path.strip()):
        raise ValueError(f"{block_key}: 'path' must be a data source name or an absolute path, got {path!r}.")
    return block_value


def source_file(block_key: str, path: str, context: dict) -> pathlib.Path:
    """
    The .py file named by a block's 'path': an absolute path, or the name of a
    `_data` source (whose file is looked up, not loaded). Records the read, so
    live mode and `ym build` see the file as an input of the document.
    """
    data = context.get("data")
    if pathlib.Path(path).is_absolute():
        file = pathlib.Path(path).resolve()
        if data is not None:
            data.record_file(file)
    elif path.isidentifier():
        if data is None:
            raise ValueError(
                f"{block_key}: 'path: {path}' names a data source, which needs ymprint 0.8 or "
                f"later. Upgrade ymprint, or give an absolute path."
            )
        if path not in data:
            declared = ", ".join(sorted(data.names())) or "none"
            raise ValueError(
                f"{block_key}: no data source named {path!r} (declared: {declared}). "
                f"'path' must be a `_data` source name or an absolute path."
            )
        file = data.path(path)
    else:
        raise ValueError(
            f"{block_key}: 'path' must be a `_data` source name or an absolute path, got "
            f"{path!r}. Declare the file in `_data` (in the project.ymprint.yml) and use its name."
        )
    if file.suffix.lower() != ".py":
        raise ValueError(f"{block_key}: 'path' must be a .py file, got {file}.")
    if not file.is_file():
        raise ValueError(f"{block_key}: the file for 'path: {path}' does not exist: {file}")
    return file


def block_source(block_key: str, options: dict, context: dict) -> tuple[str, str]:
    """Returns (source, filename): the block's inline source, or the .py file 'path' names."""
    if "path" not in options:
        return options["source"], "<handcalcs>"
    file = source_file(block_key, options["path"], context)
    return file.read_text(encoding="utf-8"), str(file)


def run_source(source: str, namespace: dict, filename: str = "<handcalcs>"):
    """Run 'source' in 'namespace'; returns the recorded line values (or None)."""
    if not get_option("line_values", True):
        exec(compile(source, filename, "exec"), namespace)
        return None
    return line_values.run(source, namespace, filename=filename)


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
    source, filename = block_source(block_key, options, context)
    # With a namespace, run in a copy of _vars (one dict, so functions defined in the
    # source can see its earlier names) and keep only the results in the namespace.
    namespace = options.get("namespace")
    run_vars = dict(context["vars"]) if namespace is not None else context["vars"]
    try:
        values = run_source(source, run_vars, filename)
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
