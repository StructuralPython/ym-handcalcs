"""
How the ``_hc`` block's heading comments (``## ...``) fit into a ymprint document:
the ``headings`` option, inherited fonts, base size and bookmarks.
"""
import pymupdf
import pytest
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

from ymprint import Ymprint

from ym_handcalcs import BLOCK_CODE, Fonts, ReportLabRenderer, convert_hc_block
from ym_handcalcs.block import block_options, document_style, inherited_fonts
from ym_handcalcs.fonts import family_from_name, missing_fonts

SOURCE = "## Moment check\nw = 12.5\n### Factored moment\nM_f = w * 6.0**2 / 8\n#### Note\nx = 1\n"
HEADINGS = ("Moment check", "Factored moment", "Note")
STYLE = {"headings": {"font": "NotoSerif"}, "body": {"font": "NotoSans"}}


@pytest.fixture
def app() -> Ymprint:
    app = Ymprint(name="hc-test")
    if BLOCK_CODE not in app.blocks:
        app.register_block(BLOCK_CODE, convert_hc_block)
    return app


def render(app, document, tmp_path):
    destination = tmp_path / "out.pdf"
    app.render(document, destination)
    pdf = pymupdf.open(destination)
    spans = {}
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text and text not in spans:
                        spans[text] = (round(span["size"], 1), span["font"])
    return spans, pdf.get_toc()


def doc_under(depth: int, hc) -> dict:
    """``hc`` nested under 'depth' list-style headings, H1..H<depth>."""
    content = [{"_hc": hc}]
    for n in reversed(range(1, depth + 1)):
        content = [{f"H{n}": content}]
    return {"_style": STYLE, **content[0]}


def heading_sizes(document_spans):
    return {name: document_spans[name][0] for name in ("H1", "H2", "H3", "H4") if name in document_spans}


# --- headings: document (the default in ymprint) ---------------------------------------

@pytest.mark.parametrize("depth", [1, 2, 3])
def test_document_headings_continue_the_documents_levels(app, tmp_path, depth):
    spans, toc = render(app, doc_under(depth, SOURCE), tmp_path)
    # Default heading sizes (body 10 pt, Major Third): h1..h6.
    sizes = [30.5, 24.4, 19.5, 15.6, 12.5, 10.0]
    expected = [sizes[min(depth + n, 5)] for n in range(3)]
    assert [spans[h][0] for h in HEADINGS] == expected
    assert all(spans[h][1].startswith("NotoSerif") for h in HEADINGS)
    assert [entry[:2] for entry in toc] == [
        *([n, f"H{n}"] for n in range(1, depth + 1)),
        [depth + 1, "Moment check"],
        [depth + 2, "Factored moment"],
        [depth + 3, "Note"],
    ]


def test_calc_headings_are_never_larger_than_the_heading_above(app, tmp_path):
    spans, _ = render(app, doc_under(3, SOURCE), tmp_path)
    assert spans["Moment check"][0] < spans["H3"][0]


def test_document_headings_stop_at_h6(app, tmp_path):
    spans, toc = render(app, doc_under(5, SOURCE), tmp_path)
    assert [spans[h][0] for h in HEADINGS] == [10.0, 10.0, 10.0]
    assert [entry[0] for entry in toc][-3:] == [6, 7, 8]


def test_document_is_the_default_inside_ymprint(app, tmp_path):
    explicit, _ = render(app, doc_under(2, {"source": SOURCE, "headings": "document"}), tmp_path)
    default, _ = render(app, doc_under(2, SOURCE), tmp_path)
    assert [default[h] for h in HEADINGS] == [explicit[h] for h in HEADINGS]


def test_document_headings_follow_the_active_text_style(app, tmp_path):
    document = {
        "_style": {**STYLE, "styles": {"small": {"body": {"size": 6}, "headings": {"font": "Helvetica"}}}},
        "H1": [{"_textstyle": "small"}, {"_hc": SOURCE}],
    }
    spans, _ = render(app, document, tmp_path)
    assert spans["Moment check"][1] == "Helvetica"
    # The calc's base size is the active family's body size.
    assert spans["w"][0] == 6.0


# --- headings: calc ---------------------------------------------------------------------

def test_calc_headings_keep_their_own_sizes_with_the_documents_font(app, tmp_path):
    spans, toc = render(app, doc_under(2, {"source": SOURCE, "headings": "calc"}), tmp_path)
    assert [spans[h][0] for h in HEADINGS] == [20.0, 14.5, 12.0]
    assert all(spans[h][1] == "NotoSerif-Bold" for h in HEADINGS)
    # Still in the document's bookmarks, under the heading that holds the block.
    assert [entry[:2] for entry in toc][2:] == [[3, "Moment check"], [4, "Factored moment"], [5, "Note"]]


# --- headings: flat ---------------------------------------------------------------------

def test_flat_headings_are_labels_without_bookmarks(app, tmp_path):
    spans, toc = render(app, doc_under(2, {"source": SOURCE, "headings": "flat"}), tmp_path)
    assert [spans[h][0] for h in HEADINGS] == [10.0, 10.0, 10.0]
    assert all(spans[h][1] == "NotoSerif-Bold" for h in HEADINGS)
    assert [entry[1] for entry in toc] == ["H1", "H2"]


def test_headings_option_is_checked():
    with pytest.raises(ValueError, match="'headings' must be one of"):
        block_options("_hc", {"source": "a = 1", "headings": "big"})
    with pytest.raises(ValueError, match="headings must be one of"):
        ReportLabRenderer(headings="big")


# --- fonts ------------------------------------------------------------------------------

def test_math_keeps_dejavu_and_comments_use_the_body_font(app, tmp_path):
    source = "## Check\n# A comment in prose.\nalpha = 2\n"
    spans, _ = render(app, {"_style": STYLE, "S": [{"_hc": source}]}, tmp_path)
    assert spans["A comment in prose."][1].startswith("NotoSans")
    assert spans["α"][1].startswith("DejaVuSans")


def test_base_14_fonts_are_inherited():
    style = type("S", (), {})()
    style.body = type("B", (), {"font": "Times-Roman"})()
    style.headings = type("H", (), {"font": "Helvetica"})()
    fonts = inherited_fonts(style)
    assert fonts.serif.regular == "Times-Roman"
    assert fonts.heading.bold == "Helvetica-Bold"
    assert fonts.sans == Fonts().sans


def test_unknown_fonts_fall_back_to_dejavu():
    assert family_from_name("NoSuchFont") is None
    style = type("S", (), {})()
    style.body = type("B", (), {"font": "NoSuchFont"})()
    style.headings = type("H", (), {"font": "NoSuchFont"})()
    assert inherited_fonts(style) == Fonts()


def test_missing_fonts_counts_standard_fonts_as_registered():
    times = family_from_name("Times-Roman")
    assert missing_fonts(Fonts(serif=times)) == []


# --- without ymprint's section (older ymprint, or no document) ------------------------

def test_without_a_section_the_calc_keeps_its_own_headings():
    from ymprint.config.config_loaders import load_report_config
    from ymprint.context_builder import build_context
    import pathlib

    s, t, d = load_report_config({}, None)
    context = build_context({}, s, d, t, {}, pathlib.Path.cwd(), pathlib.Path.cwd(), None)
    assert "section" not in context
    settings = document_style({}, context)
    assert settings["headings"] == "calc"
    assert "outline_level" not in settings and "heading_styles" not in settings


def test_standalone_renderer_sets_no_ymprint_outline():
    from handcalcs import HandCalcs

    story = HandCalcs(renderer=ReportLabRenderer())("## Check\na = 1\n")["story"]
    heading = next(f for f in story if isinstance(f, Paragraph))
    assert hasattr(heading, "hc_outline")
    assert not hasattr(heading, "ym_outline")


def test_document_mode_uses_the_given_styles():
    from handcalcs import HandCalcs

    big = ParagraphStyle("big", fontName="Helvetica", fontSize=33)
    renderer = ReportLabRenderer(headings="document", heading_styles={1: big}, outline_level=4)
    story = HandCalcs(renderer=renderer)("## Check\na = 1\n")["story"]
    heading = next(f for f in story if isinstance(f, Paragraph))
    assert heading.style is big
    assert heading.getKeepWithNext()
    assert heading.ym_outline == ("Check", 4)
