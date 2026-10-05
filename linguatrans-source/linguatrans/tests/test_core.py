"""内核测试：模型、存储、切分。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from linguatrans.core.model import (  # noqa: E402
    ImageAsset, MediaKind, Project, Segment, SegmentKind,
)
from linguatrans.core.segmenter import (  # noqa: E402
    split_paragraphs, split_sentences, split_text,
)
from linguatrans.core.store import ProjectStore  # noqa: E402


def test_segment_basic_properties():
    seg = Segment(index=0, source="Hello world")
    assert not seg.translated
    seg.target = "你好世界"
    assert seg.translated
    seg.target = "   "
    assert not seg.translated


def test_project_progress_and_resume():
    proj = Project(name="t")
    for i in range(4):
        proj.add_segment(f"sentence {i}")
    assert proj.total == 4
    assert proj.done == 0
    assert proj.progress == 0.0
    assert proj.first_untranslated() == 0

    proj.segments[0].target = "一"
    proj.segments[1].target = "二"
    assert proj.done == 2
    assert proj.progress == 0.5
    assert proj.first_untranslated() == 2

    for s in proj.segments:
        s.target = "x"
    assert proj.first_untranslated() == -1


def test_split_paragraphs():
    text = "first para\n\nsecond para\n\n\nthird para\n"
    assert split_paragraphs(text) == ["first para", "second para", "third para"]


def test_split_sentences_english():
    text = "Hello there. How are you? I am fine!"
    assert split_sentences(text, "en") == [
        "Hello there.", "How are you?", "I am fine!"
    ]


def test_split_sentences_respects_abbreviations():
    text = "Dr. Smith went home. He was tired."
    got = split_sentences(text, "en")
    assert got == ["Dr. Smith went home.", "He was tired."], got


def test_split_sentences_handles_initials():
    text = "J. K. Rowling wrote it. It sold well."
    got = split_sentences(text, "en")
    assert len(got) == 2, got
    assert got[0].endswith("wrote it.")


def test_split_sentences_chinese():
    text = "今天天气很好。我们出去走走？好的！"
    got = split_sentences(text, "zh")
    assert got == ["今天天气很好。", "我们出去走走？", "好的！"], got


def test_split_text_by_sentence():
    text = "One. Two.\n\nThree."
    assert split_text(text, "en", by_sentence=True) == ["One.", "Two.", "Three."]
    assert split_text(text, "en", by_sentence=False) == ["One. Two.", "Three."]


def test_project_roundtrip(tmp_path):
    proj = Project(name="新闻翻译", kind=MediaKind.VIDEO, source_lang="en")
    proj.add_segment("Hello.", SegmentKind.CAPTION, start=0.0, end=1.5)
    proj.add_segment("World.", SegmentKind.CAPTION, start=1.5, end=3.0)
    proj.segments[0].target = "你好。"
    proj.add_asset(ImageAsset.new("a.png", 1, 100, 50), after_index=0)

    store = ProjectStore(tmp_path / "proj")
    store.save(proj)

    back = store.load()
    assert back.name == "新闻翻译"
    assert back.kind == MediaKind.VIDEO
    assert back.total == 2
    assert back.segments[0].target == "你好。"
    assert back.segments[1].kind == SegmentKind.CAPTION
    assert back.segments[1].start == 1.5
    assert len(back.assets) == 1
    assert back.asset_anchors["0"] == [back.assets[0].asset_id]
    assert back.progress == 0.5


def test_store_import_asset(tmp_path):
    src = tmp_path / "pic.png"
    src.write_bytes(b"fake-png-bytes")
    store = ProjectStore(tmp_path / "proj")
    dst = store.import_asset(src, "pic.png")
    assert dst.exists()
    assert dst.read_bytes() == b"fake-png-bytes"
    assert store.asset_path("pic.png") == dst
