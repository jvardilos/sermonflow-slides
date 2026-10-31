"""
Provider layer: BibleGateway parsing and the default provider, all offline.

The network call itself is not exercised (it depends on a third party), but the
pure parsing that turns a fetched page into the (verse_text, reference)
contract is, against small hand-built fixtures.
"""

import pytest

from sermonflow.providers import (
    BibleGatewayProvider,
    BibleProvider,
    get_default_provider,
    parse_chapter,
)


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


class TestDefaultProvider:
    def test_default_is_bible_gateway_whatever_the_environment_holds(
        self, monkeypatch
    ):
        # The decision is that API keys are never used: a key left over in the
        # environment must not change which backend is chosen.
        monkeypatch.setenv("ESV_API_KEY", "test-key-123")
        assert isinstance(get_default_provider(), BibleGatewayProvider)

    def test_satisfies_the_protocol(self):
        assert isinstance(BibleGatewayProvider(), BibleProvider)
