# ym-handcalcs

Render [handcalcs](https://github.com/connorferster/handcalcs) calculations in
[YMPrint](https://github.com/StructuralPython/ymprint) documents.

ym-handcalcs is a handcalcs renderer that produces ReportLab flowables, plus the `_hc`
block that puts them in a YMPrint document: write Python, get typeset calculations
with symbolic, substituted and computed values.

## Installation

Install it with YMPrint's `hc` extra:

```bash
pip install "ymprint[hc]"
```

ym-handcalcs needs handcalcs 2.0, which is currently a pre-release. pip installs it
automatically; uv only installs a pre-release you name, so add it with `--with`:

```bash
uv tool install "ymprint[hc]" --with "handcalcs>=2.0.0rc2"
```

YMPrint registers the `_hc` block automatically when ym-handcalcs is installed.

## The `_hc` block

```yaml
_vars:
  w_DL: 2.5
  w_LL: 4.0

Beam design:
  - _hc: |
      ## Factored load
      L = 6.0  # span, m
      w_f = 1.25 * w_DL + 1.5 * w_LL
      M_f = w_f * L**2 / 8
  - The factored moment is {{ M_f }} kN·m.
```

The source runs in the document's `_vars`, like a `_py` block: it can use values from
`_vars` and earlier blocks, and later blocks (and `{{ }}` interpolation) can use its
results. As in handcalcs, `## ...` comments are headings, `# ...` comments are prose,
inline comments annotate their line, and `# hc:` commands work as usual.

The value is either the source as a string, or a mapping:

| Option | Default | Meaning |
| --- | --- | --- |
| `source` | | The Python source to run and render. Give `source` or `path`, not both. |
| `path` | | Read the source from a `.py` file: the name of a `_data` source, or an absolute path. |
| `theme_color` | `"#0B5F66"` | A dark `#RRGGBB` colour; the whole palette is derived from it. |
| `base_size` | the body text size of the active text style | Font size, in points, that every calc style scales from. |
| `namespace` | none | Put the block's results in `_vars[namespace]` instead of the top level of `_vars`. |
| `headings` | `document` | How `## ...` heading comments render: `document`, `calc` or `flat` (see [Headings](#headings)). |

With `namespace: beam`, the source can still use everything in `_vars`, but the names it
assigns go in `_vars["beam"]`, replaced each time the block runs, and later Python code
reads them as `beam["M_f"]`. The top level of `_vars` is left as it was, though an object
the source changes in place (`loads.append(...)`) is changed there too. Unlike a `_py`
block's `namespace`, functions and generator expressions in the source can use names it
assigned earlier.

### The source in a `.py` file

With `path`, the source is read from a `.py` file instead of being written in the document.
Declare the file once as a data source in the project config, and use its name:

```yaml
# project.ymprint.yml
_data:
  beam_calc: calcs/beam_moment.py
```

```yaml
# docs/beam.yml
Beam design:
  - _hc:
      path: beam_calc
      namespace: beam
```

`path` can also be an absolute path to a `.py` file. A relative path is an error: declare
the file in `_data` instead, so documents don't contain paths. The file runs exactly as an
inline `source` would, and an error in it is reported against the file. `ym live` re-renders
when the file changes, and `ym build` counts it as an input of the document. Naming a data
source needs YMPrint 0.8 or later.

Give a block an id to use it more than once in a mapping: `_hc_loads`, `_hc_moment`.

### Headings

A calc's heading comments (`##`, `###`, `####`) are headings of the document, not a
separate hierarchy:

| `headings` | Result |
| --- | --- |
| `document` (default) | A `##` heading gets the level a YAML heading at the block's position would get, and `###` and `####` the next two levels. They use the document's heading styles (h1–h6) and join its PDF bookmarks. The accent rule under the first two levels stays. |
| `calc` | The calc's own heading sizes (2×, 1.45× and 1.2× the base size) and accent colour. They still join the bookmarks, under the heading that holds the block. |
| `flat` | Bold labels at the base size, with no heading level and no bookmark. |

```yaml
Calculations:          # h1
  - Beam B01:          # h2
    - _hc:
        path: beam_calc   # its `## Moment check` is h3, `### Factored moment` is h4
```

So a calculation renders correctly at any depth, including inside a partial document
(`_include`).

In every mode, the calc follows the active text style (`_textstyle`):
its base size is that style's body size, prose comments (`# ...`) use its body font and
headings use its heading font. Math keeps DejaVuSans, which has the Greek letters and
operators that a document font such as Helvetica lacks. A font without registered bold
and italic faces isn't inherited.

`document` mode and the bookmarks need YMPrint 0.11 or later. With an older YMPrint, the
calc uses `calc` headings.

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

# or straight to a PDF
HandCalcs(renderer=ReportLabRenderer())("a = 2\nb = a * 3\n", destination="calcs.pdf")
```

## Development

```bash
uv sync
uv run pytest
```

Regenerate the golden files with `HANDCALCS_UPDATE_GOLDEN=1 uv run pytest` and review the diff.

## License

Apache-2.0. See [LICENSE](LICENSE).
