"""识别层测试：OCR 与语音识别。真实跑模型，不用 mock。

语音识别依赖 espeak-ng 生成的测试音频，OCR 依赖生成的测试图片。
模型首次运行会联网下载，之后走本地缓存。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from linguatrans.core.model import SegmentKind  # noqa: E402
from linguatrans.io import asr, document, ocr  # noqa: E402

ASSETS = ROOT / "tests" / "assets"


def _need(path: Path):
    if not path.exists():
        pytest.skip(f"缺少素材 {path}，请先运行 tests/make_assets.py")


# ---------------- OCR ----------------

def test_ocr_reads_chinese_and_english():
    _need(ASSETS / "news.png")
    lines = ocr.read_image(ASSETS / "news.png")
    assert len(lines) >= 3, f"识别行数偏少：{len(lines)}"
    joined = " ".join(l.text for l in lines)
    assert "markets" in joined.lower()
    assert "央行" in joined


def test_ocr_lines_sorted_top_to_bottom():
    _need(ASSETS / "news.png")
    lines = ocr.read_image(ASSETS / "news.png")
    ys = [l.y for l in lines]
    assert ys == sorted(ys), "识别结果应按纵坐标从上到下"


def test_ocr_box_region_limits_result():
    """框选只应识别框内内容。

    注意：裁图会改变 OCR 的行合并结果，所以不能假设“框小行数就少”，
    只能校验框外的文字确实没被识别进来。
    """
    _need(ASSETS / "news.png")
    full = ocr.read_image(ASSETS / "news.png")
    # 只取下半部分（跳过前两行英文）
    bottom = ocr.read_image(ASSETS / "news.png", box=(0, 110, 900, 320))
    assert bottom, "框选区域应有识别结果"

    bottom_text = " ".join(l.text for l in bottom)
    assert "央行" in bottom_text or "全球市场" in bottom_text
    assert "Breaking" not in bottom_text, "框外的第一行不应出现"
    assert len(bottom) <= len(full) + 20, "裁剪不应凭空多出大量内容"


def test_ocr_to_segments():
    _need(ASSETS / "news.png")
    lines = ocr.read_image(ASSETS / "news.png")
    segs = ocr.lines_to_segments(lines)
    assert segs, "应至少产出一个片段"
    assert all(s.kind == SegmentKind.LINE for s in segs)
    assert [s.index for s in segs] == list(range(len(segs)))


def test_join_lines_mixes_cjk_and_latin():
    assert ocr.join_lines(["全球市场", "走高"]) == "全球市场走高"
    assert ocr.join_lines(["Global", "markets"]) == "Global markets"
    assert ocr.join_lines(["央行", "announced"]) == "央行announced"


def test_import_image_project():
    _need(ASSETS / "news.png")
    proj = document.import_image(ASSETS / "news.png")
    assert proj.total >= 3
    assert proj.name == "news"


# ---------------- 语音识别 ----------------

def test_decode_audio_shape():
    _need(ASSETS / "speech.wav")
    audio = asr.decode_audio(ASSETS / "speech.wav")
    assert audio.dtype.name == "float32"
    assert 16000 * 8 < audio.size < 16000 * 16, audio.size


def test_probe_duration_matches():
    _need(ASSETS / "speech.wav")
    d = asr.probe_duration(ASSETS / "speech.wav")
    assert 8 < d < 16, d


def test_transcribe_returns_timed_captions():
    _need(ASSETS / "speech.wav")
    caps, lang = asr.transcribe(ASSETS / "speech.wav", model_name="tiny",
                                language="en")
    assert lang == "en"
    assert len(caps) >= 2, f"应至少识别出两句，实际 {len(caps)}"

    # 时间轴应单调不减
    for a, b in zip(caps, caps[1:]):
        assert b.start >= a.start - 0.01
    assert caps[0].start >= 0.0
    assert caps[-1].end > caps[0].start

    joined = " ".join(c.text.lower() for c in caps)
    # tiny 模型容错，只校验关键词片段
    assert "market" in joined or "central" in joined


def test_captions_to_segments_keeps_timing():
    _need(ASSETS / "speech.wav")
    caps, _ = asr.transcribe(ASSETS / "speech.wav", model_name="tiny",
                             language="en")
    segs = asr.captions_to_segments(caps)
    assert len(segs) == len(caps)
    assert all(s.kind == SegmentKind.CAPTION for s in segs)
    assert segs[0].end > 0
    assert [s.index for s in segs] == list(range(len(segs)))


def test_model_size_table_covers_default():
    assert asr.DEFAULT_MODEL in asr.MODEL_SIZES
    for name in ("tiny", "base", "small", "medium", "large-v3"):
        assert name in asr.MODEL_SIZES


# ---------------- 文档导入 ----------------

def test_import_text_splits_sentences(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("First sentence. Second one!\n\nThird paragraph here.",
                 encoding="utf-8")
    proj = document.import_text(p, "en", by_sentence=True)
    assert proj.total == 3
    assert proj.segments[0].source == "First sentence."


def test_import_markdown_strips_syntax(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Title\n\nSome **bold** text. [link](http://x.com)\n",
                 encoding="utf-8")
    proj = document.import_text(p, "en", by_sentence=False)
    body = " ".join(s.source for s in proj.segments)
    assert "#" not in body
    assert "**" not in body
    assert "link" in body
    assert "http" not in body


def test_detect_kind():
    assert document.detect_kind("a.mp4") == document.MediaKind.VIDEO
    assert document.detect_kind("a.mp3") == document.MediaKind.VIDEO
    assert document.detect_kind("a.pdf") == document.MediaKind.PDF
    assert document.detect_kind("a.PNG") == document.MediaKind.IMAGE
    assert document.detect_kind("a.txt") == document.MediaKind.TEXT
    assert document.detect_kind("a.md") == document.MediaKind.TEXT


def test_import_pdf_extracts_text(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    p = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello from PDF. Second sentence here.")
    doc.save(str(p))
    doc.close()

    proj = document.import_pdf(p, "en", by_sentence=True)
    body = " ".join(s.source for s in proj.segments)
    assert "Hello from PDF" in body
    assert proj.total >= 1
