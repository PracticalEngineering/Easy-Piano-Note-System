# -*- coding: utf-8 -*-
"""Checks every song in library/library.json: file present, converts, every note accounted for, license allowed."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import notencode as nc  # noqa: E402

LIBRARY = ROOT / "library"
ALLOWED_LICENSES = {"Public domain", "CPDL", "CC BY", "CC BY-SA", "CC0"}


class Library(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((LIBRARY / "library.json").read_text(encoding="utf-8"))
        cls.songs = cls.data["songs"]

    def test_entries_are_complete_and_unique(self):
        ids = [s["id"] for s in self.songs]
        self.assertEqual(len(ids), len(set(ids)), "duplicate id")
        for s in self.songs:
            with self.subTest(song=s.get("id")):
                self.assertRegex(s["id"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertTrue(s["title"].get("en"), "English title missing")
                self.assertTrue(s.get("credit"), "credit missing")
                self.assertTrue(s.get("source", "").startswith("https://"), "source must be an https link")
                self.assertIn(s.get("license"), ALLOWED_LICENSES)
                self.assertRegex(s["file"], r"^songs/[\w.-]+\.(mxl|musicxml|xml)$")
                self.assertTrue((LIBRARY / s["file"]).is_file(), "file missing")

    def test_every_song_converts_with_full_note_balance(self):
        for s in self.songs:
            with self.subTest(song=s["id"]):
                res = nc.convert_file(LIBRARY / s["file"], upper=s.get("upper"), lower=s.get("lower"))
                self.assertIn("balance OK", res.report_text)
                self.assertGreater(sum(len(m) for m in res.measures), 0)

    def test_no_unlisted_files(self):
        listed = {s["file"].split("/", 1)[1] for s in self.songs}
        present = {p.name for p in (LIBRARY / "songs").iterdir() if not p.name.startswith(".")}
        self.assertEqual(present - listed, set(), "files in library/songs/ without an entry in library.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
