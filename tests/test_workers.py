"""后台任务与框选遮罩测试。

线程测试用真实子类运行，验证信号确实发出、错误被捕获转成信号，
不用 mock 替换被测对象本身。
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from linguatrans.core.model import MediaKind, Project, SegmentKind  # noqa: E402
from linguatrans.ui.region import RegionSelector  # noqa: E402
from linguatrans.ui.workers import BurnWorker, TranscribeWorker  # noqa: E402

ASSETS = ROOT / "tests" / "assets"


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def _wait(worker, timeout_ms: int = 120000) -> bool:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    done = {"ok": False}

    def finish(*_):
        done["ok"] = True
        loop.quit()

    worker.finished_ok.connect(finish)
    worker.failed.connect(finish)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    worker.start()
    loop.exec()
    worker.wait(5000)
    return done["ok"]


# ---------------- 语音识别线程 ----------------

def test_transcribe_worker_emits_result(app):
    audio = ASSETS / "speech.wav"
    if not audio.exists():
        pytest.skip("缺少测试音频")

    results = {}
    w = TranscribeWorker(audio, "tiny", "en")
    w.finished_ok.connect(lambda caps, lang: results.update(caps=caps, lang=lang))
    assert _wait(w), "识别任务应在超时前完成"
    assert results.get("lang") == "en"
    assert len(results.get("caps", [])) >= 1


def test_transcribe_worker_reports_failure(app, tmp_path):
    """喂一个不存在的文件，应发出 failed 信号而不是崩溃。"""
    errors = []
    w = TranscribeWorker(tmp_path / "nope.wav", "tiny", "en")
    w.failed.connect(lambda msg: errors.append(msg))
    _wait(w, timeout_ms=30000)
    assert errors, "失败时应发出 failed 信号"
    assert isinstance(errors[0], str) and errors[0]


# ---------------- 烧录线程 ----------------

def test_burn_worker_emits_path(app, tmp_path):
    clip = ASSETS / "clip.mp4"
    if not clip.exists():
        pytest.skip("缺少测试视频")

    proj = Project(name="w", kind=MediaKind.VIDEO)
    proj.add_segment("Hello there.", SegmentKind.CAPTION, 0.0, 1.5)
    proj.segments[0].target = "你好。"

    out = tmp_path / "out.mp4"
    paths = []
    w = BurnWorker(clip, proj, out, None, True)
    w.finished_ok.connect(lambda p: paths.append(p))
    assert _wait(w, timeout_ms=180000), "烧录任务应在超时前完成"
    assert paths and Path(paths[0]).exists()


def test_burn_worker_reports_failure(app, tmp_path):
    proj = Project(name="w", kind=MediaKind.VIDEO)
    proj.add_segment("Hello.", SegmentKind.CAPTION, 0.0, 1.0)
    errors = []
    w = BurnWorker(tmp_path / "missing.mp4", proj, tmp_path / "o.mp4", None, True)
    w.failed.connect(lambda m: errors.append(m))
    _wait(w, timeout_ms=30000)
    assert errors, "源文件不存在时应发出 failed"


# ---------------- 框选遮罩 ----------------

def _mouse(kind, x, y, button=Qt.LeftButton, buttons=None):
    if buttons is None:
        buttons = button
    return QMouseEvent(
        kind, QPoint(x, y), QPoint(x, y),
        button, buttons, Qt.NoModifier,
    )


def test_region_selector_emits_selected_box(app):
    sel = RegionSelector()
    got = []
    sel.selected.connect(lambda b: got.append(b))

    sel.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 100, 200))
    sel.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, 300, 400, Qt.NoButton))
    sel.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, 300, 400))

    assert len(got) == 1
    left, top, right, bottom = got[0]
    assert right > left and bottom > top
    assert right - left == 200
    assert bottom - top == 200


def test_region_selector_handles_reverse_drag(app):
    """从右下往左上拖，也应收敛成同一个矩形。"""
    sel = RegionSelector()
    got = []
    sel.selected.connect(lambda b: got.append(b))

    sel.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 300, 400))
    sel.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, 100, 200, Qt.NoButton))
    sel.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, 100, 200))

    assert len(got) == 1
    left, top, right, bottom = got[0]
    assert right - left == 200 and bottom - top == 200


def test_region_selector_rejects_tiny_box(app):
    """点一下没拖动，应视为取消而不是选出一个小框。"""
    sel = RegionSelector()
    got, cancelled = [], []
    sel.selected.connect(lambda b: got.append(b))
    sel.cancelled.connect(lambda: cancelled.append(1))

    sel.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 50, 50))
    sel.mouseReleaseEvent(_mouse(QMouseEvent.Type.MouseButtonRelease, 52, 51))

    assert got == []
    assert cancelled == [1]


def test_region_selector_escape_cancels(app):
    from PySide6.QtGui import QKeyEvent

    sel = RegionSelector()
    cancelled = []
    sel.cancelled.connect(lambda: cancelled.append(1))
    sel.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 10, 10))
    sel.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    )
    assert cancelled == [1]


def test_region_selector_selection_normalized(app):
    sel = RegionSelector()
    sel._origin = QPoint(200, 150)
    sel._current = QPoint(50, 40)
    box = sel._selection()
    assert isinstance(box, QRect)
    assert box.width() == 150 and box.height() == 110
