# MCP portability

SermonFlow is a normal Python package with a standard MCP server. It is not
tied to one model or one desktop application: any MCP-capable host can use the
same installed `sermonflow-mcp` command.

## Install once

From this repository, install Python 3.11+ dependencies into an isolated
environment:

```bash
python3 -m venv deps
./deps/bin/pip install .
```

The resulting MCP command is `./deps/bin/sermonflow-mcp`. It exposes five
tools: `preview_slides`, `generate_slides`, `preview_points`,
`generate_points`, and `list_layouts`.

## Local hosts: stdio

Use this MCP configuration in any host that starts local MCP processes. Replace
the command with the absolute path to the installed executable.

```json
{
  "mcpServers": {
    "sermonflow-slides": {
      "command": "/absolute/path/to/deps/bin/sermonflow-mcp",
      "type": "stdio",
      "env": {
        "ESV_API_KEY": "optional"
      }
    }
  }
}
```

This applies to Codex, Claude Desktop and Code, LM Studio, and other local
MCP-capable hosts. The included `.mcp.json` intentionally uses the portable
`sermonflow-mcp` command name; make sure that command is on the host's `PATH`
or replace it with its absolute path in the host configuration.

## Remote hosts: streamable HTTP

For a hosted model or connector, run the server on a machine that has the
package installed:

```bash
./deps/bin/sermonflow-mcp --http --host 127.0.0.1 --port 8000
```

The MCP endpoint is `http://127.0.0.1:8000/mcp`. Put authentication and HTTPS
in front of it before exposing it beyond the local machine: rendering tools can
write files and Scripture retrieval uses external providers.

## Codex plugin support

The `.codex-plugin/plugin.json` manifest makes the skills and `.mcp.json`
discoverable to Codex. The existing `.claude-plugin/plugin.json` is retained
for Claude Desktop. Both manifests describe the same MCP server; neither
changes the renderer or introduces a host-specific API.

## Output and source behavior

- Scripture is fetched by reference through the official ESV API when
  `ESV_API_KEY` is configured, otherwise through BibleGateway.
- Point slides use only text supplied by the caller.
- Generated slides are 1920×1080 RGBA TIFF files. Set `output_dir` explicitly
  when calling a generate tool; it is the only location the renderer writes.
- The current server does not parse Word/PDF uploads or extract highlighted
  document text. A host may extract content separately and pass references or
  points to the MCP tools.
