"""用户设置：模型档位、字幕样式、导出偏好。存为 JSON。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..io.asr import DEFAULT_MODEL
from ..io.subtitle import SubtitleStyle


def config_dir() -> Path:
    """跨平台的配置目录。"""
    import os
    import sys

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "LinguaTrans"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    """全部可调项。"""

    model_name: str = DEFAULT_MODEL
    source_lang: str = "en"
    target_lang: str = "zh"

    # 字幕
    bilingual: bool = True
    hard_subtitle: bool = True          # 默认硬字幕，用户可改软字幕
    subtitle_font: str = ""
    en_size: int = 34
    zh_size: int = 38
    en_color: str = "&H00FFFFFF"
    zh_color: str = "&H0000FFFF"
    margin_v: int = 30

    # 界面
    overlay_opacity: float = 0.88
    overlay_width: int = 900
    overlay_position: str = "bottom"    # bottom 或 top
    advance_on_enter: bool = True
    autosave_seconds: int = 30

    # 导出
    word_style: str = "bilingual"
    burn_crf: int = 20

    # 最近打开的项目目录
    recent: list[str] = field(default_factory=list)

    @staticmethod
    def load() -> "Settings":
        path = config_dir() / "settings.json"
        if not path.exists():
            return Settings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Settings()
        known = {f for f in Settings.__dataclass_fields__}
        return Settings(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        path = config_dir() / "settings.json"
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def subtitle_style(self) -> SubtitleStyle:
        return SubtitleStyle(
            font=self.subtitle_font,
            en_size=self.en_size,
            zh_size=self.zh_size,
            en_color=self.en_color,
            zh_color=self.zh_color,
            margin_v=self.margin_v,
        )

    def remember(self, project_dir: str) -> None:
        if project_dir in self.recent:
            self.recent.remove(project_dir)
        self.recent.insert(0, project_dir)
        del self.recent[10:]
