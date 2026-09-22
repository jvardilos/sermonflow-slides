"""
Slide layouts: how text becomes placed ink on the 1920x1080 canvas.

Each module here owns one slide type and ends at the same place -- a `Placed`,
which is a finished slide as draw ops at ink coordinates. render.py consumes
`Placed` and nothing else, so a new layout is a new module in this folder plus
(if it is a point style) one line in POINT_STYLES below. Nothing downstream of
the layout has to change, which is the same shape as providers/.

  base   -- canvas, grid, scrim, the Placed/DrawOp IR
  verse  -- wrapped passage with its reference underneath
  points -- short statements, three styles

The registry is deliberately over point *styles* rather than over layouts in
general. Verse slides take (text, reference) pairs and point slides take plain
strings, so a single registry across both would have to type its input as
"anything" and win nothing; the axis that actually grows is the styles a caller
picks between at runtime, and that axis is uniform.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from .base import (
    CAP_HEIGHT as CAP_HEIGHT,
    GRADIENT_PROFILE as GRADIENT_PROFILE,
    GRADIENT_PROFILE_STEP as GRADIENT_PROFILE_STEP,
    GRID_ORIGIN as GRID_ORIGIN,
    LEFT_MARGIN as LEFT_MARGIN,
    LEGIBLE_ALPHA as LEGIBLE_ALPHA,
    LINE_HEIGHT as LINE_HEIGHT,
    MAX_TEXT_WIDTH as MAX_TEXT_WIDTH,
    MIN_BOTTOM_MARGIN as MIN_BOTTOM_MARGIN,
    MIN_TOP_MARGIN as MIN_TOP_MARGIN,
    SCRIM_LIMIT as SCRIM_LIMIT,
    SLIDE_HEIGHT as SLIDE_HEIGHT,
    SLIDE_WIDTH as SLIDE_WIDTH,
    DrawOp as DrawOp,
    EmptyVerseError as EmptyVerseError,
    Placed as Placed,
    PointOverflowError as PointOverflowError,
    SlideOverflowError as SlideOverflowError,
    _scrim_limit as _scrim_limit,
    fits as fits,
    snap_top as snap_top,
)
from .points import (
    POINT_BOX_WIDTH as POINT_BOX_WIDTH,
    ROLLING_STEP as ROLLING_STEP,
    STACK_BOX_WIDTH as STACK_BOX_WIDTH,
    STACK_CENTER as STACK_CENTER,
    STACK_LEFT_MARGIN as STACK_LEFT_MARGIN,
    centered_top as centered_top,
    plan_centered as plan_centered,
    plan_rolling as plan_rolling,
    plan_stacked as plan_stacked,
    rolling_tops as rolling_tops,
    stacked_blocks as stacked_blocks,
    wrap_point as wrap_point,
)
from .verse import (
    REF_CAP_HEIGHT as REF_CAP_HEIGHT,
    REF_GAP as REF_GAP,
    REF_MAX_WIDTH as REF_MAX_WIDTH,
    REFERENCE_WEIGHT as REFERENCE_WEIGHT,
    TEXT_BOX_WIDTH as TEXT_BOX_WIDTH,
    VERSE_WEIGHT as VERSE_WEIGHT,
    block_fits as block_fits,
    block_height as block_height,
    block_top as block_top,
    find_overlong_reference as find_overlong_reference,
    layout_slide as layout_slide,
    max_lines as max_lines,
    plan_verse as plan_verse,
    slide_stem as slide_stem,
)


class PointStyle(NamedTuple):
    """
    A named way of laying points out.

    `summary` is not decoration: it is what the MCP server's list_layouts tool
    returns, so a style added here explains itself to a model without anyone
    editing mcp_server.py. The tool descriptions and the CLI's --style help are
    written by hand and still need the new style added to them.
    """

    name: str
    summary: str
    plan: Callable[[Sequence[str], str], list[Placed]]


POINT_STYLES: dict[str, PointStyle] = {
    "rolling": PointStyle(
        "rolling",
        "the list builds up: slide N shows points 1..N at fixed positions, so "
        "playing them in order reveals one point at a time",
        plan_rolling,
    ),
    "centered": PointStyle(
        "centered",
        "one statement per slide, its block centered and sitting a little "
        "above the middle of the canvas",
        plan_centered,
    ),
    "stacked": PointStyle(
        "stacked",
        "one standalone slide per entry, centered, holding every paragraph the "
        "entry separates with a newline -- a lie above its truth, or a list of "
        "steps. Nothing builds up between slides. This is the shape of the "
        "hand-made Run week 2 deck",
        plan_stacked,
    ),
}

DEFAULT_POINT_STYLE = "rolling"


def point_style_names() -> list[str]:
    """Registered style names, for help text and argument choices."""
    return list(POINT_STYLES)


class UnknownPointStyleError(ValueError):
    """Raised for a style name that is not in POINT_STYLES."""


def get_point_style(name: str) -> PointStyle:
    """Look a style up by name, or raise UnknownPointStyleError naming the valid ones."""
    try:
        return POINT_STYLES[name]
    except KeyError:
        raise UnknownPointStyleError(
            f"unknown point style {name!r}; choose from "
            f"{', '.join(point_style_names())}"
        ) from None
