# ym-handcalcs

Render [handcalcs](https://github.com/connorferster/handcalcs) calculations in
[YMPrint](https://github.com/StructuralPython/ymprint) documents.

ym-handcalcs is a handcalcs renderer that produces ReportLab flowables, plus the `_hc`
block that puts them in a YMPrint document: write Python, get typeset calculations
with symbolic, substituted and computed values.

## Installation

Install it with YMPrint's `hc` extra:

```bash
uv tool install "ymprint[hc]"
# or
pip install "ymprint[hc]"
```

YMPrint registers the `_hc` block automatically when ym-handcalcs is installed.

## The `_hc` block

```yaml
_vars:
  w_DL: 2.5
  w_LL: 4.0

Beam design:
  - _hc: |
      # Factored load
      L = 6.0  # span, m
      w_f = 1.25 * w_DL + 1.5 * w_LL
      M_f = w_f * L**2 / 8
  - The factored moment is {{ M_f }} kN·m.
```

The source runs in the document's `_vars`, like a `_py` block: it can use values from
`_vars` and earlier blocks, and later blocks (and `{{ }}` interpolation) can use its
results. Comments are rendered as headings (`# ...`), prose and inline comments as in
handcalcs, and `# hc:` commands work as usual.

The value is either the source as a string, or a mapping:

| Option | Default | Meaning |
| --- | --- | --- |
| `source` | (required) | The Python source to run and render. |
| `theme_color` | `"#0B5F66"` | A dark `#RRGGBB` colour; the whole palette is derived from it. |
| `base_size` | the document's body text size | Font size, in points, that every calc style scales from. |

Give a block an id to use it more than once in a mapping: `_hc_loads`, `_hc_moment`.

## Using the renderer directly

The renderer works without YMPrint. It returns a ReportLab stylesheet and a story:

```python
from handcalcs import HandCalcs
from ym_handcalcs import ReportLabRenderer, build_pdf
from ym_handcalcs.fonts import ensure_dejavu_registered

ensure_dejavu_registered()  # YMPrint registers the DejaVu fonts itself
result = HandCalcs(renderer=ReportLabRenderer(theme_color="#7A1F1F"))("a = 2\nb = a * 3\n")
result["story"]  # list of flowables
build_pdf(result, "calcs.pdf", title="Calcs")
```

## Development

```bash
uv sync
uv run pytest
```

Regenerate the golden files with `HANDCALCS_UPDATE_GOLDEN=1 uv run pytest` and review the diff.

## License

Apache-2.0. See [LICENSE](LICENSE).
