"""界面测试：在 offscreen 模式下构建窗口并驱动关键交互。

无头环境看不到界面，但可以验证控件构建、信号连接和状态流转是否正确。
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from linguatrans.core.model import (  # noqa: E402
    MediaKind, Project, SegmentKind,
)
from linguatrans.core.session import TranslationSession  # noqa: E402
from linguatrans.core.store import ProjectStore  # noqa: E402
from linguatrans.ui.main_window import MainWindow  # noqa: E402
from linguatrans.ui.overlay import OverlayWindow  # noqa: E402
from linguatrans.ui.settings import Settings  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def project():
    p = Project(name="演示", kind=MediaKind.VIDEO)
    p.add_segment("The central bank cut rates.", SegmentKind.CAPTION, 0.0, 2.0)
    p.add_segment("Markets rallied.", SegmentKind.CAPTION, 2.0, 4.0)
    p.add_segment("Inflation may slow.", SegmentKind.CAPTION, 4.0, 6.0)
    return p


# ---------------- 浮窗 ----------------

def test_overlay_builds(app, project):
    sess = TranslationSession(project, None)
    ov = OverlayWindow(sess)
    assert ov.width() == 900
    assert ov.source.text() == "The central bank cut rates."
    assert "1" in ov.progress.text()
    ov.close()


def test_overlay_shows_current_target(app, project):
    """会话从第一个未译句开始，所以首句已译时应跳到第二句。"""
    project.segments[0].target = "央行降息。"
    sess = TranslationSession(project, None)
    assert sess.index == 1
    ov = OverlayWindow(sess)
    assert ov.source.text() == "Markets rallied."
    assert ov.input.text() == ""

    # 回到首句应能带出已有译文
    ov.go_prev()
    assert ov.input.text() == "央行降息。"
    ov.close()


def test_overlay_commit_advances(app, project):
    sess = TranslationSession(project, None)
    ov = OverlayWindow(sess)
    ov.input.setText("央行降息。")
    ov.commit()
    assert project.segments[0].target == "央行降息。"
    assert sess.index == 1
    assert ov.source.text() == "Markets rallied."
    assert ov.input.text() == ""      # 下一句尚未翻译，输入框应清空
    ov.close()


def test_overlay_prev_and_skip(app, project):
    sess = TranslationSession(project, None)
    ov = OverlayWindow(sess)
    ov.go_skip()
    assert sess.index == 1
    ov.go_prev()
    assert sess.index == 0
    assert ov.source.text() == "The central bank cut rates."
    ov.close()


def test_overlay_reports_completion(app, project):
    """全部译完后浮窗停在某一句供回看，并在进度处提示完成。"""
    for s in project.segments:
        s.target = "x"
    sess = TranslationSession(project, None)
    ov = OverlayWindow(sess)
    assert "全部完成" in ov.progress.text()
    assert ov.input.isEnabled()        # 仍可回看修改
    assert ov.source.text() == "The central bank cut rates."
    ov.close()


def test_overlay_empty_project(app):
    sess = TranslationSession(Project(name="空"), None)
    ov = OverlayWindow(sess)
    assert "项目为空" in ov.source.text()
    assert not ov.input.isEnabled()
    ov.close()


def test_overlay_progressed_signal(app, project):
    sess = TranslationSession(project, None)
    ov = OverlayWindow(sess)
    hits = []
    ov.progressed.connect(lambda: hits.append(1))
    ov.input.setText("一")
    ov.commit()
    assert hits == [1]
    ov.close()


def test_overlay_saves_on_close(app, tmp_path, project):
    store = ProjectStore(tmp_path / "p")
    store.save(project)
    sess = TranslationSession(project, store, autosave_every=99)
    ov = OverlayWindow(sess)
    ov.input.setText("央行降息。")
    ov.commit()
    ov.close()                        # 关闭时应强制保存
    assert store.load().segments[0].target == "央行降息。"


# ---------------- 主窗口 ----------------

def test_main_window_builds(app):
    w = MainWindow(Settings())
    assert "LinguaTrans" in w.windowTitle()
    assert not w.btn_overlay.isEnabled()      # 未导入项目时不可用


def test_main_window_adopts_project(app, tmp_path, project):
    w = MainWindow(Settings())
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    w._adopt(project, str(src), "video")

    assert w.project is project
    assert w.list.count() == 3
    assert w.btn_overlay.isEnabled()
    assert w.btn_word.isEnabled()
    assert w.btn_burn.isEnabled()             # 视频项目才能烧录


def test_main_window_list_marks_translated(app, tmp_path, project):
    project.segments[0].target = "央行降息。"
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    first = w.list.item(0).text()
    second = w.list.item(1).text()
    assert first.startswith("✓")
    assert second.startswith("○")


def test_main_window_selection_syncs_text(app, tmp_path, project):
    project.segments[1].target = "市场走高。"
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    w.on_select(1)
    assert w.txt_source.toPlainText() == "Markets rallied."
    assert w.txt_target.toPlainText() == "市场走高。"


def test_main_window_navigation(app, tmp_path, project):
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    w.navigate(1)
    assert w.txt_source.toPlainText() == "Markets rallied."
    w.navigate(-1)
    assert w.txt_source.toPlainText() == "The central bank cut rates."


def test_main_window_save_current(app, tmp_path, project):
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    w.txt_target.setPlainText("央行降息。")
    w.save_current()
    assert project.segments[0].target == "央行降息。"
    assert w.progress.value() == 33


def test_main_window_goto_untranslated(app, tmp_path, project):
    project.segments[0].target = "一"
    project.segments[1].target = "二"
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    w.on_select(0)
    w.goto_untranslated()
    assert w.txt_source.toPlainText() == "Inflation may slow."


def test_main_window_overlay_lifecycle(app, tmp_path, project):
    w = MainWindow(Settings())
    w._adopt(project, str(tmp_path / "a.txt"), "text")
    w.show_overlay()
    assert w.overlay is not None
    w.overlay.input.setText("央行降息。")
    w.overlay.commit()
    # 浮窗提交后主窗口应同步刷新
    assert project.segments[0].target == "央行降息。"
    assert w.list.item(0).text().startswith("✓")
    w.overlay.close()
    assert w.overlay is None


def test_non_video_cannot_burn(app, tmp_path):
    proj = Project(name="文本", kind=MediaKind.TEXT)
    proj.add_segment("Hello.")
    w = MainWindow(Settings())
    w._adopt(proj, str(tmp_path / "a.txt"), "text")
    assert not w.btn_burn.isEnabled()
    assert w.btn_word.isEnabled()


# ---------------- 设置 ----------------

def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    s = Settings(model_name="medium", overlay_opacity=0.5, bilingual=False)
    s.remember("/a")
    s.remember("/b")
    s.remember("/a")
    s.save()

    back = Settings.load()
    assert back.model_name == "medium"
    assert back.overlay_opacity == 0.5
    assert back.bilingual is False
    assert back.recent == ["/a", "/b"]


def test_settings_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    import json

    d = tmp_path / "LinguaTrans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text(
        json.dumps({"model_name": "base", "unknown_key": 1}), encoding="utf-8"
    )
    s = Settings.load()
    assert s.model_name == "base"
    assert not hasattr(s, "unknown_key")


def test_settings_corrupt_file_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    d = tmp_path / "LinguaTrans"
    d.mkdir(parents=True, exist_ok=True)
    (d / "settings.json").write_text("{ 坏掉的 json", encoding="utf-8")
    s = Settings.load()
    assert s.model_name == "small"        # 回落到默认值


def test_settings_subtitle_style():
    s = Settings(en_size=30, zh_size=32, margin_v=40)
    st = s.subtitle_style()
    assert st.en_size == 30
    assert st.zh_size == 32
    assert st.margin_v == 40
    assert st.font                     # 应自动填上平台默认字体
