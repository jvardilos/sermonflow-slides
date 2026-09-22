# Design: slide cache/database + zip packaging

**Status: proposal.** Nothing here is implemented yet. This documents the shape
of the "check if it already exists, else render, then package it up" workflow so
it can be built without re-litigating the design, and so today's code stays
aimed at it.

## The problem

Today `generate_slides` re-renders every verse, every run, straight to a local
folder. Two things we want next:

1. **Don't re-render what hasn't changed.** A chapter's slides are a pure
   function of `(verse text, reference, layout/font rules)`. Re-running the same
   chapter should be a set of cache hits, not 26 fresh 8MB TIFFs.
2. **Hand a deck off as one artifact.** A chapter is ~200MB of loose TIFFs.
   Producing a single (compressed) zip with a stable name is what actually gets
   moved to the tech team / into ProPresenter.

Both sit *around* the existing pipeline, not inside it — `render.py` should not
learn about databases or zips.

## The cache key — hash, not a version string

A slide is stale if **anything that determines its pixels** changed. Keying on a
hand-bumped `"layout v3"` string invites silent drift: someone tweaks
`TEXT_BOX_WIDTH` or swaps a font weight and forgets to bump it, and the store
serves last week's slides. So the key is a **content hash**:

```
slide_key = sha256(
    verse_text            # the formatted display text, post quote-carry
    + reference           # "John 17:1 ESV"
    + render_fingerprint  # see below
)
```

`render_fingerprint` is itself a hash over everything that moves a pixel:

- the layout constants (`SLIDE_WIDTH/HEIGHT`, `LEFT_MARGIN`, `TEXT_BOX_WIDTH`,
  `LINE_HEIGHT`, `REF_GAP`, `GRID_ORIGIN`, the `GRADIENT_PROFILE`, …)
- the selected font files' own bytes (so re-hinting or swapping the `.ttf`
  invalidates), plus `FONT_SIZE`, `VERSE_WEIGHT`, `REFERENCE_WEIGHT`
- a manual `RENDER_ALGO_VERSION` integer, bumped only when the *drawing code*
  changes in a way constants can't capture (e.g. the kerning path)

Computing this from the actual constants and font bytes — rather than trusting a
label — is what makes "check if it exists" trustworthy. It belongs next to the
values it hashes, e.g. a `render_fingerprint()` in `sermonflow.render`.

## The store interface

Keep it deliberately tiny so the first implementation is trivial and the swap to
object storage later is mechanical:

```python
class SlideStore(Protocol):
    def get(self, slide_key: str) -> bytes | None: ...        # cached TIFF, or miss
    def put(self, slide_key: str, tiff: bytes) -> None: ...
    def get_meta(self, slide_key: str) -> SlideMeta | None: ...  # reference, created_at…
```

### First implementation: SQLite + local blobs

- **SQLite** file (`slides.db`) for the index: one row per slide —
  `slide_key`, `reference`, `translation`, `render_fingerprint`, `created_at`,
  `blob_path`.
- **Blobs on disk** next to the db (`blobs/<slide_key>.tif`), not inside SQLite —
  8MB rows are a poor fit, and a bare file is what everything else here consumes.

SQLite is zero-setup (stdlib `sqlite3`), which keeps the "runs anywhere" promise
the bundled font already established.

### Later: object storage

The same `SlideStore` Protocol over S3/GCS — `get`/`put` become object reads and
writes, `blob_path` becomes an object key. Nothing above the interface changes.
This is the natural home once slides are shared with a team rather than a single
operator, and it lines up with the roadmap's "push to a bucket" item.

## Where it hooks in — without touching `generate_slides`' signature

`render.generate_slides` stays exactly as it is. Caching is a **wrapper** that
reuses its pieces (`format_verses`, `slide_filename`, `compose_slide`):

```python
def generate_slides_cached(
    verses, output_dir="./slides", store=None, formatted=False,
):
    store = store or default_store()
    fp = render_fingerprint()
    prepared = verses if formatted else format_verses(verses)
    paths = []
    for i, (text, ref) in enumerate(prepared, 1):
        if not text.strip():
            continue
        key = slide_key(text, ref, fp)
        tiff = store.get(key)
        if tiff is None:                       # miss -> render once, cache it
            tiff = compose_slide(text, ref).tobytes_tiff()
            store.put(key, tiff)
        path = os.path.join(output_dir, slide_filename(ref, i))
        write(path, tiff)
        paths.append(path)
    return paths
```

So the cache is additive: the pure renderer and its tests are untouched, and a
caller opts in by passing a `store`.

## Packaging: `package_slides` → a zip

A thin step after generation, and a natural **third MCP tool** so an LLM can hand
back one downloadable artifact:

```python
def package_slides(reference, translation="ESV", store=None) -> str:
    """Render (via cache) and bundle a chapter into a single zip. Returns its path."""
```

- Uses the cache above, so a re-package of an unchanged chapter renders nothing.
- Writes a **compressed** archive (`ZIP_DEFLATED`) — the loose TIFFs are ~200MB
  uncompressed; the scrim + flat type compress hard, and switching to
  LZW-TIFF or PNG first (a roadmap item) compounds it.
- Stable inner names (`John_17_001.tif` …) and a stable archive name
  (`John_17_ESV.zip`) so re-runs overwrite predictably.
- Includes a small `manifest.json` (references in order, `render_fingerprint`,
  created-at) so a consumer can tell two builds apart.

MCP surface, alongside today's `preview_slides` / `generate_slides`:

| Tool | Returns |
|---|---|
| `package_slides(reference, translation)` | path to a single `.zip` of the chapter |

## Build order

1. `render_fingerprint()` + `slide_key()` in `sermonflow.render` (pure, unit-testable).
2. `SlideStore` Protocol + the SQLite/blob implementation in a new
   `sermonflow/store.py`, with an in-memory store for tests.
3. `generate_slides_cached` wrapper — hit/miss behaviour tested against the
   in-memory store.
4. `package_slides` + the zip writer.
5. Wire `package_slides` into `mcp_server.py`; add a `--package` flag to the CLI.
6. (Later) an object-storage `SlideStore` behind the same Protocol.

Steps 1–4 need no network and no new heavy dependency (stdlib `sqlite3`,
`zipfile`, `hashlib`), keeping the project's zero-setup posture intact.
