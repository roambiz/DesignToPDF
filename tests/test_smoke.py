import tempfile
import unittest
from pathlib import Path

from brand import APP_NAME, VERSION
from convert import (
    HANDLERS,
    convert_sources,
    expand_sources,
    page_result_note,
    split_skip_note,
    supported_extensions,
)
from export_kind import ExportKind
from source_scan import (
    SOURCE_EXTENSIONS,
    clean_path_text,
    collect_batch_sources,
    is_ephemeral_path,
    path_key,
    suggest_output_dir,
)


class SmokeTests(unittest.TestCase):
    def test_brand_constants(self) -> None:
        self.assertEqual(VERSION, "1.1.0")
        self.assertIn("底稿", APP_NAME)

    def test_supported_extensions(self) -> None:
        exts = supported_extensions()
        self.assertIn(".ai", exts)
        self.assertIn(".psd", exts)
        self.assertEqual(set(exts), set(HANDLERS))
        self.assertEqual(set(exts), set(SOURCE_EXTENSIONS))

    def test_expand_sources_empty(self) -> None:
        self.assertEqual(expand_sources([]), [])

    def test_collect_batch_keeps_missing_files(self) -> None:
        missing = Path(tempfile.gettempdir()) / "design-export-missing-xyz.ai"
        if missing.exists():
            missing.unlink()
        kept = collect_batch_sources([missing], recursive=False)
        self.assertEqual(len(kept), 1)
        self.assertEqual(path_key(kept[0]), path_key(missing))
        self.assertEqual(expand_sources([missing], recursive=False), [])

    def test_convert_sources_missing_and_skip_are_handled(self) -> None:
        missing = Path(tempfile.gettempdir()) / "design-export-gone-xyz.png"
        if missing.exists():
            missing.unlink()
        with tempfile.TemporaryDirectory() as tmp:
            outbox = Path(tmp)
            existing = outbox / "keep.pdf"
            existing.write_bytes(b"%PDF-1.1\n")
            src = outbox / "keep.png"
            src.write_bytes(b"not-a-real-png")
            batch = convert_sources(
                [missing, src],
                outbox,
                recursive=False,
            )
            self.assertEqual(batch.failed, 1)
            self.assertEqual(batch.skipped, 1)
            self.assertEqual(batch.ok, 0)
            handled = {path_key(path) for path in batch.handled}
            self.assertIn(path_key(missing), handled)
            self.assertIn(path_key(src), handled)

    def test_split_skip_note(self) -> None:
        self.assertEqual(split_skip_note([]), "")
        self.assertIn("稿件_2.pdf", split_skip_note(["稿件_2.pdf"]))

    def test_page_result_note_with_skipped_pages(self) -> None:
        note = page_result_note(3, True, ExportKind.PDF, ["a_2.pdf"])
        self.assertIn("未覆盖", note)

    def test_clean_path_text(self) -> None:
        self.assertEqual(clean_path_text('  "D:\\客户\\稿"  '), r"D:\客户\稿")
        self.assertEqual(clean_path_text("file:///D:/a/b"), "D:/a/b")

    def test_ephemeral_and_normal_paths(self) -> None:
        temp = Path(tempfile.gettempdir()) / "chat-draft.ai"
        self.assertTrue(is_ephemeral_path(temp))
        wechat = Path.home() / "Documents" / "WeChat Files" / "wxid" / "FileStorage" / "Temp" / "a.ai"
        self.assertTrue(is_ephemeral_path(wechat))
        asset = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
        self.assertFalse(is_ephemeral_path(asset))
        self.assertEqual(suggest_output_dir([asset]), asset.parent / "导出结果")
        suggested = suggest_output_dir([temp])
        self.assertEqual(suggested.name, "导出结果")
        self.assertFalse(is_ephemeral_path(suggested))

    def test_assets_exist(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.assertTrue((root / "assets" / "app.ico").is_file())


if __name__ == "__main__":
    unittest.main()
