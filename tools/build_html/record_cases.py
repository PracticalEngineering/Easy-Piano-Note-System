# -*- coding: utf-8 -*-
"""
Records every convert_xml_text() call of the Python tests (XML + options + result) plus the
example files in all option combinations, into cases.json. compare_js_python.js then runs the
JavaScript core on the same cases and checks that the output is identical, character by character.

Run:   python tools/build_html/record_cases.py [EXTRA_FOLDER ...]

EXTRA_FOLDER: more .mxl/.musicxml files to compare. If a file has more than two staves, put a
staves.json next to it: {"file.mxl": {"upper": "P5/1", "lower": "P5/2"}}
"""
import itertools
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import notencode as nc  # noqa: E402

cases = []
orig = nc.convert_xml_text


def entry_from(result):
    return dict(code=result.code_text, checklist=result.checklist_text, report=result.report_text,
                warnings=result.report.warnings, check=result.report.check,
                hands=result.report.hands, info=result.report.info)


def record(text, **opts):
    entry = {"xml": text, "opts": opts}
    try:
        r = orig(text, **opts)
        entry.update(entry_from(r))
    except nc.NotencodeError as e:
        entry["error"] = str(e)
    cases.append(entry)
    if "error" in entry:
        raise nc.NotencodeError(entry["error"])
    return r


nc.convert_xml_text = record
import test_notencode  # noqa: E402
test_notencode.nc.convert_xml_text = record
suite = unittest.defaultTestLoader.loadTestsFromModule(test_notencode)
unittest.TextTestRunner(verbosity=0).run(suite)

folders = [ROOT / "examples"] + [Path(a) for a in sys.argv[1:]]
for folder in folders:
    staves = {}
    if (folder / "staves.json").exists():
        staves = json.loads((folder / "staves.json").read_text(encoding="utf-8"))
    for f in sorted(p for p in folder.glob("*") if p.suffix.lower() in (".mxl", ".musicxml", ".xml")):
        combos = itertools.product(("sounding", "written"), ("hold", "restrike"), ("playable", "staff")) \
            if folder == ROOT / "examples" else (("sounding", "hold", h) for h in ("playable", "staff"))
        for acc, slur, hands in combos:
            o = dict(staves.get(f.name, {}), accidentals=acc, same_pitch_slur=slur, hands=hands)
            try:
                r = nc.convert_file(f, **o)
            except nc.NotencodeError as e:
                print(f"skipped {f.name}: {str(e).splitlines()[0]}")
                break
            cases.append(dict({"file": str(f), "opts": o}, **entry_from(r)))

(Path(__file__).resolve().parent / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=0), encoding="utf-8")
print(len(cases), "cases,", sum(1 for c in cases if "error" in c), "of them expected errors")
