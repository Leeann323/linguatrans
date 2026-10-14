"""主窗口：项目导入、逐句校对、导出。

左侧是全文列表，可跳转任意句；右侧是当前句的原文与译文；
底部是导出与浮窗入口。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from ..core.model import MediaKind, Project, SegmentKind
from ..core.session import TranslationSession
from ..core.store import ProjectStore
from ..io import document, ocr, screen, video, word
from .overlay import OverlayWindow
from .region import RegionSelector
from .settings import Settings
from .workers import BurnWorker, TranscribeWorker


class MainWindow(QWidget):
    """软件主界面。"""

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings.load()
        self.project: Project | None = None
        self.store: ProjectStore | None = None
        self.session: TranslationSession | None = None
        self.overlay: OverlayWindow | None = None

        self.setWindowTitle("LinguaTrans 逐句人工翻译工作台")
        self.resize(1080, 720)
        self._build_ui()

    # ---------- 界面 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.btn_open = QPushButton("导入原文")
        self.btn_open_pdf = QPushButton("导入 PDF")
        self.btn_open_ocr = QPushButton("屏幕取词")
        self.btn_open_video = QPushButton("导入视频")
        self.btn_overlay = QPushButton("打开浮窗翻译")
        self.btn_overlay.setEnabled(False)
        for b in (self.btn_open, self.btn_open_pdf, self.btn_open_ocr,
                  self.btn_open_video, self.btn_overlay):
            top.addWidget(b)
        top.addStretch(1)
        self.lbl_project = QLabel("尚未打开项目")
        top.addWidget(self.lbl_project)
        root.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.currentRowChanged.connect(self.on_select)
        split.addWidget(self.list)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        rl.addWidget(QLabel("原文"))
        self.txt_source = QPlainTextEdit()
        self.txt_source.setReadOnly(True)
        rl.addWidget(self.txt_source)

        rl.addWidget(QLabel("译文（可修改）"))
        self.txt_target = QPlainTextEdit()
        rl.addWidget(self.txt_target)

        nav = QHBoxLayout()
        self.btn_save = QPushButton("保存本句")
        self.btn_next = QPushButton("下一句")
        self.btn_prev = QPushButton("上一句")
        self.btn_next_un = QPushButton("跳到未翻译")
        for b in (self.btn_save, self.btn_next, self.btn_prev, self.btn_next_un):
            nav.addWidget(b)
        nav.addStretch(1)
        rl.addLayout(nav)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        root.addWidget(split)

        bottom = QHBoxLayout()
        self.btn_word = QPushButton("导出 Word")
        self.btn_soft = QPushButton("导出软字幕")
        self.btn_burn = QPushButton("烧录硬字幕")
        self.btn_burn.setEnabled(False)
        for b in (self.btn_word, self.btn_soft, self.btn_burn):
            b.setEnabled(False)
            bottom.addWidget(b)
        self.btn_word.setEnabled(False)
        bottom.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(240)
        bottom.addWidget(self.progress)
        root.addLayout(bottom)

        self.btn_open.clicked.connect(self.open_document)
        self.btn_open_pdf.clicked.connect(self.open_pdf)
        self.btn_open_ocr.clicked.connect(self.open_ocr)
        self.btn_open_video.clicked.connect(self.open_video)
        self.btn_overlay.clicked.connect(self.show_overlay)
        self.btn_save.clicked.connect(self.save_current)
        self.btn_next.clicked.connect(lambda: self.navigate(1))
        self.btn_prev.clicked.connect(lambda: self.navigate(-1))
        self.btn_next_un.clicked.connect(self.goto_untranslated)
        self.btn_word.clicked.connect(self.export_word)
        self.btn_soft.clicked.connect(self.export_soft)
        self.btn_burn.clicked.connect(self.burn_hard)

        self._export_buttons = (self.btn_word, self.btn_soft, self.btn_burn)

    # ---------- 导入 ----------

    def _adopt(self, project: Project, source_path: str, kind_hint: str) -> None:
        """把导入结果接进界面。"""
        base = Path(source_path).parent / f"{Path(source_path).stem}_linguatrans"
        self.store = ProjectStore(base)
        self.project = project
        self.session = TranslationSession(project, self.store, autosave_every=1)

        # PDF 抽出的图片要搬进项目目录
        if project.assets:
            tmp = Path(source_path).parent / f".{Path(source_path).stem}_assets"
            if tmp.exists():
                for asset in project.assets:
                    src = tmp / asset.filename
                    if src.exists():
                        self.store.import_asset(src, asset.filename)
        self.store.save(project)

        self.lbl_project.setText(f"{project.name}（{project.total} 句）")
        for b in self._export_buttons:
            b.setEnabled(True)
        self.btn_burn.setEnabled(project.kind == MediaKind.VIDEO)
        self.btn_overlay.setEnabled(True)
        self.refresh_list()
        self.refresh_progress()

    def open_document(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择原文", "",
            "文本 (*.txt *.md *.markdown);;所有文件 (*)",
        )
        if not path:
            return
        try:
            proj = document.import_text(path, self.settings.source_lang, True)
        except Exception as e:
            self._error("导入失败", e)
            return
        self._adopt(proj, path, "text")

    def open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            proj = document.import_pdf(path, self.settings.source_lang, True)
        except Exception as e:
            self._error("导入失败", e)
            return
        self._adopt(proj, path, "pdf")

    def open_ocr(self) -> None:
        """屏幕取词：可选全屏识别或手动框选，也可导入已有图片。"""
        choice = self._ask_ocr_mode()
        if choice is None:
            return
        if choice == "file":
            self._ocr_from_file()
        elif choice == "full":
            self._ocr_fullscreen()
        elif choice == "region":
            self._ocr_region()

    def _ask_ocr_mode(self) -> str | None:
        from PySide6.QtWidgets import QMessageBox

        available, reason = screen.capture_available()
        box = QMessageBox(self)
        box.setWindowTitle("屏幕取词")
        box.setText("选择取词方式")
        if not available:
            box.setInformativeText(f"当前环境无法直接截屏：{reason}")
        btn_full = box.addButton("全屏识别", QMessageBox.AcceptRole)
        btn_region = box.addButton("手动框选", QMessageBox.AcceptRole)
        btn_file = box.addButton("导入图片", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        if not available:
            btn_full.setEnabled(False)
            btn_region.setEnabled(False)
        box.exec()

        clicked = box.clickedButton()
        if clicked is btn_full:
            return "full"
        if clicked is btn_region:
            return "region"
        if clicked is btn_file:
            return "file"
        return None

    def _ocr_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片（可先用系统截图工具截取屏幕）", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*)",
        )
        if not path:
            return
        try:
            proj = document.import_image(path)
        except Exception as e:
            self._error("识别失败", e)
            return
        self._adopt(proj, path, "image")

    def _ocr_fullscreen(self) -> None:
        try:
            lines = screen.recognize_screen()
        except screen.ScreenCaptureError as e:
            self._error("取词失败", e)
            return
        self._adopt_ocr_lines(lines, "屏幕")

    def _ocr_region(self) -> None:
        self._selector = RegionSelector()
        self._selector.selected.connect(self._on_region_selected)
        self._selector.cancelled.connect(lambda: setattr(self, "_selector", None))
        self._selector.showFullScreen()
        self._selector.raise_()
        self._selector.activateWindow()

    def _on_region_selected(self, box: tuple[int, int, int, int]) -> None:
        self._selector = None
        try:
            lines = screen.recognize_region(box)
        except screen.ScreenCaptureError as e:
            self._error("取词失败", e)
            return
        self._adopt_ocr_lines(lines, "框选区域")

    def _adopt_ocr_lines(self, lines, label: str) -> None:
        segs = ocr.lines_to_segments(lines)
        if not segs:
            QMessageBox.information(self, "提示", "没有识别到文字，换个区域或图片再试")
            return
        proj = Project(name=label, kind=MediaKind.IMAGE)
        for seg in segs:
            proj.add_segment(seg.source, SegmentKind.LINE)
        self._adopt(proj, str(Path.home() / f"{label}.png"), "image")

    def open_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频或音频", "",
            "媒体 (*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac);;所有文件 (*)",
        )
        if not path:
            return
        QMessageBox.information(
            self, "语音识别",
            f"将使用模型 {self.settings.model_name} 识别，"
            "首次使用需下载模型，识别在后台进行，界面不会卡住。",
        )
        self._pending_video = path
        self._set_busy(True, "正在识别语音……")
        self._worker = TranscribeWorker(path, self.settings.model_name)
        self._worker.finished_ok.connect(self._on_transcribed)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def _on_transcribed(self, caps, lang: str) -> None:
        from ..io.asr import captions_to_segments

        path = self._pending_video
        proj = Project(name=Path(path).stem, kind=MediaKind.VIDEO, source_path=path)
        for seg in captions_to_segments(caps):
            proj.add_segment(seg.source, seg.kind, seg.start, seg.end)
        self._adopt(proj, path, "video")
        self.lbl_project.setText(
            f"{proj.name}（{proj.total} 句，识别语言 {lang or '未知'}）"
        )
        self._set_busy(False)
        if proj.total == 0:
            QMessageBox.information(self, "提示", "没有识别到语音内容")

    def _on_worker_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "任务失败", message)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        """忙时禁用会冲突的按钮，并在状态栏显示进度。"""
        for b in (self.btn_open, self.btn_open_pdf, self.btn_open_ocr,
                  self.btn_open_video, self.btn_overlay, self.btn_burn):
            b.setEnabled(not busy and self._button_should_enable(b))
        if busy:
            self.lbl_project.setText(message)
            self.progress.setRange(0, 0)      # 不确定进度，走循环动画
        else:
            self.progress.setRange(0, 100)
            self.refresh_progress()

    def _button_should_enable(self, button) -> bool:
        """忙结束后恢复按钮时，按当前状态判断该不该启用。"""
        if button is self.btn_overlay:
            return self.project is not None
        if button is self.btn_burn:
            return self.project is not None and self.project.kind == MediaKind.VIDEO
        return True

    # ---------- 列表与导航 ----------

    def refresh_list(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        if not self.project:
            self.list.blockSignals(False)
            return
        for seg in self.project.segments:
            mark = "✓" if seg.translated else "○"
            text = seg.source[:40] + ("…" if len(seg.source) > 40 else "")
            item = QListWidgetItem(f"{mark} {seg.index + 1}. {text}")
            if seg.kind == SegmentKind.CAPTION:
                item.setToolTip(f"{seg.start:.1f}s - {seg.end:.1f}s")
            self.list.addItem(item)
        if self.session:
            self.list.setCurrentRow(self.session.index)
        self.list.blockSignals(False)

    def on_select(self, row: int) -> None:
        if not self.session or row < 0:
            return
        self.session.jump(row)
        seg = self.session.current
        if seg:
            self.txt_source.setPlainText(seg.source)
            self.txt_target.setPlainText(seg.target)
        self.refresh_progress()

    def navigate(self, delta: int) -> None:
        if not self.session:
            return
        if delta > 0:
            self.session.advance()
        else:
            self.session.back()
        self._sync_current()

    def goto_untranslated(self) -> None:
        if not self.session:
            return
        self.session.jump_to_next_untranslated()
        self._sync_current()

    def save_current(self) -> None:
        if not self.session:
            return
        self.session.commit(self.txt_target.toPlainText(), advance=False)
        self.session.save()
        self.refresh_list()
        self.refresh_progress()

    def _sync_current(self) -> None:
        if not self.session:
            return
        self.list.setCurrentRow(self.session.index)
        seg = self.session.current
        if seg:
            self.txt_source.setPlainText(seg.source)
            self.txt_target.setPlainText(seg.target)
        self.refresh_progress()

    def refresh_progress(self) -> None:
        if not self.project:
            self.progress.setValue(0)
            return
        pct = int(self.project.progress * 100)
        self.progress.setValue(pct)
        self.progress.setFormat(f"{self.project.done}/{self.project.total} 已译 {pct}%")

    # ---------- 浮窗 ----------

    def show_overlay(self) -> None:
        if not self.session:
            return
        if self.overlay is None:
            self.overlay = OverlayWindow(
                self.session,
                opacity=self.settings.overlay_opacity,
                width=self.settings.overlay_width,
                position=self.settings.overlay_position,
            )
            self.overlay.progressed.connect(self._on_overlay_progress)
            self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.refresh()

    def _on_overlay_progress(self) -> None:
        self.refresh_list()
        self.refresh_progress()

    def _on_overlay_closed(self) -> None:
        self.overlay = None
        self.refresh_list()
        self.refresh_progress()

    # ---------- 导出 ----------

    def _ensure(self) -> bool:
        if not self.project:
            QMessageBox.warning(self, "提示", "请先导入原文")
            return False
        return True

    def export_word(self) -> None:
        if not self._ensure():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Word", f"{self.project.name}.docx", "Word (*.docx)"
        )
        if not path:
            return
        try:
            word.export_word(
                self.project, path,
                style=self.settings.word_style,
                asset_dir=self.store.asset_dir if self.store else None,
            )
        except Exception as e:
            self._error("导出失败", e)
            return
        QMessageBox.information(self, "完成", f"已导出：{path}")

    def export_soft(self) -> None:
        if not self._ensure():
            return
        if self.project.kind != MediaKind.VIDEO:
            QMessageBox.warning(self, "提示", "当前项目不是视频，无字幕可导出")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择字幕输出目录")
        if not out_dir:
            return
        try:
            res = video.export_soft_subtitles(
                self.project.source_path, self.project, out_dir,
                self.settings.subtitle_style(), self.settings.bilingual,
            )
        except Exception as e:
            self._error("导出失败", e)
            return
        QMessageBox.information(
            self, "完成", f"已导出：\n{res['srt']}\n{res['ass']}"
        )

    def burn_hard(self) -> None:
        if not self._ensure():
            return
        if self.project.kind != MediaKind.VIDEO:
            QMessageBox.warning(self, "提示", "当前项目不是视频，无法烧录")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出带字幕的视频", f"{self.project.name}_sub.mp4", "MP4 (*.mp4)"
        )
        if not path:
            return
        self._set_busy(True, "正在烧录字幕，需重新编码，请稍候……")
        self._burn_worker = BurnWorker(
            self.project.source_path, self.project, path,
            self.settings.subtitle_style(), self.settings.bilingual,
        )
        self._burn_worker.finished_ok.connect(self._on_burn_done)
        self._burn_worker.failed.connect(self._on_worker_failed)
        self._burn_worker.start()

    def _on_burn_done(self, path: str) -> None:
        self._set_busy(False)
        QMessageBox.information(self, "完成", f"已输出：{path}")

    # ---------- 杂项 ----------

    def _error(self, title: str, exc: Exception) -> None:
        QMessageBox.critical(self, title, str(exc))
