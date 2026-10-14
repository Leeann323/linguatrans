"""生成测试素材：图片、音频、视频。供测试与演示使用。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent / "assets"

CJK_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def _first_existing(paths: list[str]) -> str | None:
    for p in paths:
        if Path(p).exists():
            return p
    return None


def make_news_image(path: Path | None = None) -> Path:
    """造一张中英混排的模拟新闻图，用于 OCR 测试。"""
    path = path or ASSETS / "news.png"
    path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (900, 320), (255, 255, 255))
    d = ImageDraw.Draw(img)

    zh_path = _first_existing(CJK_CANDIDATES)
    mono_path = _first_existing(MONO_CANDIDATES)
    en = ImageFont.truetype(mono_path, 22) if mono_path else ImageFont.load_default()
    zh = ImageFont.truetype(zh_path, 22) if zh_path else en

    lines = [
        ("Breaking: Global markets rally after policy shift", en),
        ("The central bank announced a surprise rate cut on Tuesday.", en),
        ("全球市场在政策转向后走高", zh),
        ("央行于周二宣布意外降息。", zh),
    ]
    y = 30
    for text, font in lines:
        d.text((30, y), text, font=font, fill=(20, 20, 20))
        y += 50
    img.save(path)
    return path


def make_speech_audio(path: Path | None = None) -> Path:
    """用 espeak-ng 合成英文语音，用于语音识别测试。"""
    path = path or ASSETS / "speech.wav"
    path.parent.mkdir(parents=True, exist_ok=True)

    text = (
        "The central bank announced a surprise rate cut on Tuesday. "
        "Global markets rallied sharply after the news. "
        "Analysts expect inflation to slow next quarter."
    )
    txt = path.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")

    subprocess.run(
        ["espeak-ng", "-v", "en-us", "-s", "140", "-f", str(txt), "-w", str(path)],
        check=True, capture_output=True,
    )
    return path


def make_test_video(path: Path | None = None, seconds: int = 4) -> Path:
    """造一段带音频的测试视频，用于字幕烧录测试。"""
    path = path or ASSETS / "clip.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


if __name__ == "__main__":
    print(make_news_image())
    print(make_speech_audio())
    print(make_test_video())
