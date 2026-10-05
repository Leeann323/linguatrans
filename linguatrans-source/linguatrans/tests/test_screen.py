"""屏幕截取测试。

无头环境里抓不到屏，正好用来验证错误处理是否优雅：
程序应给出可读的提示，而不是抛出一堆栈。
"""

import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from linguatrans.io import screen  # noqa: E402


def _headless() -> bool:
    return not os.environ.get("DISPLAY")


def test_capture_available_returns_reason():
    ok, reason = screen.capture_available()
    assert isinstance(ok, bool)
    assert isinstance(reason, str) and reason


@pytest.mark.skipif(not _headless(), reason="仅在无显示环境验证降级行为")
def test_headless_reports_unavailable():
    ok, reason = screen.capture_available()
    assert ok is False
    assert reason, "应给出不可用的原因"


@pytest.mark.skipif(not _headless(), reason="仅在无显示环境验证降级行为")
def test_grab_full_raises_readable_error():
    with pytest.raises(screen.ScreenCaptureError) as exc:
        screen.grab_full()
    msg = str(exc.value)
    assert "截图" in msg
    # 提示里应引导用户改用系统截图工具，而不是只抛技术细节
    assert "Wayland" in msg or "截图工具" in msg


@pytest.mark.skipif(not _headless(), reason="仅在无显示环境验证降级行为")
def test_grab_region_raises_readable_error():
    with pytest.raises(screen.ScreenCaptureError):
        screen.grab_region(0, 0, 100, 100)


def test_list_monitors_raises_readable_error():
    """无显示时列出显示器应抛出可读错误，而不是别的异常类型。"""
    if not _headless():
        monitors = screen.list_monitors()
        assert monitors and monitors[0].index == 0
        return
    with pytest.raises(screen.ScreenCaptureError):
        screen.list_monitors()


def test_monitor_info_box():
    m = screen.MonitorInfo(index=1, left=10, top=20, width=100, height=50)
    assert m.box == (10, 20, 110, 70)


def test_save_png_roundtrip(tmp_path):
    arr = np.zeros((40, 60, 3), dtype=np.uint8)
    arr[:, :, 0] = 200
    path = screen.save_png(arr, tmp_path / "shot.png")
    assert path.exists()

    from PIL import Image

    back = np.array(Image.open(path))
    assert back.shape == (40, 60, 3)
    assert back[0, 0, 0] == 200


def test_recognize_region_uses_ocr(monkeypatch):
    """区域识别应把裁剪后的数组交给 OCR，不真的抓屏。"""
    from linguatrans.io import ocr

    calls = {}

    fake = np.full((30, 80, 3), 255, dtype=np.uint8)

    def fake_grab(left, top, width, height):
        calls["box"] = (left, top, width, height)
        return fake

    monkeypatch.setattr(screen, "grab_region", fake_grab)
    monkeypatch.setattr(ocr, "read_array", lambda arr: [("box", "hello", 0.9)])

    out = screen.recognize_region((100, 200, 180, 230))
    assert calls["box"] == (100, 200, 80, 30)
    assert out == [("box", "hello", 0.9)]


def test_recognize_screen_saves_when_asked(tmp_path, monkeypatch):
    from linguatrans.io import ocr

    fake = np.full((20, 20, 3), 128, dtype=np.uint8)
    monkeypatch.setattr(screen, "grab_full", lambda monitor=1: fake)
    monkeypatch.setattr(ocr, "read_array", lambda arr: [])

    out_path = tmp_path / "full.png"
    screen.recognize_screen(monitor=1, save_to=out_path)
    assert out_path.exists(), "指定保存路径时应落盘"
