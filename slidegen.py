#!/usr/bin/env python3
"""
Verse Slide Generator for ProPresenter
Generates transparent 1920x1080 TIFF slides with verse text over a
black-to-transparent gradient (left to right), matching the style of
NEW_MESSAGE_SIDESCREEN.psd / thing.tif.
"""

from PIL import Image, ImageDraw, ImageFont
import os

WIDTH, HEIGHT = 1920, 1080

# Gradient: solid black on the left, easing out to fully transparent by
# roughly 60% of the width, matching the "Rectangle 1" layer in the PSD.
GRADIENT_MAX_ALPHA = 207          # layer opacity baked into the pixel alpha
GRADIENT_PLATEAU_X = 281          # stays fully opaque up to here
GRADIENT_END_X = 1150             # fully transparent from here on

FONT_PATH = '/System/Library/Fonts/HelveticaNeue.ttc'
FONT_INDEX_REGULAR = 0            # verse body copy (NHaasGroteskDSPro-55Rg equivalent)
FONT_INDEX_MEDIUM = 10            # reference line (NHaasGroteskDSPro-65Md equivalent)
FONT_SIZE = 60
LINE_HEIGHT = 72                  # ~1.2x font size, matches PSD leading

LEFT_MARGIN = 91
TOP_MARGIN = 248
TEXT_BOX_WIDTH = 651
REF_GAP = 143                     # blank-line gap before the reference line


def _smoothstep(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def _make_gradient(width, height):
    """Black RGBA gradient, opaque on the left fading to transparent by ~60% width."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    row = Image.new('RGBA', (width, 1), (0, 0, 0, 0))
    pixels = row.load()
    for x in range(width):
        if x <= GRADIENT_PLATEAU_X:
            alpha = GRADIENT_MAX_ALPHA
        elif x >= GRADIENT_END_X:
            alpha = 0
        else:
            t = (x - GRADIENT_PLATEAU_X) / (GRADIENT_END_X - GRADIENT_PLATEAU_X)
            alpha = int(GRADIENT_MAX_ALPHA * (1 - _smoothstep(t)))
        pixels[x, 0] = (0, 0, 0, alpha)
    return row.resize((width, height))


def _load_font(index, size):
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size, index=index)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_to_width(draw, text, font, max_width):
    """Word-wrap text so each line's rendered width fits within max_width."""
    words = text.split()
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def create_verse_slide(verse_text, reference, output_path):
    """
    Create a transparent verse slide with a black-to-transparent gradient
    on the left and white verse/reference text, matching thing.tif's style.

    Args:
        verse_text: The verse quote (str)
        reference: The verse reference e.g., "Matthew 10:45 ESV" (str)
        output_path: Path to save the output .tif file
    """
    img = _make_gradient(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(img)

    font_verse = _load_font(FONT_INDEX_REGULAR, FONT_SIZE)
    font_ref = _load_font(FONT_INDEX_MEDIUM, FONT_SIZE)

    verse_display = f'“{verse_text}"'
    lines = _wrap_to_width(draw, verse_display, font_verse, TEXT_BOX_WIDTH)

    y = TOP_MARGIN
    for line in lines:
        draw.text((LEFT_MARGIN, y), line, fill=(255, 255, 255, 255), font=font_verse)
        y += LINE_HEIGHT

    ref_y = y + REF_GAP - LINE_HEIGHT
    draw.text((LEFT_MARGIN, ref_y), reference, fill=(255, 255, 255, 255), font=font_ref)

    img.save(output_path, 'TIFF')
    print(f"✓ Created: {output_path}")
    return output_path


def batch_create(verses_list, output_dir='./slides'):
    """
    Generate multiple verse slides from a list of tuples.

    Args:
        verses_list: List of (verse_text, reference) tuples
        output_dir: Directory to save slides

    Example:
        verses = [
            ("For God so loved the world...", "John 3:16 ESV"),
            ("In the beginning was the Word...", "John 1:1 ESV"),
        ]
        batch_create(verses)
    """
    os.makedirs(output_dir, exist_ok=True)

    for i, (verse, ref) in enumerate(verses_list, 1):
        filename = f"{output_dir}/verse_{i:03d}.tif"
        create_verse_slide(verse, ref, filename)


if __name__ == '__main__':
    verse = "For even the Son of Man came not to be served but to serve, and to give his life as a ransom for many."
    reference = "Matthew 10:45 ESV"

    create_verse_slide(verse, reference, 'output_verse.tif')
