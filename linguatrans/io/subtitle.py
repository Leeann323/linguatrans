"""生成字幕文件：软字幕用的 srt 与 ass。

ass 用于硬字幕烧录，可精确控制中英两行的字体、颜色和位置；
srt 用于软字幕或外挂，兼容性最好。
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path

from ..core.model import Project, SegmentKind


def default_font() -> str:
    """按平台给出一个自带中英文的字体名。"""
    if platform.system() == "Windows":
        return "Microsoft YaHei"
    return "Noto Sans CJK SC"


@dataclass
class SubtitleStyle:
    """字幕样式。"""

    font: str = ""
    en_size: int = 34
    zh_size: int = 38
    en_color: str = "&H00FFFFFF"   # 白
    zh_color: str = "&H0000FFFF"   # 黄
    outline: int = 2
    margin_v: int = 30
    play_res_x: int = 1920
    play_res_y: int = 1080

    def __post_init__(self):
        if not self.font:
            self.font = default_font()


def _ts_srt(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_ass(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def caption_segments(project: Project):
    """取出带时间轴的片段，并保证时间递增且不重叠。"""
    segs = [s for s in project.segments if s.kind == SegmentKind.CAPTION]
    fixed = []
    prev_end = 0.0
    for s in segs:
        start = max(s.start, prev_end)
        end = max(s.end, start + 0.4)
        fixed.append((start, end, s))
        prev_end = end
    return fixed


def to_srt(project: Project, bilingual: bool = True) -> str:
    """生成 srt。bilingual 为真时每个时间轴内先原文后译文。"""
    blocks: list[str] = []
    for i, (start, end, seg) in enumerate(caption_segments(project), start=1):
        lines = [seg.source.strip()]
        if bilingual and seg.target.strip():
            lines.append(seg.target.strip())
        text = "\n".join(l for l in lines if l)
        blocks.append(f"{i}\n{_ts_srt(start)} --> {_ts_srt(end)}\n{text}\n")
    return "\n".join(blocks)


def to_ass(project: Project, style: SubtitleStyle | None = None,
           bilingual: bool = True) -> str:
    """生成 ass，中英两行上下排布。"""
    st = style or SubtitleStyle()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {st.play_res_x}
PlayResY: {st.play_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: EN,{st.font},{st.en_size},{st.en_color},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{st.outline},0,2,30,30,{st.margin_v + st.zh_size + 12},1
Style: ZH,{st.font},{st.zh_size},{st.zh_color},&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{st.outline},0,2,30,30,{st.margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    events: list[str] = []
    for start, end, seg in caption_segments(project):
        en = _ass_escape(seg.source.strip())
        zh = _ass_escape(seg.target.strip())
        if bilingual and zh:
            text = f"{{\\rEN}}{en}\\N{{\\rZH}}{zh}"
        else:
            text = f"{{\\rEN}}{en}"
        events.append(
            f"Dialogue: 0,{_ts_ass(start)},{_ts_ass(end)},EN,,0,0,0,,{text}"
        )
    return header + "\n".join(events) + "\n"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_subtitles(project: Project, out_dir: str | Path,
                    style: SubtitleStyle | None = None,
                    bilingual: bool = True) -> dict[str, str]:
    """把 srt 与 ass 都写到目录，返回两种格式的路径。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(project.name)
    srt_path = out_dir / f"{stem}.srt"
    ass_path = out_dir / f"{stem}.ass"
    srt_path.write_text(to_srt(project, bilingual), encoding="utf-8")
    ass_path.write_text(to_ass(project, style, bilingual), encoding="utf-8")
    return {"srt": str(srt_path), "ass": str(ass_path)}


def _safe_stem(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in name).strip() or "subtitle"
    return out
