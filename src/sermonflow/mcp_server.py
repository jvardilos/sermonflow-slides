"""
MCP server: expose slide generation to an LLM over the Model Context Protocol.

An assistant with this server configured can go from a reference to finished
slides in one tool call, or preview the wrapped text first.

The tools are split by *slide type* rather than gathered behind one call with a
mode flag, because that split is what tells the model which one to reach for.
A chapter reference and a list of sermon points are different shapes of input,
and a tool per shape lets the choice be made from the argument the user
actually gave:

  preview_slides  -- wrapped lines per verse, nothing written; the safe look
                     before committing files.
  generate_slides -- fetch, validate and render a chapter; returns the paths.
  preview_points  -- how a list of points will lay out, nothing written.
  generate_points -- render a list of points; returns the paths.
  list_layouts    -- the point styles and when each is right, generated from
                     the registry so a style added in layouts/ shows up here
                     without this file changing.

All of them surface validation problems (scrape residue, a too-long verse, a
glyph the font cannot draw) in their result rather than only on a log, so the
model can decide what to do.

Run it with the `sermonflow-mcp` console script. By default it speaks stdio,
which is what a local host (Claude Code/Desktop, or an agent SDK) spawns. Pass
`--http` to serve streamable HTTP instead, for remote hosts such as ChatGPT
connectors that connect to a URL rather than launching a process.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from typing import Any

from mcp.server import MCPServer

from . import __version__
from .cli import (
    SKIP_MARKER,
    points_fit,
    prepare,
    preview_points as _preview_points,
    renderable_verses,
    skipped_points,
    validate_points,
)
from .layouts import DEFAULT_POINT_STYLE, POINT_STYLES
from .providers import DEFAULT_TRANSLATION
from .render import generate_points as _render_points, generate_slides as _render_slides

mcp = MCPServer("sermonflow-slides", version=__version__)

#: Refusal hints. strict=false draws past what validation merely doubts -- a
#: stray marker, a character with no glyph -- and leaves out a verse too long
#: for a slide. But content with nothing to render makes the renderer raise (or
#: render nothing) whatever strict says, so offering strict=false for it would
#: send the model into a failing retry. Points are the caller's own words, so
#: the problems say what to change. Scripture is fetched and cannot be edited
#: -- and the ESV API ignores the translation -- so for a passage the honest
#: next step is telling the user.
_OVERRIDE_HINT = "call again with strict=false to render anyway"
#: When something would be dropped, say so: the caller must not promise a
#: complete deck, and `skipped` saves reading the problems as prose.
_OVERRIDE_SKIP_HINT = (
    "call again with strict=false to render anyway; `skipped` lists what is "
    f"left out (the problems mark it '{SKIP_MARKER}'), so tell the user what "
    "is missing"
)
#: On a render that left something out. `count` alone reads like a full deck.
_SKIPPED_HINT = (
    "rendered, but `skipped` lists what never reached a slide -- tell the user "
    "what is missing from the deck"
)
_POINTS_BLOCKED_HINT = (
    "these points cannot be laid out as given; change what the problems name "
    "-- changing strict will not help"
)
_PASSAGE_BLOCKED_HINT = (
    "this passage cannot be laid out on these slides as it stands, and "
    "changing strict will not help; tell the user what the problems say"
)


def _refusal_hint(fits: bool, skipped: Sequence[str], blocked: str) -> str:
    """The hint for a refusal: blocked, overridable, or overridable with a cost."""
    if not fits:
        return blocked
    return _OVERRIDE_SKIP_HINT if skipped else _OVERRIDE_HINT


def _resolve_dir(output_dir: str) -> str:
    """
    `output_dir` as an absolute path, `~` expanded.

    The model reading a tool result cannot know this process's working
    directory, so a relative path in the result would not locate anything.
    """
    return os.path.abspath(os.path.expanduser(output_dir))


@mcp.tool()
def preview_slides(
    reference: str, translation: str = DEFAULT_TRANSLATION
) -> dict[str, Any]:
    """
    Show how each verse of a chapter will wrap, without rendering anything.

    Use this (and generate_slides) when the user names a passage of scripture
    to put on screen. For a statement the user wrote themselves -- a sermon
    point, a heading, a paraphrase -- use preview_points/generate_points
    instead: those set no reference line and lay out differently.

    Args:
        reference: book and chapter, e.g. "John 17" or "1 John 4".
        translation: version code (default ESV; ignored by the ESV API backend).

    Returns `slides` (the wrapped lines per verse that will render),
    `skipped` (references of the verses that will not -- blank, or too long for
    a slide), `verse_count` for the whole chapter, and any validation problems.
    A non-empty `skipped` means the deck would come out short of those verses:
    say so before rendering.
    """
    verses, problems = prepare(reference, translation)
    # A verse too long for a slide is left out of `slides`, as generate_slides
    # leaves it out of the deck. `skipped` names those, so the safe look before
    # committing files says which verse will go missing.
    previews, skipped = renderable_verses(verses)
    return {
        "reference": reference,
        # Every verse fetched, so len(slides) + len(skipped) adds up.
        "verse_count": len(verses),
        "slides": [{"reference": ref, "lines": lines} for ref, lines in previews],
        "skipped": skipped,
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

    This is the scripture tool: it fetches the passage from a Bible provider,
    so it only takes a reference, never the text itself. To put the user's own
    words on a slide, call generate_points.

    Args:
        reference: book and chapter, e.g. "John 17".
        translation: version code (default ESV; ignored by the ESV API backend).
        output_dir: folder to write the TIFF slides into (created if missing).
        strict: when True, refuse to render if validation finds any problem and
            return those problems instead of writing files. When False, a
            verse too long for a slide is skipped (the problems name it) and
            the rest render. A passage where nothing fits, or with no text at
            all, is refused either way.

    Returns the written paths plus `skipped` (references that never reached a
    slide), or the problems, `skipped` and a hint when it refuses.
    """
    verses, problems = prepare(reference, translation)
    # One layout pass answers both questions: whether anything renders, and
    # which verses with text the render will leave out. A clean passage needs
    # neither -- validate() laid every verse out already.
    skipped: list[str] = []
    fits = True
    if problems:
        # Blank or too long, a verse that does not render is one the deck is
        # short, so `skipped` names it either way.
        previews, skipped = renderable_verses(verses)
        fits = bool(previews)
    if problems and (strict or not fits):
        return {
            "reference": reference,
            "rendered": False,
            "problems": problems,
            "skipped": skipped,
            "hint": _refusal_hint(fits, skipped, _PASSAGE_BLOCKED_HINT),
        }

    # Straight to the renderer rather than through cli.build: that would fetch
    # the passage a second time and print its summary onto stdout, which over
    # stdio is the protocol stream.
    output_dir = _resolve_dir(output_dir)
    paths = _render_slides(verses, output_dir=output_dir, formatted=True)
    result: dict[str, Any] = {
        "reference": reference,
        "rendered": True,
        "count": len(paths),
        "paths": paths,
        "output_dir": output_dir,
        "problems": problems,
        "skipped": skipped,
    }
    if skipped:
        # `count` on its own reads like a complete deck.
        result["hint"] = _SKIPPED_HINT
    return result


@mcp.tool()
def list_layouts() -> dict[str, Any]:
    """
    The available point styles and what each one is for.

    Call this when unsure which style a request wants, or to show the user
    their options. The list is read from the layout registry, so it is always
    what the renderer actually supports.
    """
    return {
        "default": DEFAULT_POINT_STYLE,
        "styles": [
            {"name": style.name, "summary": style.summary}
            for style in POINT_STYLES.values()
        ],
        "verse_slides": (
            "scripture is a separate slide type with its own tools "
            "(preview_slides / generate_slides); it is fetched by reference "
            "and carries a reference line"
        ),
    }


@mcp.tool()
def preview_points(
    points: list[str], style: str = DEFAULT_POINT_STYLE
) -> dict[str, Any]:
    """
    Show how a list of sermon points will lay out, without rendering anything.

    Use this (and generate_points) for text the user supplies: sermon points,
    headings, a paraphrase, a pull quote -- anything that is not a passage
    fetched by reference.

    Args:
        points: the statements, in the order they should appear on screen.
        style: "rolling" (default) builds the list up one point at a time, so
            N points produce N slides and slide N shows points 1..N. Use it for
            an outline the speaker walks through. "centered" gives each point
            its own slide, centered on the canvas -- use it for a single
            statement meant to land on its own. "stacked" also gives each
            entry its own slide, but splits the entry on newlines into
            paragraphs stacked on that slide -- a lie above its truth, or a
            short list of steps. Call list_layouts for the current set.

    Returns one entry per slide it would render, with the wrapped lines, plus
    `skipped` (labels of the points that will not reach a slide) and any
    validation problems.
    """
    problems = validate_points(points, style)
    try:
        slides = [
            {"name": stem, "lines": lines}
            for stem, lines in _preview_points(points, style)
        ]
    except ValueError:
        # Whatever made planning impossible is already in `problems`:
        # validate_points ran the same plan and recorded it. Nothing will
        # render, so every point is missing, not just the blank ones.
        return {
            "style": style,
            "slide_count": 0,
            "slides": [],
            "skipped": skipped_points(points, blocked=True),
            "problems": problems,
        }
    return {
        "style": style,
        "slide_count": len(slides),
        "slides": slides,
        "skipped": skipped_points(points),
        "problems": problems,
    }


@mcp.tool()
def generate_points(
    points: list[str],
    style: str = DEFAULT_POINT_STYLE,
    output_dir: str = "./slides",
    strict: bool = True,
) -> dict[str, Any]:
    """
    Render a list of sermon points to `output_dir`.

    The tool for the user's own words. See preview_points for what `style`
    does, and generate_slides for scripture.

    Args:
        points: the statements, in the order they should appear on screen.
        style: "rolling" (default), "centered" or "stacked"; see
            preview_points and list_layouts.
        output_dir: folder to write the TIFF slides into (created if missing).
        strict: when True, refuse to render if validation finds any problem and
            return those problems instead of writing files. Points that cannot
            be laid out at all are refused either way.

    Returns the written paths plus `skipped` (labels of the points that never
    reached a slide -- the blank ones), or the problems, `skipped` and a hint
    when it refuses.
    """
    problems = validate_points(points, style)
    # validate_points has already planned the deck, so a clean deck fits.
    fits = not problems or points_fit(points, style)
    # Blocked: nothing renders, so every point is missing, not just the blanks.
    skipped = skipped_points(points, blocked=not fits) if problems else []
    if problems and (strict or not fits):
        return {
            "style": style,
            "rendered": False,
            "problems": problems,
            "skipped": skipped,
            "hint": _refusal_hint(fits, skipped, _POINTS_BLOCKED_HINT),
        }

    # As in generate_slides: the renderer directly, so nothing reaches stdout.
    output_dir = _resolve_dir(output_dir)
    paths = _render_points(points, output_dir=output_dir, style=style)
    result: dict[str, Any] = {
        "style": style,
        "rendered": True,
        "count": len(paths),
        "paths": paths,
        "output_dir": output_dir,
        "problems": problems,
        "skipped": skipped,
    }
    if skipped:
        result["hint"] = _SKIPPED_HINT
    return result


def main() -> None:
    """
    Run the server (the `sermonflow-mcp` console script).

    stdio by default -- what a local host spawns. `--http` serves streamable
    HTTP on host:port for remote hosts that connect to a URL.
    """
    parser = argparse.ArgumentParser(
        prog="sermonflow-mcp",
        description="MCP server exposing sermonflow's slide tools.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve streamable HTTP instead of stdio (for remote hosts)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
