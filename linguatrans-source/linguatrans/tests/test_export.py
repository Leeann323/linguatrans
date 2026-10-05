"""导出层测试：字幕、Word、视频烧录。这些都不依赖图形界面。"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from linguatrans.core.model import (  # noqa: E402
    ImageAsset, MediaKind, Project, SegmentKind,
)
from linguatrans.core.store import ProjectStore  # noqa: E402
from linguatrans.io import subtitle as sub  # noqa: E402
from linguatrans.io import video as vid  # noqa: E402
from linguatrans.io import word as wd  # noqa: E402

ASSETS = ROOT / "tests" / "assets"


def _caption_project() -> Project:
    proj = Project(name="新闻字幕", kind=MediaKind.VIDEO, source_lang="en")
    proj.add_segment("The central bank cut rates.", SegmentKind.CAPTION, 0.0, 2.5)
    proj.add_segment("Markets rallied after the news.", SegmentKind.CAPTION, 2.5, 5.0)
    proj.add_segment("Analysts expect slower inflation.", SegmentKind.CAPTION, 5.0, 8.0)
    proj.segments[0].target = "央行降息。"
    proj.segments[1].target = "消息公布后市场走高。"
    # 第三句故意留空，检验空译文不会污染字幕
    return proj


def test_srt_format_and_timing():
    proj = _caption_project()
    text = sub.to_srt(proj, bilingual=True)
    assert "1\n00:00:00,000 --> 00:00:02,500" in text
    assert "央行降息。" in text
    assert "The central bank cut rates." in text
    # 未翻译的第三句只出原文
    assert "Analysts expect slower inflation." in text
    assert text.count("-->") == 3


def test_srt_monolingual_excludes_target():
    proj = _caption_project()
    text = sub.to_srt(proj, bilingual=False)
    assert "央行降息。" not in text
    assert "The central bank cut rates." in text


def test_ass_structure_and_bilingual_lines():
    proj = _caption_project()
    text = sub.to_ass(proj, bilingual=True)
    assert "[Script Info]" in text
    assert "[V4+ Styles]" in text
    assert "Style: EN," in text and "Style: ZH," in text
    # 双语用 \N 换行，并切到对应样式
    assert "\\N" in text
    assert "{\\rEN}" in text and "{\\rZH}" in text
    assert text.count("Dialogue:") == 3


def test_ass_escapes_braces():
    proj = Project(name="esc", kind=MediaKind.VIDEO)
    proj.add_segment("a {weird} line", SegmentKind.CAPTION, 0.0, 1.0)
    text = sub.to_ass(proj)
    assert "\\{weird\\}" in text


def test_caption_timing_is_clamped_monotonic():
    proj = Project(name="overlap", kind=MediaKind.VIDEO)
    proj.add_segment("one", SegmentKind.CAPTION, 0.0, 5.0)
    proj.add_segment("two", SegmentKind.CAPTION, 1.0, 2.0)   # 起点早于上一句终点
    fixed = sub.caption_segments(proj)
    assert fixed[0][0] == 0.0
    assert fixed[1][0] >= fixed[0][1], fixed


def test_write_subtitles_creates_both_files(tmp_path):
    proj = _caption_project()
    out = sub.write_subtitles(proj, tmp_path, bilingual=True)
    assert Path(out["srt"]).exists()
    assert Path(out["ass"]).exists()
    assert Path(out["srt"]).read_text(encoding="utf-8").startswith("1\n")


def test_word_export_bilingual(tmp_path):
    proj = _caption_project()
    out = wd.export_word(proj, tmp_path / "out.docx", style="bilingual")
    assert out.exists() and out.stat().st_size > 0

    from docx import Document

    doc = Document(str(out))
    body = "\n".join(p.text for p in doc.paragraphs)
    assert "The central bank cut rates." in body
    assert "央行降息。" in body
    assert "[00:00 - 00:02]" in body     # 时间码
    assert "新闻字幕" in body


def test_word_export_target_only(tmp_path):
    proj = _caption_project()
    out = wd.export_word(proj, tmp_path / "target.docx", style="target")
    from docx import Document

    body = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "央行降息。" in body
    assert "The central bank cut rates." not in body


def test_word_keeps_images_in_order(tmp_path):
    proj = Project(name="图文", kind=MediaKind.PDF)
    proj.add_segment("Paragraph one.")
    proj.add_segment("Paragraph two.")

    store = ProjectStore(tmp_path / "proj")
    # 造两张可嵌入的图片
    from PIL import Image

    for i, (w, h) in enumerate([(300, 200), (200, 300)], start=1):
        p = store.asset_dir / f"img{i}.png"
        Image.new("RGB", (w, h), (30 * i, 60, 90)).save(p)
        proj.add_asset(ImageAsset.new(f"img{i}.png", i, w, h), after_index=i - 1)
    store.save(proj)

    out = wd.export_word(proj, tmp_path / "doc.docx", style="bilingual",
                         asset_dir=store.asset_dir)
    from docx import Document

    doc = Document(str(out))
    assert len(doc.inline_shapes) == 2, "两张图片都应嵌入"
    # 图片应出现在对应段落之后
    texts = [p.text for p in doc.paragraphs]
    assert texts.index("Paragraph one.") < texts.index("Paragraph two.")


def test_word_skips_missing_image(tmp_path):
    proj = Project(name="缺图", kind=MediaKind.PDF)
    proj.add_segment("Only paragraph.")
    proj.add_asset(ImageAsset.new("not_there.png", 1, 100, 100), after_index=0)
    store = ProjectStore(tmp_path / "p")
    store.save(proj)
    out = wd.export_word(proj, tmp_path / "d.docx", asset_dir=store.asset_dir)
    from docx import Document

    assert len(Document(str(out)).inline_shapes) == 0


@pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists(), reason="需要 ffmpeg")
def test_burn_subtitles_produces_video(tmp_path):
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频素材")

    proj = _caption_project()
    out = vid.burn_subtitles(clip, proj, tmp_path / "burned.mp4", bilingual=True)
    assert out.exists()
    assert out.stat().st_size > 0

    # 用 ffprobe 确认输出可解析且有视频流
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "default=noprint_wrappers=1", str(out)],
        capture_output=True, text=True,
    )
    assert "codec_name=h264" in probe.stdout
    assert "width=640" in probe.stdout


@pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists(), reason="需要 ffmpeg")
def test_burned_video_differs_from_source(tmp_path):
    """烧录后画面应当与原视频不同，否则说明字幕没画上去。"""
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频素材")
    proj = _caption_project()
    out = vid.burn_subtitles(clip, proj, tmp_path / "b.mp4", bilingual=True)

    def frame_bytes(path, n=40):
        proc = subprocess.run(
            ["ffmpeg", "-v", "quiet", "-i", str(path),
             "-vf", f"select=eq(n\\,{n})", "-vframes", "1",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True,
        )
        return proc.stdout

    assert frame_bytes(clip) != frame_bytes(out), "烧录后的帧应与原帧不同"


@pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists(), reason="需要 ffmpeg")
def test_burn_leaves_no_temp_file(tmp_path):
    """烧录用到的临时 ass 不应留在输出目录里。"""
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频素材")

    proj = _caption_project()
    out_dir = tmp_path / "outdir"
    out = vid.burn_subtitles(clip, proj, out_dir / "b.mp4", bilingual=True)
    assert out.exists()

    leftovers = [p.name for p in out_dir.iterdir() if p.name != "b.mp4"]
    assert leftovers == [], f"输出目录残留了临时文件：{leftovers}"


@pytest.mark.skipif(not Path("/usr/bin/ffmpeg").exists(), reason="需要 ffmpeg")
def test_burn_cleans_temp_in_work_dir(tmp_path):
    """显式指定工作目录时，临时 ass 也应在结束后删掉。"""
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频素材")

    work = tmp_path / "work"
    proj = _caption_project()
    out = vid.burn_subtitles(
        clip, proj, tmp_path / "o.mp4", bilingual=True, work_dir=work
    )
    assert out.exists()
    assert [p.name for p in work.iterdir()] == [], "工作目录应清理干净"


def test_probe_duration():
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频素材")
    d = vid.probe_duration(clip)
    assert 3.0 < d < 5.0, d
