#!/usr/bin/env python3
"""
Verse retrieval from BibleGateway.

This is the deliberately thin, disposable layer. It scrapes HTML, which means
it will break whenever BibleGateway restyles their passage page -- the plan is
to swap it for a proper API or a local corpus later.

Because of that, it does as little as possible: fetch, pull the verse spans
out, hand back *raw* verse strings. All display formatting (quote handling,
capitalization, artifact scrubbing) lives in slidegen.py so that it survives
this module being replaced. The only cleanup done here is structural --
dropping the footnote/cross-reference/verse-number nodes, which is far more
reliable done against the DOM than against a flat string. slidegen's
find_artifacts is the regex safety net for anything that slips through.

Contract for any future replacement: return a list of
(verse_text, "Book Chapter:Verse TRANSLATION") tuples in verse order.
"""

import re

import requests
from bs4 import BeautifulSoup

PASSAGE_URL = 'https://www.biblegateway.com/passage/'
TRANSLATION = 'ESV'

# Verse-identifying class on each text span, e.g. "John-17-6" or "1John-4-18".
_VERSE_CLASS_RE = re.compile(r'^([1-3]?[A-Za-z]+)-(\d+)-(\d+)$')
_WHITESPACE_RE = re.compile(r'\s+')

# Nodes that are navigation aids, not scripture.
_JUNK_SUP_CLASSES = ('footnote', 'crossreference', 'versenum')


def fetch_chapter(reference, translation=TRANSLATION, timeout=15):
    """
    Fetch a chapter and return [(verse_text, reference), ...] in verse order.

    Args:
        reference: book and chapter, e.g. "John 17" or "1 John 4". Passed
            through to BibleGateway's own search, so anything it resolves
            works here.
        translation: version code, ESV by default.

    Raises:
        requests.HTTPError: on a non-2xx response.
        ValueError: if the page contains no passage for this reference.
    """
    response = requests.get(
        PASSAGE_URL,
        params={'search': reference, 'version': translation},
        headers={'User-Agent': 'Mozilla/5.0'},
        timeout=timeout,
    )
    response.raise_for_status()
    return parse_chapter(response.text, translation)


def parse_chapter(html, translation=TRANSLATION):
    """
    Pull verses out of a BibleGateway passage page.

    Split out from fetch_chapter so it can be exercised against a saved page
    without touching the network.
    """
    soup = BeautifulSoup(html, 'html.parser')

    heading = soup.select_one('div.bcv .dropdown-display-text')
    if heading is None:
        raise ValueError('no passage found on page')
    book_chapter = heading.get_text(strip=True).rsplit(':', 1)[0]

    body = soup.select_one(f'div.passage-content div.version-{translation}')
    if body is None:
        raise ValueError(f'no {translation} text found on page')

    fragments = {}
    order = []
    for span in body.find_all('span', class_='text'):
        if span.find_parent('h3'):
            continue  # section heading

        match = next(
            (m for m in (_VERSE_CLASS_RE.match(c) for c in span.get('class', [])) if m),
            None,
        )
        if match is None:
            continue
        verse_num = int(match.group(3))

        for junk in span.find_all('sup', class_=_JUNK_SUP_CLASSES):
            junk.decompose()
        for junk in span.find_all('span', class_='chapternum'):
            junk.decompose()

        text = _WHITESPACE_RE.sub(' ', span.get_text()).strip()
        if not text:
            continue

        if verse_num not in fragments:
            fragments[verse_num] = []
            order.append(verse_num)
        fragments[verse_num].append(text)

    if not order:
        raise ValueError('passage contained no verses')

    return [
        (
            _WHITESPACE_RE.sub(' ', ' '.join(fragments[n])).strip(),
            f'{book_chapter}:{n} {translation}',
        )
        for n in order
    ]


if __name__ == '__main__':
    import sys

    for text, ref in fetch_chapter(' '.join(sys.argv[1:]) or 'John 1'):
        print(f'{ref}\t{text}')
