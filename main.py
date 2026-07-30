#!/usr/bin/env python3
"""
Entry point: pull a chapter and render a slide per verse.

    python main.py "John 17"
    python main.py "1 John 4" --output-dir ./slides/1john4
    python main.py "John 17" --dry-run       # show the text, render nothing

The pipeline is retrieve -> slidegen.format_verses -> slidegen.generate_slides.
Validation runs between formatting and rendering so scrape residue is reported
loudly instead of quietly ending up on a slide.
"""

import argparse
import sys

import slidegen
from retrieve import TRANSLATION, fetch_chapter


def validate(verses):
    """
    Check formatted verses for leftover artifacts and unrenderable lengths.

    Returns a list of human-readable problem strings; empty means clean.
    """
    problems = []
    for text, ref in verses:
        for kind, snippet in slidegen.find_artifacts(text):
            problems.append(f'{ref}: {kind} {snippet!r}')
        for kind, snippet in slidegen.find_unrenderable(text):
            problems.append(f'{ref}: {kind} {snippet}')
        try:
            slidegen.layout_slide(text, ref)
        except slidegen.EmptyVerseError:
            problems.append(f'{ref}: empty, will be skipped')
        except slidegen.SlideOverflowError as exc:
            problems.append(str(exc))
    return problems


def build(reference, output_dir='./slides', translation=TRANSLATION,
          dry_run=False, strict=True):
    """
    Fetch, format, validate and render a chapter.

    Args:
        strict: when True, refuse to render if validation found anything.

    Returns the list of written paths (empty for a dry run).
    """
    raw = fetch_chapter(reference, translation=translation)
    verses = slidegen.format_verses(raw)

    problems = validate(verses)
    if problems:
        print(f'{len(problems)} problem(s) found:', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        if strict and not dry_run:
            raise SystemExit('refusing to render; pass --no-strict to override')

    if dry_run:
        for text, ref in verses:
            lines, _, _ = slidegen.layout_slide(text, ref)
            print(f'\n{ref}  ({len(lines)} lines)')
            for line in lines:
                print(f'    {line}')
        return []

    paths = slidegen.generate_slides(verses, output_dir=output_dir, formatted=True)
    print(f'Rendered {len(paths)} slides to {output_dir}')
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('reference', nargs='?', default='John 17',
                        help='book and chapter, e.g. "John 17"')
    parser.add_argument('-o', '--output-dir', default='./slides')
    parser.add_argument('-t', '--translation', default=TRANSLATION)
    parser.add_argument('-n', '--dry-run', action='store_true',
                        help='print wrapped lines instead of rendering')
    parser.add_argument('--no-strict', dest='strict', action='store_false',
                        help='render even if validation reports problems')
    args = parser.parse_args(argv)

    build(
        args.reference,
        output_dir=args.output_dir,
        translation=args.translation,
        dry_run=args.dry_run,
        strict=args.strict,
    )


if __name__ == '__main__':
    main()
