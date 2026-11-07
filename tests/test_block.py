"""
Tests for the ``_hc`` ymprint block, rendered through a ymprint application.
"""
import pathlib
import re
import traceback

import pymupdf
import pytest

from ymprint import Ymprint
from ymprint.errors import PythonBlockError

from ym_handcalcs import BLOCK_CODE, convert_hc_block
from ym_handcalcs.block import block_options, namespace_results, source_file
from ymprint.data_sources import DataCatalog


@pytest.fixture
def app() -> Ymprint:
    app = Ymprint(name="hc-test")
    if BLOCK_CODE not in app.blocks:
        app.register_block(BLOCK_CODE, convert_hc_block)
    return app


def render_text(app: Ymprint, document: dict, tmp_path) -> str:
    destination = tmp_path / "out.pdf"
    app.render(document, destination)
    with pymupdf.open(destination) as pdf:
        return "".join(page.get_text() for page in pdf)


def test_bare_source_renders_the_calc(app, tmp_path):
    text = render_text(app, {"Calcs": [{"_hc": "a = 2\nb = 3\nc = a * b\n"}]}, tmp_path)
    assert "c = a · b = 2 · 3 = 6" in " ".join(text.split())


def test_source_runs_in_the_document_vars(app, tmp_path):
    document = {
        "_vars": {"w": 3},
        "Beam": [
            {"_hc_moment": {"source": "L = 6\nM = w * L**2 / 8\n"}},
            {"_py": {"source": "assert M == 13.5, M", "echo": False}},
        ],
    }
    text = render_text(app, document, tmp_path)
    assert "13.5" in text


def test_a_namespace_keeps_results_out_of_the_top_level(app, tmp_path):
    document = {
        "_vars": {"w": 3, "L": 99},
        "Beam": [
            {"_hc_moment": {"source": "L = 6\nM = w * L**2 / 8\n", "namespace": "beam"}},
            {
                "_py": {
                    "source": "assert L == 99, L\nassert 'M' not in globals()\n"
                    "assert beam == {'L': 6, 'M': 13.5}, beam",
                    "echo": False,
                }
            },
        ],
    }
    text = render_text(app, document, tmp_path)
    assert "13.5" in text


def test_functions_in_a_namespaced_source_see_its_earlier_names(app, tmp_path):
    source = "y = 2\ndef f():\n    return y\nz = f()\nt = sum(y * i for i in range(3))\n"
    document = {
        "Calcs": [
            {"_hc": {"source": source, "namespace": "calc"}},
            {"_py": {"source": "assert calc['z'] == 2 and calc['t'] == 6, calc", "echo": False}},
        ]
    }
    render_text(app, document, tmp_path)


def test_namespace_results_include_rebinding_to_the_same_value():
    document_vars = {"w": 3, "i": 0}
    source = "w = 3\nsquares = [i * i for i in range(3)]\n[n := 5 for _ in range(1)]\n"
    run_vars = dict(document_vars)
    exec(source, run_vars)
    assert namespace_results(source, document_vars, run_vars) == {"w": 3, "squares": [0, 1, 4], "n": 5}


def test_options_are_accepted(app, tmp_path):
    document = {"Calcs": [{"_hc": {"source": "x = 1\n", "theme_color": "#7A1F1F", "base_size": 12}}]}
    assert "x = 1" in render_text(app, document, tmp_path)


def test_a_failing_source_is_a_python_block_error(app, tmp_path):
    with pytest.raises(PythonBlockError):
        app.render({"Calcs": [{"_hc": "x = 1 / 0\n"}]}, tmp_path / "out.pdf")


@pytest.mark.parametrize(
    "value, message",
    [
        ({"code": "x = 1"}, "'source' or 'path' key"),
        (42, "'source' or 'path' key"),
        ({"source": "x = 1", "colour": "#000000"}, "unknown option(s) colour"),
        ({"source": "x = 1", "namespace": "my beam"}, "'namespace' must be a Python identifier"),
        ({"source": "x = 1", "path": "beam"}, "either 'source' or 'path', not both"),
        ({"path": ""}, "'path' must be a data source name or an absolute path"),
        ({"path": 3}, "'path' must be a data source name or an absolute path"),
    ],
)
def test_bad_block_values_are_reported(value, message):
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        block_options("_hc", value)


# --- path: the source in a .py file ----------------------------------------------

BEAM_PY = "L = 6\nM = w * L**2 / 8\n"


def write_project(root: pathlib.Path, data: str = "beam_calc: calcs/beam.py") -> None:
    """A project with a .py data source, and a document in a subfolder that uses it."""
    (root / "project.ymprint.yml").write_text(f"_data:\n  {data}\n", encoding="utf-8")
    (root / "calcs").mkdir()
    (root / "calcs" / "beam.py").write_text(BEAM_PY, encoding="utf-8")
    (root / "docs").mkdir()


def render_document(app: Ymprint, root: pathlib.Path, yaml_text: str) -> str:
    document = root / "docs" / "calc.yml"
    document.write_text(yaml_text, encoding="utf-8")
    app.render(document, root / "out.pdf")
    with pymupdf.open(root / "out.pdf") as pdf:
        return "".join(page.get_text() for page in pdf)


CHECK_M = "  - _py: {source: 'assert M == 13.5, M', echo: false}\n"


def test_path_names_a_py_data_source(app, tmp_path):
    write_project(tmp_path)
    text = render_document(
        app, tmp_path, "_vars: {w: 3}\nBeam:\n  - _hc: {path: beam_calc}\n" + CHECK_M
    )
    assert "13.5" in text


def test_path_can_be_absolute(app, tmp_path):
    file = tmp_path / "beam.py"
    file.write_text(BEAM_PY, encoding="utf-8")
    document = {
        "_vars": {"w": 3},
        "Beam": [
            {"_hc": {"path": str(file)}},
            {"_py": {"source": "assert M == 13.5, M", "echo": False}},
        ],
    }
    assert "13.5" in render_text(app, document, tmp_path)


def test_path_works_with_the_other_options(app, tmp_path):
    write_project(tmp_path)
    render_document(
        app,
        tmp_path,
        "_vars: {w: 3}\nBeam:\n"
        "  - _hc: {path: beam_calc, namespace: beam, theme_color: '#7A1F1F', base_size: 11}\n"
        "  - _py: {source: \"assert beam == {'L': 6, 'M': 13.5}, beam\", echo: false}\n",
    )


def test_a_path_read_is_recorded(tmp_path):
    write_project(tmp_path)
    catalog = DataCatalog.from_config([tmp_path], None, tmp_path / "docs")
    file = source_file("_hc", "beam_calc", {"data": catalog})
    assert file == (tmp_path / "calcs" / "beam.py").resolve()
    assert catalog.reads["beam_calc"] == (file,)

    absolute = tmp_path / "other.py"
    absolute.write_text("x = 1\n", encoding="utf-8")
    source_file("_hc", str(absolute), {"data": catalog})
    assert absolute.resolve() in catalog.files


def test_a_failing_path_source_is_a_python_block_error(app, tmp_path):
    file = tmp_path / "bad.py"
    file.write_text("x = 1 / 0\n", encoding="utf-8")
    with pytest.raises(PythonBlockError) as info:
        app.render({"Calcs": [{"_hc": {"path": str(file)}}]}, tmp_path / "out.pdf")
    assert any(frame.filename == str(file) for frame in traceback.extract_tb(info.value.__cause__.__traceback__))


@pytest.mark.parametrize(
    "path, data, message",
    [
        ("calcs/beam.py", "beam_calc: calcs/beam.py", "must be a `_data` source name or an absolute path"),
        ("./beam.py", "beam_calc: calcs/beam.py", "must be a `_data` source name or an absolute path"),
        ("columns", "beam_calc: calcs/beam.py", "no data source named 'columns'"),
        ("loads", "loads: calcs/loads.yml", "must be a .py file"),
        ("missing", "missing: calcs/missing.py", "does not exist"),
    ],
)
def test_bad_paths_are_reported(tmp_path, path, data, message):
    write_project(tmp_path, data)
    (tmp_path / "calcs" / "loads.yml").write_text("w: 3\n", encoding="utf-8")
    catalog = DataCatalog.from_config([tmp_path], None, tmp_path / "docs")
    with pytest.raises(ValueError, match=re.escape(message)):
        source_file("_hc", path, {"data": catalog})


def test_an_absolute_path_must_be_an_existing_py_file(tmp_path):
    with pytest.raises(ValueError, match="must be a .py file"):
        source_file("_hc", str(tmp_path / "beam.txt"), {"data": DataCatalog()})
    with pytest.raises(ValueError, match="does not exist"):
        source_file("_hc", str(tmp_path / "beam.py"), {"data": DataCatalog()})


def test_a_data_source_name_needs_a_ymprint_with_data_sources():
    with pytest.raises(ValueError, match="needs ymprint 0.8 or later"):
        source_file("_hc", "beam_calc", {})
