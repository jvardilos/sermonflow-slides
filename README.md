# sermonflow-slides

Generate ProPresenter-ready verse slides that match a hand-built Photoshop
template, one slide per verse, from a chapter reference — as a command, as a
Python library, or as an **MCP tool an LLM can call directly**.

Give it `"John 17"` and it produces 26 transparent 1920×1080 TIFFs — verse text
set over a black left-hand scrim, reference line underneath — laid out to match
a professionally produced reference deck closely enough that they can be dropped
into the same service.

```
retrieve  →  format  →  validate  →  render
```

1. **Retrieve** — fetch a chapter through a pluggable [provider](#bible-providers):
   the official **ESV API** when a key is set, the **BibleGateway** scraper
   otherwise. Returns raw verse strings.
2. **Format** — the "light edits" that make a verse readable standing alone on a
   screen: strip scrape residue (`[a]` footnotes, `(BZ)` cross-refs, stranded
   verse numbers), **quote carry** (a verse mid-quotation gets its own opening
   and closing marks — a quotation spanning 20 verses gets marks on all 20),
   capitalize the first letter, normalize quotes to typographic ones.
3. **Validate** — refuse to render if anything suspicious survived: leftover
   markers, straight quotes, characters the font cannot draw, verses too long
   for a slide. Fails loudly rather than putting `[a]` on a screen mid-service.
4. **Render** — balanced line wrapping, grid-snapped vertical centering, the
   black gradient scrim, output as RGBA TIFF.

Nearly every layout constant was derived by **measuring the reference deck**
rather than guessing — box width, line height, the 72px placement grid, the
gradient's alpha curve.

---

## Install

Requires **Python 3.11+**. The typeface is **bundled** with the package, so it
renders identically on macOS, Linux and Windows with nothing to install — see
[Fonts](#fonts).

```bash
git clone <this repo>
cd sermonflow-slides

python3 -m venv deps
./deps/bin/pip install -e '.[dev]'      # or: pip install .   (no dev tools)
```

This installs two console commands, `sermonflow` and `sermonflow-mcp`.

---

## Connect it to a model (MCP)

The reason this is a package: any model that speaks the **Model Context
Protocol** can go from a reference to finished slides in one tool call. The
`sermonflow-mcp` command is a standard MCP server, so it drops into any
MCP-capable host — from a local open model like **gpt-oss** to the **ChatGPT**
app. The model gets two tools:

| Tool | What it does |
|---|---|
| `preview_slides(reference, translation="ESV")` | Wrapped lines per verse, **nothing written** — the safe look before committing files. Returns any validation problems. |
| `generate_slides(reference, translation="ESV", output_dir="./slides", strict=True)` | Fetch, validate and render to a folder. Returns the written paths, or the blocking problems if `strict` and the text isn't clean. |

So *"preview John 17, then render it to ~/sunday/slides"* becomes a
`preview_slides` call the model reads back to you, then a `generate_slides` call
— the validation gate keeping scrape residue off the screen mid-service.

### Two transports — pick by where the model runs

```bash
sermonflow-mcp            # stdio (default): a LOCAL host launches this process
sermonflow-mcp --http     # streamable HTTP on 127.0.0.1:8000: a REMOTE host connects to a URL
```

| Transport | Use when | Hosts |
|---|---|---|
| **stdio** (default) | the host runs on the same machine and can launch a process | Claude Code / Desktop, LM Studio, an OpenAI Agents-SDK agent (incl. local gpt-oss) |
| **HTTP** (`--http`) | the host is remote and connects to a URL | ChatGPT connectors, OpenAI Responses API, any hosted agent |

> **You don't keep the stdio server running yourself.** A local host *spawns its
> own copy* on demand — you only register the command. Only the HTTP mode is a
> long-lived server you run and hand out a URL for.

### Local hosts (stdio)

**Claude Code** — from the repo root:

```bash
claude mcp add sermonflow-slides -- "$(pwd)/deps/bin/sermonflow-mcp"
# optional ESV API key:  claude mcp add sermonflow-slides --env ESV_API_KEY=... -- "$(pwd)/deps/bin/sermonflow-mcp"
```

**Claude Desktop** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sermonflow-slides": {
      "command": "/absolute/path/to/deps/bin/sermonflow-mcp",
      "env": { "ESV_API_KEY": "optional" }
    }
  }
}
```

**A local open model (gpt-oss, Llama, …)** — the model doesn't speak MCP itself;
you wrap it in an MCP-capable host. Easiest is the **OpenAI Agents SDK**, which
launches the stdio server and hands the tools to *any* model, including a local
gpt-oss served behind an OpenAI-compatible endpoint (Ollama / vLLM / LM Studio):

```python
from agents import Agent, Runner            # pip install openai-agents
from agents.mcp import MCPServerStdio

async def main():
    async with MCPServerStdio(params={
        "command": "/absolute/path/to/deps/bin/sermonflow-mcp",
    }) as slides:
        agent = Agent(
            name="deck-builder",
            model="gpt-oss:20b",              # or any OpenAI-compatible model id
            mcp_servers=[slides],
        )
        print(await Runner.run(agent, "Preview John 17 and render it to ./out"))
```

LM Studio works too: add the same `command` to its `mcp.json`, then any model
you load can call the tools.

### Remote hosts (HTTP) — ChatGPT and hosted agents

ChatGPT's **connectors / developer mode** attach to a *remote* MCP server, so
run the HTTP transport and give ChatGPT its URL:

```bash
sermonflow-mcp --http --host 0.0.0.0 --port 8000     # serves MCP at http://<host>:8000/mcp
```

- **Locally, to try it:** put a tunnel in front (`ngrok http 8000`,
  `cloudflared tunnel --url http://localhost:8000`) and add the resulting HTTPS
  URL (…/mcp) as a connector in a fresh ChatGPT window.
- **For real use:** deploy it behind HTTPS and put **auth** in front — the
  server has none of its own, and `generate_slides` writes files, so don't
  expose it open to the internet.
- The **OpenAI Responses API** accepts the same server:
  `tools=[{"type": "mcp", "server_url": "https://…/mcp", "server_label": "sermonflow"}]`.

### Is my server up? (health check)

`sermonflow-mcp` speaks stdio, so you can't just `curl` it. To confirm the
handshake, tool list and a real call, run it as a client — the OpenAI Agents SDK
snippet above does exactly that, or use the `mcp` SDK's `stdio_client` +
`ClientSession` to `initialize()`, `list_tools()`, and `call_tool(...)`. A
correct server reports name `sermonflow-slides`, version `0.2.0`, and both tools
with their schemas.

---

## Command line

```bash
# render a chapter
./deps/bin/sermonflow "John 17"

# another translation / another folder
./deps/bin/sermonflow "Psalm 23" --translation NIV --output-dir ./slides/ps23

# see the wrapped lines without rendering 200MB of TIFFs
./deps/bin/sermonflow "John 17" --dry-run

# force a specific backend
./deps/bin/sermonflow "John 1" --provider bible-gateway
```

`python main.py "John 17"` still works too — it forwards to the same entry point.

| Flag | Meaning |
|---|---|
| `-o`, `--output-dir` | where slides land (default `./slides`) |
| `-t`, `--translation` | version code (default `ESV`) |
| `-p`, `--provider` | force `esv-api` or `bible-gateway` (default: auto) |
| `-n`, `--dry-run` | print wrapped lines, render nothing |
| `--no-strict` | render even if validation complains |

Slides are named `John_17_001.tif` … `John_17_026.tif`, zero-padded so they sort
into verse order in any file browser or import dialog.

> **Heads up on size:** uncompressed RGBA TIFFs are ~8MB each, so a chapter is
> roughly 200MB. `slides/` is gitignored.

---

## Bible providers

Retrieval is the failure-prone edge — it depends on a third party staying put —
so it lives behind a `BibleProvider` interface (`sermonflow.providers`), and
everything durable (formatting, layout, rendering) sits above it and never
imports a concrete backend. The contract is one line:

> `fetch_chapter(reference, translation)` → `[(verse_text, "Book Chapter:Verse TRANSLATION"), ...]` in verse order

Two backends ship, and the choice is automatic:

| Backend | When it's used | Notes |
|---|---|---|
| **ESV API** (`api.esv.org`) | `ESV_API_KEY` is set in the environment | Preferred: first-party, stable, documented. Free for non-commercial use — [get a key](https://api.esv.org/). ESV only. |
| **BibleGateway** (scraper) | no key present | Zero-config fallback so the tool always runs. Parses HTML, so it can break if the site restyles — hence the abstraction. Any translation BibleGateway resolves. |

Adding a third backend (API.Bible, a licensed local corpus, a cache) is a new
class in `sermonflow/providers/` plus a line in the registry; nothing downstream
changes. See [`docs/DATABASE_AND_PACKAGING.md`](docs/DATABASE_AND_PACKAGING.md)
for the planned caching/database layer.

---

## As a library

`sermonflow` is flat: `import sermonflow` gives you the whole pipeline.

```python
import sermonflow

# Text from anywhere -- it's really a generic quote-slide renderer.
verses = [
    ("Some quoted line of text,", "Iliad 1:1"),
    ("and the line that follows it.", "Iliad 1:2"),
]
sermonflow.generate_slides(verses, output_dir="./out")
```

`generate_slides` runs the formatting pipeline itself. The quote-carry rule is
order-dependent, so pass the **whole passage in order** and let it run once.

To drive retrieval too:

```python
from sermonflow.providers import get_default_provider
from sermonflow.cli import build

build("John 17", output_dir="./out", provider=get_default_provider())
```

---

## Fonts

The template is set in **Neue Haas Grotesk Display Pro** — 55 Roman for verse
text, 65 Medium for the reference line, 60pt, 72px leading, tracking 0, read
straight out of the PSD. Those `.ttf` files are **bundled in the package**
(`sermonflow/assets/fonts/`) and located with `importlib.resources`, so the deck
typeface is used everywhere with zero setup — no reliance on system font
directories, which is what the proof of concept got wrong off macOS.

### Kerning

Photoshop kerns, so the reference deck is kerned. A Pillow built with **Raqm
(HarfBuzz)** — which the current wheels are — shapes and kerns natively, and
`sermonflow` additionally applies the font's GPOS pair kerning as a
deliberately conservative wrap metric (it can only break a line early, never
overflow the box). Kerning is what takes per-line ink width from a median of
1.0033 against the deck to **1.0000**.

### Glyph coverage

Neue Haas Grotesk Display Pro carries **432 glyphs and no Greek at all**. So a
verse quoting a Greek word is refused by validation (`find_unrenderable`) rather
than rendered as tofu boxes — the safe failure, but a real difference worth
knowing before a service.

### Checking a change against a reference deck

`compare.py` diffs generated slides against a reference deck and prints per-slide
metrics — line count, first-line offset, reference gap, width ratio, ink overlap,
background error:

```bash
./deps/bin/python compare.py ./slides "./John 17 " --overlays ./overlays
```

`--overlays` writes red/green onion-skin images (reference red, ours green,
overlap yellow) so misalignment is visible at a glance. Its `iou` column — ink
overlap — is the metric that sees letterform *shape*, and it's the one that
showed the bundled Neue Haas (~0.51) beats a squeezed Helvetica substitute
(~0.24).

---

## Layout, as measured

| | |
|---|---|
| Canvas | 1920 × 1080 RGBA |
| Left margin | 91px |
| Text box | 678px |
| Font size | 60px |
| Line height | 72px (auto-leading 1.2 × 60) |
| Reference gap | 143px below the last verse line |
| Vertical placement | block centered, snapped to a 197 + 72k grid |
| Reference budget | 741px (scrim, not the verse box) |
| Max verse lines | 12 |

---

## Developing

### Dev build

The build backend is [Hatchling](https://hatch.pypa.io/) (modern, no
`.egg-info`). A "dev build" is just an **editable install** — your source edits
take effect immediately, no rebuild:

```bash
python3 -m venv deps
./deps/bin/pip install -e '.[dev]'    # package + pytest, numpy, pyright
```

Add or drop a dependency by editing the `dependencies` list in
`pyproject.toml`, then re-run that install. There is no `requirements.txt` —
`pyproject.toml` is the single source of truth.

### Everyday commands

```bash
./deps/bin/python -m pytest tests/ -q     # 278 tests, ~45s
./deps/bin/pyright                        # 0 errors; src is strict
./deps/bin/sermonflow "John 17" --dry-run # run the CLI without rendering
```

Tests cover the text rules, wrap quality, layout geometry, hostile input (empty
text, junk tokens, emoji, CJK, control chars), all 66 books of the canon, and
the provider parsers (offline, against fixtures). The package source
(`src/sermonflow/`) type-checks clean under **pyright strict** — set Pylance to
strict in VS Code and the package reports nothing; tests and dev scripts run at a
lightly relaxed level (see `[tool.pyright]` in `pyproject.toml`).

### In VS Code

The repo ships a `.vscode/` so the editor "just works":

1. **Open the folder**, then when prompted, install the **recommended
   extensions** (`.vscode/extensions.json`: Python, Pylance, debugpy,
   Even Better TOML, and **Luna Paint**).
2. **Select the interpreter**: it defaults to `./deps/bin/python` via
   `settings.json`; if imports still read as "not found", run *Python: Select
   Interpreter* → `./deps/bin/python` and reload. That's what makes Pylance
   resolve Pillow / mcp / bs4.
3. **Run & Debug (F5)** — `launch.json` gives you: the CLI (dry-run John 17), the
   MCP server, and pytest (all / current file).
4. **Build & test as tasks** — Ctrl+Shift+B runs the editable install;
   *Terminal → Run Task* also lists pytest, pyright, and a wheel build
   (`tasks.json`).
5. **Open a rendered `slides/*.tif`** with **Luna Paint** (right-click →
   *Open With*) — VS Code cannot show TIFFs natively.

### Building a distributable

```bash
./deps/bin/python -m pip wheel . --no-deps -w dist     # -> dist/sermonflow_slides-0.2.0-*.whl
```

Install that wheel anywhere (or `pipx install .`) to put the `sermonflow` and
`sermonflow-mcp` commands on `PATH` globally — handy so a model host config can
reference `sermonflow-mcp` by name instead of an absolute venv path.

---

## Layout of the repo

| Path | Role |
|---|---|
| `src/sermonflow/text.py` | Text normalization: artifacts, quote carry, capitalization |
| `src/sermonflow/wrap.py` | Line breaking: greedy + balanced wrap |
| `src/sermonflow/fonts.py` | Font selection, metrics, kerning, glyph drawing |
| `src/sermonflow/layout.py` | Geometry: grid-snapped placement, fit/overflow, scrim budget |
| `src/sermonflow/render.py` | Gradient, composition, TIFF output |
| `src/sermonflow/cli.py` | `sermonflow` command |
| `src/sermonflow/mcp_server.py` | `sermonflow-mcp` MCP server |
| `src/sermonflow/providers/` | Retrieval behind `BibleProvider` (ESV API, BibleGateway) |
| `src/sermonflow/assets/fonts/` | Bundled Neue Haas Grotesk Display Pro |
| `compare.py` | Dev tool: diff generated slides against a reference deck |
| `tests/` | 278 tests |
| `docs/DATABASE_AND_PACKAGING.md` | Design: slide cache/database + zip packaging |

---

## Roadmap

- **A real Bible API — done.** The ESV API backend is in; set `ESV_API_KEY` to
  use it. A licensed local corpus would make the pipeline fully offline.
- **Slide cache + zip packaging.** Check a store before rendering, then bundle a
  chapter into a zip for hand-off. Designed in
  [`docs/DATABASE_AND_PACKAGING.md`](docs/DATABASE_AND_PACKAGING.md).
- **NLP-driven slide selection from sermon notes.** Hand it notes, get back the
  slides the sermon actually needs — reference extraction, point-vs-passage
  judgement, deck ordering. This is where the LLM/MCP integration earns its
  place; everything downstream is already deterministic and tested.
- **Point slides.** A second slide type: short emphasis line, no reference,
  centered, bold. `block_height`/`block_top` are the only places the reference
  line is assumed. Waiting on a reference example to measure against.
- **Smaller things:** split an over-long verse across two slides instead of
  raising; wrap the reference line; LZW-compressed TIFF or PNG output; a
  `--compress` flag.
