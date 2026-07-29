#!/usr/bin/env python3
"""
Verse Slide Generator for ProPresenter
Generates full 1920x1080 TIFF slides with verse text on gradient background
No template file needed.
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

def create_verse_slide(verse_text, reference, output_path):
    """
    Create a complete verse slide with gradient background and text.

    Args:
        verse_text: The verse quote (str)
        reference: The verse reference e.g., "Matthew 10:45 ESV" (str)
        output_path: Path to save the output .tif file
    """

    width, height = 1920, 1080

    # Create gradient background using PIL
    img = Image.new('RGB', (width, height))
    pixels = img.load()

    # Create diagonal gradient: dark gray (bottom-left) to light gray (top-right)
    # Matches the original template style
    dark = (35, 35, 35)      # Dark gray
    light = (215, 215, 215)  # Light gray

    for y in range(height):
        for x in range(width):
            # Create smooth diagonal gradient
            # Stronger weight on x-axis (left to right) than y-axis
            blend = (x / width * 0.7) + (y / height * 0.3)
            blend = min(1.0, max(0.0, blend))

            r = int(dark[0] + (light[0] - dark[0]) * blend)
            g = int(dark[1] + (light[1] - dark[1]) * blend)
            b = int(dark[2] + (light[2] - dark[2]) * blend)

            pixels[x, y] = (r, g, b)

    # Set up drawing context
    draw = ImageDraw.Draw(img)

    # Load font - try to find a clean sans-serif font
    font_large = None
    font_small = None

    font_paths = [
        '/System/Library/Fonts/Helvetica.ttc',           # macOS Helvetica
        '/System/Library/Fonts/Arial.ttf',               # macOS Arial
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',  # Linux
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',  # Linux
        'C:\\Windows\\Fonts\\arial.ttf',                 # Windows
        'C:\\Windows\\Fonts\\Helvetica.ttf',             # Windows
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font_large = ImageFont.truetype(font_path, 70)
                font_small = ImageFont.truetype(font_path, 55)
                break
            except:
                continue

    # Fallback to default if no font found
    if font_large is None:
        font_large = ImageFont.load_default()
        font_small = font_large

    # Text positioning and styling
    left_margin = 70
    top_margin = 180
    right_margin = 150
    text_width = width - left_margin - right_margin

    # Wrap verse text to fit width (approximately 40 chars per line)
    wrapped_verse = textwrap.fill(verse_text, width=45)
    verse_display = f'"{wrapped_verse}"'

    # Draw verse text in white
    draw.text(
        (left_margin, top_margin),
        verse_display,
        fill=(255, 255, 255),
        font=font_large
    )

    # Draw reference text (lower left area)
    ref_y = height - 220
    draw.text(
        (left_margin, ref_y),
        reference,
        fill=(255, 255, 255),
        font=font_small
    )

    # Save as TIFF
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
    # Example: Single verse
    verse = "For even the Son of Man came not to be served but to serve, and to give his life as a ransom for many."
    reference = "Matthew 10:45 ESV"

    create_verse_slide(verse, reference, 'output_verse.tif')

    # Example: Batch processing (uncomment to use)
    # verses = [
    #     ("For God so loved the world that he gave his one and only Son...", "John 3:16 ESV"),
    #     ("In the beginning was the Word...", "John 1:1 ESV"),
    # ]
    # batch_create(verses)