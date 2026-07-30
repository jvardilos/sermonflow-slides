#!/usr/bin/env python3
"""
Diff generated slides against a reference deck.

    python compare.py slides "John 17"
    python compare.py slides "John 17" --overlays out/

A raw pixel diff of two slides is nearly useless here: the substituted font is
a different width, so glyphs drift progressively across every line and the diff
lights up everywhere without saying why. These metrics separate the things that
*should* match exactly from the one thing that cannot:

  lines        line count -- must match
  top          first-line ink top delta, px -- must be 0
  ref_gap      reference line offset -- must match REF_GAP
  width        mean per-line ink width ratio, ours/theirs -- 1.00 is a
               perfect match; ~1.10 is the Helvetica Neue substitution
  bg_rms       RMS difference of the gradient outside all text -- isolates the
               background from the type, so it must be ~0

The overlay renders the reference in red and ours in green, so overlap is
yellow: misalignment is visible at a glance in a way numbers are not.
"""

import argparse
import os
import re
import sys

import numpy as np
from PIL import Image, ImageFilter

import slidegen

INK_THRESHOLD = 235


def ink_mask(img):
    """Boolean mask of white text ink."""
    arr = np.array(img.convert('RGB')).astype(float).mean(axis=2)
    return arr > INK_THRESHOLD


def _dilate(mask, radius=9):
    """Grow a boolean mask outward by `radius` pixels."""
    img = Image.fromarray((mask * 255).astype(np.uint8))
    grown = img.filter(ImageFilter.MaxFilter(radius))
    return np.array(grown) > 0


def text_lines(mask):
    """
    [(ink_top, left, right), ...] per text line, using the validated 72px grid.

    Grid bucketing rather than proximity clustering: descenders form separate
    ink islands and would otherwise register as phantom lines.
    """
    rows = np.where(mask.any(axis=1))[0]
    if not len(rows):
        return []
    phase = slidegen.GRID_ORIGIN - 10
    slots = {}
    for y in rows:
        slots.setdefault((int(y) - phase) // slidegen.LINE_HEIGHT, []).append(int(y))
    lines = []
    for slot in sorted(slots):
        ys = slots[slot]
        band = mask[min(ys):max(ys) + 1, :]
        cols = np.where(band.any(axis=0))[0]
        lines.append((min(ys), int(cols.min()), int(cols.max())))
    return lines


def compare_slide(our_path, ref_path):
    """Metrics for one pair of slides. See module docstring."""
    ours = Image.open(our_path).convert('RGBA')
    theirs = Image.open(ref_path).convert('RGBA')

    our_mask, ref_mask = ink_mask(ours), ink_mask(theirs)
    our_lines, ref_lines = text_lines(our_mask), text_lines(ref_mask)

    # Everything except the reference line is verse text.
    our_verse, ref_verse = our_lines[:-1], ref_lines[:-1]

    ratios = [
        (o[2] - o[1]) / (r[2] - r[1])
        for o, r in zip(our_verse, ref_verse)
        if r[2] > r[1]
    ]

    # Background: pixels neither image inked, generously dilated. Without the
    # dilation the antialiased halo around every glyph stays in the "background"
    # (it never reaches the ink threshold) and, since the two fonts differ, it
    # dominates the result -- reporting gradient error that is really type.
    background = ~_dilate(our_mask | ref_mask, radius=9)
    diff = np.array(ours).astype(float) - np.array(theirs).astype(float)
    bg_rms = float(np.sqrt((diff[background] ** 2).mean()))

    # The median resists a single diverged break; the spread between lines is
    # itself the signal that breaks differ even when the line count matches.
    ordered = sorted(ratios)
    median = ordered[len(ordered) // 2] if ordered else None
    spread = (max(ratios) - min(ratios)) if len(ratios) > 1 else 0.0

    return {
        'our_lines': len(our_verse),
        'ref_lines': len(ref_verse),
        'top_delta': (our_lines[0][0] - ref_lines[0][0]) if our_lines and ref_lines else None,
        'our_ref_gap': (our_lines[-1][0] - our_verse[-1][0]) if our_verse else None,
        'ref_ref_gap': (ref_lines[-1][0] - ref_verse[-1][0]) if ref_verse else None,
        'width_ratio': median,
        'width_spread': spread,
        'bg_rms': bg_rms,
    }


def write_overlay(our_path, ref_path, out_path):
    """Reference in red, ours in green, overlap in yellow."""
    ours = ink_mask(Image.open(our_path))
    theirs = ink_mask(Image.open(ref_path))
    h, w = ours.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = theirs * 255
    rgb[..., 1] = ours * 255
    Image.fromarray(rgb).save(out_path)
    return out_path


def _verse_number(name):
    """Pull a verse number out of either naming scheme."""
    stem = os.path.splitext(os.path.basename(name))[0]
    tail = re.search(r'[.:_](\d+)\s*$', stem)
    return int(tail.group(1)) if tail else 1


def index_dir(path):
    """{verse number: file path} for every slide in a directory."""
    return {
        _verse_number(f): os.path.join(path, f)
        for f in os.listdir(path)
        if f.lower().endswith(('.tif', '.tiff', '.png'))
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('ours', help='directory of generated slides')
    parser.add_argument('reference', help='directory of reference slides')
    parser.add_argument('--overlays', metavar='DIR',
                        help='also write red/green overlay images here')
    args = parser.parse_args(argv)

    ours, theirs = index_dir(args.ours), index_dir(args.reference)
    shared = sorted(set(ours) & set(theirs))
    if not shared:
        raise SystemExit('no verses in common between the two directories')

    for missing, where in ((set(theirs) - set(ours), args.ours),
                           (set(ours) - set(theirs), args.reference)):
        if missing:
            print(f'missing from {where}: {sorted(missing)}', file=sys.stderr)

    if args.overlays:
        os.makedirs(args.overlays, exist_ok=True)

    print(f'{"v":>3} {"lines":>11} {"top":>5} {"gap":>9} '
          f'{"width":>7} {"spread":>7} {"bg_rms":>7}  notes')
    ratios, mismatched, diverged = [], [], []
    for verse in shared:
        m = compare_slide(ours[verse], theirs[verse])
        notes = []
        if m['our_lines'] != m['ref_lines']:
            mismatched.append(verse)
            notes.append('line count differs')
        elif m['width_spread'] > 0.6:
            # Same number of lines, but words fell differently across them.
            diverged.append(verse)
            notes.append('breaks differ')
        if abs(m['top_delta'] or 0) > 2:
            notes.append(f'off grid by {m["top_delta"]:+d}px')
        if m['width_ratio']:
            ratios.append(m['width_ratio'])
        print(
            f'{verse:>3} '
            f'{m["our_lines"]:>5}/{m["ref_lines"]:<5} '
            f'{m["top_delta"]:>+5} '
            f'{m["our_ref_gap"]:>4}/{m["ref_ref_gap"]:<4} '
            f'{m["width_ratio"] or 0:>7.3f} '
            f'{m["width_spread"]:>7.3f} '
            f'{m["bg_rms"]:>7.2f}  '
            f'{"; ".join(notes)}'
        )
        if args.overlays:
            write_overlay(ours[verse], theirs[verse],
                          os.path.join(args.overlays, f'overlay_{verse:03d}.png'))

    print()
    print(f'{len(shared) - len(mismatched)}/{len(shared)} match on line count')
    if mismatched:
        print(f'  line count differs: {mismatched}')
    if diverged:
        print(f'  same count, breaks differ: {diverged}')
    if ratios:
        ordered = sorted(ratios)
        print(f'median width ratio {ordered[len(ordered) // 2]:.3f} '
              f'(1.000 = exact; >1 means our type sets wider)')


if __name__ == '__main__':
    main()
