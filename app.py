"""设计底稿导出 1.2.0

Copyright © 2026 lazysci.com 懒研科技
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from qt_compat import (
    AlignCenter,
    Antialiasing,
    DashLine,
    InOutSine,
    LeftButton,
    NoBrush,
    NoFrame,
    PointingHandCursor,
    QApplication,
    QCheckBox,
    QCloseEvent,
    QColor,
    QComboBox,
    QDesktopServices,
    QDialog,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QEvent,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QMouseEvent,
    QObject,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QProgressBar,
    QPropertyAnimation,
    QPushButton,
    QSettings,
    QTextBrowser,
    QTextEdit,
    QThread,
    QUrl,
    QVBoxLayout,
    QWidget,
    WindowMinimized,
    WindowStateChange,
    Signal,
    Slot,
    qt_exec,
    ui_font,
)

from brand import (
    APP_NAME,
    COMPANY,
    COPYRIGHT,
    INFO_HTML,
    SITE,
    SITE_URL,
    VERSION,
)
from export_kind import ExportKind
from source_scan import (
    clean_path_text,
    is_ephemeral_path,
    is_unstable_output,
    path_key,
    prepare_sources,
    suggest_output_dir,
    user_desktop,
)

PREF_KEYS = (
    "output_dir",
    "export_kind",
    "split_by_page",
    "overwrite",
    "open_after",
)


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(base) / relative


def app_icon() -> QIcon:
    for name in ("assets/app.ico", "assets/app_icon.png"):
        icon_file = resource_path(name)
        if icon_file.is_file():
            return QIcon(str(icon_file))
    return QIcon()


class ConvertWorker(QObject):
    progressed = Signal(int, int, str)
    finished = Signal(int, int, int, list, str)

    def __init__(
        self,
        sources: List[Path],
        outdir: Path,
        force: bool,
        export_kind: ExportKind,
        split_pages: bool,
        stop_event: threading.Event,
    ) -> None:
        super().__init__()
        self._sources = sources
        self._outdir = outdir
        self._force = force
        self._export_kind = export_kind
        self._split_pages = split_pages
        self._stop_event = stop_event

    @Slot()
    def run(self) -> None:
        # 延迟加载转换库，避免窗口出现前在 Win7 上卡很久。
        from convert import convert_sources

        try:
            def progress(index: int, total: int, _src: Path, message: str) -> None:
                self.progressed.emit(index, total, message)

            batch = convert_sources(
                self._sources,
                self._outdir,
                force=self._force,
                recursive=False,
                progress=progress,
                should_stop=self._stop_event.is_set,
                export_kind=self._export_kind,
                split_pages=self._split_pages,
            )
            last_dir = str(batch.last_output_dir or self._outdir.resolve())
            handled = [str(path) for path in batch.handled]
            self.finished.emit(batch.ok, batch.skipped, batch.failed, handled, last_dir)
        except Exception as exc:
            self.progressed.emit(0, 1, f"任务异常: {exc}")
            handled = [str(path) for path in self._sources]
            self.finished.emit(0, 0, 1, handled, str(self._outdir))


class DropZone(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setFrameShape(NoFrame)
        self._hover = False
        layout = QVBoxLayout(self)
        layout.setAlignment(AlignCenter)
        self._recognizing = False
        self.title = QLabel("把文件拖到这里")
        self.title.setObjectName("dropTitle")
        self.title.setAlignment(AlignCenter)
        self.hint = QLabel("AI / PSD / zip 会自动识别。先解压到桌面更稳")
        self.hint.setObjectName("dropHint")
        self.hint.setAlignment(AlignCenter)
        self.hint.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)

    def set_recognizing(self, busy: bool) -> None:
        self._recognizing = busy
        if busy:
            self._hover = False
            self.title.setText("正在识别…")
        else:
            self.title.setText("把文件拖到这里")
        self.update()

    def set_hover(self, hover: bool) -> None:
        if self._recognizing:
            return
        self._hover = hover
        self.title.setText("松开即可加入队列" if hover else "把文件拖到这里")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        if self._hover:
            fill = QColor("#e5f4ea")
            stripe = QColor(47, 111, 62, 36)
            border = QColor("#2f6f3e")
        else:
            fill = QColor("#eef1f6")
            stripe = QColor(107, 114, 128, 40)
            border = QColor("#8b93a7")

        painter = QPainter(self)
        painter.setRenderHint(Antialiasing)
        box = self.rect().adjusted(1, 1, -2, -2)
        path = QPainterPath()
        path.addRoundedRect(box, 12, 12)
        painter.fillPath(path, fill)

        painter.save()
        painter.setClipPath(path)
        painter.setPen(QPen(stripe, 1.25))
        step = 9
        width = self.width()
        height = self.height()
        start = -height
        while start < width:
            painter.drawLine(start, height, start + height, 0)
            start += step
        painter.restore()

        pen = QPen(border, 2)
        pen.setStyle(DashLine)
        pen.setDashPattern([5, 4])
        painter.setPen(pen)
        painter.setBrush(NoBrush)
        painter.drawRoundedRect(box, 12, 12)
        painter.end()


class FooterLink(QLabel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(COPYRIGHT, parent)
        self.setObjectName("copyright")
        self.setAlignment(AlignCenter)
        self.setCursor(PointingHandCursor)
        self.setToolTip(SITE_URL)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.55)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(2400)
        anim.setStartValue(0.32)
        anim.setKeyValueAt(0.5, 0.92)
        anim.setEndValue(0.32)
        anim.setEasingCurve(InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._breath = anim

    def set_animating(self, running: bool) -> None:
        if running:
            self._breath.start()
        else:
            self._breath.stop()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == LeftButton:
            QDesktopServices.openUrl(QUrl(SITE_URL))
        super().mouseReleaseEvent(event)


class InfoDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用说明")
        self.setWindowIcon(app_icon())
        self.resize(480, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        browser = QTextBrowser()
        browser.setHtml(INFO_HTML)
        browser.setFrameShape(NoFrame)
        layout.addWidget(browser)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(600, 680)
        self.setMinimumSize(500, 580)
        self.setAcceptDrops(True)

        self._settings = QSettings(COMPANY, APP_NAME)
        self._paths: List[Path] = []
        self._stop_event = threading.Event()
        self._thread: Optional[QThread] = None
        self._worker: Optional[ConvertWorker] = None
        self._busy = False
        self._recognizing = False
        self._last_output_dir: Optional[Path] = None
        self._run_outdir: Optional[Path] = None
        self._run_open_after = False

        self._build()
        self._restore_prefs()
        self._update_queue_label()
        self._update_open_btn()

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        intro = QLabel("拖入设计文件，导出 PDF、PNG 或 JPEG 底稿。")
        intro.setObjectName("intro")
        header.addWidget(intro, 1)
        info_btn = QPushButton("使用说明")
        info_btn.setObjectName("ghostBtn")
        info_btn.clicked.connect(self._show_info)
        header.addWidget(info_btn)
        layout.addLayout(header)

        self.drop_zone = DropZone()
        self.drop_zone.setFixedHeight(120)
        layout.addWidget(self.drop_zone)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出到"))
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("选择保存文件夹")
        self.out_edit.setAcceptDrops(False)
        self.out_edit.textChanged.connect(self._update_open_btn)
        out_row.addWidget(self.out_edit, 1)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._pick_output)
        out_row.addWidget(browse_btn)
        self.remember_box = QCheckBox("记住设置")
        self.remember_box.setChecked(True)
        self.remember_box.setToolTip("下次打开时保留输出文件夹和勾选。不勾选则不记住。")
        self.remember_box.toggled.connect(self._on_remember_toggled)
        out_row.addWidget(self.remember_box)
        layout.addLayout(out_row)

        option_row = QHBoxLayout()
        option_row.addWidget(QLabel("导出为"))
        self.format_box = QComboBox()
        self.format_box.addItem("PDF", ExportKind.PDF.value)
        self.format_box.addItem("PNG 图片", ExportKind.PNG.value)
        self.format_box.addItem("JPEG 图片", ExportKind.JPEG.value)
        option_row.addWidget(self.format_box)
        self.split_box = QCheckBox("按页分割")
        self.split_box.setChecked(False)
        self.split_box.setToolTip("多页内容拆成多个文件。PDF 一页一个 PDF，图片一页一张图。")
        option_row.addWidget(self.split_box)
        self.force_box = QCheckBox("覆盖已有文件")
        self.force_box.setToolTip("输出文件夹里已有同名结果时直接覆盖。不勾选则跳过。")
        option_row.addWidget(self.force_box)
        self.open_after_box = QCheckBox("完成后打开")
        self.open_after_box.setToolTip("全部导出成功后自动打开输出文件夹。停止或失败时不会打开。")
        option_row.addWidget(self.open_after_box)
        option_row.addStretch(1)
        layout.addLayout(option_row)

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("导出")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        self.open_btn = QPushButton("打开输出文件夹")
        self.open_btn.setObjectName("openBtn")
        self.open_btn.clicked.connect(lambda: self._open_output())
        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addStretch(1)
        action_row.addWidget(self.open_btn)
        layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        log_header = QHBoxLayout()
        self.queue_label = QLabel("日志")
        self.queue_label.setObjectName("logTitle")
        log_header.addWidget(self.queue_label)
        log_header.addStretch(1)
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setObjectName("ghostBtn")
        clear_log_btn.clicked.connect(self._clear_log)
        clear_btn = QPushButton("清空队列")
        clear_btn.setObjectName("ghostBtn")
        clear_btn.clicked.connect(self._clear_files)
        self.clear_btn = clear_btn
        log_header.addWidget(clear_log_btn)
        log_header.addWidget(clear_btn)
        layout.addLayout(log_header)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAcceptDrops(False)
        self.log.setPlaceholderText("拖入文件后，加入记录和导出结果都会显示在这里")
        layout.addWidget(self.log, 1)

        self._footer = FooterLink()
        layout.addWidget(self._footer)

    def _save_bool(self, key: str, value: bool) -> None:
        self._settings.setValue(key, 1 if value else 0)

    def _set_exporting(self, busy: bool) -> None:
        self._busy = busy
        self.setAcceptDrops(not busy)
        self.drop_zone.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        if busy:
            self.drop_zone.set_hover(False)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == WindowStateChange:
            minimized = bool(self.windowState() & WindowMinimized)
            self._footer.set_animating(not minimized)
        super().changeEvent(event)

    def _show_info(self) -> None:
        dialog = InfoDialog(self)
        qt_exec(dialog)

    def _current_kind(self) -> ExportKind:
        value = str(self.format_box.currentData() or "pdf").lower()
        for kind in ExportKind:
            if kind.value == value:
                return kind
        return ExportKind.PDF

    def _urls_to_paths(self, event: QDropEvent) -> List[Path]:
        paths: List[Path] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(Path(local))
        return paths

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_zone.set_hover(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.drop_zone.set_hover(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self.drop_zone.set_hover(False)
        paths = self._urls_to_paths(event)
        if paths:
            event.acceptProposedAction()
            self._add_paths(paths)
        else:
            event.ignore()

    def _pick_output(self) -> None:
        current = clean_path_text(self.out_edit.text())
        if current and not is_unstable_output(Path(current)):
            start = current
        else:
            start = str(user_desktop())
        folder = QFileDialog.getExistingDirectory(self, "选择输出文件夹", start)
        if folder:
            self.out_edit.setText(folder)
            self._persist_prefs()

    def _setting_bool(self, key: str, default: bool = False) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        return str(value or "").lower() in ("1", "true", "yes")

    def _on_remember_toggled(self) -> None:
        self._persist_prefs()

    def _persist_prefs(self) -> None:
        remembering = self.remember_box.isChecked()
        self._save_bool("remember_prefs", remembering)
        if not remembering:
            for key in PREF_KEYS:
                self._settings.remove(key)
            return
        text = clean_path_text(self.out_edit.text())
        if text:
            folder = Path(text)
            if folder.is_dir() and not is_unstable_output(folder):
                self._settings.setValue("output_dir", str(folder))
            else:
                self._settings.remove("output_dir")
        self._settings.setValue("export_kind", self._current_kind().value)
        self._save_bool("split_by_page", self.split_box.isChecked())
        self._save_bool("overwrite", self.force_box.isChecked())
        self._save_bool("open_after", self.open_after_box.isChecked())

    def _restore_prefs(self) -> None:
        remembering = self._setting_bool("remember_prefs", True)
        self.remember_box.blockSignals(True)
        self.remember_box.setChecked(remembering)
        self.remember_box.blockSignals(False)
        if not remembering:
            return
        saved = clean_path_text(str(self._settings.value("output_dir", "") or ""))
        if saved and Path(saved).is_dir() and not is_unstable_output(Path(saved)):
            self.out_edit.setText(saved)
        elif saved:
            self._settings.remove("output_dir")
        kind = str(self._settings.value("export_kind", "pdf") or "pdf").lower()
        for index in range(self.format_box.count()):
            data = str(self.format_box.itemData(index) or "")
            if data.lower() == kind:
                self.format_box.setCurrentIndex(index)
                break
        self.split_box.setChecked(self._setting_bool("split_by_page"))
        self.force_box.setChecked(self._setting_bool("overwrite"))
        self.open_after_box.setChecked(self._setting_bool("open_after"))

    def _add_paths(self, paths: List[Path]) -> None:
        if self._busy:
            self._append_log("正在导出，请等待结束后再加入文件")
            return
        if self._recognizing:
            self._append_log("正在识别，请稍后再加入文件")
            return
        self._recognizing = True
        self.drop_zone.set_recognizing(True)
        self._update_queue_label()
        self._append_log("正在识别拖入的文件…")
        QApplication.processEvents()
        try:
            prepared = prepare_sources(paths, recursive=True)
            for note in prepared.notes:
                self._append_log(note)
            added = prepared.files
            if not added:
                if not prepared.notes:
                    self._append_log("没有支持的设计文件")
                return
            existing = {path_key(path) for path in self._paths}
            new_items = [path for path in added if path_key(path) not in existing]
            if not new_items:
                self._append_log("这些文件已经在队列里")
                return
            self._paths.extend(new_items)
            if not clean_path_text(self.out_edit.text()):
                suggested = suggest_output_dir(paths)
                self.out_edit.setText(str(suggested))
                if any(is_ephemeral_path(path) for path in paths):
                    self._append_log("文件来自聊天或临时目录，输出已放到桌面「导出结果」，避免微信清理后找不到")
            for path in new_items:
                self._append_log(f"加入  {path.name}")
            self._append_log(f"当前队列 {len(self._paths)} 个文件")
            self._update_queue_label()
        finally:
            self._recognizing = False
            self.drop_zone.set_recognizing(False)
            self._update_queue_label()

    def _clear_files(self) -> None:
        if self._busy or self._recognizing:
            self._append_log("正在处理，无法清空队列")
            return
        self._paths = []
        self._append_log("已清空队列")
        self._update_queue_label()

    def _clear_log(self) -> None:
        self.log.clear()

    def _update_queue_label(self) -> None:
        count = len(self._paths)
        if count:
            self.queue_label.setText(f"日志 · 队列 {count} 个文件")
        else:
            self.queue_label.setText("日志")
        self.start_btn.setEnabled(count > 0 and not self._busy and not self._recognizing)

    def _append_log(self, message: str) -> None:
        self.log.append(message)

    def _start(self) -> None:
        if self._busy or self._recognizing or self._thread is not None:
            return
        if not self._paths:
            self._append_log("请先把设计文件拖进窗口")
            return
        if not clean_path_text(self.out_edit.text()):
            self._pick_output()
            if not clean_path_text(self.out_edit.text()):
                self._append_log("还没有选择输出文件夹")
                return
        outdir = Path(clean_path_text(self.out_edit.text()))
        if is_unstable_output(outdir):
            outdir = user_desktop() / "导出结果"
            self.out_edit.setText(str(outdir))
            self._append_log("原输出位置不稳定（聊天缓存或临时目录），已改到桌面「导出结果」")
        try:
            outdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "无法创建输出目录", str(exc))
            return

        kind = self._current_kind()
        split = self.split_box.isChecked()
        self._persist_prefs()

        self._stop_event.clear()
        self._run_outdir = outdir
        self._last_output_dir = outdir
        self._run_open_after = self.open_after_box.isChecked()
        self._update_open_btn()
        self._set_exporting(True)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        split_note = "，按页分割" if split else ""
        self._append_log(f"开始导出 {kind.label}{split_note}  →  {outdir}")
        self._append_log(f"共 {len(self._paths)} 个文件")

        self._thread = QThread()
        self._worker = ConvertWorker(
            list(self._paths),
            outdir,
            self.force_box.isChecked(),
            kind,
            split,
            self._stop_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _stop(self) -> None:
        self._stop_event.set()
        self._append_log("正在停止…")

    def _on_progress(self, index: int, total: int, message: str) -> None:
        percent = 0 if total == 0 else int(index * 100 / total)
        self.progress.setValue(percent)
        self._append_log(f"[{index}/{total}] {message}")

    def _on_finished(self, ok: int, skipped: int, failed: int, handled: list, last_dir: str) -> None:
        self.stop_btn.setEnabled(False)
        stopped = self._stop_event.is_set()
        self._stop_event.clear()
        run_dir = self._run_outdir
        if last_dir:
            folder = Path(last_dir)
            if folder.is_dir():
                self._last_output_dir = folder
        handled_keys = {path_key(Path(item)) for item in handled}
        before = len(self._paths)
        self._paths = [path for path in self._paths if path_key(path) not in handled_keys]
        removed = before - len(self._paths)
        if removed:
            self._append_log(f"已从队列去掉 {removed} 个已处理文件")
        self._set_exporting(False)
        self._update_queue_label()
        self._update_open_btn()
        if stopped:
            summary = f"已停止：完成 {ok}，跳过 {skipped}，失败 {failed}"
        else:
            summary = f"导出结束：完成 {ok}，跳过 {skipped}，失败 {failed}"
        self._append_log(summary)
        if not stopped:
            self.progress.setValue(100)
        if failed and not stopped:
            QMessageBox.warning(self, "导出结束", summary)
        elif not stopped and self._run_open_after and ok > 0:
            self._open_output(run_dir)

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None
        self._set_exporting(False)
        self._update_queue_label()

    def _has_openable_output(self) -> bool:
        return any(
            self._as_existing_dir(candidate) is not None
            for candidate in (
                self.out_edit.text().strip(),
                self._run_outdir,
                self._last_output_dir,
            )
        )

    def _update_open_btn(self) -> None:
        ready = self._has_openable_output()
        self.open_btn.setProperty("ready", "true" if ready else "false")
        self.open_btn.setToolTip("打开已选好的输出文件夹" if ready else "先选择或成功导出后，即可打开输出文件夹")
        style = self.open_btn.style()
        style.unpolish(self.open_btn)
        style.polish(self.open_btn)
        self.open_btn.update()

    def _as_existing_dir(self, value: object) -> Optional[Path]:
        if isinstance(value, Path):
            folder = value
        elif isinstance(value, str) and clean_path_text(value):
            folder = Path(clean_path_text(value))
        else:
            return None
        try:
            folder = folder.expanduser()
        except OSError:
            return None
        if folder.is_dir():
            return folder
        return None

    def _open_output(self, preferred: object = None) -> None:
        # QPushButton.clicked 会传入 bool，不能把它当成路径。
        candidates: List[Optional[Path]] = [
            self._as_existing_dir(preferred),
            self._as_existing_dir(self._run_outdir),
            self._as_existing_dir(self.out_edit.text()),
            self._as_existing_dir(self._last_output_dir),
        ]
        seen = set()
        for candidate in candidates:
            if candidate is None:
                continue
            key = path_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            if open_local_dir(candidate):
                return
        self._pick_output()
        chosen = self._as_existing_dir(self.out_edit.text().strip())
        if chosen is None:
            return
        if not open_local_dir(chosen):
            self._append_log(f"无法打开文件夹: {chosen}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._recognizing:
            event.ignore()
            return
        self._stop_event.set()
        if self._thread is not None:
            deadline = time.monotonic() + 30.0
            while self._thread is not None and time.monotonic() < deadline:
                QApplication.processEvents()
                if self._thread is not None:
                    self._thread.wait(100)
            if self._thread is not None:
                event.ignore()
                QMessageBox.warning(self, APP_NAME, "正在结束导出，请稍候再关闭窗口。")
                return
        super().closeEvent(event)


STYLESHEET = """
QWidget {
    font-size: 13px;
    color: #1f2430;
    background: #f6f6f4;
}
QLabel#intro {
    color: #4b5563;
}
QLabel#logTitle {
    font-weight: 600;
}
QFrame#dropZone {
    background: transparent;
    border: none;
}
QLabel#dropTitle {
    font-size: 20px;
    font-weight: 600;
    background: transparent;
}
QLabel#dropHint {
    color: #5b6577;
    background: transparent;
}
QTextEdit, QLineEdit, QComboBox, QTextBrowser {
    background: #ffffff;
    border: 1px solid #d5d8e0;
    border-radius: 6px;
    padding: 6px 8px;
}
QTextEdit {
    font-family: "Consolas", "Microsoft YaHei", monospace;
    font-size: 12px;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #c7ccd8;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover {
    background: #eef1f6;
}
QPushButton#ghostBtn {
    padding: 4px 10px;
    color: #3b4354;
}
QPushButton#startBtn {
    background: #1f2430;
    color: #ffffff;
    border: none;
    padding: 8px 22px;
    font-weight: 600;
}
QPushButton#startBtn:hover {
    background: #2d3546;
}
QPushButton#startBtn:disabled {
    background: #9aa3b2;
}
QPushButton#openBtn[ready="true"] {
    background: #e7f3ea;
    color: #21532c;
    border: 1px solid #2f6f3e;
    font-weight: 600;
}
QPushButton#openBtn[ready="true"]:hover {
    background: #d5ead9;
}
QProgressBar {
    border: none;
    border-radius: 3px;
    background: #e4e7ee;
    height: 8px;
    max-height: 8px;
}
QProgressBar::chunk {
    background: #2f6f3e;
    border-radius: 3px;
}
QLabel#copyright {
    color: #6b7280;
    font-size: 12px;
    padding-top: 2px;
    background: transparent;
}
"""


def open_local_dir(path: Path) -> bool:
    try:
        folder = path.resolve()
    except OSError:
        return False
    if not folder.is_dir():
        return False
    target = os.path.normpath(str(folder))
    if sys.platform == "win32":
        try:
            result = int(ctypes.windll.shell32.ShellExecuteW(None, "explore", target, None, None, 1))
            if result > 32:
                return True
        except (AttributeError, OSError, ValueError):
            pass
        try:
            os.startfile(target)
            return True
        except OSError:
            pass
        try:
            subprocess.Popen(["explorer.exe", target])
            return True
        except OSError:
            return False
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(target)))


def _warmup_convert() -> None:
    try:
        import convert  # noqa: F401
    except Exception:
        pass


def start_convert_warmup() -> None:
    thread = threading.Thread(target=_warmup_convert, name="warmup-convert", daemon=True)
    thread.start()


def main() -> int:
    if "--cli" in sys.argv or "-h" in sys.argv or "--help" in sys.argv:
        # 命令行才加载转换库；窗口启动走轻量路径。
        from convert import main_cli

        return main_cli()

    app = QApplication(sys.argv)
    icon = app_icon()
    app.setWindowIcon(icon)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName(COMPANY)
    app.setOrganizationDomain(SITE)
    app.setStyle("Fusion")
    app.setFont(ui_font(10))
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    start_convert_warmup()
    return qt_exec(app)


if __name__ == "__main__":
    raise SystemExit(main())
