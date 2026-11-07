"""Uploads de importação expiram sem atingir arquivos externos ou recentes."""
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.utils.import_files import cleanup_expired_imports, delete_import_file


class ImportUploadCleanupTests(unittest.TestCase):
    def test_completed_and_abandoned_uploads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "import_uploads"
            folder.mkdir()
            old = folder / ("a" * 32 + "_legacy.csv")
            recent = folder / ("b" * 32 + "_new.csv")
            outside = root / ("c" * 32 + "_outside.csv")
            unrelated = folder / "notes.txt"
            for path in (old, recent, outside, unrelated):
                path.write_text("personal data", encoding="utf-8")
            now = time.time()
            os.utime(old, (now - 25 * 3600, now - 25 * 3600))
            os.utime(unrelated, (now - 25 * 3600, now - 25 * 3600))
            self.assertEqual(cleanup_expired_imports(folder, now=now), 1)
            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue(unrelated.exists())
            self.assertFalse(delete_import_file(folder, outside))
            self.assertTrue(outside.exists())
            self.assertTrue(delete_import_file(folder, recent))
            self.assertFalse(recent.exists())


if __name__ == "__main__":
    unittest.main()
