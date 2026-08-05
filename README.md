# sermonflow-slides

Generate ProPresenter-ready verse slides that match a hand-built Photoshop
template, one slide per verse, from a chapter reference.

Give it `"John 17"` and it produces 26 transparent 1920×1080 TIFFs — verse text
set over a black left-hand scrim, reference line underneath — laid out to match
a professionally produced reference deck closely enough that they can be
dropped into the same service.

**Status: proof of concept.** It works end to end and is well covered by tests,
but it scrapes HTML for verse text and writes to a local folder. See
[Roadmap](#roadmap).

---

## What it actually does

```
retrieve  →  format  →  validate  →  render
```

1. **Retrieve** — fetch a chapter from BibleGateway, return raw verse strings.
2. **Format** — the "light edits" that make a verse readable standing alone on
   a screen:
   - strip scrape residue (`[a]` footnote markers, `(BZ)` cross-references,
     stranded verse numbers)
   - **quote carry**: a verse in the middle of an ongoing quotation gets its
     own opening and closing marks, because each slide is read on its own. A
     quotation that spans 20 verses gets marks on all 20, not just the ends.
   - **capitalize** the first letter, even mid-sentence fragments
   - normalize straight quotes to typographic ones
3. **Validate** — refuse to render if anything suspicious survived: leftover
   markers, straight quotes, characters the font cannot draw, verses too long
   for a slide. Fails loudly rather than putting `[a]` on a screen mid-service.
4. **Render** — balanced line wrapping, grid-snapped vertical centering, the
   black gradient scrim, output as RGBA TIFF.

Nearly every layout constant was derived by **measuring the reference deck**
rather than guessing — box width, line height, the 72px placement grid, the
gradient's alpha curve. The reasoning and measurements are written up in
[`FORMATTING_NOTES.md`](FORMATTING_NOTES.md), including two places where an
assumption from the PSD turned out to be wrong.

---

## Install

Requires **Python 3.11+** (developed on 3.14) and macOS. It renders with Neue
Haas Grotesk Display Pro if installed and falls back to the system's Helvetica
Neue otherwise. See [Fonts](#fonts).

```bash
git clone <this repo>
cd sermonflow-slides

python3 -m venv deps
./deps/bin/pip install -r requirements.txt
```

---

## Usage

```bash
# render a chapter
./deps/bin/python main.py "John 17"

# somewhere else, another translation
./deps/bin/python main.py "1 John 4" --output-dir ./slides/1john4
./deps/bin/python main.py "Psalm 23" --translation NIV

# see the wrapped lines without rendering 200MB of TIFFs
./deps/bin/python main.py "John 17" --dry-run
```

| Flag | Meaning |
|---|---|
| `-o`, `--output-dir` | where slides land (default `./slides`) |
| `-t`, `--translation` | version code (default `ESV`) |
| `-n`, `--dry-run` | print wrapped lines, render nothing |
| `--no-strict` | render even if validation complains |

Slides are named `John_17_001.tif` … `John_17_026.tif`, zero-padded so they
sort into verse order in any file browser or import dialog.

> **Heads up on size:** uncompressed RGBA TIFFs are ~8MB each, so a chapter is
> roughly 200MB. `slides/` is gitignored.

### Comparing against a reference deck

```bash
./deps/bin/python compare.py slides "John 17 "
./deps/bin/python compare.py slides "John 17 " --overlays ./overlays
```

Prints per-slide metrics — line count, first-line offset, reference gap, width
ratio, ink overlap, background error — and `--overlays` writes red/green
onion-skin images (reference red, ours green, overlap yellow) so misalignment is
visible at a glance. See [Checking a change](#checking-a-change).

### Tests

```bash
./deps/bin/python -m pytest tests/ -q     # 247 tests, ~27s
```

Covers the text rules, wrap quality ("blockiness"), layout geometry against the
real reference deck, hostile input (empty text, 150-character junk tokens,
emoji, CJK, control characters), and all 66 books of the canon. Tests that
depend on glyph coverage assert the *contract* rather than a hardcoded verdict,
so they hold under either font choice.

---

## Using it as a library

`slidegen` has no network or CLI dependency, so it works fine on text from
anywhere:

```python
import slidegen

verses = [
    ("Some quoted line of text,", "Iliad 1:1"),
    ("and the line that follows it.", "Iliad 1:2"),
]

slidegen.generate_slides(verses, output_dir="./out")
```

`generate_slides` runs the formatting pipeline itself. The quote-carry rule is
order-dependent, so pass the **whole passage in order** and let it run once.

---

## Fonts

The template is set in **Neue Haas Grotesk Display Pro** — 55 Roman for verse
text, 65 Medium for the reference line, 60pt, 72px leading, tracking 0, read
straight out of the PSD.

Font selection is a list in `slidegen.py`, best first; the first choice whose
files are all present wins, so installing the real font is the only step needed
to use it:

| Choice | Files | Scale |
|---|---|---|
| Neue Haas Grotesk Display Pro | `~/Library/Fonts/NeueHaasDisplay{Roman,Mediu}.ttf` | 1.0 |
| Helvetica Neue (substitute) | `/System/Library/Fonts/HelveticaNeue.ttc` idx 0 / 10 | 1/1.10 |

The scale condenses rendered text horizontally. It exists only for the
substitute — Helvetica Neue sets ~10% wider at the same size, so the reciprocal
pulls line widths back onto the reference. With the real font it is `1.0`, text
is drawn directly with no resample step, and it is both exact and sharper.

`TEXT_BOX_WIDTH = 678` is the best-scoring width for **both** choices, so
switching fonts needs no refit.

### Kerning

Pillow's basic layout engine positions each glyph by its bare advance width and
ignores GPOS entirely. Photoshop kerns, so the reference deck is kerned and
unkerned text runs measurably wide — about 0.3% on a typical line and up to
1.3% on one full of kerned pairs, which is enough to move a line break.

`slidegen` therefore reads the font's GPOS `kern` pairs itself and applies them
in both measurement and drawing. Drawing per character at kerned offsets is
safe because PIL's basic layout already places each glyph independently, so
per-character drawing at the same offsets is pixel-identical to drawing the
whole string — verified across the deck. Kerning is what takes per-line ink
width from a median of 1.0033 against the deck to **1.0000**.

Only `LookupType 2` (pair adjustment) is read, which is all Neue Haas uses.
The legacy `kern` table that Helvetica Neue carries instead is deliberately
ignored, so the substitute keeps the metrics its scale was fitted against.

> Installing Pillow with **Raqm** would get kerning, shaping and bidi from
> HarfBuzz for free and make this code unnecessary — but it needs Pillow built
> from source against `libraqm`, which the plain wheel in `requirements.txt`
> gives up.

### Glyph coverage

Neue Haas Grotesk Display Pro carries **432 glyphs and no Greek at all**;
Helvetica Neue does have it. So a verse or point quoting a Greek word is
refused by validation under the real font rather than rendered as tofu boxes.
That is the safe failure, but it is a real difference worth knowing before a
service. `find_unrenderable` is what reports it.

### Checking a change

`compare.py` is how you verify any of this. Its `iou` column — ink overlap with
the reference deck — is the metric that sees letterform *shape* rather than
just extent, and it is the one that showed the font swap mattered:

| | width ratio | ink overlap |
|---|---|---|
| Helvetica Neue + 1/1.10 squeeze | 1.002 | 0.241 |
| Neue Haas Grotesk + kerning | 1.002 | **0.511** |

The width ratio is identical because the squeeze was fitted to make it so.
Overlap more than doubled.

---

## Layout, as measured

| | |
|---|---|
| Canvas | 1920 × 1080 RGBA |
| Left margin | 91px |
| Text box | 678px (post-scale) |
| Font size | 60px |
| Line height | 72px (auto-leading 1.2 × 60) |
| Reference gap | 143px below the last verse line |
| Vertical placement | block centered, snapped to a 197 + 72k grid |
| Reference budget | 741px (scrim, not the verse box) |
| Max verse lines | 12 |

---

## Roadmap

Current state is a proof of concept. Roughly in order of how much each would
improve things:

### 1. A real Bible API

`retrieve.py` scrapes HTML and **will break** whenever BibleGateway restyles
their passage page. It is deliberately thin and isolated for exactly this
reason — all the durable logic lives in `slidegen.py`, and the replacement
contract is one line:

> return `[(verse_text, "Book Chapter:Verse TRANSLATION"), ...]` in verse order

Candidates: API.Bible, ESV API (free for non-commercial, and the project is
already ESV-first), or a licensed local corpus. A local corpus also makes the
whole pipeline offline and removes the copyright question around caching.

Worth adding alongside: **caching**, so re-running a chapter never re-fetches.

### 2. NLP-driven slide selection from sermon notes

The interesting one. Today you tell it a chapter and it renders every verse.
What you actually want is to hand it **sermon notes** and get back the slides
the sermon needs:

- extract scripture references from free-form notes, including loose ones
  ("later in that chapter", "the passage about the vine")
- decide which verses actually get a slide vs. which are read past
- detect **Point slides** — the emphasis lines that are not scripture at all
  (see below)
- order the deck to follow the sermon rather than the chapter
- optionally split a long verse across two slides at a sensible clause break

This is where an LLM earns its place: reference extraction and "is this a point
or a passage" are judgment calls, not regexes. Everything downstream of that
decision is already deterministic and tested.

### 3. Point slides

A second slide type: a short phrase of emphasis, **no reference line**,
centered, bold. The architecture already supports it cleanly — `block_height`
and `block_top` are the only places the reference line is assumed. Waiting on a
reference example to measure, rather than guessing the centering.

### 4. Push to GCS

Render straight to a bucket instead of a local folder, so the slides are
available to whoever is running ProPresenter without a hand-off:

- upload per chapter with a stable object path
- probably switch to **LZW-compressed TIFF or PNG** first — 200MB per chapter
  uncompressed is a lot to push every week
- signed URLs or a simple index page for the tech team
- a scheduled job that builds next Sunday's deck from the notes doc
  automatically

### Smaller things

- Split an over-long verse across two slides instead of raising
  `SlideOverflowError` (nothing in John 17 comes close, but a long Psalm might)
- The reference line still does not wrap. It is now budgeted against the scrim
  (`REF_MAX_WIDTH`, 741px) rather than the narrower verse box, which is enough
  for every reference in the canon — `"Song of Solomon 8:14 ESV"` is the
  longest at 686px — but a long non-canonical reference is still reported
  rather than handled
- Poetry (Psalms) and short disconnected verses have no professional reference
  slides to validate against yet
- A `--compress` flag, and PNG output for previewing

---

## Layout of the repo

| File | Role |
|---|---|
| `main.py` | CLI entry point |
| `slidegen.py` | All generation: text rules, wrapping, layout, rendering |
| `retrieve.py` | BibleGateway scraping — thin, disposable, expected to be replaced |
| `compare.py` | Dev tool: diff generated slides against a reference deck |
| `tests/` | 247 tests |
| `FORMATTING_NOTES.md` | How every constant was derived, and what is still open |
