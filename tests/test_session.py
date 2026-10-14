"""会话逻辑测试：逐句推进、回退、跳转、断点续传。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from linguatrans.core.model import Project, SegmentKind  # noqa: E402
from linguatrans.core.session import TranslationSession  # noqa: E402
from linguatrans.core.store import ProjectStore  # noqa: E402


def _proj(n: int = 4) -> Project:
    p = Project(name="s")
    for i in range(n):
        p.add_segment(f"sentence {i}")
    return p


def test_starts_at_first_untranslated():
    proj = _proj(4)
    proj.segments[0].target = "一"
    proj.segments[1].target = "二"
    sess = TranslationSession(proj, None)
    assert sess.index == 2


def test_starts_at_zero_when_all_empty():
    sess = TranslationSession(_proj(3), None)
    assert sess.index == 0
    assert not sess.finished


def test_commit_advances_and_marks_done():
    proj = _proj(3)
    sess = TranslationSession(proj, None)
    seg = sess.commit("第一句")
    assert seg.target == "第一句"
    assert proj.done == 1
    assert sess.index == 1


def test_commit_without_advance():
    proj = _proj(3)
    sess = TranslationSession(proj, None)
    sess.commit("x", advance=False)
    assert sess.index == 0
    assert proj.done == 1


def test_commit_strips_whitespace():
    proj = _proj(1)
    sess = TranslationSession(proj, None)
    sess.commit("   有空格   ")
    assert proj.segments[0].target == "有空格"


def test_empty_commit_is_not_counted_as_done():
    proj = _proj(2)
    sess = TranslationSession(proj, None)
    sess.commit("   ")
    assert proj.done == 0


def test_back_and_forward_bounds():
    proj = _proj(2)
    sess = TranslationSession(proj, None)
    assert sess.back() == 0           # 已在开头，不应越界
    sess.advance()
    assert sess.index == 1
    sess.advance()
    assert sess.index == 1            # 已在末尾，不应越界


def test_jump_and_jump_to_untranslated():
    proj = _proj(5)
    sess = TranslationSession(proj, None)
    sess.jump(4)
    assert sess.index == 4
    proj.segments[0].target = "一"
    proj.segments[1].target = "二"
    sess.jump_to_next_untranslated()
    assert sess.index == 2
    sess.jump(99)                     # 越界不应生效
    assert sess.index == 2


def test_finished_when_all_translated():
    proj = _proj(2)
    sess = TranslationSession(proj, None)
    sess.commit("一")
    sess.commit("二")
    assert sess.finished
    assert sess.stats().remaining == 0
    assert sess.stats().percent == 100.0


def test_skip_keeps_existing_translation():
    proj = _proj(2)
    proj.segments[1].target = "已译"
    sess = TranslationSession(proj, None)
    sess.skip()
    assert proj.segments[1].target == "已译"


def test_clear_current_only_affects_current():
    proj = _proj(2)
    proj.segments[0].target = "一"
    proj.segments[1].target = "二"
    sess = TranslationSession(proj, None)
    sess.jump(0)
    sess.clear_current()
    assert proj.segments[0].target == ""
    assert proj.segments[1].target == "二"


def test_autosave_writes_project(tmp_path):
    proj = _proj(3)
    store = ProjectStore(tmp_path / "p")
    store.save(proj)
    sess = TranslationSession(proj, store, autosave_every=1)
    sess.commit("第一句")
    # 已自动保存，重新载入应能看到译文
    back = store.load()
    assert back.segments[0].target == "第一句"


def test_autosave_batching(tmp_path):
    proj = _proj(4)
    store = ProjectStore(tmp_path / "p")
    store.save(proj)
    sess = TranslationSession(proj, store, autosave_every=3)
    sess.commit("一")
    sess.commit("二")
    assert store.load().segments[0].target == ""    # 未到阈值，尚未落盘
    sess.commit("三")
    assert store.load().segments[0].target == "一"  # 达到阈值后落盘


def test_context_window():
    proj = _proj(5)
    sess = TranslationSession(proj, None)
    sess.jump(2)
    ctx = sess.context(before=1, after=1)
    assert [s.index for s in ctx] == [1, 2, 3]
    sess.jump(0)
    ctx = sess.context(before=2, after=1)
    assert [s.index for s in ctx] == [0, 1]         # 前边界收敛


def test_fill_untranslated_and_clear_all():
    proj = _proj(3)
    proj.segments[0].target = "已译"
    sess = TranslationSession(proj, None)
    n = sess.fill_untranslated("待补")
    assert n == 2
    assert proj.done == 3
    sess.clear_all()
    assert proj.done == 0


def test_export_pairs():
    proj = _proj(2)
    proj.segments[0].target = "一"
    sess = TranslationSession(proj, None)
    assert sess.export_pairs() == [("sentence 0", "一"), ("sentence 1", "")]


def test_stats_on_empty_project():
    sess = TranslationSession(Project(name="empty"), None)
    st = sess.stats()
    assert st.total == 0
    assert st.percent == 0.0
    assert sess.current is None


def test_resume_after_reload(tmp_path):
    """断点续传：保存后重新载入，应回到未译的第一句。"""
    proj = _proj(5)
    store = ProjectStore(tmp_path / "p")
    sess = TranslationSession(proj, store, autosave_every=1)
    sess.commit("一")
    sess.commit("二")
    sess.save()

    store2 = ProjectStore(tmp_path / "p")
    reloaded = store2.load()
    sess2 = TranslationSession(reloaded, store2)
    assert sess2.index == 2
    assert reloaded.segments[0].target == "一"
