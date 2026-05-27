#!/usr/bin/env python3
"""
word_to_ppt.py — Convert a Word (.docx) document to a PowerPoint (.pptx) presentation.

Usage:
    python word_to_ppt.py <input.docx> [output.pptx] [--style default|minimal|title-content] [--ai]

Slides are split on Heading 1 paragraphs. Each Heading 1 starts a new slide;
its Heading 2+ children become bullet points. Title slides use the document's
first Heading 1 (or filename) as the main title.

Dependencies:
    pip install python-docx python-pptx openai
"""

import argparse
import os
import sys
import json
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# ── Style presets ──────────────────────────────────────────────────────────

STYLES = {
    "default": {
        "bg_color": RGBColor(0x1B, 0x1B, 0x2F),        # dark navy
        "title_color": RGBColor(0xFF, 0xFF, 0xFF),       # white
        "body_color": RGBColor(0xE0, 0xE0, 0xE0),         # light gray
        "accent_color": RGBColor(0x4E, 0xC9, 0xB0),       # teal
        "title_font": "Calibri Light",
        "body_font": "Calibri",
        "title_size": Pt(32),
        "body_size": Pt(18),
        "slide_width": Inches(13.333),
        "slide_height": Inches(7.5),
    },
    "minimal": {
        "bg_color": RGBColor(0xFF, 0xFF, 0xFF),           # white
        "title_color": RGBColor(0x22, 0x22, 0x22),        # near-black
        "body_color": RGBColor(0x55, 0x55, 0x55),         # gray
        "accent_color": RGBColor(0xCC, 0x00, 0x00),       # red
        "title_font": "Arial",
        "body_font": "Arial",
        "title_size": Pt(30),
        "body_size": Pt(17),
        "slide_width": Inches(13.333),
        "slide_height": Inches(7.5),
    },
    "title-content": {
        "bg_color": RGBColor(0x00, 0x33, 0x66),           # corporate blue
        "title_color": RGBColor(0xFF, 0xFF, 0xFF),
        "body_color": RGBColor(0xDD, 0xDD, 0xDD),
        "accent_color": RGBColor(0xFF, 0xCC, 0x00),       # gold
        "title_font": "Cambria",
        "body_font": "Calibri",
        "title_size": Pt(34),
        "body_size": Pt(18),
        "slide_width": Inches(13.333),
        "slide_height": Inches(7.5),
    },
}

# ── AI Summarization ────────────────────────────────────────────────────────

def summarize_with_ai(title: str, text_content: list[str]) -> list[tuple]:
    """Use LLM to summarize long text into crisp bullet points."""
    try:
        from dotenv import load_dotenv
        import anthropic
        load_dotenv()
        
        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "dummy"),
            base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            default_headers={"Authorization": f"Bearer {os.environ.get('ANTHROPIC_API_KEY', '')}"}
        )
        
        full_text = "\n".join(text_content)
        prompt = f"""
        请将以下长文本精简为幻灯片(PPT)的核心要点(Bullet Points)。
        当前页面的标题是：{title}
        
        要求：
        1. 必须提炼为 3 到 5 个核心短句，每个短句不要超过 30 个字。
        2. 删除所有的冗余废话，只保留干货。
        3. 请直接输出 JSON 数组格式的字符串，例如：["要点1", "要点2"]。不要包含任何 markdown 代码块标记。
        
        待处理文本：
        {full_text}
        """
        
        response = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        content = response.content[0].text.strip()
        if content.startswith("```"):
            content = content.split('\n', 1)[1]
            if content.rfind("```") != -1:
                content = content[:content.rfind("```")].strip()
        
        bullets = json.loads(content)
        if isinstance(bullets, list):
            return [(2, str(b)) for b in bullets]
    except Exception as e:
        print(f"[Warning] AI 总结失败 ({e})，将回退到普通分页模式。")
    return None


# ── Parsing ─────────────────────────────────────────────────────────────────

def parse_docx(path: str, use_ai: bool = False) -> list[dict]:
    """
    Parse a .docx file into a list of slide-dicts.
    """
    doc = Document(path)
    slides: list[dict] = []
    current: dict | None = None

    raw_blocks = []
    for para in paras_in_order(doc):
        style = para.style.name.lower()
        text = para.text.strip()
        if text:
            raw_blocks.append((style, text))

    for style, text in raw_blocks:
        if "heading 1" in style or "标题 1" in style or "标题1" in style:
            # Start a new slide
            if current is not None:
                _finalize_slide(current, slides, use_ai)
            current = {"title": text, "bullets": [], "raw_text": [], "is_title_slide": len(slides) == 0}
        elif current is not None:
            # Treat any non-Heading-1 as bullet content
            level = None
            for token in ("heading", "标题"):
                if token in style:
                    parts = style.replace(token, "").strip()
                    try:
                        level = int(parts)
                    except ValueError:
                        level = 2
                    break

            if level is None or level < 2:
                level = 2
            
            current["bullets"].append((level, text))
            current["raw_text"].append(text)
        else:
            # Content before any Heading 1 — create an implicit title slide
            current = {"title": text, "bullets": [], "raw_text": [], "is_title_slide": True}

    if current is not None:
        _finalize_slide(current, slides, use_ai)

    return slides

def _finalize_slide(current: dict, slides: list[dict], use_ai: bool):
    MAX_BULLETS = 5
    MAX_CHARS = 100
    
    if not current["bullets"]:
        slides.append(current)
        return
        
    if use_ai and current["raw_text"]:
        print(f"[AI] 正在用 AI 智能总结幻灯片: {current['title']}")
        ai_bullets = summarize_with_ai(current["title"], current["raw_text"])
        if ai_bullets:
            current["bullets"] = ai_bullets
            slides.append(current)
            return

    # Fallback pagination logic
    final_bullets = []
    for lvl, text in current["bullets"]:
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "..."
        final_bullets.append((lvl, text))
        
    chunks = [final_bullets[i:i + MAX_BULLETS] for i in range(0, len(final_bullets), MAX_BULLETS)]
    for idx, chunk in enumerate(chunks):
        title = current["title"]
        if idx > 0:
            title += " (续)"
        slides.append({
            "title": title,
            "bullets": chunk,
            "is_title_slide": current["is_title_slide"] and idx == 0
        })


def paras_in_order(doc):
    """Yield paragraphs in visual order (including tables, if any)."""
    from docx.oxml.ns import qn

    body = doc.element.body
    for child in body:
        if child.tag == qn("w:p"):
            yield ParagraphProxy(child, doc)
        elif child.tag == qn("w:tbl"):
            for row in child.iter(qn("w:tr")):
                for cell in row.iter(qn("w:tc")):
                    for p in cell.iter(qn("w:p")):
                        yield ParagraphProxy(p, doc)


class ParagraphProxy:
    """Minimal proxy so we can iterate mixed paragraphs from body."""

    def __init__(self, element, doc):
        self._element = element
        self._doc = doc
        # Build a temp Paragraph-like object to reuse style resolution
        from docx.text.paragraph import Paragraph
        self._para = Paragraph(element, doc)

    @property
    def text(self):
        return self._para.text

    @property
    def style(self):
        return self._para.style

    @property
    def alignment(self):
        return self._para.alignment


# ── Slide building ──────────────────────────────────────────────────────────

def build_pptx(slides: list[dict], output_path: str, style_name: str = "default"):
    """Build a .pptx from parsed slide data."""
    style = STYLES.get(style_name, STYLES["default"])
    prs = Presentation()
    prs.slide_width = style["slide_width"]
    prs.slide_height = style["slide_height"]

    for i, slide_data in enumerate(slides):
        if slide_data["is_title_slide"] and i == 0:
            _add_title_slide(prs, slide_data, style)
        else:
            _add_content_slide(prs, slide_data, style, i + 1, len(slides))

    prs.save(output_path)
    print(f"[Success] Saved: {output_path}  ({len(slides)} slides)")


def _set_bg(slide, color: RGBColor):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_title_slide(prs, data: dict, style: dict):
    layout = prs.slide_layouts[0]  # Title Slide
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, style["bg_color"])

    title_shape = slide.shapes.title
    title_shape.text_frame.paragraphs[0].text = data["title"]
    for run in title_shape.text_frame.paragraphs[0].runs:
        run.font.size = style["title_size"]
        run.font.color.rgb = style["accent_color"]
        run.font.name = style["title_font"]
        run.font.bold = True

    # Subtitle / first bullet(s)
    if slide.placeholders.__len__() > 1:
        subtitle = slide.placeholders[1]
        bullets_text = "\n".join(t for _, t in data["bullets"][:5])
        if bullets_text:
            subtitle.text = bullets_text


def _add_content_slide(prs, data: dict, style: dict, page_num: int, total: int):
    layout = prs.slide_layouts[1]  # Title + Content
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, style["bg_color"])

    # Title
    title_shape = slide.shapes.title
    title_shape.text_frame.paragraphs[0].text = data["title"]
    for run in title_shape.text_frame.paragraphs[0].runs:
        run.font.size = style["title_size"]
        run.font.color.rgb = style["title_color"]
        run.font.name = style["title_font"]

    # Body bullets
    body = slide.placeholders[1]
    tf = body.text_frame
    tf.word_wrap = True

    bullets = data["bullets"]
    for idx, (level, text) in enumerate(bullets):
        if idx == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()

        p.text = text
        p.level = min(level - 1, 4)  # 0-indexed
        for run in p.runs:
            run.font.size = style["body_size"]
            run.font.color.rgb = style["body_color"]
            run.font.name = style["body_font"]

    # Footer page number
    txBox = slide.shapes.add_textbox(
        Inches(12.0), Inches(7.0), Inches(1.2), Inches(0.4)
    )
    tf_footer = txBox.text_frame
    p_footer = tf_footer.paragraphs[0]
    p_footer.text = f"{page_num} / {total}"
    p_footer.font.size = Pt(10)
    p_footer.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
    p_footer.alignment = PP_ALIGN.RIGHT


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert a Word document (.docx) to a PowerPoint presentation (.pptx)."
    )
    parser.add_argument("input", help="Path to input .docx file")
    parser.add_argument(
        "output", nargs="?",
        help="Path to output .pptx file (default: same name, .pptx extension)"
    )
    parser.add_argument(
        "--style", choices=list(STYLES.keys()), default="default",
        help="Visual style preset (default: default)"
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="Use OpenAI to smartly summarize long text into crisp bullet points."
    )
    args = parser.parse_args()

    input_path = args.input
    if not os.path.isfile(input_path):
        print(f"[Error] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        output_path = Path(input_path).with_suffix(".pptx")

    slides = parse_docx(input_path, use_ai=args.ai)
    if not slides:
        print("[Warning] No content found in the document.", file=sys.stderr)
        sys.exit(1)

    build_pptx(slides, str(output_path), args.style)


if __name__ == "__main__":
    main()