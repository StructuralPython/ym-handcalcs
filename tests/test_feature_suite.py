"""
handcalcs' shared feature suite (``handcalcs.testing``), run against the ReportLab
renderer: every feature renders without an error and shows (and hides) the names it
should. The cases come from the installed handcalcs, so a new handcalcs feature is
tested here as soon as CI installs the release (or the pre-release) that adds it.
"""
import pytest

testing = pytest.importorskip("handcalcs.testing", reason="handcalcs has no feature suite yet")

from reportlab.platypus import Paragraph

from ym_handcalcs import ReportLabRenderer
from ym_handcalcs.flowables import BreakingParagraph, CalcLine, Chip, ParamGrid
from ym_handcalcs.renderer import plain_text

from test_reportlab_renderer import leaves


def story_text(rendered: dict) -> str:
    """The visible text of a rendered story: every line, grid cell, heading and comment."""
    texts = []
    for _, flowable in leaves(rendered["story"]):
        if isinstance(flowable, CalcLine):
            texts.extend([*flowable.columns, flowable.comment or ""])
        elif isinstance(flowable, ParamGrid):
            texts.extend(part for cell in flowable.cells for part in cell if part)
        elif isinstance(flowable, BreakingParagraph):
            texts.append(flowable.markup)
        elif isinstance(flowable, Chip):
            texts.append(flowable.paragraph.text)
        elif isinstance(flowable, Paragraph):
            texts.append(flowable.text)
    return "\n".join(plain_text(str(text)) for text in texts)


@pytest.mark.parametrize("case", testing.FEATURE_CASES, ids=lambda case: case.id)
def test_feature_case(case):
    testing.check_case(ReportLabRenderer(), case, text_of=story_text)
