"""
ym_handcalcs: renders handcalcs to ReportLab, and the `_hc` block for ymprint.

    from handcalcs import HandCalcs
    from ym_handcalcs import ReportLabRenderer

    result = HandCalcs(renderer=ReportLabRenderer())(source)
    result["stylesheet"]  # reportlab.lib.styles.StyleSheet1
    result["story"]       # list of flowables
"""
__version__ = "0.1.0"

from .fonts import Fonts, FontFamily, ensure_dejavu_registered
from .styles import DEFAULT_THEME, Palette, build_stylesheet
from .renderer import ReportLabRenderer
from .pdf import build_pdf
from .block import BLOCK_CODE, convert_hc_block
