# SermonFlow Slides Plugin

Generate beautiful ProPresenter sermon slides directly from Claude—extract verses and points from your sermon documents automatically, then render them with intelligent typography.

## What It Does

- **Upload sermon documents** (Word or PDF) → Claude extracts yellow-highlighted verses and points
- **Ask for verses naturally** → "Give me all of Romans 8" → slides generated instantly
- **Automatic rendering** → Respects ProPresenter bounds, handles text wrapping, applies sermon point styling
- **Organized output** → All slides saved to a dated folder on your Desktop

## Installation

### Prerequisites

- Claude desktop app with plugin support
- SermonFlow Slides package installed on your system:
  ```bash
  pip install sermonflow-slides
  ```

### Add the Plugin

1. Download the `.plugin` file
2. Open Claude desktop app → Settings → Plugins
3. Click "Add Plugin" and select the `.plugin` file
4. Claude will extract and enable the plugin

## Usage

### From a Sermon Document

1. Upload your sermon Word doc or PDF to Claude
2. Claude will automatically extract highlighted content
3. Confirm the verses/points look right
4. Slides render and save to `Desktop/sermonflow-slides-[date]/`

### From Natural Language

Just ask:
- "Generate slides for Romans 8"
- "Make me a slide deck of 1 John 1-3"
- "Create sermon point slides for: Jesus is Lord, He rose from death, We are redeemed"

## Highlight Rules

- **Yellow highlights** in your document = content to extract
- **Verses** (text with book names like "John", "Romans") → rendered as verse slides (one per verse)
- **Points** (your own text/phrases) → rendered as sermon points with bold emphasis
- Plain text (non-highlighted) is ignored

## Output

Slides are saved to:
```
~/Desktop/sermonflow-slides-YYYY-MM-DD_HH-MM/
```

Each slide is a ProPresenter-ready PNG file ready to import.

## Supported Bible Versions

- ESV (English Standard Version, default)
- Other versions available—ask Claude to specify a different one

## Troubleshooting

**"I can't extract highlights from this PDF"**
- Try uploading as a Word document instead
- Or paste the verses/points directly as text

**"The text doesn't fit on the slide"**
- The code automatically wraps text to fit. If it's too crowded, break your content into smaller chunks (fewer verses per slide, shorter points).

**"Where did my slides go?"**
- Check `~/Desktop/` for a folder named `sermonflow-slides-[date-time]/`

## Tips

- **One yellow highlight per idea** → Cleaner extraction and more usable slides
- **Serif fonts for verses, sans-serif for points** → Already built in; no configuration needed
- **Presets for different point styles** → Available as you level up; ask Claude what's available

## Questions or Issues?

Reach out to Jacob Vardi or your church tech team.
