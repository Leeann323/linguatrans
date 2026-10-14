"""屏幕截取：全屏识别与手动框选。

全屏识别直接抓整个屏幕或指定显示器，交给 OCR。
手动框选先抓全屏，弹出一个半透明遮罩，用户拖出矩形，只识别框内区域。

截图依赖 mss，在 X11 与 Windows 下都可用；Wayland 下 mss 可能受限，
这时会给出提示，让用户改用系统截图工具截图后导入图片。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


class ScreenCaptureError(RuntimeError):
    """截图失败。"""


def _open_mss():
    """打开 mss 会话。优先用新接口 MSS，兼容旧版 mss。"""
    import mss

    factory = getattr(mss, "MSS", None) or getattr(mss, "mss")
    return factory()


@dataclass
class MonitorInfo:
    """一个显示器的信息。"""

    index: int
    left: int
    top: int
    width: int
    height: int

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + self.width, self.top + self.height)


def list_monitors() -> list[MonitorInfo]:
    """列出所有显示器。0 号通常是全部显示器的合集。"""
    try:
        import mss
    except ImportError as e:
        raise ScreenCaptureError("缺少 mss 模块，无法截图") from e

    try:
        with _open_mss() as sct:
            out: list[MonitorInfo] = []
            for i, m in enumerate(sct.monitors):
                out.append(
                    MonitorInfo(
                        index=i,
                        left=int(m["left"]),
                        top=int(m["top"]),
                        width=int(m["width"]),
                        height=int(m["height"]),
                    )
                )
            return out
    except Exception as e:
        raise ScreenCaptureError(
            "截图失败。若使用 Wayland 桌面，系统通常不允许程序直接抓屏，"
            "请改用系统截图工具截图后再导入图片。"
        ) from e


def grab_full(monitor: int = 1) -> np.ndarray:
    """抓取指定显示器的全屏画面，返回 RGB 数组。

    monitor 为 0 表示所有显示器拼成的大画面，1 起为各个显示器。
    """
    try:
        import mss
    except ImportError as e:
        raise ScreenCaptureError("缺少 mss 模块，无法截图") from e

    try:
        with _open_mss() as sct:
            monitors = sct.monitors
            if monitor >= len(monitors):
                monitor = 1 if len(monitors) > 1 else 0
            shot = sct.grab(monitors[monitor])
            arr = np.frombuffer(shot.rgb, dtype=np.uint8)
            return arr.reshape(shot.height, shot.width, 3)
    except Exception as e:
        raise ScreenCaptureError(
            "截图失败。若使用 Wayland 桌面，请改用系统截图工具截图后再导入图片。"
        ) from e


def grab_region(left: int, top: int, width: int, height: int) -> np.ndarray:
    """抓取屏幕上的一块矩形区域，返回 RGB 数组。"""
    try:
        import mss
    except ImportError as e:
        raise ScreenCaptureError("缺少 mss 模块，无法截图") from e

    try:
        with _open_mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            arr = np.frombuffer(shot.rgb, dtype=np.uint8)
            return arr.reshape(shot.height, shot.width, 3)
    except Exception as e:
        raise ScreenCaptureError(f"区域截图失败：{e}") from e


def save_png(arr: np.ndarray, path: str | Path) -> Path:
    """把截图存成 PNG，便于复现或存档。"""
    from PIL import Image

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)
    return path


def recognize_screen(monitor: int = 1, save_to: str | Path | None = None):
    """全屏识别：截图后直接走 OCR，返回识别行。"""
    from . import ocr

    arr = grab_full(monitor)
    if save_to:
        save_png(arr, save_to)
    return ocr.read_array(arr)


def recognize_region(box: tuple[int, int, int, int],
                     save_to: str | Path | None = None):
    """框选识别：只识别矩形区域。box 为 (left, top, right, bottom)。"""
    from . import ocr

    left, top, right, bottom = box
    arr = grab_region(left, top, right - left, bottom - top)
    if save_to:
        save_png(arr, save_to)
    return ocr.read_array(arr)


def capture_available() -> tuple[bool, str]:
    """检查当前环境能否直接截图，返回是否可用与原因。"""
    try:
        import mss  # noqa: F401
    except ImportError:
        return False, "缺少 mss 模块"

    try:
        with _open_mss() as sct:
            if len(sct.monitors) <= 1:
                return False, "没有检测到显示器"
    except Exception as e:
        return False, f"无法访问显示器：{e}"

    import os

    if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        return False, "Wayland 桌面不允许程序直接抓屏，请改用系统截图工具"

    return True, "可截图"
