"""悬浮歌词窗：像桌面歌词一样贴在屏幕上，逐句翻译。

上面一行显示英文原文，下面一行是输入框，打完一句回车即推进下一句。
窗口无边框、可拖动、可调透明度、可置顶。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..core.session import TranslationSession


class OverlayWindow(QWidget):
    """桌面歌词式的翻译浮窗。"""

    closed = Signal()
    progressed = Signal()

    def __init__(self, session: TranslationSession, opacity: float = 0.88,
                 width: int = 900, position: str = "bottom"):
        super().__init__()
        self.session = session
        self._drag_origin: QPoint | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowOpacity(opacity)
        self.resize(width, 132)

        self._build_ui()
        self._place(position)
        self._bind_shortcuts()
        self.refresh()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.progress = QLabel("0 / 0")
        self.progress.setStyleSheet("color:#8fb7ff;font-size:12px;")
        bar.addWidget(self.progress)
        bar.addStretch(1)

        self.btn_prev = QPushButton("上一句")
        self.btn_next = QPushButton("跳过")
        self.btn_close = QPushButton("关闭")
        for b in (self.btn_prev, self.btn_next, self.btn_close):
            b.setFixedHeight(22)
            b.setStyleSheet(
                "QPushButton{color:#cfd6e4;background:#2b3140;border:none;"
                "border-radius:4px;padding:0 8px;font-size:12px;}"
                "QPushButton:hover{background:#3a4256;}"
            )
        bar.addWidget(self.btn_prev)
        bar.addWidget(self.btn_next)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)

        self.source = QLabel("")
        self.source.setWordWrap(True)
        self.source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source.setStyleSheet("color:#ffffff;font-size:17px;")
        root.addWidget(self.source)

        self.input = QLineEdit()
        self.input.setPlaceholderText("在此输入译文，回车进入下一句")
        self.input.setStyleSheet(
            "QLineEdit{background:#1c2130;color:#ffe066;border:1px solid #39405a;"
            "border-radius:5px;padding:6px 8px;font-size:16px;}"
            "QLineEdit:focus{border:1px solid #5b8cff;}"
        )
        self.input.setFont(QFont("", 12))
        root.addWidget(self.input)

        self.setStyleSheet("OverlayWindow{background:#151a24;border:1px solid #39405a;}")

        self.btn_prev.clicked.connect(self.go_prev)
        self.btn_next.clicked.connect(self.go_skip)
        self.btn_close.clicked.connect(self.close)
        self.input.returnPressed.connect(self.commit)

    def _bind_shortcuts(self) -> None:
        # 全局快捷键只在窗口激活时生效，避免抢占其他程序
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.commit)
        QShortcut(QKeySequence("Alt+Up"), self, activated=self.go_prev)
        QShortcut(QKeySequence("Alt+Down"), self, activated=self.go_skip)
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

    def _place(self, position: str) -> None:
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is None:
            return
        x = screen.x() + (screen.width() - self.width()) // 2
        if position == "top":
            y = screen.y() + 60
        else:
            y = screen.y() + screen.height() - self.height() - 90
        self.move(x, y)

    # ---------- 行为 ----------

    def refresh(self) -> None:
        """按会话状态刷新显示。"""
        seg = self.session.current
        st = self.session.stats()
        if st.total and st.remaining == 0:
            self.progress.setText(f"{st.done} / {st.total}   全部完成，可回看修改")
        else:
            self.progress.setText(f"{st.done} / {st.total}   第 {st.current + 1} 句")
        if seg is None:
            self.source.setText("项目为空，请先导入原文")
            self.input.setEnabled(False)
            return
        self.input.setEnabled(True)
        self.source.setText(seg.source)
        self.input.setText(seg.target)
        self.input.selectAll()
        self.input.setFocus()

    def commit(self) -> None:
        text = self.input.text()
        self.session.commit(text, advance=True)
        self.progressed.emit()
        self.refresh()

    def go_prev(self) -> None:
        self.session.back()
        self.refresh()

    def go_skip(self) -> None:
        self.session.skip()
        self.refresh()

    # ---------- 拖动与关闭 ----------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_origin = None

    def closeEvent(self, event) -> None:
        self.session.save()
        self.closed.emit()
        super().closeEvent(event)
