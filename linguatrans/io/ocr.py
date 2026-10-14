"""屏幕取词与图片文字识别。

两种取词方式：
    全屏识别    整屏或整图交给 OCR
    手动框选    只识别用户框出的矩形区域

识别结果按纵坐标聚类成行，再按纵坐标间隔合并成段落，便于逐句翻译。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core.model import Segment, SegmentKind

_ENGINE = None


def _engine():
    """惰性加载 OCR 引擎，首次调用会初始化模型。"""
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


@dataclass
class OcrLine:
    """OCR 得到的一行文字。"""

    text: str
    score: float
    x: float
    y: float
    height: float


def read_image(path: str | Path, box: tuple[int, int, int, int] | None = None) -> list[OcrLine]:
    """识别一张图片，box 为 (left, top, right, bottom)，None 表示整图。"""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    if box is not None:
        img = img.crop(box)
    return read_array(np.array(img))


def read_array(arr: np.ndarray) -> list[OcrLine]:
    """识别一个 RGB 数组。"""
    result, _ = _engine()(arr)
    lines: list[OcrLine] = []
    if not result:
        return lines
    for box, text, score in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        lines.append(
            OcrLine(
                text=str(text).strip(),
                score=float(score),
                x=float(min(xs)),
                y=float(min(ys)),
                height=float(max(ys) - min(ys)),
            )
        )
    return sort_lines(lines)


def sort_lines(lines: list[OcrLine]) -> list[OcrLine]:
    """按阅读顺序排序：先按纵坐标分行，同一行内按横坐标。"""
    if not lines:
        return []
    avg_h = sum(l.height for l in lines) / len(lines)
    tol = max(6.0, avg_h * 0.6)
    ordered = sorted(lines, key=lambda l: l.y)
    rows: list[list[OcrLine]] = []
    for line in ordered:
        if rows and abs(line.y - rows[-1][0].y) <= tol:
            rows[-1].append(line)
        else:
            rows.append([line])
    out: list[OcrLine] = []
    for row in rows:
        out.extend(sorted(row, key=lambda l: l.x))
    return out


def lines_to_segments(lines: list[OcrLine], merge_paragraphs: bool = True) -> list[Segment]:
    """把识别行转成待翻译片段。同一段落内的相邻行会合并。"""
    if not lines:
        return []
    avg_h = sum(l.height for l in lines) / len(lines)
    gap = avg_h * 1.8

    groups: list[list[OcrLine]] = [[lines[0]]]
    for prev, cur in zip(lines, lines[1:]):
        # 行距明显变大，或上一行以句末标点收尾，都视为换段
        new_para = (cur.y - prev.y) > gap or prev.text.rstrip().endswith((".", "!", "?", "。", "！", "？"))
        if merge_paragraphs and not new_para:
            groups[-1].append(cur)
        else:
            groups.append([cur])

    segments: list[Segment] = []
    for group in groups:
        text = join_lines([g.text for g in group])
        if text:
            segments.append(Segment(index=0, source=text, kind=SegmentKind.LINE))
    for i, seg in enumerate(segments):
        seg.index = i
    return segments


def join_lines(texts: list[str]) -> str:
    """把多行合成一段。中文行直接接，英文行之间补空格。"""
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        if _is_cjk(out[-1]) or _is_cjk(t[0]):
            out += t
        else:
            out += " " + t
    return out


def _is_cjk(ch: str) -> bool:
    return "\u3000" <= ch <= "\u9fff"
