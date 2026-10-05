"""音频解码与语音识别。

注意：faster-whisper 1.2 自带的音频解码会调用 PyAV 已移除的参数，
这里统一先用 ffmpeg 把音轨解成 16k 单声道浮点数组再喂给模型，
既绕开版本冲突，也省去重复解码。

模型按需加载并缓存。默认用 small，用户可在设置里换更大或更小的档。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core.model import Segment, SegmentKind

# 可选模型档位，括号内为大致体积，用于界面提示
MODEL_SIZES = {
    "tiny": "约 75 MB，最快，准确率一般",
    "base": "约 145 MB",
    "small": "约 480 MB，速度与准确率较均衡",
    "medium": "约 1.5 GB，较准",
    "large-v3": "约 3 GB，最准，最慢",
}

DEFAULT_MODEL = "small"
SAMPLE_RATE = 16000

_MODELS: dict[str, object] = {}


class FfmpegMissing(RuntimeError):
    """找不到 ffmpeg 时抛出，界面据此提示用户安装。"""


def ensure_ffmpeg() -> str:
    """确认 ffmpeg 可用并返回路径。"""
    from shutil import which

    path = which("ffmpeg")
    if not path:
        raise FfmpegMissing("未找到 ffmpeg，请先安装后再使用视频与音频功能")
    return path


def decode_audio(path: str | Path) -> np.ndarray:
    """把任意音视频文件解成 16k 单声道 float32 数组。"""
    ensure_ffmpeg()
    cmd = [
        "ffmpeg", "-v", "quiet", "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"音频解码失败：{path}")
    return np.frombuffer(proc.stdout, dtype=np.float32)


def probe_duration(path: str | Path) -> float:
    """读取媒体时长，单位秒。"""
    ensure_ffmpeg()
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def load_model(name: str = DEFAULT_MODEL):
    """按名字加载并缓存模型。"""
    if name not in _MODELS:
        from faster_whisper import WhisperModel

        _MODELS[name] = WhisperModel(name, device="cpu", compute_type="int8")
    return _MODELS[name]


@dataclass
class Caption:
    """一句识别结果。"""

    text: str
    start: float
    end: float


def transcribe(
    path: str | Path,
    model_name: str = DEFAULT_MODEL,
    language: str | None = None,
    split_sentences: bool = True,
) -> tuple[list[Caption], str]:
    """识别音视频中的语音，返回句子列表与检测到的语言。"""
    audio = decode_audio(path)
    if audio.size == 0:
        return [], ""

    model = load_model(model_name)
    segments, info = model.transcribe(
        audio,
        language=language,
        word_timestamps=split_sentences,
        vad_filter=True,
    )

    detected = info.language or ""
    captions: list[Caption] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if split_sentences and getattr(seg, "words", None):
            captions.extend(_split_by_words(seg.words, text))
        else:
            captions.append(Caption(text=text, start=float(seg.start), end=float(seg.end)))
    return captions, detected


def _split_by_words(words, fallback_text: str) -> list[Caption]:
    """利用词级时间戳，把一句话按句末标点切成更细的字幕。"""
    out: list[Caption] = []
    buf: list = []
    for w in words:
        buf.append(w)
        token = w.word.strip()
        if token.endswith((".", "!", "?", "…")):
            text = "".join(x.word for x in buf).strip()
            if text:
                out.append(Caption(text=text, start=float(buf[0].start), end=float(buf[-1].end)))
            buf = []
    if buf:
        text = "".join(x.word for x in buf).strip()
        if text:
            out.append(Caption(text=text, start=float(buf[0].start), end=float(buf[-1].end)))
    if not out:
        out.append(Caption(text=fallback_text, start=0.0, end=0.0))
    return out


def captions_to_segments(captions: list[Caption]) -> list[Segment]:
    """转成项目片段，保留时间轴。"""
    segs: list[Segment] = []
    for i, c in enumerate(captions):
        segs.append(
            Segment(
                index=i,
                source=c.text,
                kind=SegmentKind.CAPTION,
                start=c.start,
                end=c.end,
            )
        )
    return segs
