"""项目存储：一个项目对应一个目录，内含 project.json 与 assets/。"""

from __future__ import annotations

import shutil
from pathlib import Path

from .model import Project

PROJECT_FILE = "project.json"
ASSET_DIR = "assets"


class ProjectStore:
    """管理项目目录的读写，支持断点续传。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.asset_dir = self.root / ASSET_DIR
        self.asset_dir.mkdir(exist_ok=True)
        self.file = self.root / PROJECT_FILE

    @property
    def exists(self) -> bool:
        return self.file.exists()

    def save(self, project: Project) -> None:
        project.asset_dir = str(self.asset_dir)
        project.save(self.file)

    def load(self) -> Project:
        if not self.exists:
            raise FileNotFoundError(f"项目文件不存在：{self.file}")
        proj = Project.load(self.file)
        if not proj.asset_dir:
            proj.asset_dir = str(self.asset_dir)
        return proj

    def import_asset(self, src: str | Path, name: str) -> Path:
        """把外部图片复制进项目，返回项目内的路径。"""
        src = Path(src)
        dst = self.asset_dir / name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        return dst

    def asset_path(self, filename: str) -> Path:
        return self.asset_dir / filename
