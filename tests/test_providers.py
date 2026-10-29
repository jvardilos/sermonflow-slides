"""
Provider layer: parsing and selection, all offline.

The network calls themselves are not exercised (they depend on a third party),
but the pure parsing that turns a fetched payload into the (verse_text,
reference) contract is, against small hand-built fixtures, plus the registry
rule that decides which backend to use.
"""

import pytest

from sermonflow.providers import (
    BibleGatewayProvider,
    BibleProvider,
    EsvApiProvider,
    get_default_provider,
    get_provider,
    parse_chapter,
    parse_passage_text,
)
from sermonflow.providers.registry import ESV_API_KEY_ENV


class TestEsvApiParse:
    """ESV API text: verses delimited by inline [n] markers."""

    SAMPLE = (
        "  [1] In the beginning, God created the heavens and the earth. "
        "[2] The earth was without form and void, and darkness was over the "
        "face of the deep.\n\n  [3] And God said, “Let there be light,” "
        "and there was light."
    )

    def test_splits_on_markers(self):
        verses = parse_passage_text(self.SAMPLE, "Genesis 1")
        assert [ref for _, ref in verses] == [
            "Genesis 1:1 ESV",
            "Genesis 1:2 ESV",
            "Genesis 1:3 ESV",
        ]

    def test_verse_text_is_clean_and_whitespace_collapsed(self):
        verses = parse_passage_text(self.SAMPLE, "Genesis 1")
        assert verses[0][0] == (
            "In the beginning, God created the heavens and the earth."
        )
        assert "  " not in verses[2][0]
        assert "\n" not in verses[2][0]

    def test_chapter_qualified_markers_use_the_verse_number(self):
        text = "[3:16] For God so loved the world, [3:17] For God did not send"
        verses = parse_passage_text(text, "John 3")
        assert [ref for _, ref in verses] == ["John 3:16 ESV", "John 3:17 ESV"]

    def test_high_verse_numbers(self):
        verses = parse_passage_text("[176] My final plea.", "Psalm 119")
        assert verses == [("My final plea.", "Psalm 119:176 ESV")]

    def test_empty_between_markers_is_skipped(self):
        verses = parse_passage_text("[1]   [2] Real text here.", "Book 1")
        assert verses == [("Real text here.", "Book 1:2 ESV")]

    def test_no_markers_raises(self):
        with pytest.raises(ValueError, match="no verse markers"):
            parse_passage_text("Just some prose with no markers.", "Book 1")


class TestBibleGatewayParse:
    """BibleGateway HTML: verse spans classed Book-Chapter-Verse."""

    HTML = """
    <html><body>
      <div class="bcv"><div class="dropdown-display-text">John 3:16-17</div></div>
      <div class="passage-content">
        <div class="version-ESV">
          <h3><span class="text John-3-15">a heading span, ignored</span></h3>
          <p>
            <span class="text John-3-16">
              <sup class="versenum">16</sup>For God so loved<sup
              class="footnote">[a]</sup> the world,
              <span class="crossreference">(A)</span>
            </span>
            <span class="text John-3-17">
              <span class="chapternum">3</span>For God did not send his Son
            </span>
          </p>
        </div>
      </div>
    </body></html>
    """

    def test_returns_verses_in_order_with_labels(self):
        verses = parse_chapter(self.HTML, "ESV")
        assert [ref for _, ref in verses] == ["John 3:16 ESV", "John 3:17 ESV"]

    def test_structural_junk_is_dropped(self):
        verses = parse_chapter(self.HTML, "ESV")
        text = verses[0][0]
        assert "16" not in text            # versenum sup decomposed
        assert "the world" in text
        # footnote/crossref residue is scrubbed downstream; the number node is
        # gone here structurally.
        assert text.startswith("For God so loved")

    def test_heading_spans_are_skipped(self):
        verses = parse_chapter(self.HTML, "ESV")
        assert all("heading" not in text for text, _ in verses)

    def test_small_caps_divine_name_is_upper_cased(self):
        # The ESV prints the divine name in small capitals; BibleGateway marks
        # it with a CSS span whose text is "Lord". Dropping the span silently
        # turns LORD (YHWH) into Lord (Adonai) -- a different word on screen.
        html = """
        <div class="bcv"><div class="dropdown-display-text">Genesis 2</div></div>
        <div class="passage-content"><div class="version-ESV"><p>
          <span id="en-ESV-47" class="text Gen-2-16"><sup class="versenum">16 </sup>And the
          <span style="font-variant: small-caps" class="small-caps">Lord</span> God
          commanded the man, the <span class="small-caps">Lord</span>’s word,</span>
          <span class="text Gen-2-17"><sup class="versenum">17 </sup>O Lord
          <span class="small-caps">God</span>, and the Lord Jesus</span>
        </p></div></div>
        """
        verses = parse_chapter(html, "ESV")
        assert verses[0][0] == (
            "And the LORD God commanded the man, the LORD’s word,"
        )
        # Plain "Lord" is Adonai / Kyrios and stays as written.
        assert verses[1][0] == "O Lord GOD, and the Lord Jesus"

    def test_missing_passage_raises(self):
        with pytest.raises(ValueError, match="no passage found"):
            parse_chapter("<html><body>nothing here</body></html>", "ESV")

    def test_missing_translation_body_raises(self):
        html = (
            '<div class="bcv"><div class="dropdown-display-text">John 3</div>'
            "</div><div class=\"passage-content\"></div>"
        )
        with pytest.raises(ValueError, match="no ESV text"):
            parse_chapter(html, "ESV")


class TestBibleGatewayMarkupDrift:
    """The scraper keys on class names, so it survives element-name changes."""

    # Shape of the live page: the heading is <span class="bcv"> (it used to be
    # <div>), wrapped in an <h1>, and the text sits beside a decoy heading.
    LIVE_SHAPED = """
    <h1 class='passage-display'>
      <span class='bcv'><span class="dropdown-display">
        <span class="dropdown-display-text">John 3</span><span>&nbsp;</span>
      </span></span>
    </h1>
    <div class="passage-text"><div class='passage-content passage-class-0'>
      <div class="version-ESV result-text-style-normal text-html">
        <h3><span id="en-ESV-26111" class="text John-3-1">You Must Be Born Again</span></h3>
        <p class="chapter-1"><span class="text John-3-1"><span class="chapternum">3 </span>Now there was
          a man <sup class='crossreference' data-cr='#x'>(<a href="#x">A</a>)</sup>named Nicodemus.</span>
        <span id="en-ESV-26112" class="text John-3-2"><sup class="versenum">2 </sup>This man came
          to Jesus<sup class='footnote'>[<a href="#f">a</a>]</sup> by night.</span></p>
      </div>
    </div></div>
    """

    def test_live_shaped_page(self):
        assert parse_chapter(self.LIVE_SHAPED, "ESV") == [
            ("Now there was a man named Nicodemus.", "John 3:1 ESV"),
            ("This man came to Jesus by night.", "John 3:2 ESV"),
        ]

    def test_heading_wrapper_may_be_a_span(self):
        html = TestBibleGatewayParse.HTML.replace(
            '<div class="bcv"><div class="dropdown-display-text">John 3:16-17</div></div>',
            '<span class="bcv"><span class="dropdown-display-text">John 3:16-17</span></span>',
        )
        assert len(parse_chapter(html, "ESV")) == 2

    def test_heading_without_the_dropdown_node(self):
        html = TestBibleGatewayParse.HTML.replace(
            '<div class="bcv"><div class="dropdown-display-text">John 3:16-17</div></div>',
            '<p class="bcv">John 3:16-17</p>',
        )
        assert [ref for _, ref in parse_chapter(html, "ESV")][0] == "John 3:16 ESV"

    def test_every_element_name_may_change(self):
        html = """
        <header class="bcv"><b class="dropdown-display-text">John 3</b></header>
        <main class="passage-content"><article class="version-ESV">
          <section><i class="text John-3-16"><em class="versenum">16 </em>For God so
            loved <small class="footnote">[a]</small>the world.</i></section>
        </article></main>
        """
        assert parse_chapter(html, "ESV") == [
            ("For God so loved the world.", "John 3:16 ESV")
        ]

    def test_section_heading_level_does_not_matter(self):
        html = TestBibleGatewayParse.HTML.replace("<h3>", "<h4>").replace("</h3>", "</h4>")
        assert all("heading" not in t for t, _ in parse_chapter(html, "ESV"))

    def test_nested_verse_element_is_not_counted_twice(self):
        html = """
        <span class="bcv"><span class="dropdown-display-text">John 3</span></span>
        <div class="passage-content"><div class="version-ESV">
          <div class="text John-3-16">For God <span class="text John-3-16">so loved</span> the world.</div>
        </div></div>
        """
        assert parse_chapter(html, "ESV") == [
            ("For God so loved the world.", "John 3:16 ESV")
        ]

    def test_version_div_outside_passage_content(self):
        html = """
        <span class="bcv"><span class="dropdown-display-text">John 3</span></span>
        <div class="version-ESV"><span class="text John-3-16">For God so loved.</span></div>
        """
        assert parse_chapter(html, "ESV")[0][1] == "John 3:16 ESV"


class TestRegistry:
    def test_no_key_falls_back_to_bible_gateway(self, monkeypatch):
        monkeypatch.delenv(ESV_API_KEY_ENV, raising=False)
        provider = get_default_provider()
        assert isinstance(provider, BibleGatewayProvider)

    def test_key_selects_the_esv_api(self, monkeypatch):
        monkeypatch.setenv(ESV_API_KEY_ENV, "test-key-123")
        provider = get_default_provider()
        assert isinstance(provider, EsvApiProvider)
        assert provider.api_key == "test-key-123"

    def test_get_provider_by_name(self, monkeypatch):
        monkeypatch.setenv(ESV_API_KEY_ENV, "test-key-123")
        assert isinstance(get_provider("esv-api"), EsvApiProvider)
        assert isinstance(get_provider("bible-gateway"), BibleGatewayProvider)

    def test_esv_api_by_name_without_key_raises(self, monkeypatch):
        monkeypatch.delenv(ESV_API_KEY_ENV, raising=False)
        with pytest.raises(ValueError, match=ESV_API_KEY_ENV):
            get_provider("esv-api")

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("esv", EsvApiProvider),
            ("esvapi", EsvApiProvider),
            ("  ESV-API ", EsvApiProvider),
            ("biblegateway", BibleGatewayProvider),
            ("gateway", BibleGatewayProvider),
            ("Bible-Gateway", BibleGatewayProvider),
        ],
    )
    def test_aliases_and_spacing_resolve(self, monkeypatch, name, expected):
        monkeypatch.setenv(ESV_API_KEY_ENV, "test-key-123")
        assert isinstance(get_provider(name), expected)

    def test_unknown_provider_name_raises(self):
        with pytest.raises(ValueError, match="unknown provider"):
            get_provider("some-nonsense")

    def test_every_table_entry_can_resolve(self):
        # get_provider lowercases its input, so a key with capitals -- or an
        # alias aimed at a name that isn't a key -- would be dead on arrival.
        from sermonflow.providers.registry import _ALIASES, PROVIDERS

        assert all(name == name.lower() for name in [*PROVIDERS, *_ALIASES])
        assert set(_ALIASES.values()) <= set(PROVIDERS)

    def test_provider_names_lists_the_canonical_backends(self):
        from sermonflow import provider_names

        assert provider_names() == ["esv-api", "bible-gateway"]

    def test_unknown_provider_error_names_the_choices(self):
        with pytest.raises(ValueError) as exc:
            get_provider("some-nonsense")
        assert "'esv-api'" in str(exc.value)
        assert "'bible-gateway'" in str(exc.value)

    def test_both_providers_satisfy_the_protocol(self):
        assert isinstance(BibleGatewayProvider(), BibleProvider)
        assert isinstance(EsvApiProvider("k"), BibleProvider)
