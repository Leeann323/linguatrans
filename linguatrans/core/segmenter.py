"""把原文切分成适合逐句翻译的片段。

英文按句末标点切，遇到缩写和常见省略要避免误切；中文按句号、问号、
叹号、分号切。段落切分与句子切分分开，段落用于控制 Word 排版。
"""

from __future__ import annotations

import re

# 常见英文缩写，句点不算句末
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "fig", "no", "vol", "al", "inc", "ltd", "co", "corp",
    "u.s", "u.k", "a.m", "p.m", "ph.d", "b.c", "a.d",
}

_SENT_END = re.compile(r"(?<=[.!?])\s+")
_ZH_END = re.compile(r"(?<=[。！？；])\s*")


def split_paragraphs(text: str) -> list[str]:
    """按空行切段落，去掉首尾空白，丢弃空段。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _is_abbrev(token: str) -> bool:
    t = token.rstrip(".").lower()
    if t in _ABBREV:
        return True
    # 单个大写字母加句点，如 "J." 或 "A."，通常是姓名缩写
    if len(t) == 1 and t.isalpha():
        return True
    # 多字母缩写如 "U.S." 内部还有点
    if re.fullmatch(r"(?:[a-z]\.){2,}", token.lower()):
        return True
    return False


def split_sentences(paragraph: str, lang: str = "en") -> list[str]:
    """把一段文字切成句子。lang 为 zh 时按中文标点切。"""
    paragraph = paragraph.strip()
    if not paragraph:
        return []

    if lang.startswith("zh"):
        raw = [s.strip() for s in _ZH_END.split(paragraph) if s.strip()]
        return raw

    pieces = _SENT_END.split(paragraph)
    sentences: list[str] = []
    buf = ""
    for piece in pieces:
        candidate = (buf + " " + piece).strip() if buf else piece
        # 若这一段以缩写结尾，说明句点不是句末，继续攒
        last_token = candidate.split()[-1] if candidate.split() else ""
        if last_token.endswith(".") and _is_abbrev(last_token):
            buf = candidate
            continue
        sentences.append(candidate)
        buf = ""
    if buf:
        sentences.append(buf)
    return [s for s in sentences if s]


def split_text(text: str, lang: str = "en", by_sentence: bool = True) -> list[str]:
    """总入口：先切段，再按需切句。"""
    out: list[str] = []
    for para in split_paragraphs(text):
        if by_sentence:
            out.extend(split_sentences(para, lang))
        else:
            out.append(para)
    return out
