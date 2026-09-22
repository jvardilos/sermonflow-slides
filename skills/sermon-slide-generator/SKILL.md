---
name: sermon-slide-generator
description: Preview and generate ProPresenter-ready Scripture or sermon-point slides through SermonFlow's local MCP tools.
---

# Sermon slide generation

Use SermonFlow for a Scripture reference or sermon-point text supplied by the
user. It creates 1920×1080 RGBA TIFF slides suitable for ProPresenter import.

## Choose the correct tool

- Scripture reference, such as `John 17` or `Romans 8:28`: use
  `preview_slides`, then `generate_slides` after the preview is acceptable.
- User-authored statements, headings, paraphrases, or sermon points: use
  `preview_points`, then `generate_points` after the preview is acceptable.
- If the requested point treatment is unclear, call `list_layouts` or ask the
  user whether they want a rolling outline or a centered statement.

Do not claim that SermonFlow extracts highlights from Word or PDF files: the
current MCP server accepts only Scripture references and supplied point text.

## Scripture workflow

1. Call `preview_slides(reference, translation)`.
2. Surface any validation problems or wrapped-line concerns to the user.
3. Call `generate_slides(reference, translation, output_dir, strict=true)` only
   after the user accepts the preview, or when their request clearly authorizes
   generation without a preview.
4. Report the returned file paths and output directory.

`translation` defaults to `ESV`. With `ESV_API_KEY`, retrieval uses the ESV
API; otherwise BibleGateway is the fallback. The ESV API supports ESV only.

## Point workflow

1. Choose a style: `rolling` for an outline that builds one point at a time,
   `centered` for one statement per slide, or `stacked` for one slide per entry
   holding the paragraphs that entry separates with newlines (a lie above its
   truth, or a short list of steps). Call `list_layouts` if unsure.
2. Call `preview_points(points, style)`.
3. Call `generate_points(points, style, output_dir, strict=true)` when approved.
4. Report the returned file paths and output directory.

## Output handling

Always pass an explicit `output_dir` chosen by the user or a host-appropriate
project output location. Do not assume a Desktop path. SermonFlow creates the
directory if necessary and writes uncompressed TIFFs, approximately 8 MB per
slide. A chapter can therefore use hundreds of MB.

Each call writes into its own timestamped subfolder of `output_dir`, so a
re-run never overwrites an earlier deck. Report the `output_dir` from the
result, not the one that was requested, since that is where the files are.

If the result carries `skipped`, those verses or points never reached a slide:
tell the user what is missing from the deck rather than reporting a clean run.

## Errors

- Invalid or unavailable passage: show the provider or validation error and
  ask for a corrected reference.
- Validation issue with `strict=true`: do not render until the user chooses to
  shorten/edit the content or explicitly authorizes `strict=false`.
- Write failure: report the attempted output directory and ask for another
  writable location.
