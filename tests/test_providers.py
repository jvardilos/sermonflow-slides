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

    def test_unknown_provider_name_raises(self):
        with pytest.raises(ValueError, match="unknown provider"):
            get_provider("some-nonsense")

    def test_both_providers_satisfy_the_protocol(self):
        assert isinstance(BibleGatewayProvider(), BibleProvider)
        assert isinstance(EsvApiProvider("k"), BibleProvider)
