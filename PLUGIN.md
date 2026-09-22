# SermonFlow Slides

Generate 1920×1080 ProPresenter-ready sermon slides from Scripture references
or supplied sermon points. SermonFlow runs as a standard local MCP server, so
it can be connected to any compatible LLM host.

## What it does

- Fetches a Scripture passage by reference and creates one TIFF slide per verse
- Creates rolling outline or centered-statement slides from sermon points
- Previews wrapping and validation results before writing slide files
- Uses the ESV API when `ESV_API_KEY` is configured, with BibleGateway as a
  zero-configuration fallback

## Install

Install the package with Python 3.11 or later:

```bash
python3 -m venv deps
./deps/bin/pip install .
```

Register `./deps/bin/sermonflow-mcp` as a stdio MCP server in your preferred
LLM host. A portable configuration example is in
[`docs/MCP_PORTABILITY.md`](docs/MCP_PORTABILITY.md).

## Use

Ask the connected host to preview first, then render to an explicit directory:

- “Preview John 17.”
- “Generate slides for Romans 8 to `/path/to/sunday-slides`.”
- “Create rolling point slides: Jesus is Lord; He rose from death; We are redeemed.”

The server exposes `preview_slides`, `generate_slides`, `preview_points`,
`generate_points`, and `list_layouts`.

## Current scope

Slides are written as ProPresenter-ready TIFF files. This package currently
does not read Word/PDF files or extract highlighted text from them; pass a
Scripture reference or the sermon-point text directly.
