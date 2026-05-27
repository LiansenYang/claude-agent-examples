---
name: word-to-ppt
description: Convert Microsoft Word documents (.docx) to PowerPoint presentations (.pptx). Use when the user wants to transform a Word file into slides, generate a presentation from a document, or auto-create PPT from structured text. Triggers on phrases like "word to ppt", "convert docx to pptx", "word转PPT", "文档转幻灯片", "generate slides from word".
---

# Word to Ppt

Convert a `.docx` file into a `.pptx` presentation using the bundled `word_to_ppt.py` script.

## Quick Start

```bash
python scripts/word_to_ppt.py input.docx output.pptx --style default
```

If `output.pptx` is omitted, the script uses the input filename with a `.pptx` extension.

## Workflow

1. **Validate input** — Confirm the input file exists and is a `.docx` file.
2. **Choose style** — Pick a visual preset (see below). Default is `default` (dark navy).
3. **Run conversion** — Execute the script.
4. **Report result** — Tell the user the output path and slide count.

## Document Structure → Slide Mapping

The script parses Word heading styles to determine slide layout:

| Word Element | PowerPoint Result |
|---|---|
| **Heading 1** (or 标题 1) | Starts a new slide; text becomes the slide title |
| **Heading 2+** (or 标题 2+) | Bullet point (indent level = heading level − 1) |
| **Normal paragraphs** | Bullet point at level 0 |
| **First Heading 1** | Title slide (large centered title + subtitle) |

### Tips for Best Results

- Use **Heading 1** to separate sections → each becomes one slide.
- Use **Heading 2/3** for sub-points → nested bullets.
- Keep body text concise; long paragraphs don't translate well to slides.
- If the document has no headings, the entire content becomes a single title slide.

## Style Presets

| Preset | Background | Title | Accent | Best For |
|---|---|---|---|---|
| `default` | Dark navy `#1B1B2F` | White | Teal `#4EC9B0` | General purpose, modern |
| `minimal` | White `#FFFFFF` | Near-black | Red `#CC0000` | Clean, print-friendly |
| `title-content` | Corporate blue `#003366` | White | Gold `#FFCC00` | Business presentations |

Override with `--style <name>`.

## Dependencies

Both are auto-installed if missing:

```bash
pip install python-docx python-pptx
```

## Advanced

- **Custom scripts**: Modify `scripts/word_to_ppt.py` directly for custom layouts, branding, or additional slide types.
- **Batch conversion**: Loop over multiple files in a shell script or Python wrapper.
- **Post-processing**: After generation, open the `.pptx` in PowerPoint/Google Slides for manual adjustments.