"""翻译会话：管理“当前翻译到哪一句”以及提交、回退、跳转。

把逐句推进的逻辑从界面里抽出来，好处是可以脱离图形界面单独测试，
界面只负责把用户输入交给它，再把结果画出来。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .model import Project, Segment
from .store import ProjectStore


@dataclass
class SessionStats:
    """一次会话的统计。"""

    total: int = 0
    done: int = 0
    current: int = 0
    remaining: int = 0

    @property
    def percent(self) -> float:
        return (self.done / self.total * 100.0) if self.total else 0.0


class TranslationSession:
    """驱动逐句翻译的过程。"""

    def __init__(self, project: Project, store: ProjectStore | None = None,
                 autosave_every: int = 1):
        self.project = project
        self.store = store
        self.autosave_every = max(1, autosave_every)
        self._since_save = 0
        # 从第一个未翻译的句子开始，支持断点续传
        first = project.first_untranslated()
        self.index = first if first >= 0 else 0

    # ---------- 查询 ----------

    @property
    def current(self) -> Segment | None:
        if 0 <= self.index < len(self.project.segments):
            return self.project.segments[self.index]
        return None

    @property
    def finished(self) -> bool:
        return self.project.first_untranslated() < 0

    def stats(self) -> SessionStats:
        return SessionStats(
            total=self.project.total,
            done=self.project.done,
            current=self.index,
            remaining=self.project.total - self.project.done,
        )

    def context(self, before: int = 1, after: int = 1) -> list[Segment]:
        """取当前句前后的若干句，界面上做上下文参考。"""
        lo = max(0, self.index - before)
        hi = min(len(self.project.segments), self.index + after + 1)
        return self.project.segments[lo:hi]

    # ---------- 修改 ----------

    def commit(self, text: str, advance: bool = True) -> Segment | None:
        """写入当前句的译文。advance 为真时自动前进到下一句。"""
        seg = self.current
        if seg is None:
            return None
        seg.target = text.strip()
        self._after_change()
        if advance:
            self.advance()
        return seg

    def skip(self) -> Segment | None:
        """跳过当前句，不清空已有译文。"""
        seg = self.current
        self.advance()
        return seg

    def clear_current(self) -> None:
        seg = self.current
        if seg is not None:
            seg.target = ""
            self._after_change()

    def advance(self) -> int:
        """前进到下一句，到末尾则停在末尾。

        不回绕到前面的未译句，那样在逐句翻译时会让人迷惑；
        需要跳到未译句请用 jump_to_next_untranslated。
        """
        if self.index < len(self.project.segments) - 1:
            self.index += 1
        return self.index

    def back(self) -> int:
        if self.index > 0:
            self.index -= 1
        return self.index

    def jump(self, index: int) -> int:
        if 0 <= index < len(self.project.segments):
            self.index = index
        return self.index

    def jump_to_next_untranslated(self) -> int:
        nxt = self.project.first_untranslated()
        if nxt >= 0:
            self.index = nxt
        return self.index

    # ---------- 保存 ----------

    def _after_change(self) -> None:
        self._since_save += 1
        if self.store is not None and self._since_save >= self.autosave_every:
            self.save()

    def save(self) -> None:
        if self.store is not None:
            self.store.save(self.project)
            self._since_save = 0

    # ---------- 批量操作 ----------

    def fill_untranslated(self, text: str) -> int:
        """把所有空白译文填成同一段文字，用于占位或统一署名。"""
        n = 0
        for seg in self.project.segments:
            if not seg.translated:
                seg.target = text
                n += 1
        self._after_change()
        return n

    def clear_all(self) -> None:
        for seg in self.project.segments:
            seg.target = ""
        self._after_change()

    def export_pairs(self) -> list[tuple[str, str]]:
        """导出原文译文配对，供外部使用。"""
        return [(s.source, s.target) for s in self.project.segments]
