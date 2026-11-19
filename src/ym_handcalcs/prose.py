"""
Inline Markdown in comments, as ReportLab paragraph markup.

Headings, comment lines, inline comments and docstrings are prose, and their
inline Markdown is rendered with `wenmode <https://pypi.org/project/wenmode/>`_,
as ymprint renders it in a document's own text:

- ``**strong**`` -> ``<b>``, ``*emphasis*`` -> ``<i>``;
- `` `code` `` -> the monospaced font;
- ``[label](url)`` and ``<https://...>`` -> a link.

Only inline rules are used, so a comment that starts with ``1.``, ``-``, ``#`` or
``>`` stays as written rather than becoming a list, heading or quote. Raw HTML is
text. Everything else is escaped for paragraph markup.

Inline comments are already set in italic, so their emphasis is set upright
(the usual typographic convention) and their code in the monospaced italic.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from wenmode import Wenmode
from wenmode.presets import Autolink, BackslashEscape, Emphasis, InlineCode, Link
from wenmode.renderers import BaseRenderer, RenderContext

__all__ = ["prose_markup", "ProseMarkup", "CommentProseMarkup"]

INLINE_RULES = (BackslashEscape, Emphasis, InlineCode, Link, Autolink)


class ProseMarkup(BaseRenderer):
    """Renders inline Markdown nodes as ReportLab paragraph markup."""

    def __init__(self, code_font: str) -> None:
        super().__init__()
        self.code_font = code_font


@ProseMarkup.register("text")
def render_text(renderer: ProseMarkup, node, context: RenderContext) -> str:
    return escape(node.value)


@ProseMarkup.register("emphasis")
def render_emphasis(renderer: ProseMarkup, node, context: RenderContext) -> str:
    return f"<i>{renderer.render_children(node.children, context)}</i>"


@ProseMarkup.register("strong")
def render_strong(renderer: ProseMarkup, node, context: RenderContext) -> str:
    return f"<b>{renderer.render_children(node.children, context)}</b>"


@ProseMarkup.register("inlineCode")
def render_inline_code(renderer: ProseMarkup, node, context: RenderContext) -> str:
    return f'<font name="{renderer.code_font}">{escape(node.value)}</font>'


@ProseMarkup.register("link")
def render_link(renderer: ProseMarkup, node, context: RenderContext) -> str:
    label = renderer.render_children(node.children, context)
    url = escape(node.url, {'"': "&quot;"})
    return f'<link href="{url}"><u>{label}</u></link>'


class CommentProseMarkup(ProseMarkup):
    """Inline comments: already italic, so emphasis is set upright."""


@CommentProseMarkup.register("emphasis")
def render_comment_emphasis(renderer: ProseMarkup, node, context: RenderContext) -> str:
    return f"</i>{renderer.render_children(node.children, context)}<i>"


def prose_markup(text: str, renderer: ProseMarkup) -> str:
    """``text``, a comment written as prose, as paragraph markup (see the module docstring)."""
    wen = renderer.__dict__.get("_wen")
    if wen is None:
        wen = renderer._wen = Wenmode(rules=INLINE_RULES, renderer=renderer)
    return wen.render(text)
