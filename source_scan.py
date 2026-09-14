"""扫描待导出文件。不导入转换库，避免窗口启动和加入文件时在 Win7 上卡住。

expand_sources：只列当前能看到的文件（测试 / CLI）。
prepare_sources：窗口加入队列（zip、预览拖入、重试、必要时拷缓存）。
collect_batch_sources：导出时保留已失踪的路径，便于记失败。
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import stat
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

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

_ARCHIVE_HINTS = {".rar", ".7z"}
_ALLOWED = {ext.lower() for ext in SOURCE_EXTENSIONS}


@dataclass
class PrepareResult:
    files: List[Path] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


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


def win_long_path(path: Path) -> str:
    try:
        raw = os.path.abspath(str(Path(path)))
    except OSError:
        raw = str(path)
    if sys.platform != "win32" or raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def is_unc_path(path: Path) -> bool:
    text = str(path).replace("/", "\\")
    return text.startswith("\\\\") and not text.startswith("\\\\?\\")


def path_too_long(path: Path) -> bool:
    try:
        return len(os.path.abspath(str(path))) >= 240
    except OSError:
        return len(str(path)) >= 240


def exists_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.stat(win_long_path(path)).st_mode)
    except OSError:
        return False


def exists_dir(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.stat(win_long_path(path)).st_mode)
    except OSError:
        return False


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


def source_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        folder = Path(base) / "lazysci" / "design-export-cache"
    else:
        folder = user_desktop() / "设计底稿缓存"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def is_cache_path(path: Path) -> bool:
    try:
        return path_key(path.expanduser().resolve().parent) == path_key(source_cache_dir())
    except OSError:
        return False


def is_cache_location(path: Path) -> bool:
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        resolved = Path(path)
    try:
        cache = source_cache_dir().expanduser().resolve()
    except OSError:
        cache = source_cache_dir()
    text = path_key(resolved)
    root = path_key(cache)
    return text == root or text.startswith(root + os.sep)


def is_unstable_output(path: Path) -> bool:
    """聊天缓存、系统临时目录、程序内部缓存，都不能当输出文件夹。"""
    return is_ephemeral_path(path) or is_cache_location(path)


def suggest_output_dir(sources: Sequence[Path]) -> Path:
    safe = user_desktop() / "导出结果"
    if not sources:
        return safe
    parent = Path(sources[0]).parent
    sample = list(sources[:8])
    if is_unstable_output(parent) or any(is_unstable_output(item) for item in sample):
        return safe
    return parent / "导出结果"


def path_key(path: Path) -> str:
    raw = Path(path)
    try:
        raw = raw.expanduser().resolve()
    except OSError:
        raw = Path(path)
    return os.path.normcase(str(raw))


def split_zip_member(path: Path) -> Optional[Tuple[Path, str]]:
    text = str(path).replace("/", "\\")
    lowered = text.lower()
    mark = ".zip\\"
    index = lowered.find(mark)
    if index < 0:
        return None
    zip_path = Path(text[: index + 4])
    member = text[index + 5 :].replace("\\", "/")
    if not member:
        return None
    return zip_path, member


def wait_readable(path: Path, tries: int = 5, delay: float = 0.25) -> Tuple[bool, bool]:
    """返回 (能否读, 是否重试过)。给网盘未同步完、电脑卡、压缩软件刚写出的文件用。"""
    retried = False
    last_size = -1
    for attempt in range(tries):
        try:
            info = os.stat(win_long_path(path))
            if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
                raise OSError("empty")
            with open(win_long_path(path), "rb") as handle:
                chunk = handle.read(64)
            if not chunk:
                raise OSError("empty")
            if info.st_size == last_size:
                return True, retried
            last_size = info.st_size
            if attempt == 0:
                return True, False
        except OSError:
            pass
        if attempt + 1 < tries:
            retried = True
            time.sleep(delay)
    return False, retried


def needs_local_copy(path: Path, retried: bool) -> bool:
    if is_cache_path(path):
        return False
    return retried or is_ephemeral_path(path) or is_unc_path(path) or path_too_long(path)


def copy_to_cache(src: Path) -> Path:
    digest = hashlib.sha1(path_key(src).encode("utf-8", "surrogateescape")).hexdigest()[:8]
    stem = src.stem[:40] or "file"
    dest = source_cache_dir() / f"{stem}_{digest}{src.suffix.lower()}"
    shutil.copy2(win_long_path(src), win_long_path(dest))
    return dest


def _safe_zip_base(name: str) -> Optional[str]:
    raw = name.replace("\\", "/")
    if not raw or raw.endswith("/") or ".." in raw.split("/"):
        return None
    base = Path(raw).name
    if Path(base).suffix.lower() not in _ALLOWED:
        return None
    return base


def extract_from_zip(zip_path: Path, members: Optional[Sequence[str]] = None) -> List[Path]:
    written: List[Path] = []
    try:
        archive = zipfile.ZipFile(win_long_path(zip_path), "r")
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return written
    try:
        names = archive.namelist()
        wanted = list(members) if members else names
        lower_map = {item.replace("\\", "/").lower(): item for item in names}
        for raw in wanted:
            key = raw.replace("\\", "/").lower()
            real = lower_map.get(key)
            if real is None:
                real = lower_map.get(Path(raw.replace("\\", "/")).name.lower())
            if real is None:
                continue
            base = _safe_zip_base(real)
            if base is None:
                continue
            digest = hashlib.sha1(
                "{}|{}".format(path_key(zip_path), real).encode("utf-8", "surrogateescape")
            ).hexdigest()[:8]
            dest = source_cache_dir() / f"{Path(base).stem[:40]}_{digest}{Path(base).suffix.lower()}"
            try:
                with archive.open(real) as source, open(win_long_path(dest), "wb") as target:
                    shutil.copyfileobj(source, target)
                written.append(dest)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                continue
    finally:
        archive.close()
    return written


def _materialize(path: Path, tries: int = 5, delay: float = 0.25) -> Tuple[Optional[Path], List[str]]:
    notes: List[str] = []
    ok, retried = wait_readable(path, tries=tries, delay=delay)
    if not ok:
        notes.append(
            f"暂时读不到 {path.name}（电脑较卡或文件还在写入），请稍后再拖，或先复制到桌面"
        )
        return None, notes
    if needs_local_copy(path, retried):
        try:
            cached = copy_to_cache(path)
            if retried:
                notes.append(f"文件刚刚才读到，已把 {path.name} 复制到本地")
            else:
                notes.append(f"已把 {path.name} 复制到本地再处理")
            return cached, notes
        except OSError:
            notes.append(f"{path.name} 已找到，但复制本地失败，仍按原路径尝试")
            return path, notes
    return path, notes


def prepare_sources(paths: Sequence[Path], recursive: bool = True) -> PrepareResult:
    """加入队列前展开 zip、等待可读、必要时拷到本地缓存。"""
    result = PrepareResult()
    seen: Set[str] = set()

    def add(item: Path) -> None:
        key = path_key(item)
        if key in seen:
            return
        seen.add(key)
        result.files.append(item)

    for raw in paths:
        path = Path(clean_path_text(str(raw))).expanduser()
        inner = split_zip_member(path)
        if inner is not None:
            zip_path, member = inner
            if exists_file(zip_path):
                extracted = extract_from_zip(zip_path, [member])
                if extracted:
                    result.notes.append(f"已从压缩包取出 {extracted[0].name}")
                    for item in extracted:
                        add(item)
                else:
                    result.notes.append("压缩包里没有可用的设计文件，请先解压到桌面再拖")
            else:
                result.notes.append("请先解压到桌面再拖，不要从压缩包预览窗口里直接拖文件")
            continue
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        suffix = resolved.suffix.lower()
        if exists_file(resolved) and suffix == ".zip":
            extracted = extract_from_zip(resolved)
            if extracted:
                result.notes.append(f"已从压缩包展开 {len(extracted)} 个文件")
                for item in extracted:
                    add(item)
            else:
                result.notes.append("压缩包里没有支持的设计文件，或需要密码，请先解压到桌面")
            continue
        if exists_file(resolved) and suffix in _ARCHIVE_HINTS:
            result.notes.append(f"暂不支持 {suffix} 压缩包，请先解压到桌面再拖入")
            continue
        if exists_file(resolved):
            candidates = [resolved]
        elif exists_dir(resolved):
            candidates = iter_source_files(resolved, recursive, SOURCE_EXTENSIONS)
            if not candidates:
                result.notes.append(f"文件夹里没有支持的设计文件：{resolved.name}")
        else:
            result.notes.append(f"找不到 {path.name}，请先解压到桌面，或等网盘同步完成后再拖")
            continue
        for item in candidates:
            if item.suffix.lower() not in _ALLOWED:
                continue
            ready, notes = _materialize(item)
            result.notes.extend(notes)
            if ready is not None:
                add(ready)
    return result


def iter_source_files(root: Path, recursive: bool, exts: Sequence[str]) -> List[Path]:
    allowed = {ext.lower() for ext in exts}
    files = root.rglob("*") if recursive else root.glob("*")
    found = [
        path
        for path in files
        if exists_file(path) and path.suffix.lower() in allowed
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
        if exists_file(path):
            candidates = [path]
        elif exists_dir(path):
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
    found: List[Path] = []
    seen: Set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if exists_dir(resolved):
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
        if exists_file(resolved):
            if resolved.suffix.lower() not in _ALLOWED:
                continue
            found.append(resolved)
            continue
        found.append(path)
    return found
