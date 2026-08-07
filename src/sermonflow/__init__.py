"""
sermonflow: generate ProPresenter-ready verse slides that match a hand-built
Photoshop template, one slide per verse.

Organized internally into focused modules -- text, wrap, fonts, layout, render,
providers -- but flat externally: the whole API is re-exported here, so
`import sermonflow` gives you every function the pipeline uses without needing
to know which module it lives in. The pipeline itself is:

    provider.fetch_chapter -> text.format_verses -> layout -> render

The private names re-exported below (drawing helpers, kerning loaders, the font
selection internals) are deliberately part of the surface: the test suite pins
them, and they are the seams a future contributor reaches for.
"""

from __future__ import annotations

# -- text normalization -----------------------------------------------------
from .text import (
    CLOSE_QUOTE as CLOSE_QUOTE,
    OPEN_QUOTE as OPEN_QUOTE,
    Verse as Verse,
    apply_quote_carry as apply_quote_carry,
    capitalize_first_letter as capitalize_first_letter,
    find_artifacts as find_artifacts,
    format_verses as format_verses,
    normalize_quotes as normalize_quotes,
    strip_artifacts as strip_artifacts,
)

# -- line breaking ----------------------------------------------------------
from .wrap import (
    Measure as Measure,
    balance_wrap as balance_wrap,
    break_long_word as break_long_word,
    greedy_wrap as greedy_wrap,
    raggedness as raggedness,
)

# -- fonts, metrics, kerning, drawing ---------------------------------------
from .fonts import (
    FONT_CHOICES as FONT_CHOICES,
    FONT_INDEX_MEDIUM as FONT_INDEX_MEDIUM,
    FONT_INDEX_REGULAR as FONT_INDEX_REGULAR,
    FONT_NAME as FONT_NAME,
    FONT_PATH as FONT_PATH,
    FONT_PATH_MEDIUM as FONT_PATH_MEDIUM,
    FONT_SIZE as FONT_SIZE,
    HORIZONTAL_SCALE as HORIZONTAL_SCALE,
    IS_REFERENCE_FONT as IS_REFERENCE_FONT,
    POINT_WEIGHT as POINT_WEIGHT,
    REFERENCE_WEIGHT as REFERENCE_WEIGHT,
    VERSE_WEIGHT as VERSE_WEIGHT,
    WEIGHTS as WEIGHTS,
    Face as Face,
    _Kerning as _Kerning,
    _as_face as _as_face,
    _draw_line as _draw_line,
    _font_charset as _font_charset,
    _font_choices as _font_choices,
    _ink_offset as _ink_offset,
    _load_kerning as _load_kerning,
    draw_text as draw_text,
    find_unrenderable as find_unrenderable,
    kern_width as kern_width,
    load_fonts as load_fonts,
    text_measurer as text_measurer,
)

# -- layout geometry --------------------------------------------------------
from .layout import (
    GRADIENT_PROFILE as GRADIENT_PROFILE,
    GRADIENT_PROFILE_STEP as GRADIENT_PROFILE_STEP,
    GRID_ORIGIN as GRID_ORIGIN,
    LEFT_MARGIN as LEFT_MARGIN,
    LEGIBLE_ALPHA as LEGIBLE_ALPHA,
    LINE_HEIGHT as LINE_HEIGHT,
    MIN_BOTTOM_MARGIN as MIN_BOTTOM_MARGIN,
    MIN_TOP_MARGIN as MIN_TOP_MARGIN,
    REF_CAP_HEIGHT as REF_CAP_HEIGHT,
    REF_GAP as REF_GAP,
    REF_MAX_WIDTH as REF_MAX_WIDTH,
    SLIDE_HEIGHT as SLIDE_HEIGHT,
    SLIDE_WIDTH as SLIDE_WIDTH,
    TEXT_BOX_WIDTH as TEXT_BOX_WIDTH,
    EmptyVerseError as EmptyVerseError,
    SlideOverflowError as SlideOverflowError,
    _scrim_limit as _scrim_limit,
    block_fits as block_fits,
    block_height as block_height,
    block_top as block_top,
    find_overlong_reference as find_overlong_reference,
    layout_slide as layout_slide,
    max_lines as max_lines,
)

# -- rendering --------------------------------------------------------------
from .render import (
    compose_slide as compose_slide,
    generate_slides as generate_slides,
    make_gradient as make_gradient,
    render_slide as render_slide,
    slide_filename as slide_filename,
)

# -- retrieval --------------------------------------------------------------
from .providers import (
    DEFAULT_TRANSLATION as DEFAULT_TRANSLATION,
    BibleGatewayProvider as BibleGatewayProvider,
    BibleProvider as BibleProvider,
    EsvApiProvider as EsvApiProvider,
    get_default_provider as get_default_provider,
    get_provider as get_provider,
)

__version__ = "0.2.0"
