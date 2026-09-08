"""导出格式枚举。单独放，避免窗口启动时加载转换库。"""

from __future__ import annotations

from enum import Enum
from typing import NoReturn

try:
    from typing import assert_never
except ImportError:
    def assert_never(value: object) -> NoReturn:
        raise AssertionError("Unhandled value: {!r}".format(value))


class ExportKind(Enum):
    PDF = "pdf"
    PNG = "png"
    JPEG = "jpeg"

    @property
    def suffix(self) -> str:
        if self is ExportKind.PDF:
            return ".pdf"
        if self is ExportKind.PNG:
            return ".png"
        if self is ExportKind.JPEG:
            return ".jpg"
        assert_never(self)

    @property
    def label(self) -> str:
        if self is ExportKind.PDF:
            return "PDF"
        if self is ExportKind.PNG:
            return "PNG"
        if self is ExportKind.JPEG:
            return "JPEG"
        assert_never(self)
