"""
Tests for the ``_hc`` ymprint block, rendered through a ymprint application.
"""
import pymupdf
import pytest

from ymprint import Ymprint
from ymprint.errors import PythonBlockError

from ym_handcalcs import BLOCK_CODE, convert_hc_block
from ym_handcalcs.block import block_options


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


def test_options_are_accepted(app, tmp_path):
    document = {"Calcs": [{"_hc": {"source": "x = 1\n", "theme_color": "#7A1F1F", "base_size": 12}}]}
    assert "x = 1" in render_text(app, document, tmp_path)


def test_a_failing_source_is_a_python_block_error(app, tmp_path):
    with pytest.raises(PythonBlockError):
        app.render({"Calcs": [{"_hc": "x = 1 / 0\n"}]}, tmp_path / "out.pdf")


@pytest.mark.parametrize(
    "value, message",
    [
        ({"code": "x = 1"}, "'source' key"),
        (42, "'source' key"),
        ({"source": "x = 1", "colour": "#000000"}, "unknown option(s) colour"),
    ],
)
def test_bad_block_values_are_reported(value, message):
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        block_options("_hc", value)
