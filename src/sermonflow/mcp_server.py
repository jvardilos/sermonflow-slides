"""
MCP server: expose slide generation to an LLM over the Model Context Protocol.

An assistant with this server configured can go from a reference to finished
slides in one tool call, or preview the wrapped text first. Two tools:

  preview_slides  -- wrapped lines per verse, nothing written; the safe look
                     before committing files.
  generate_slides -- fetch, validate and render to a folder; returns the paths.

Both surface validation problems (scrape residue, a too-long verse, a glyph the
font cannot draw) in their result rather than only on a log, so the model can
decide what to do. Run over stdio via the `sermonflow-mcp` console script.
"""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .cli import build, prepare, preview_lines
from .providers import DEFAULT_TRANSLATION

mcp = MCPServer("sermonflow-slides")


@mcp.tool()
def preview_slides(
    reference: str, translation: str = DEFAULT_TRANSLATION
) -> dict[str, Any]:
    """
    Show how each verse will wrap, without rendering anything.

    Args:
        reference: book and chapter, e.g. "John 17" or "1 John 4".
        translation: version code (default ESV; ignored by the ESV API backend).

    Returns the per-verse wrapped lines and any validation problems.
    """
    verses, problems = prepare(reference, translation)
    slides = [
        {"reference": ref, "lines": lines}
        for ref, lines in preview_lines(verses)
    ]
    return {
        "reference": reference,
        "verse_count": len(slides),
        "slides": slides,
        "problems": problems,
    }


@mcp.tool()
def generate_slides(
    reference: str,
    translation: str = DEFAULT_TRANSLATION,
    output_dir: str = "./slides",
    strict: bool = True,
) -> dict[str, Any]:
    """
    Render one slide per verse of a chapter to `output_dir`.

    Args:
        reference: book and chapter, e.g. "John 17".
        translation: version code (default ESV; ignored by the ESV API backend).
        output_dir: folder to write the TIFF slides into (created if missing).
        strict: when True, refuse to render if validation finds any problem and
            return those problems instead of writing files.

    Returns the written paths, or the blocking problems when strict and unclean.
    """
    _, problems = prepare(reference, translation)
    if problems and strict:
        return {
            "reference": reference,
            "rendered": False,
            "problems": problems,
            "hint": "call again with strict=false to render anyway",
        }

    paths = build(
        reference,
        output_dir=output_dir,
        translation=translation,
        dry_run=False,
        strict=False,
    )
    return {
        "reference": reference,
        "rendered": True,
        "count": len(paths),
        "paths": paths,
        "output_dir": output_dir,
        "problems": problems,
    }


def main() -> None:
    """Run the server over stdio (the `sermonflow-mcp` console script)."""
    mcp.run()


if __name__ == "__main__":
    main()
