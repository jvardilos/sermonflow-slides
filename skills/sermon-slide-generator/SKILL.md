---
name: sermon-slide-generator
description: Generate ProPresenter slides from sermon documents or verse references—extracts yellow-highlighted verses and points, renders them with intelligent typography.
---

# Sermon Slide Generation

When a user uploads a sermon document (Word or PDF) or asks to generate slides from scripture, use this workflow to extract highlighted content and render polished ProPresenter slides.

## Triggers

- User uploads a `.docx` or `.pdf` file that appears to be a sermon
- User asks: "generate slides for [verses]" or "give me Romans 8"
- User mentions sermon points they want on slides

## Workflow

### 1. Extract Content

**If document uploaded:**
Extract all yellow-highlighted text from the document:
- Use `python-docx` (for .docx files) to read highlight color from text runs
- Use `pdfplumber` or `pypdf` (for .pdf files) to extract text and attempt highlight detection
- If extraction fails, fall back to asking user to paste or specify verses manually

**If natural language input:**
Parse the verse reference using the `preview_slides` tool first to validate:
- "Romans 8" → "Romans 8:1-39" (full chapter)
- "John 3:16-20" → exact range
- "1 Corinthians 13" → full chapter

### 2. Classify Content

For each extracted highlight, determine if it's:
- **Verse** (contains book name like "John", "Romans", "Matthew" + reference)
  - Route to `generate_slides` tool
- **Point** (sermon point text, typically a phrase or statement)
  - Route to `generate_points` tool

Use simple heuristics: if the text includes a book name + colon + number(s), treat as verse. Otherwise, treat as point.

### 3. Generate Slides

**For verses:**
```
Call generate_slides(reference="[book chapter:verse-range]", translation="ESV")
```
Returns the paths to generated slide files. The tool handles:
- Fetching scripture text
- Wrapping text to fit ProPresenter bounds
- Rendering with the configured typeface

**For points:**
```
Call generate_points(points=["point 1 text", "point 2 text", ...], style="default")
```
Returns the paths to generated point slides. The tool:
- Renders each point in the configured layout
- Sizes text within the predefined bounds
- Applies the sermon point styling

### 4. Output Management

Create an output directory on the user's Desktop:
- Directory name: `sermonflow-slides-{timestamp}` or `sermonflow-{date}_{time}`
- Move or copy all generated slides into this directory
- Tell the user the full path to the directory

## Extraction Details

### Yellow Highlight Detection (DOCX)

```python
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

doc = Document(file_path)
highlights = []

for paragraph in doc.paragraphs:
    for run in paragraph.runs:
        if run.font.highlight_color == WD_COLOR_INDEX.YELLOW:
            highlights.append(run.text)
```

### Yellow Highlight Detection (PDF)

For PDFs, highlight extraction is approximate:
- Use `pdfplumber` to extract text and page structure
- Attempt to detect highlight color from PDF annotations
- If annotations not available, extract all text and ask user to manually confirm

### Natural Language Verse Parsing

Match patterns like:
- `Genesis 1` → "Genesis 1"
- `John 3:16` → "John 3:16"
- `Romans 12:1-3` → "Romans 12:1-3"
- `1 Thessalonians 4` → "1 Thessalonians 4"

Use regex: `([1-3]?\s?)?([A-Za-z\s]+)\s+(\d+)(?::(\d+))?(?:-(\d+))?`

## Error Handling

If extraction fails:
- "I couldn't extract highlights from the PDF. Try uploading a Word document, or paste the verses/points you want."

If verse reference is invalid:
- Let the `preview_slides` tool validate; it will report if the reference doesn't exist

If no output directory can be created:
- Fall back to saving in the current working directory or temp location
- Tell the user the fallback path

## Example Flow

```
User: [uploads sermon.docx]
Claude: "I found 12 highlighted verses and 3 sermon points in your document. 
         Generating slides..."

→ Extract highlights: ["John 3:16", "Romans 12:1", ...] + ["Jesus is Lord", ...]
→ Call generate_slides for each verse
→ Call generate_points for each point
→ Collect outputs into Desktop/sermonflow-slides-2026-09-20_14-32/
→ "Done! Your slides are in Desktop/sermonflow-slides-2026-09-20_14-32/"
```

## Notes

- Trust the sermonflow code to handle layout within its predefined bounds—no manual adjustment needed
- As the code improves, the point style detection will get better; for now, render points literally as extracted
- If a point text is too long, the code will wrap it; no pre-processing needed
- Always save to Desktop by default, but respect if the user specifies a different output location
