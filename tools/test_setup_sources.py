"""Offline checks for source verification and safe PDF replacement."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import setup_sources


class SetupSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.wiki = self.root / "sources/zh.wikisource/封神演義"
        self.pdfs = self.root / "sources/najda"
        self.wiki.mkdir(parents=True)
        self.pdfs.mkdir(parents=True)
        chapters = []
        for n in range(1, 101):
            name = f"{n:03}.md"
            data = f"chapter {n}".encode()
            (self.wiki / name).write_bytes(data)
            chapters.append({"chapter": n, "file": name, "sha256": hashlib.sha256(data).hexdigest()})
        (self.wiki / "sources.json").write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
        self.data = b"%PDF-1.4 reference fixture"
        records = []
        for n in range(1, 21):
            name = f"vol{n:02}.pdf"
            (self.pdfs / name).write_bytes(self.data)
            records.append({"file": name, "size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()})
        (self.pdfs / "manifest.json").write_text(json.dumps({
            "repository": "example/private", "release": "sources-v1", "files": records,
        }), encoding="utf-8")
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def test_complete_sources_need_no_network(self):
        with patch("setup_sources.subprocess.run") as run:
            self.assertEqual(setup_sources.prepare(self.root), 0)
            run.assert_not_called()

    def test_check_reports_missing_pdf_without_downloading(self):
        (self.pdfs / "vol01.pdf").unlink()
        with patch("setup_sources.subprocess.run") as run:
            self.assertEqual(setup_sources.prepare(self.root, check=True), 1)
            run.assert_not_called()

    def test_changed_wikisource_stops_before_download(self):
        (self.wiki / "001.md").write_bytes(b"changed")
        with patch("setup_sources.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "Wikisource missing or changed"):
                setup_sources.prepare(self.root)
            run.assert_not_called()

    def download(self, args, check):
        name = args[args.index("--pattern") + 1]
        destination = Path(args[args.index("--dir") + 1])
        (destination / name).write_bytes(self.data)
        return subprocess.CompletedProcess(args, 0)

    def test_download_only_missing_file_then_skip_on_retry(self):
        (self.pdfs / "vol01.pdf").unlink()
        with patch("setup_sources.shutil.which", return_value="gh"), patch(
            "setup_sources.subprocess.run", side_effect=self.download,
        ) as run:
            self.assertEqual(setup_sources.prepare(self.root), 0)
            self.assertEqual(setup_sources.prepare(self.root), 0)
            self.assertEqual(run.call_count, 1)
        self.assertEqual((self.pdfs / "vol01.pdf").read_bytes(), self.data)

    def test_wrong_hash_preserves_existing_pdf(self):
        existing = self.pdfs / "vol01.pdf"
        existing.write_bytes(b"old file")
        self.data = b"x" * len(self.data)  # Correct size, wrong checksum.
        with patch("setup_sources.shutil.which", return_value="gh"), patch(
            "setup_sources.subprocess.run", side_effect=self.download,
        ):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                setup_sources.prepare(self.root)
        self.assertEqual(existing.read_bytes(), b"old file")
        self.assertFalse((self.pdfs / "vol01.pdf.part").exists())

    def test_failed_download_preserves_existing_pdf(self):
        existing = self.pdfs / "vol01.pdf"
        existing.write_bytes(b"old file")
        with patch("setup_sources.shutil.which", return_value="gh"), patch(
            "setup_sources.subprocess.run", return_value=subprocess.CompletedProcess([], 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "Download failed"):
                setup_sources.prepare(self.root)
        self.assertEqual(existing.read_bytes(), b"old file")


if __name__ == "__main__":
    unittest.main()
