"""扫描待导出文件。不导入转换库，避免窗口启动和加入文件时在 Win7 上卡住。"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import List, Sequence, Set

# 聊天缓存、系统临时目录：文件随时会消失，不能当稳定输出位置。
_EPHEMERAL_MARKERS = (
    "\\filestorage\\temp",
    "\\filestorage\\cache",
    "\\xwechat\\temp",
    "\\xwechat_files\\temp",
    "\\weixin\\temp",
    "\\wxwork\\temp",
    "\\wxwork files\\temp",
)

SOURCE_EXTENSIONS = (
    ".ai",
    ".eps",
    ".ps",
    ".psd",
    ".psb",
    ".svg",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
    ".tga",
    ".gif",
    ".indd",
    ".cdr",
    ".sketch",
    ".xd",
    ".afdesign",
    ".afphoto",
)


def clean_path_text(text: str) -> str:
    value = (text or "").strip().strip('"').strip("'")
    if value.lower().startswith("file:"):
        rest = value[5:].lstrip("/")
        if rest.lower().startswith("localhost/"):
            rest = rest[10:]
        value = rest
    return value.strip()


def _norm_win(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def is_ephemeral_path(path: Path) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        resolved = Path(path)
    text = _norm_win(resolved)
    for env_name in ("TEMP", "TMP", "TMPDIR"):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            root = _norm_win(Path(raw).expanduser().resolve())
        except OSError:
            root = _norm_win(Path(raw))
        if text == root or text.startswith(root + os.sep):
            return True
    windir = os.environ.get("WINDIR") or r"C:\Windows"
    win_temp = _norm_win(Path(windir) / "Temp")
    if text == win_temp or text.startswith(win_temp + os.sep):
        return True
    lowered = text.replace("/", "\\")
    return any(marker in lowered for marker in _EPHEMERAL_MARKERS)


def user_desktop() -> Path:
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf) == 0:
                folder = Path(buf.value)
                if folder.is_dir():
                    return folder
        except (AttributeError, OSError, ValueError):
            pass
    for name in ("Desktop", "桌面"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return candidate
    return Path.home()


def suggest_output_dir(sources: Sequence[Path]) -> Path:
    safe = user_desktop() / "导出结果"
    if not sources:
        return safe
    parent = Path(sources[0]).parent
    sample = list(sources[:8])
    if is_ephemeral_path(parent) or any(is_ephemeral_path(item) for item in sample):
        return safe
    return parent / "导出结果"


def path_key(path: Path) -> str:
    raw = Path(path)
    try:
        raw = raw.expanduser().resolve()
    except OSError:
        raw = Path(path)
    return os.path.normcase(str(raw))


def iter_source_files(root: Path, recursive: bool, exts: Sequence[str]) -> List[Path]:
    allowed = {ext.lower() for ext in exts}
    files = root.rglob("*") if recursive else root.glob("*")
    found = [
        path
        for path in files
        if path.is_file() and path.suffix.lower() in allowed
    ]
    return sorted(found)


def expand_sources(paths: Sequence[Path], recursive: bool = True) -> List[Path]:
    allowed = {ext.lower() for ext in SOURCE_EXTENSIONS}
    found: List[Path] = []
    seen: Set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            path = path.resolve()
        except OSError:
            continue
        if path.is_file():
            candidates = [path]
        elif path.is_dir():
            candidates = iter_source_files(path, recursive, SOURCE_EXTENSIONS)
        else:
            continue
        for item in candidates:
            if item.suffix.lower() not in allowed:
                continue
            key = path_key(item)
            if key in seen:
                continue
            seen.add(key)
            found.append(item)
    return found


def collect_batch_sources(paths: Sequence[Path], recursive: bool = True) -> List[Path]:
    """展开目录；失踪的源文件也保留，便于记失败并从队列移除。"""
    allowed = {ext.lower() for ext in SOURCE_EXTENSIONS}
    found: List[Path] = []
    seen: Set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved.is_dir():
            for item in iter_source_files(resolved, recursive, SOURCE_EXTENSIONS):
                key = path_key(item)
                if key in seen:
                    continue
                seen.add(key)
                found.append(item)
            continue
        key = path_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            if resolved.suffix.lower() not in allowed:
                continue
            found.append(resolved)
            continue
        found.append(path)
    return found
