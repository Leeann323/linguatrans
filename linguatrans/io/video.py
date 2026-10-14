"""视频字幕处理：硬字幕烧录与软字幕输出。

硬字幕把字幕画进画面，任何播放器都能看，代价是重新编码、画质有损。
软字幕只生成外挂字幕文件，画质无损，播放器需支持。
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.model import Project
from .asr import ensure_ffmpeg, probe_duration
from .subtitle import SubtitleStyle, to_ass, write_subtitles


class BurnError(RuntimeError):
    """烧录失败。"""


@dataclass
class BurnOptions:
    """烧录参数。"""

    crf: int = 20              # 画质，越小越好，18 到 23 较常用
    preset: str = "medium"     # 编码速度与压缩率权衡
    audio_copy: bool = True    # 尽量直接复制音轨
    progress_cb: object = None  # 可选回调，接收 0 到 100 的进度


def _escape_for_filter(path: str) -> str:
    """ffmpeg 滤镜里的路径需要转义冒号和反斜杠。"""
    p = str(path).replace("\\", "/")
    p = p.replace(":", "\\:")
    return p


def burn_subtitles(
    video: str | Path,
    project: Project,
    out_path: str | Path,
    style: SubtitleStyle | None = None,
    bilingual: bool = True,
    options: BurnOptions | None = None,
    work_dir: str | Path | None = None,
) -> Path:
    """把字幕烧进视频，返回输出文件路径。"""
    ensure_ffmpeg()
    opts = options or BurnOptions()
    video = Path(video)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fonts_dir = _fonts_dir(style)

    if work_dir:
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        ass_path = work / "_burn.ass"
        ass_path.write_text(to_ass(project, style, bilingual), encoding="utf-8")
        try:
            return _run_burn(video, out_path, ass_path, fonts_dir, opts)
        finally:
            ass_path.unlink(missing_ok=True)

    # 未指定工作目录时用临时目录，跑完删掉，不在用户文件里留垃圾
    with tempfile.TemporaryDirectory(prefix="linguatrans-burn-") as tmp:
        ass_path = Path(tmp) / "burn.ass"
        ass_path.write_text(to_ass(project, style, bilingual), encoding="utf-8")
        return _run_burn(video, out_path, ass_path, fonts_dir, opts)


def _run_burn(video: Path, out_path: Path, ass_path: Path,
              fonts_dir: str | None, opts: BurnOptions) -> Path:
    vf = f"subtitles='{_escape_for_filter(str(ass_path))}'"
    if fonts_dir:
        vf += f":fontsdir='{_escape_for_filter(fonts_dir)}'"

    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-vf", vf,
        "-c:v", "libx264", "-crf", str(opts.crf), "-preset", opts.preset,
        "-pix_fmt", "yuv420p",
    ]
    if opts.audio_copy:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd.append(str(out_path))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-800:]
        raise BurnError(f"字幕烧录失败：\n{tail}")
    return out_path


def _fonts_dir(style: SubtitleStyle | None) -> str | None:
    """给出字体目录，让 libass 能找到中文字体。"""
    from pathlib import Path as _P

    candidates = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        str(_P.home() / ".fonts"),
    ]
    for c in candidates:
        if _P(c).exists():
            return c
    return None


def export_soft_subtitles(video: str | Path, project: Project,
                          out_dir: str | Path,
                          style: SubtitleStyle | None = None,
                          bilingual: bool = True) -> dict[str, str]:
    """只导出字幕文件，不动视频。"""
    return write_subtitles(project, out_dir, style, bilingual)


def estimate_burn_time(video: str | Path) -> float:
    """粗略估计烧录耗时，用于界面提示。经验值约为时长的 0.6 倍。"""
    return probe_duration(video) * 0.6
