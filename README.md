# sermonflow-slides

A Claude plugin that makes ProPresenter-ready slides for a sermon: Scripture
one verse per slide, or sermon points in three styles. The slides match a
hand-built Photoshop template closely enough to drop into the same service.

Ask for `"John 17"` and it produces 26 transparent 1920×1080 TIFFs: verse text
set over a black left-hand scrim, with the reference line underneath.

The plugin file is the only supported way to use it. Everything below the
[Maintaining](#maintaining) heading is for whoever builds that file.

---

## Install

You need:

- **Claude**: the desktop app (Cowork) or Claude Code
- **[uv](https://docs.astral.sh/uv/)** on the same machine. The plugin starts
  its slide server with `uv run`. Install uv with `brew install uv`, or with the
  installer from the uv docs.
- **An internet connection on first use.** The first launch downloads the
  server's Python dependencies. Fetching Scripture needs the network every time.

Then add the plugin:

1. Get the `sermonflow-slides.plugin` file from whoever maintains it.
2. In the Claude desktop app, open **Customize → Plugins**.
3. Choose the upload option and select `sermonflow-slides.plugin`.

A plugin uploaded in the desktop app also syncs to Claude Code on the same
account, where it shows up as `sermonflow-slides@synced` in
`claude plugin list`.

**To update**, uninstall the old version under **Customize → Plugins** and
upload the new file.

---

## Use

Ask Claude in plain language:

- "Preview John 17."
- "Make slides for Romans 8 in ~/Documents/sunday-slides."
- "Rolling point slides: Jesus is Lord. He rose from the dead. We are redeemed."
- "Which point styles are there?"

Claude usually previews first and shows you how every slide will wrap. It
renders once you approve the preview, or straight away if you asked outright
for the files. Name the folder you want the slides in; otherwise Claude picks
one and tells you the path. If validation finds a problem, it stops and tells
you instead of rendering. The kinds of problem it catches: leftover footnote
markers, a character the font cannot draw, a verse too long for one slide, or
too many points for one screen. Tell it to go ahead anyway and it renders what
it can: a verse too long for a slide is left out, and Claude tells you which.

### Slide types

**Scripture** is fetched by reference. You name the passage and never paste
the text. Each verse becomes one slide, with its reference line
(`John 17:1 ESV`) underneath.

**Points** are your own words, set in italic with no reference line. There are
three styles:

| Style | What you get |
|---|---|
| `rolling` (default) | The list builds up: slide N shows points 1 to N, each at a fixed position, so playing the slides in order reveals one point at a time. For an outline the speaker walks through. |
| `centered` | One statement per slide, centered. For a single line meant to land on its own. |
| `stacked` | One slide per entry. Put line breaks inside an entry to stack several paragraphs on its slide, such as a lie above its truth or a short list of steps. |

### Where the Scripture comes from

The **ESV API** is used when `ESV_API_KEY` is set in the environment the slide
server runs in. Keys are free for non-commercial use from
[api.esv.org](https://api.esv.org/). Without a key, the plugin falls back to
**BibleGateway**, which needs no setup and also serves translations other than
the ESV.

### Output

- 1920×1080 RGBA TIFFs, uncompressed: about **8 MB per slide**, so a whole
  chapter is roughly 200 MB.
- Files are named so they sort in order: `John_17_001.tif`, `John_17_002.tif`,
  and so on for Scripture, and `point_001.tif` onward for points.
- Every run writes into its own timestamped folder inside the one you name
  (`.../2026-09-22_101530/`), so re-running never overwrites an earlier deck or
  leaves one of its slides sitting in this one.

### Limits

- The plugin does not read Word or PDF files. Name the passage, or give the
  points as text.
- The typeface has no Greek. A verse that quotes a Greek word is refused
  rather than rendered with empty boxes.

---

## Maintaining

### How it fits together

```
.claude-plugin/plugin.json   the plugin manifest
.mcp.json                    starts the server: uv run --project ${CLAUDE_PLUGIN_ROOT} sermonflow-mcp
skills/                      tells Claude when and how to use the tools
src/sermonflow/              the Python package the server runs
```

The server (`src/sermonflow/mcp_server.py`) gives Claude five tools:

| Tool | What it does |
|---|---|
| `preview_slides(reference, translation="ESV")` | Wrapped lines per verse, plus any validation problems. Writes nothing. |
| `generate_slides(reference, translation="ESV", output_dir="./slides", strict=True)` | Fetches, validates and renders a chapter. Returns absolute paths, or the problems and a hint when it refuses. |
| `preview_points(points, style="rolling")` | How a list of points will lay out. Writes nothing. |
| `generate_points(points, style="rolling", output_dir="./slides", strict=True)` | Renders a list of points. Returns absolute paths, or the problems and a hint when it refuses. |
| `list_layouts()` | The point styles and when each fits, read from the layout registry. |

Validation problems come in three kinds:

- **Doubts**, like a character the font can't draw. `strict=True` refuses;
  `strict=False` renders anyway.
- **A verse too long for one slide.** `strict=True` refuses; `strict=False`
  renders the rest of the passage and leaves that verse out. The problem says
  `would be skipped`, the result's `skipped` field names it, and the hint tells
  Claude to say what is missing from the deck.
- **Nothing to render**: points that run past the safe area, no text, or a
  passage where no verse fits. These are refused either way, and the hint says
  so, so Claude doesn't retry something that can't work.

The tools are split by slide type rather than combined behind one mode flag,
because the split lets Claude choose from what the user said. A passage named
by reference can only mean `generate_slides`, and words the user supplies can
only mean `generate_points`.

Every chapter goes through the same four steps:

```
retrieve  →  format  →  validate  →  render
```

1. **Retrieve**: fetch the chapter through a [provider](#bible-providers).
2. **Format**: the light edits that make a verse readable standing alone on a
   screen. It strips scrape residue (`[a]` footnotes, `(BZ)` cross-references,
   stranded verse numbers) and applies **quote carry**: a verse in the middle
   of a quotation gets its own opening and closing marks. It also capitalizes
   the first letter and converts straight quotes to typographic ones.
3. **Validate**: refuse to render anything suspicious that survived.
4. **Render**: balanced line wrapping, grid-snapped vertical placement, the
   gradient scrim, and RGBA TIFF output.

### Build the plugin file

```bash
git archive --format=zip -o sermonflow-slides.plugin HEAD \
    .claude-plugin .mcp.json pyproject.toml README.md skills src
```

This builds from committed files only, so commit first. `README.md` has to be
in the archive because `pyproject.toml` names it as the package readme, and the
package build fails without it.

To try a build in Claude Code before handing it out, give it a `.zip` name.
`--plugin-dir` ignores the `.plugin` extension.

```bash
cp sermonflow-slides.plugin /somewhere/sermonflow-slides.zip
claude --plugin-dir /somewhere/sermonflow-slides.zip mcp list   # expect: ✔ Connected
```

When you release, bump the version in `pyproject.toml`,
`src/sermonflow/__init__.py` and `.claude-plugin/plugin.json` together.

### Dev setup

```bash
python3 -m venv deps
./deps/bin/pip install -e '.[dev]'      # the package plus pytest, numpy, pyright

./deps/bin/python -m pytest -q
./deps/bin/pyright                      # src/ is held to strict
```

`pyproject.toml` is the only dependency list; there is no `requirements.txt`.
CI runs the tests on ubuntu-24.04. Its Pillow is built with Raqm and the macOS
wheels are not, which is what caught the kerning bug described under
[Kerning](#kerning).

The tests are offline. They cover the text rules, wrap quality, layout
geometry, hostile input (empty text, junk tokens, emoji, CJK, control
characters), all 66 books of the canon, the provider parsers (against saved
fixtures) and the MCP tools.

In VS Code, the interpreter defaults to `./deps/bin/python` through
`.vscode/settings.json`. VS Code can't display TIFFs, so the recommended
extensions include Luna Paint for viewing rendered slides.

### Bible providers

Retrieval is the part most likely to fail, because it depends on a third party
staying put. So it sits behind a `BibleProvider` interface
(`sermonflow.providers`), and nothing above it imports a concrete backend. The
contract is:

> `fetch_chapter(reference, translation)` → `[(verse_text, "Book Chapter:Verse TRANSLATION"), ...]` in verse order

| Backend | When it's used | Notes |
|---|---|---|
| **ESV API** (`api.esv.org`) | `ESV_API_KEY` is set | First-party, stable and documented. ESV only. |
| **BibleGateway** (scraper) | no key | Zero-config fallback. It parses HTML, so it breaks if the site changes its markup. |

A new backend is a class in `src/sermonflow/providers/` plus a line in
`registry.py`. See [`docs/DATABASE_AND_PACKAGING.md`](docs/DATABASE_AND_PACKAGING.md)
for the planned caching layer.

**The reference line is built here, not trusted.** Sources disagree about what
to call a passage: BibleGateway's heading for Jude is `Jude`, while the ESV API
calls the same request `Jude 1-25`. `format_citation` parses whichever label
arrived and always emits `Book Chapter:Verse TRANSLATION`. Single-chapter books
get an explicit chapter (`Jude 1:3 ESV`) so every slide in a deck is labelled
the same way.

### Fonts

The template is set in **Neue Haas Grotesk Display Pro** at 60px with 72px
leading: 55 Roman for verse text and 65 Medium for the reference line, read
from the PSD. Point slides use 65 Medium Italic, measured from the point
templates. The `.ttf` files are bundled in `src/sermonflow/assets/fonts/` and
found with `importlib.resources`, so nothing depends on system fonts.

#### Kerning

Photoshop kerns, so the reference deck is kerned. Pillow's basic layout engine
ignores the font's GPOS kerning, so `fonts.py` applies the pair kerning itself,
in measurement and in drawing alike. With kerning, per-line ink width goes from
a median of 1.0033 against the deck to **1.0000**.

The engine is **pinned to BASIC** (`fonts.LAYOUT_ENGINE`). Linux Pillow wheels
include Raqm, which kerns natively. Left unpinned, Raqm would kern the
measurement a second time but not the drawing, so the wrapping would no longer
describe what gets drawn. On CI the two disagreed by 26px on one line.

#### Glyph coverage

The typeface has 432 glyphs and no Greek, so `find_unrenderable` refuses a
verse with a Greek word rather than letting it render as empty boxes.

#### Checking a change against a reference deck

`compare.py` compares generated slides with a reference deck and prints
metrics for each slide: line count, first-line offset, reference gap, width
ratio, ink overlap and background error.

```bash
./deps/bin/python compare.py ./slides "./John 17 " --overlays ./overlays
```

`--overlays` writes onion-skin images, with the reference in red, ours in green
and overlap in yellow.

### Layout, as measured

Nearly every constant was measured from the reference decks rather than
guessed.

Shared by every slide type:

| | |
|---|---|
| Canvas | 1920 × 1080 RGBA |
| Left margin | 91px |
| Line height | 72px |
| Vertical placement | block centered, snapped to a 197 + 72k grid |
| Legible width | 741px, where the scrim falls below half opacity |

Verse slides:

| | |
|---|---|
| Text box | 678px, deliberately narrower than the scrim |
| Reference gap | 143px below the last verse line |
| Max verse lines | 12 |

Point slides (`rolling` and `centered`), measured from
`template/point-templates/`:

| | |
|---|---|
| Text box | 741px: points wrap at the scrim, not the verse box |
| Rolling step | 144px between points, exactly two line heights |
| Centered block | centered and snapped to the shared grid |

`stacked`, measured from a later hand-made deck (Run week 2):

| | |
|---|---|
| Left margin | 70px, the deck's own |
| Vertical placement | ink block centered on y=520, not snapped to the grid |
| Paragraph gap | 144px, the same step as `rolling` |

### Slide types, and adding one

```
layouts/
  base.py     canvas, the 197 + 72k grid, the scrim, and the Placed/DrawOp IR
  verse.py    wrapped passage with its reference underneath
  points.py   short statements: rolling, centered and stacked
```

Every layout produces the same thing: a `Placed`, which is a finished slide
expressed as draw operations at ink coordinates and nothing else.

```python
DrawOp(text="The Atonement.", left=91, ink_top=629, weight="medium-italic")
Placed(ops=(...), stem="point_004")
```

`render.py` consumes only `Placed`, so it draws any layout without changes.
Weights are names (`"roman"`, `"medium-italic"`), not font paths, so a layout
set in another cut of the typeface needs no font code.

A new point style is a planning function plus one entry in `POINT_STYLES`
(`layouts/__init__.py`). Its summary then appears in `list_layouts`
automatically. The tool descriptions in `mcp_server.py` and the skill in
`skills/` are written by hand, so add the style to both.

### Repo layout

| Path | Role |
|---|---|
| `.claude-plugin/`, `.mcp.json`, `skills/` | The plugin itself |
| `src/sermonflow/mcp_server.py` | The MCP server the plugin starts |
| `src/sermonflow/cli.py` | Fetch/validate/preview helpers the server uses, and a `sermonflow` command for local runs |
| `src/sermonflow/providers/` | Retrieval behind `BibleProvider` (ESV API, BibleGateway) |
| `src/sermonflow/text.py` | Text normalization: artifacts, quote carry, capitalization |
| `src/sermonflow/wrap.py` | Line breaking: greedy and balanced wrap |
| `src/sermonflow/fonts.py` | Font loading, metrics, kerning, glyph drawing |
| `src/sermonflow/layouts/` | One module per slide type, behind the shared `Placed` IR |
| `src/sermonflow/render.py` | Scrim, composition and TIFF output, independent of layout |
| `src/sermonflow/assets/fonts/` | The bundled typeface |
| `compare.py` | Dev tool: compare generated slides with a reference deck |
| `tests/` | The test suite |

---

## Roadmap

- **Slide cache and zip hand-off.** Check a store before rendering, and bundle
  a chapter into one file. Designed in
  [`docs/DATABASE_AND_PACKAGING.md`](docs/DATABASE_AND_PACKAGING.md).
- **Slides from sermon notes.** Hand Claude the notes and get back the slides
  the sermon needs: extracting references, telling passages from points, and
  ordering the deck.
- **Smaller things:** split an over-long verse across two slides instead of
  refusing it; wrap the reference line; compressed TIFF or PNG output.
