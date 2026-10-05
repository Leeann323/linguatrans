"""文档导入：纯文本、Markdown、PDF、图片。

PDF 会同时抽取正文与内嵌图片，并记录图片出现的段落位置，
导出 Word 时按原顺序放回，保证图文对应。
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.model import ImageAsset, MediaKind, Project, SegmentKind
from ..core.segmenter import split_sentences, split_paragraphs
from . import ocr


def import_text(path: str | Path, lang: str = "en",
                by_sentence: bool = True) -> Project:
    """导入纯文本或 Markdown。"""
    path = Path(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".md", ".markdown"):
        raw = strip_markdown(raw)
    proj = Project(name=path.stem, kind=MediaKind.TEXT, source_path=str(path),
                   source_lang=lang)
    for para in split_paragraphs(raw):
        pieces = split_sentences(para, lang) if by_sentence else [para]
        for piece in pieces:
            proj.add_segment(piece, SegmentKind.PARAGRAPH)
    return proj


def strip_markdown(text: str) -> str:
    """去掉 Markdown 标记，保留可翻译的正文。"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)      # 代码块
    text = re.sub(r"`([^`]*)`", r"\1", text)               # 行内代码
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)       # 图片
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # 链接
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)   # 标题
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)        # 引用
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    return text


def import_image(path: str | Path, box: tuple[int, int, int, int] | None = None) -> Project:
    """导入图片，走 OCR 取词。"""
    path = Path(path)
    lines = ocr.read_image(path, box)
    proj = Project(name=path.stem, kind=MediaKind.IMAGE, source_path=str(path))
    for seg in ocr.lines_to_segments(lines):
        proj.add_segment(seg.source, SegmentKind.LINE)
    return proj


def import_pdf(path: str | Path, lang: str = "en",
               by_sentence: bool = True) -> Project:
    """导入 PDF，抽正文与内嵌图片，并记录图片位置。"""
    import pymupdf

    path = Path(path)
    doc = pymupdf.open(path)
    proj = Project(name=path.stem, kind=MediaKind.PDF, source_path=str(path),
                   source_lang=lang)

    asset_counter = 0
    for page_no, page in enumerate(doc):
        text = page.get_text("text")
        for para in split_paragraphs(text):
            pieces = split_sentences(para, lang) if by_sentence else [para]
            for piece in pieces:
                proj.add_segment(piece, SegmentKind.PARAGRAPH)

        # 记录本页图片，锚点放在当前最后一段之后
        images = page.get_images(full=True)
        anchor = len(proj.segments) - 1
        for img in images:
            xref = img[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:      # CMYK 转 RGB
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                asset_counter += 1
                name = f"p{page_no + 1}_img{asset_counter}.png"
                pix.save(str(_asset_tmp(path) / name))
                proj.add_asset(
                    ImageAsset.new(name, asset_counter, pix.width, pix.height),
                    max(anchor, 0),
                )
            except Exception:
                continue
            finally:
                pix = None

    doc.close()
    return proj


def _asset_tmp(pdf_path: Path) -> Path:
    """PDF 图片先落在一个临时目录，稍后由调用方复制进项目。"""
    d = pdf_path.parent / f".{pdf_path.stem}_assets"
    d.mkdir(exist_ok=True)
    return d


def detect_kind(path: str | Path) -> MediaKind:
    """按扩展名判断来源类型。"""
    ext = Path(path).suffix.lower()
    if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts",
               ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"):
        return MediaKind.VIDEO
    if ext == ".pdf":
        return MediaKind.PDF
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
        return MediaKind.IMAGE
    return MediaKind.TEXT


def import_auto(path: str | Path, lang: str = "en",
                by_sentence: bool = True) -> Project:
    """按扩展名自动选择导入方式。"""
    kind = detect_kind(path)
    if kind == MediaKind.IMAGE:
        return import_image(path)
    if kind == MediaKind.PDF:
        return import_pdf(path, lang, by_sentence)
    return import_text(path, lang, by_sentence)
