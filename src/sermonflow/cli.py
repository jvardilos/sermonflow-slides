"""
Command-line entry point: pull a chapter and render a slide per verse, or set
a list of sermon points.

    sermonflow "John 17"
    sermonflow "1 John 4" --output-dir ./slides/1john4
    sermonflow "John 17" --dry-run          # show the text, render nothing

    sermonflow --points "The Sovereignty of Christ." "The Atonement."
    sermonflow --points "My kingdom is not of this world." --style centered

The pipeline is provider.fetch_chapter -> format_verses -> validate -> render.
Validation runs between formatting and rendering so scrape residue is reported
loudly instead of quietly ending up on a slide.

The provider is chosen from the environment (ESV API when ESV_API_KEY is set,
BibleGateway otherwise); `--provider` overrides that.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .fonts import find_unrenderable
from .layouts import (
    DEFAULT_POINT_STYLE,
    EmptyVerseError,
    SlideOverflowError,
    find_overlong_reference,
    layout_slide,
    point_style_names,
)
from .providers import DEFAULT_TRANSLATION, BibleProvider, get_default_provider, get_provider
from .render import generate_points, generate_slides, plan_points
from .text import Verse, find_artifacts, format_verses


def validate(verses: Sequence[Verse]) -> list[str]:
    """
    Check formatted verses for leftover artifacts and unrenderable lengths.

    Returns a list of human-readable problem strings; empty means clean.
    """
    problems: list[str] = []
    for text, ref in verses:
        for kind, snippet in find_artifacts(text):
            problems.append(f"{ref}: {kind} {snippet!r}")
        for kind, snippet in find_unrenderable(text):
            problems.append(f"{ref}: {kind} {snippet}")
        for kind, snippet in find_overlong_reference(ref):
            problems.append(f"{ref}: {kind} {snippet}")
        try:
            layout_slide(text, ref)
        except EmptyVerseError:
            problems.append(f"{ref}: empty, will be skipped")
        except SlideOverflowError as exc:
            problems.append(str(exc))
    return problems


def prepare(
    reference: str,
    translation: str = DEFAULT_TRANSLATION,
    provider: BibleProvider | None = None,
) -> tuple[list[Verse], list[str]]:
    """
    Fetch and format a chapter, then validate it.

    Returns (formatted_verses, problems). Does no I/O beyond the fetch, so both
    the CLI and the MCP server build on it.
    """
    source = provider if provider is not None else get_default_provider()
    raw = source.fetch_chapter(reference, translation)
    verses = format_verses(raw)
    return verses, validate(verses)


def preview_lines(verses: Sequence[Verse]) -> list[tuple[str, list[str]]]:
    """(reference, wrapped_lines) per non-empty verse -- the dry-run view."""
    out: list[tuple[str, list[str]]] = []
    for text, ref in verses:
        try:
            lines, _, _ = layout_slide(text, ref)
        except EmptyVerseError:
            continue
        out.append((ref, lines))
    return out


def build(
    reference: str,
    output_dir: str = "./slides",
    translation: str = DEFAULT_TRANSLATION,
    dry_run: bool = False,
    strict: bool = True,
    provider: BibleProvider | None = None,
) -> list[str]:
    """
    Fetch, format, validate and render a chapter.

    Args:
        strict: when True, refuse to render if validation found anything.

    Returns the list of written paths (empty for a dry run).
    """
    verses, problems = prepare(reference, translation, provider)

    if problems:
        print(f"{len(problems)} problem(s) found:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if strict and not dry_run:
            raise SystemExit("refusing to render; pass --no-strict to override")

    if dry_run:
        try:
            preview = preview_lines(verses)
        except SlideOverflowError as exc:
            raise SystemExit(f"cannot lay this passage out: {exc}") from None
        for ref, lines in preview:
            print(f"\n{ref}  ({len(lines)} lines)")
            for line in lines:
                print(f"    {line}")
        return []

    paths = generate_slides(verses, output_dir=output_dir, formatted=True)
    print(f"Rendered {len(paths)} slides to {output_dir}")
    return paths


# ---------------------------------------------------------------------------
# Point slides
# ---------------------------------------------------------------------------


def validate_points(
    points: Sequence[str], style: str = DEFAULT_POINT_STYLE
) -> list[str]:
    """
    Check a list of points the way `validate` checks a passage.

    The artifact scan is deliberately not run here: it hunts scrape residue,
    and points are typed by a person rather than pulled off a web page.
    """
    problems: list[str] = []
    for i, text in enumerate(points, 1):
        if not text.strip():
            problems.append(f"point {i}: empty, will be skipped")
            continue
        for kind, snippet in find_unrenderable(text):
            problems.append(f"point {i}: {kind} {snippet}")
    try:
        plan_points(points, style)
    except EmptyVerseError:
        problems.append("no renderable points")
    except (SlideOverflowError, ValueError) as exc:
        problems.append(str(exc))
    return problems


def preview_points(
    points: Sequence[str], style: str = DEFAULT_POINT_STYLE
) -> list[tuple[str, list[str]]]:
    """(stem, lines) per planned slide -- the dry-run view for points."""
    return [
        (placed.stem, [op.text for op in placed.ops])
        for placed in plan_points(points, style)
    ]


def build_points(
    points: Sequence[str],
    output_dir: str = "./slides",
    style: str = DEFAULT_POINT_STYLE,
    dry_run: bool = False,
    strict: bool = True,
) -> list[str]:
    """Validate and render a list of points. Mirrors `build`."""
    problems = validate_points(points, style)

    if problems:
        print(f"{len(problems)} problem(s) found:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        if strict and not dry_run:
            raise SystemExit("refusing to render; pass --no-strict to override")

    if dry_run:
        try:
            preview = preview_points(points, style)
        except ValueError as exc:
            # A dry run that cannot be laid out at all still owes the operator
            # the reason, not a traceback. The detail is already on stderr
            # above; this is the exit line.
            raise SystemExit(f"cannot lay these points out: {exc}") from None
        for stem, lines in preview:
            print(f"\n{stem}  ({len(lines)} lines)")
            for line in lines:
                print(f"    {line}")
        return []

    paths = generate_points(points, output_dir=output_dir, style=style)
    print(f"Rendered {len(paths)} {style} point slides to {output_dir}")
    return paths


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Render ProPresenter-ready slides: a verse per slide from a "
        "chapter, or a deck of sermon points."
    )
    parser.add_argument(
        "reference", nargs="?", default="John 17", help='book and chapter, e.g. "John 17"'
    )
    parser.add_argument(
        "--points",
        nargs="+",
        metavar="POINT",
        help="render these statements as point slides instead of a chapter",
    )
    parser.add_argument(
        "--style",
        default=DEFAULT_POINT_STYLE,
        choices=point_style_names(),
        help=f"point layout (default: {DEFAULT_POINT_STYLE}); "
        "rolling reveals one point at a time, centered gives each its own slide",
    )
    parser.add_argument("-o", "--output-dir", default="./slides")
    parser.add_argument("-t", "--translation", default=DEFAULT_TRANSLATION)
    parser.add_argument(
        "-p",
        "--provider",
        default=None,
        help="force a backend: 'esv-api' or 'bible-gateway' (default: auto)",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="print wrapped lines instead of rendering",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="render even if validation reports problems",
    )
    args = parser.parse_args(argv)

    if args.points:
        build_points(
            args.points,
            output_dir=args.output_dir,
            style=args.style,
            dry_run=args.dry_run,
            strict=args.strict,
        )
        return

    provider = get_provider(args.provider) if args.provider else None
    build(
        args.reference,
        output_dir=args.output_dir,
        translation=args.translation,
        dry_run=args.dry_run,
        strict=args.strict,
        provider=provider,
    )


if __name__ == "__main__":
    main()
