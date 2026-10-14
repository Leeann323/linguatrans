"""后台任务线程。

语音识别和字幕烧录都很耗时，跑在主线程会让界面卡住不动。
这里用 QThread 把它们挪到后台，通过信号把结果和进度送回界面。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.model import Project
from ..io import asr, video


class TranscribeWorker(QThread):
    """语音识别后台任务。"""

    finished_ok = Signal(list, str)     # (caption 列表, 检测到的语言)
    failed = Signal(str)

    def __init__(self, path: str | Path, model_name: str,
                 language: str | None = None):
        super().__init__()
        self.path = path
        self.model_name = model_name
        self.language = language

    def run(self) -> None:
        try:
            caps, lang = asr.transcribe(self.path, self.model_name, self.language)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(caps, lang)


class BurnWorker(QThread):
    """字幕烧录后台任务。"""

    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, video_path: str | Path, project: Project,
                 out_path: str | Path, style=None, bilingual: bool = True):
        super().__init__()
        self.video_path = video_path
        self.project = project
        self.out_path = out_path
        self.style = style
        self.bilingual = bilingual

    def run(self) -> None:
        try:
            path = video.burn_subtitles(
                self.video_path, self.project, self.out_path,
                self.style, self.bilingual,
            )
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.finished_ok.emit(str(path))
