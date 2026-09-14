"""把设计文件转成可快速浏览的 PDF 或图片底稿。

目标不是还原可编辑源文件，而是在装不了 AI / PS 的电脑上预览画面。

设计底稿导出 1.2.1
Copyright © 2026 lazysci.com 懒研科技
"""

from __future__ import annotations

import argparse
import hashlib
import io
import mmap
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from export_kind import ExportKind, assert_never
from source_scan import (
    SOURCE_EXTENSIONS,
    collect_batch_sources,
    expand_sources,
    iter_source_files,
    wait_readable,
    win_long_path,
)

try:
    import win32com.client
except ImportError:
    win32com = None

from PIL import Image

try:
    from reportlab.graphics import renderPDF
    from svglib.svglib import svg2rlg
except ImportError:
    renderPDF = None
    svg2rlg = None

try:
    import pymupdf
except ImportError:
    pymupdf = None

from brand import APP_NAME, COPYRIGHT, VERSION

PDF_MAGIC = b"%PDF"
PDF_EOF = b"%%EOF"
JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
EPS_BINARY_MAGIC = b"\xc5\xd0\xd3\xc6"
PSD_MAGIC = b"8BPS"
MAX_COMPOSITE_PIXELS = 16_000_000
MAX_PREVIEW_SCAN = 120 * 1024 * 1024

INBOX_DIRNAME = "待转换"
OUTBOX_DIRNAME = "导出结果"


@dataclass(frozen=True)
class ConvertResult:
    method: str
    warning: str = ""


Handler = Callable[[Path, Path], ConvertResult]


@dataclass
class BatchResult:
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    handled: List[Path] = field(default_factory=list)
    last_output_dir: Optional[Path] = None


def script_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_inbox() -> Path:
    return script_dir() / INBOX_DIRNAME


def default_outbox() -> Path:
    return script_dir() / OUTBOX_DIRNAME


def ensure_work_folders() -> Tuple[Path, Path]:
    inbox = default_inbox()
    outbox = default_outbox()
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    return inbox, outbox


def which_exe(names: Sequence[str], extra_dirs: Sequence[Path]) -> Optional[str]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for folder in extra_dirs:
        for name in names:
            candidate = folder / name
            if candidate.is_file():
                return str(candidate)
    return None


def write_pdf_bytes(pdf_path: Path, data: bytes) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(data)


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode == "RGBA":
        bg = Image.new("RGB", image.size, (255, 255, 255))
        bg.paste(image, mask=image.split()[-1])
        return bg
    if image.mode == "CMYK":
        return image.convert("RGB")
    if image.mode == "P":
        return flatten_to_rgb(image.convert("RGBA"))
    if image.mode == "LA":
        return flatten_to_rgb(image.convert("RGBA"))
    return image.convert("RGB")


def images_to_pdf(images: Sequence[Image.Image], pdf_path: Path) -> None:
    if not images:
        raise RuntimeError("没有可写入 PDF 的图像")
    rgb_frames = [flatten_to_rgb(frame) for frame in images]
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    first = rgb_frames[0]
    extra = rgb_frames[1:]
    first.save(
        pdf_path,
        "PDF",
        resolution=150.0,
        save_all=bool(extra),
        append_images=extra,
    )


def image_bytes_to_pdf(data: bytes, pdf_path: Path, fmt: Optional[str] = None) -> None:
    with Image.open(io.BytesIO(data), formats=[fmt] if fmt else None) as image:
        frames: List[Image.Image] = []
        try:
            index = 0
            while True:
                image.seek(index)
                frames.append(image.copy())
                index += 1
        except EOFError:
            pass
        if not frames:
            frames = [image.copy()]
        images_to_pdf(frames, pdf_path)


def extract_embedded_pdf_bytes(data: bytes) -> Optional[bytes]:
    start = data.find(PDF_MAGIC)
    if start < 0:
        return None
    end = data.rfind(PDF_EOF)
    if end < start:
        payload = data[start:]
    else:
        payload = data[start : end + len(PDF_EOF)]
        after = end + len(PDF_EOF)
        if after < len(data) and data[after : after + 1] in (b"\n", b"\r"):
            payload += b"\n"
    if not payload.startswith(PDF_MAGIC):
        return None
    return payload


def read_prefix(path: Path, limit: int = MAX_PREVIEW_SCAN) -> bytes:
    with open(win_long_path(path), "rb") as fh:
        return fh.read(limit)


def extract_embedded_pdf_from_file(path: Path) -> Optional[bytes]:
    size = os.path.getsize(win_long_path(path))
    if size == 0:
        return None
    if size <= MAX_PREVIEW_SCAN:
        with open(win_long_path(path), "rb") as fh:
            return extract_embedded_pdf_bytes(fh.read())
    with open(win_long_path(path), "rb") as fh:
        mapped = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            start = mapped.find(PDF_MAGIC)
            if start < 0:
                return None
            end = mapped.rfind(PDF_EOF)
            if end < start:
                return bytes(mapped[start:])
            payload = bytes(mapped[start : end + len(PDF_EOF)])
            after = end + len(PDF_EOF)
            if after < len(mapped) and mapped[after : after + 1] in (b"\n", b"\r"):
                payload += b"\n"
            return payload
        finally:
            mapped.close()


def largest_jpeg_bytes(data: bytes) -> Optional[bytes]:
    best: Optional[bytes] = None
    cursor = 0
    limit = min(len(data), MAX_PREVIEW_SCAN)
    while cursor < limit:
        start = data.find(JPEG_SOI, cursor, limit)
        if start < 0:
            break
        end = data.find(JPEG_EOI, start + 2, limit)
        if end < 0:
            break
        chunk = data[start : end + 2]
        if best is None or len(chunk) > len(best):
            if len(chunk) < 4096:
                cursor = start + 2
                continue
            try:
                with Image.open(io.BytesIO(chunk)) as probe:
                    probe.verify()
                best = chunk
            except Exception:
                pass
        cursor = start + 2
    return best


def convert_with_pdf_payload(payload: bytes, pdf_path: Path, method: str) -> ConvertResult:
    write_pdf_bytes(pdf_path, payload)
    return ConvertResult(method)


def convert_raster(path: Path, pdf_path: Path) -> ConvertResult:
    frames: List[Image.Image] = []
    with Image.open(win_long_path(path)) as image:
        try:
            index = 0
            while True:
                image.seek(index)
                frames.append(image.copy())
                index += 1
        except EOFError:
            pass
        if not frames:
            frames = [image.copy()]
    images_to_pdf(frames, pdf_path)
    return ConvertResult("raster")


def convert_pdf(path: Path, pdf_path: Path) -> ConvertResult:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(win_long_path(path), win_long_path(pdf_path))
    return ConvertResult("copy")


def decode_packbits(data: bytes, expected: int) -> bytes:
    out = bytearray()
    i = 0
    length = len(data)
    while len(out) < expected and i < length:
        flag = data[i]
        i += 1
        if flag > 127:
            flag -= 256
        if 0 <= flag <= 127:
            count = flag + 1
            out.extend(data[i : i + count])
            i += count
        elif flag == -128:
            continue
        else:
            count = 1 - flag
            if i >= length:
                break
            out.extend([data[i]] * count)
            i += 1
    if len(out) < expected:
        out.extend(b"\x00" * (expected - len(out)))
    return bytes(out[:expected])


def _read_u32(buf: bytes, offset: int, psb: bool) -> Tuple[int, int]:
    if psb:
        return struct.unpack(">Q", buf[offset : offset + 8])[0], offset + 8
    return struct.unpack(">I", buf[offset : offset + 4])[0], offset + 4


def extract_psd_thumbnail(buf: bytes) -> Optional[Image.Image]:
    if len(buf) < 26 or buf[:4] != PSD_MAGIC:
        return None
    offset = 26
    color_len, offset = _read_u32(buf, offset, False)
    offset += color_len
    res_len, offset = _read_u32(buf, offset, False)
    end = offset + res_len
    while offset + 12 <= end and offset + 12 <= len(buf):
        if buf[offset : offset + 4] not in (b"8BIM", b"MeSa"):
            break
        offset += 4
        res_id = struct.unpack(">H", buf[offset : offset + 2])[0]
        offset += 2
        name_len = buf[offset]
        offset += 1
        offset += name_len
        if (name_len + 1) % 2 == 1:
            offset += 1
        size = struct.unpack(">I", buf[offset : offset + 4])[0]
        offset += 4
        data = buf[offset : offset + size]
        offset += size
        if size % 2 == 1:
            offset += 1
        if res_id in (1033, 1036) and len(data) > 28:
            fmt = struct.unpack(">I", data[:4])[0]
            jpeg_payload = data[28:]
            if fmt == 1 and jpeg_payload.startswith(JPEG_SOI):
                with Image.open(io.BytesIO(jpeg_payload)) as thumb:
                    return thumb.copy()
    return None


def read_psd_merged_image(buf: bytes) -> Optional[Image.Image]:
    try:
        return _parse_psd_merged_image(buf)
    except (struct.error, ValueError, IndexError, OSError):
        return None


def _parse_psd_merged_image(buf: bytes) -> Optional[Image.Image]:
    if len(buf) < 26 or buf[:4] != PSD_MAGIC:
        return None
    version = struct.unpack(">H", buf[4:6])[0]
    if version not in (1, 2):
        return None
    psb = version == 2
    channels = struct.unpack(">H", buf[12:14])[0]
    height = struct.unpack(">I", buf[14:18])[0]
    width = struct.unpack(">I", buf[18:22])[0]
    depth = struct.unpack(">H", buf[22:24])[0]
    color_mode = struct.unpack(">H", buf[24:26])[0]
    if depth != 8 or width <= 0 or height <= 0:
        return None
    if width * height > MAX_COMPOSITE_PIXELS:
        return None
    if color_mode not in (1, 3, 4) or channels < 1:
        return None

    offset = 26
    color_len, offset = _read_u32(buf, offset, False)
    offset += color_len
    res_len, offset = _read_u32(buf, offset, False)
    offset += res_len
    layer_len, offset = _read_u32(buf, offset, psb)
    offset += layer_len
    if offset + 2 > len(buf):
        return None

    compression = struct.unpack(">H", buf[offset : offset + 2])[0]
    offset += 2
    use_channels = min(channels, 4)
    plane = width * height

    if compression == 0:
        raw = buf[offset : offset + plane * use_channels]
        if len(raw) < plane * use_channels:
            return None
        planes = [raw[i * plane : (i + 1) * plane] for i in range(use_channels)]
    elif compression == 1:
        row_count = height * channels
        count_size = 4 if psb else 2
        table_bytes = row_count * count_size
        if offset + table_bytes > len(buf):
            return None
        counts: List[int] = []
        table = buf[offset : offset + table_bytes]
        step = count_size
        fmt = ">I" if psb else ">H"
        for i in range(row_count):
            counts.append(struct.unpack(fmt, table[i * step : (i + 1) * step])[0])
        offset += table_bytes
        planes_out: List[bytearray] = [bytearray() for _ in range(use_channels)]
        for ch in range(channels):
            for row in range(height):
                nbytes = counts[ch * height + row]
                chunk = buf[offset : offset + nbytes]
                offset += nbytes
                if ch < use_channels:
                    planes_out[ch].extend(decode_packbits(chunk, width))
        planes = [bytes(p) for p in planes_out]
    else:
        return None

    size = (width, height)
    if any(len(plane_bytes) < width * height for plane_bytes in planes):
        return None
    bands = [Image.frombytes("L", size, planes[i]) for i in range(len(planes))]
    if color_mode == 1:
        return bands[0]
    if color_mode == 3:
        if len(bands) >= 4:
            return Image.merge("RGBA", bands[:4])
        if len(bands) >= 3:
            return Image.merge("RGB", bands[:3])
        return None
    if color_mode == 4 and len(bands) >= 4:
        return Image.merge("CMYK", bands[:4])
    return None


def convert_psd(path: Path, pdf_path: Path) -> ConvertResult:
    size = os.path.getsize(win_long_path(path))
    large = size > 80 * 1024 * 1024
    if large:
        data = read_prefix(path, 16 * 1024 * 1024)
    else:
        with open(win_long_path(path), "rb") as fh:
            data = fh.read()
    if not large:
        merged = read_psd_merged_image(data)
        if merged is not None:
            images_to_pdf([merged], pdf_path)
            return ConvertResult("psd-composite")
    thumb = extract_psd_thumbnail(data)
    if thumb is not None:
        warning = "文件较大，仅导出缩略图以免占满内存" if large else "未读到合成图，已用文件内缩略图"
        images_to_pdf([thumb], pdf_path)
        return ConvertResult("psd-thumbnail", warning)
    jpeg = largest_jpeg_bytes(data)
    if jpeg:
        image_bytes_to_pdf(jpeg, pdf_path, "JPEG")
        return ConvertResult("embedded-jpeg", "未读到合成图，已用内嵌 JPEG")
    raise RuntimeError("无法从 PSD 抽出预览")


def extract_eps_preview(path: Path) -> Optional[bytes]:
    with open(win_long_path(path), "rb") as fh:
        header = fh.read(32)
        if not header.startswith(EPS_BINARY_MAGIC) or len(header) < 32:
            return None
        tiff_start, tiff_len = struct.unpack("<II", header[20:28])
        if tiff_len <= 0 or tiff_start <= 0:
            return None
        fh.seek(tiff_start)
        return fh.read(tiff_len)


def convert_with_ghostscript(path: Path, pdf_path: Path) -> bool:
    exe = which_exe(
        ["gswin64c.exe", "gswin32c.exe", "gs"],
        [Path(r"C:\Program Files\gs")],
    )
    if not exe and Path(r"C:\Program Files\gs").is_dir():
        versions = sorted(Path(r"C:\Program Files\gs").glob("gs*/bin/gswin64c.exe"), reverse=True)
        exe = str(versions[0]) if versions else None
    if not exe:
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            exe,
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            f"-sOutputFile={pdf_path}",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and pdf_path.is_file() and pdf_path.stat().st_size > 0


def convert_with_inkscape(path: Path, pdf_path: Path) -> bool:
    exe = which_exe(
        ["inkscape.exe", "inkscape"],
        [
            Path(r"C:\Program Files\Inkscape\bin"),
            Path(r"C:\Program Files (x86)\Inkscape\bin"),
        ],
    )
    if not exe:
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [exe, str(path), f"--export-filename={pdf_path}", "--export-type=pdf"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and pdf_path.is_file() and pdf_path.stat().st_size > 0


def convert_with_illustrator(path: Path, pdf_path: Path) -> bool:
    if sys.platform != "win32" or win32com is None:
        return False
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = None
    try:
        app = win32com.client.Dispatch("Illustrator.Application")
        app.UserInteractionLevel = -1
        doc = app.Open(str(path.resolve()))
        options = win32com.client.Dispatch("Illustrator.PDFSaveOptions")
        doc.SaveAs(str(pdf_path.resolve()), options)
        doc.Close(2)
        doc = None
        return pdf_path.is_file() and pdf_path.stat().st_size > 0
    except Exception:
        return False
    finally:
        if doc is not None:
            try:
                doc.Close(2)
            except Exception:
                pass


def convert_ai_like(path: Path, pdf_path: Path) -> ConvertResult:
    payload = extract_embedded_pdf_from_file(path)
    if payload:
        return convert_with_pdf_payload(payload, pdf_path, "embedded-pdf")
    preview = extract_eps_preview(path)
    if preview:
        image_bytes_to_pdf(preview, pdf_path)
        return ConvertResult("eps-tiff-preview", "无内嵌 PDF，已用 EPS 预览图")
    if convert_with_illustrator(path, pdf_path):
        return ConvertResult("illustrator")
    if convert_with_inkscape(path, pdf_path):
        return ConvertResult("inkscape")
    if convert_with_ghostscript(path, pdf_path):
        return ConvertResult("ghostscript")
    jpeg = largest_jpeg_bytes(read_prefix(path))
    if jpeg:
        image_bytes_to_pdf(jpeg, pdf_path, "JPEG")
        return ConvertResult("embedded-jpeg", "无矢量 PDF，已用内嵌预览图")
    raise RuntimeError("没有内嵌 PDF/预览图，且本机没有 Ghostscript / Inkscape")


def convert_svg(path: Path, pdf_path: Path) -> ConvertResult:
    if renderPDF is None or svg2rlg is None:
        raise RuntimeError("转换 SVG 需要安装 svglib 和 reportlab")
    drawing = svg2rlg(win_long_path(path))
    if drawing is None:
        raise RuntimeError("SVG 解析失败")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    renderPDF.drawToFile(drawing, str(pdf_path))
    return ConvertResult("svg")


def _zip_first_image(path: Path, candidates: Sequence[str]) -> Optional[bytes]:
    opened = win_long_path(path)
    if not zipfile.is_zipfile(opened):
        return None
    with zipfile.ZipFile(opened) as zf:
        names = zf.namelist()
        lower_map = {name.lower(): name for name in names}
        for candidate in candidates:
            real = lower_map.get(candidate.lower())
            if real:
                return zf.read(real)
        for name in names:
            lowered = name.lower()
            if "preview" in lowered and lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
                return zf.read(name)
    return None


def convert_zip_preview(path: Path, pdf_path: Path, labels: Sequence[str]) -> ConvertResult:
    data = _zip_first_image(path, labels)
    if not data:
        raise RuntimeError("压缩包里没有 preview 图")
    image_bytes_to_pdf(data, pdf_path)
    return ConvertResult("zip-preview")


def convert_cdr(path: Path, pdf_path: Path) -> ConvertResult:
    try:
        return convert_zip_preview(
            path,
            pdf_path,
            (
                "preview.png",
                "preview.bmp",
                "metadata/thumbnails/thumbnail.png",
                "metadata/thumbnails/thumbnail.jpg",
            ),
        )
    except RuntimeError:
        payload = extract_embedded_pdf_from_file(path)
        if payload:
            return convert_with_pdf_payload(payload, pdf_path, "embedded-pdf")
        head = read_prefix(path)
        jpeg = largest_jpeg_bytes(head)
        if jpeg:
            image_bytes_to_pdf(jpeg, pdf_path, "JPEG")
            return ConvertResult("embedded-jpeg")
        raise RuntimeError("无法从 CDR 抽出预览")


def convert_indd(path: Path, pdf_path: Path) -> ConvertResult:
    payload = extract_embedded_pdf_from_file(path)
    if payload:
        return convert_with_pdf_payload(payload, pdf_path, "embedded-pdf")
    jpeg = largest_jpeg_bytes(read_prefix(path))
    if jpeg:
        image_bytes_to_pdf(jpeg, pdf_path, "JPEG")
        return ConvertResult("embedded-jpeg", "InDesign 源文件无法完整渲染，已用页面预览图")
    raise RuntimeError("无法从 INDD 抽出预览图")


HANDLERS: Dict[str, Handler] = {
    ".ai": convert_ai_like,
    ".eps": convert_ai_like,
    ".ps": convert_ai_like,
    ".psd": convert_psd,
    ".psb": convert_psd,
    ".svg": convert_svg,
    ".pdf": convert_pdf,
    ".png": convert_raster,
    ".jpg": convert_raster,
    ".jpeg": convert_raster,
    ".tif": convert_raster,
    ".tiff": convert_raster,
    ".bmp": convert_raster,
    ".webp": convert_raster,
    ".tga": convert_raster,
    ".gif": convert_raster,
    ".indd": convert_indd,
    ".cdr": convert_cdr,
    ".sketch": lambda src, dst: convert_zip_preview(src, dst, ("previews/preview.png", "preview.png")),
    ".xd": lambda src, dst: convert_zip_preview(src, dst, ("preview.png", "resources/graphics/preview.png")),
    ".afdesign": lambda src, dst: convert_zip_preview(src, dst, ("preview.png", "preview.tiff")),
    ".afphoto": lambda src, dst: convert_zip_preview(src, dst, ("preview.png", "preview.tiff")),
}


def supported_extensions() -> Tuple[str, ...]:
    return SOURCE_EXTENSIONS


def convert_file(src: Path, dst: Path) -> ConvertResult:
    ext = src.suffix.lower()
    handler = HANDLERS.get(ext)
    if handler is None:
        raise RuntimeError(f"不支持的格式: {ext}")
    return handler(src, dst)


def convert_tree(
    input_dir: Path,
    output_dir: Path,
    recursive: bool = True,
    force: bool = False,
    exts: Optional[Sequence[str]] = None,
    progress: Optional[Callable[[int, int, Path, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    export_kind: ExportKind = ExportKind.PDF,
    split_pages: bool = False,
) -> BatchResult:
    chosen = tuple(exts) if exts else supported_extensions()
    files = iter_source_files(input_dir, recursive, chosen)
    return convert_sources(
        files,
        output_dir,
        force=force,
        recursive=False,
        progress=progress,
        should_stop=should_stop,
        export_kind=export_kind,
        split_pages=split_pages,
    )


def unique_output_path(src: Path, outdir: Path, used_lower: Set[str], suffix: str) -> Path:
    name = f"{src.stem}{suffix}"
    if name.lower() in used_lower:
        digest = hashlib.sha1(str(src.resolve()).encode("utf-8", "surrogateescape")).hexdigest()[:6]
        name = f"{src.parent.name}_{src.stem}_{digest}{suffix}"
    stem = Path(name).stem
    extra = 2
    while name.lower() in used_lower:
        name = f"{stem}_{extra}{suffix}"
        extra += 1
    used_lower.add(name.lower())
    return outdir / name


def parse_export_kind(value: str) -> ExportKind:
    key = value.lower().strip()
    if key == "pdf":
        return ExportKind.PDF
    if key == "png":
        return ExportKind.PNG
    if key in ("jpg", "jpeg"):
        return ExportKind.JPEG
    raise argparse.ArgumentTypeError("格式必须是 pdf、png 或 jpg")


def require_pymupdf():
    if pymupdf is None:
        raise RuntimeError("导出图片或按页分割 PDF 需要安装 pymupdf")
    return pymupdf


def allocate_split_path(first_dest: Path, page_no: int, used_lower: Set[str]) -> Path:
    extra = page_no
    path = first_dest.with_name(f"{first_dest.stem}_{extra}{first_dest.suffix}")
    while path.name.lower() in used_lower:
        extra += 1
        path = first_dest.with_name(f"{first_dest.stem}_{extra}{first_dest.suffix}")
    used_lower.add(path.name.lower())
    return path


def split_skip_note(skipped_names: Sequence[str]) -> str:
    if not skipped_names:
        return ""
    if len(skipped_names) == 1:
        return f"已有文件未覆盖: {skipped_names[0]}"
    shown = ", ".join(skipped_names[:3])
    if len(skipped_names) > 3:
        shown += "…"
    return f"已有 {len(skipped_names)} 个分页未覆盖: {shown}"


def page_result_note(
    page_count: int,
    split_pages: bool,
    kind: ExportKind,
    skipped_names: Sequence[str] = (),
) -> str:
    parts: List[str] = []
    if page_count <= 1:
        parts.append("共 1 页")
    elif split_pages:
        unit = "个文件" if kind is ExportKind.PDF else "张图"
        parts.append(f"共 {page_count} 页，已按页拆成 {page_count} {unit}")
    elif kind is ExportKind.PDF:
        parts.append(f"共 {page_count} 页，未拆分")
    elif kind in (ExportKind.PNG, ExportKind.JPEG):
        parts.append(f"共 {page_count} 页，未拆分仅导出第 1 页")
    else:
        assert_never(kind)
    skip = split_skip_note(skipped_names)
    if skip:
        parts.append(skip)
    return "；".join(parts)


def render_pdf_pages(pdf_path: Path) -> List[Image.Image]:
    pdf = require_pymupdf()
    pages: List[Image.Image] = []
    document = pdf.open(pdf_path)
    try:
        if document.page_count < 1:
            raise RuntimeError("没有可导出的页面")
        zoom = 150 / 72
        matrix = pdf.Matrix(zoom, zoom)
        for page in document:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(image.copy())
    finally:
        document.close()
    return pages


def pdf_page_count(pdf_path: Path) -> int:
    pdf = require_pymupdf()
    document = pdf.open(pdf_path)
    try:
        return int(document.page_count)
    finally:
        document.close()


def save_one_image(image: Image.Image, path: Path, kind: ExportKind) -> None:
    rgb = flatten_to_rgb(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind is ExportKind.PNG:
        rgb.save(path, "PNG")
        return
    if kind is ExportKind.JPEG:
        rgb.save(path, "JPEG", quality=90, optimize=True)
        return
    if kind is ExportKind.PDF:
        raise AssertionError("PDF 不应走图片保存")
    assert_never(kind)


def write_image_outputs(
    pages: Sequence[Image.Image],
    first_dest: Path,
    kind: ExportKind,
    split_pages: bool,
    used_lower: Set[str],
    force: bool,
) -> Tuple[List[Path], List[str]]:
    chosen = list(pages if split_pages else pages[:1])
    written: List[Path] = []
    skipped_names: List[str] = []
    for index, image in enumerate(chosen):
        path = first_dest if index == 0 else allocate_split_path(first_dest, index + 1, used_lower)
        if path.exists() and not force and index > 0:
            skipped_names.append(path.name)
            continue
        save_one_image(image, path, kind)
        written.append(path)
    return written, skipped_names


def write_pdf_outputs(
    tmp_pdf: Path,
    first_dest: Path,
    split_pages: bool,
    used_lower: Set[str],
    force: bool,
) -> Tuple[List[Path], int, List[str]]:
    first_dest.parent.mkdir(parents=True, exist_ok=True)
    if not split_pages:
        shutil.copy2(tmp_pdf, first_dest)
        count = pdf_page_count(tmp_pdf) if pymupdf is not None else 1
        return [first_dest], count, []

    pdf = require_pymupdf()
    document = pdf.open(tmp_pdf)
    try:
        page_count = int(document.page_count)
        if page_count <= 1:
            shutil.copy2(tmp_pdf, first_dest)
            return [first_dest], page_count, []
        written: List[Path] = []
        skipped_names: List[str] = []
        for index in range(page_count):
            path = first_dest if index == 0 else allocate_split_path(first_dest, index + 1, used_lower)
            if path.exists() and not force and index > 0:
                skipped_names.append(path.name)
                continue
            single = pdf.open()
            try:
                single.insert_pdf(document, from_page=index, to_page=index)
                single.save(str(path), deflate=True)
            finally:
                single.close()
            written.append(path)
        return written, page_count, skipped_names
    finally:
        document.close()


def export_one(
    src: Path,
    dest: Path,
    kind: ExportKind,
    split_pages: bool,
    used_lower: Set[str],
    force: bool,
) -> Tuple[ConvertResult, List[Path]]:
    with tempfile.TemporaryDirectory(prefix="design-export-") as tmp:
        tmp_pdf = Path(tmp) / "preview.pdf"
        result = convert_file(src, tmp_pdf)
        if kind is ExportKind.PDF:
            written, page_count, skipped_names = write_pdf_outputs(
                tmp_pdf, dest, split_pages, used_lower, force
            )
            extra = page_result_note(page_count, split_pages, kind, skipped_names)
            warning = f"{result.warning}  {extra}".strip() if result.warning else extra
            return ConvertResult(result.method, warning), written
        if kind in (ExportKind.PNG, ExportKind.JPEG):
            pages = render_pdf_pages(tmp_pdf)
            written, skipped_names = write_image_outputs(
                pages, dest, kind, split_pages, used_lower, force
            )
            extra = page_result_note(len(pages), split_pages, kind, skipped_names)
            warning = f"{result.warning}  {extra}".strip() if result.warning else extra
            return ConvertResult(result.method, warning), written
        assert_never(kind)


def convert_sources(
    sources: Sequence[Path],
    output_dir: Path,
    force: bool = False,
    recursive: bool = True,
    progress: Optional[Callable[[int, int, Path, str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    export_kind: ExportKind = ExportKind.PDF,
    split_pages: bool = False,
) -> BatchResult:
    files = collect_batch_sources(sources, recursive=recursive)
    outbox = output_dir.resolve()
    outbox.mkdir(parents=True, exist_ok=True)
    used_lower: Set[str] = set()
    batch = BatchResult(last_output_dir=outbox)
    if not files and sources:
        total = len(sources)
        for index, raw in enumerate(sources, start=1):
            src = Path(raw)
            batch.failed += 1
            batch.handled.append(src)
            if progress:
                progress(
                    index,
                    total,
                    src,
                    f"失败 {src.name}  源文件读不到，请先解压到桌面后再导出",
                )
        return batch
    total = len(files)
    for index, src in enumerate(files, start=1):
        if should_stop and should_stop():
            break
        readable, _retried = wait_readable(src, tries=8, delay=0.25)
        if not readable:
            batch.failed += 1
            batch.handled.append(src)
            if progress:
                progress(
                    index,
                    total,
                    src,
                    f"失败 {src.name}  电脑较卡或文件还在写入，请稍后再试或先复制到桌面",
                )
            continue
        dest = unique_output_path(src, outbox, used_lower, export_kind.suffix)
        if dest.exists() and not force:
            batch.skipped += 1
            batch.handled.append(src)
            if progress:
                progress(index, total, src, f"跳过 {src.name}  （已有 {export_kind.label}）")
            continue
        try:
            result, written = export_one(src, dest, export_kind, split_pages, used_lower, force)
            batch.ok += 1
            batch.handled.append(src)
            if written:
                batch.last_output_dir = written[0].parent
            if len(written) > 1:
                shown = f"{written[0].name} 等 {len(written)} 个文件"
            elif written:
                shown = written[0].name
            else:
                shown = dest.name
            note = f"完成 {src.name}  →  {shown}  ({result.method})"
            if result.warning:
                note += f"  提示: {result.warning}"
            if progress:
                progress(index, total, src, note)
        except Exception as exc:
            batch.failed += 1
            batch.handled.append(src)
            if progress:
                progress(index, total, src, f"失败 {src.name}  {exc}")
    return batch


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME}：把设计文件转成 PDF 或图片预览底稿",
        epilog=COPYRIGHT,
    )
    parser.add_argument("input_dir", nargs="?", default=None, help="待转换目录")
    parser.add_argument("-o", "--outdir", default=None, help="输出目录")
    parser.add_argument("--no-recursive", action="store_true", help="不扫描子目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有文件")
    parser.add_argument(
        "--format",
        dest="export_format",
        default=ExportKind.PDF,
        type=parse_export_kind,
        metavar="pdf|png|jpg",
        help="导出格式：pdf / png / jpg，默认 pdf",
    )
    parser.add_argument("--split", action="store_true", help="按页拆成多个文件（PDF 与图片均适用）")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    return parser.parse_args(argv)


def main_cli(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    inbox, outbox = ensure_work_folders()
    root = Path(args.input_dir).expanduser().resolve() if args.input_dir else inbox
    dest = Path(args.outdir).expanduser().resolve() if args.outdir else outbox
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 1

    def log(index: int, total: int, _src: Path, message: str) -> None:
        print(f"[{index}/{total}] {message}")

    files = iter_source_files(root, recursive=not args.no_recursive, exts=supported_extensions())
    print(f"{APP_NAME}")
    print(f"找到 {len(files)} 个文件  ->  {dest}\n")
    batch = convert_sources(
        files,
        dest,
        force=args.force,
        recursive=False,
        progress=log,
        export_kind=args.export_format,
        split_pages=args.split,
    )
    print(f"\n完成 {batch.ok}，跳过 {batch.skipped}，失败 {batch.failed}")
    return 1 if batch.failed else 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
