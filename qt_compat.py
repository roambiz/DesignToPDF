"""Qt 绑定：优先 PySide6，没有则用 PySide2（Windows 7）。"""

from __future__ import annotations

try:
    from PySide6.QtCore import (  # type: ignore
        QEasingCurve,
        QObject,
        QPropertyAnimation,
        QSettings,
        Qt,
        QThread,
        QUrl,
        Signal,
        Slot,
    )
    from PySide6.QtCore import QEvent  # type: ignore
    from PySide6.QtGui import (  # type: ignore
        QCloseEvent,
        QColor,
        QDesktopServices,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDragMoveEvent,
        QDropEvent,
        QFont,
        QIcon,
        QMouseEvent,
        QPainter,
        QPainterPath,
        QPaintEvent,
        QPen,
    )
    from PySide6.QtWidgets import (  # type: ignore
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QTextBrowser,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    from PySide2.QtCore import (  # type: ignore
        QEasingCurve,
        QObject,
        QPropertyAnimation,
        QSettings,
        Qt,
        QThread,
        QUrl,
        Signal,
        Slot,
    )
    from PySide2.QtCore import QEvent  # type: ignore
    from PySide2.QtGui import (  # type: ignore
        QCloseEvent,
        QColor,
        QDesktopServices,
        QDragEnterEvent,
        QDragLeaveEvent,
        QDragMoveEvent,
        QDropEvent,
        QFont,
        QIcon,
        QMouseEvent,
        QPainter,
        QPainterPath,
        QPaintEvent,
        QPen,
    )
    from PySide2.QtWidgets import (  # type: ignore
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFrame,
        QGraphicsOpacityEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QTextBrowser,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

AlignCenter = Qt.AlignCenter if hasattr(Qt, "AlignCenter") else Qt.AlignmentFlag.AlignCenter
NoFrame = QFrame.NoFrame if hasattr(QFrame, "NoFrame") else QFrame.Shape.NoFrame
Antialiasing = QPainter.Antialiasing if hasattr(QPainter, "Antialiasing") else QPainter.RenderHint.Antialiasing
DashLine = Qt.DashLine if hasattr(Qt, "DashLine") else Qt.PenStyle.DashLine
NoBrush = Qt.NoBrush if hasattr(Qt, "NoBrush") else Qt.BrushStyle.NoBrush
PointingHandCursor = Qt.PointingHandCursor if hasattr(Qt, "PointingHandCursor") else Qt.CursorShape.PointingHandCursor
InOutSine = QEasingCurve.InOutSine if hasattr(QEasingCurve, "InOutSine") else QEasingCurve.Type.InOutSine
LeftButton = Qt.LeftButton if hasattr(Qt, "LeftButton") else Qt.MouseButton.LeftButton
WindowMinimized = Qt.WindowMinimized if hasattr(Qt, "WindowMinimized") else Qt.WindowState.WindowMinimized
WindowStateChange = (
    QEvent.WindowStateChange if hasattr(QEvent, "WindowStateChange") else QEvent.Type.WindowStateChange
)


def qt_exec(widget: QWidget) -> int:
    runner = getattr(widget, "exec", None)
    if runner is None:
        runner = widget.exec_
    return int(runner())


def ui_font(point_size: int = 10) -> QFont:
    return QFont("Microsoft YaHei", point_size)
