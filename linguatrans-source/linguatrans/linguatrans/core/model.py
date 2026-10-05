"""内核数据模型。

一篇待翻译的原文被拆成若干 Segment，每个 Segment 是原文与译文的一对，
翻译进度就以“译文是否为空”来衡量。带时间轴的 Segment 用于视频字幕。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any


class MediaKind(str, Enum):
    """项目来源类型。"""

    TEXT = "text"        # 纯文本或 Markdown
    IMAGE = "image"      # 截图识别
    PDF = "pdf"          # PDF 文档
    VIDEO = "video"      # 视频或音频，走语音识别


class SegmentKind(str, Enum):
    """片段的种类。"""

    PARAGRAPH = "paragraph"   # 文档正文段落
    LINE = "line"             # 屏幕取词得到的一行
    CAPTION = "caption"       # 视频字幕句，带时间轴


@dataclass
class ImageAsset:
    """原文中的一张图片，导出时按顺序放回译文文档。"""

    asset_id: str
    filename: str
    order: int
    width: int = 0
    height: int = 0
    caption: str = ""

    @staticmethod
    def new(filename: str, order: int, width: int = 0, height: int = 0) -> "ImageAsset":
        return ImageAsset(
            asset_id=uuid.uuid4().hex[:12],
            filename=filename,
            order=order,
            width=width,
            height=height,
        )


@dataclass
class Segment:
    """原文与译文的一对。"""

    index: int
    source: str
    target: str = ""
    kind: SegmentKind = SegmentKind.PARAGRAPH
    start: float = 0.0          # 视频字幕用，单位秒
    end: float = 0.0
    note: str = ""

    @property
    def translated(self) -> bool:
        return bool(self.target.strip())

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Project:
    """一个翻译项目，可保存到磁盘并断点续传。"""

    name: str = "未命名项目"
    kind: MediaKind = MediaKind.TEXT
    source_lang: str = "en"
    target_lang: str = "zh"
    source_path: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    segments: list[Segment] = field(default_factory=list)
    assets: list[ImageAsset] = field(default_factory=list)
    asset_dir: str = ""
    # 原文在段落之间插入图片的位置：键为段落序号，值为该位置之后的图片 asset_id 列表
    asset_anchors: dict[str, list[str]] = field(default_factory=dict)

    def add_segment(self, source: str, kind: SegmentKind = SegmentKind.PARAGRAPH,
                    start: float = 0.0, end: float = 0.0) -> Segment:
        seg = Segment(
            index=len(self.segments),
            source=source,
            kind=kind,
            start=start,
            end=end,
        )
        self.segments.append(seg)
        return seg

    def add_asset(self, asset: ImageAsset, after_index: int) -> None:
        self.assets.append(asset)
        self.asset_anchors.setdefault(str(after_index), []).append(asset.asset_id)

    def asset_by_id(self, asset_id: str) -> ImageAsset | None:
        for a in self.assets:
            if a.asset_id == asset_id:
                return a
        return None

    @property
    def total(self) -> int:
        return len(self.segments)

    @property
    def done(self) -> int:
        return sum(1 for s in self.segments if s.translated)

    @property
    def progress(self) -> float:
        return self.done / self.total if self.total else 0.0

    def first_untranslated(self) -> int:
        """返回第一个未翻译片段的序号，全部译完则返回 -1。"""
        for s in self.segments:
            if not s.translated:
                return s.index
        return -1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["segments"] = [
            {**asdict(s), "kind": s.kind.value} for s in self.segments
        ]
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Project":
        proj = Project(
            name=d.get("name", "未命名项目"),
            kind=MediaKind(d.get("kind", "text")),
            source_lang=d.get("source_lang", "en"),
            target_lang=d.get("target_lang", "zh"),
            source_path=d.get("source_path", ""),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            asset_dir=d.get("asset_dir", ""),
            asset_anchors={k: list(v) for k, v in d.get("asset_anchors", {}).items()},
        )
        for s in d.get("segments", []):
            proj.segments.append(
                Segment(
                    index=s["index"],
                    source=s["source"],
                    target=s.get("target", ""),
                    kind=SegmentKind(s.get("kind", "paragraph")),
                    start=s.get("start", 0.0),
                    end=s.get("end", 0.0),
                    note=s.get("note", ""),
                )
            )
        for a in d.get("assets", []):
            proj.assets.append(
                ImageAsset(
                    asset_id=a["asset_id"],
                    filename=a["filename"],
                    order=a.get("order", 0),
                    width=a.get("width", 0),
                    height=a.get("height", 0),
                    caption=a.get("caption", ""),
                )
            )
        return proj

    def save(self, path: str | Path) -> None:
        path = Path(path)
        self.updated_at = time.time()
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def load(path: str | Path) -> "Project":
        return Project.from_dict(
            json.loads(Path(path).read_text(encoding="utf-8"))
        )
