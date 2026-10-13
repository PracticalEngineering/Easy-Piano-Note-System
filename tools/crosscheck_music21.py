# -*- coding: utf-8 -*-
"""
Independent cross-check: the same file is read with the music21 library
(its own MusicXML reader, its own timing and tie logic) and the result is compared
line by line with the output of notencode.py.

Install once:   python -m pip install music21
Run:            python tools/crosscheck_music21.py input/FILE.mxl [--same-pitch-slur restrike]

More than two staves: empty staves (rests only) are skipped; otherwise give
--upper / --lower as for notencode.py, e.g.  --upper P1,P2 --lower P3
"""
import argparse
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notencode as nc  # noqa: E402

try:
    from music21 import converter, harmony, spanner
except ImportError:
    sys.exit("music21 is not installed:  python -m pip install music21")

ACC = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}


def name(p, lower):
    s = p.step + ACC[int(p.alter)]
    return f"{s.lower() if lower else s}{p.octave}"


def hand_selection(path, parts, upper, lower):
    """Which music21 staves belong to which hand: [(index, lower?), ...]"""
    if upper or lower:
        staves = nc.find_staves(nc.load_root(Path(path)))
        if len(staves) != len(parts):
            sys.exit(f"music21 reads {len(parts)} staves, notencode {len(staves)} - assignment is ambiguous.")
        keys = [(p, s) for p, s, _ in staves]
        return ([(keys.index(k), False) for k in nc.parse_staff_spec(upper, staves)]
                + [(keys.index(k), True) for k in nc.parse_staff_spec(lower, staves)])
    idx = list(range(len(parts)))
    if len(parts) > 2:      # skip empty staves (rests only) - checked separately with music21
        full = [i for i, p in enumerate(parts)
                if any(not isinstance(n, harmony.ChordSymbol) for n in p.recurse().notes)]
        if 1 <= len(full) <= 2:
            idx = full
    if len(idx) != 2:
        sys.exit(f"The cross-check expects exactly 2 staves, found: {len(idx)}. Please give --upper/--lower.")
    return [(idx[0], False), (idx[1], True)]


def without_cue_notes(path):
    """Cue notes (<cue/>) are not played (rule of the spec). music21 does not mark them,
    so they are turned into rests of the same duration first (or removed from chords)."""
    data = Path(path).read_bytes()
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            cands = [n for n in z.namelist() if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF")]
            data = z.read(cands[0])
    root = ET.fromstring(data)
    n_cue = 0
    for parent in root.iter():
        for note in list(parent):
            if note.tag != "note" or note.find("cue") is None:
                continue
            n_cue += 1
            if note.find("chord") is not None:
                parent.remove(note)
                continue
            for tag in ("pitch", "unpitched", "cue", "tie", "notations", "accidental", "stem", "beam", "lyric"):
                for el in note.findall(tag):
                    note.remove(el)
            note.insert(0, ET.Element("rest"))
    return ET.tostring(root, encoding="unicode"), n_cue


def music21_code(path, slur_mode, hands, upper=None, lower=None):
    text, n_cue = without_cue_notes(path)
    sc = converter.parse(text, format="musicxml") if n_cue else converter.parse(str(path))
    parts = list(sc.parts)
    selection = hand_selection(path, parts, upper, lower)

    # slurs between two directly consecutive equal pitches (only for mode 'hold')
    slur_held = set()
    if slur_mode == "hold":
        for sl in sc.recurse().getElementsByClass(spanner.Slur):
            els = sl.getSpannedElements()
            if len(els) >= 2:
                a, b = els[0], els[-1]
                if (hasattr(a, "pitch") and hasattr(b, "pitch") and a.pitch.ps == b.pitch.ps
                        and a.getOffsetInHierarchy(sc) + a.quarterLength == b.getOffsetInHierarchy(sc)):
                    slur_held.add(id(b))

    groups = defaultdict(dict)          # (measure, time) -> {(lower?, midi): pitch}
    n_measures = 0
    for part_idx, lower_hand in selection:
        part = parts[part_idx]
        measures = list(part.getElementsByClass("Measure"))
        n_measures = max(n_measures, len(measures))
        for mi, m in enumerate(measures):
            for el in m.flatten().notes:
                if el.duration.isGrace or isinstance(el, harmony.ChordSymbol):
                    continue            # grace notes and chord symbols (Bb, F7 ...) are not played notes
                t = Fraction(el.offset).limit_denominator(10000)
                notes = el.notes if el.isChord else [el]
                for n in notes:
                    own = el.isChord and any(x.tie is not None for x in el.notes)
                    tie = n.tie if (n.tie is not None or own) else (el.tie if el.isChord else None)
                    if tie is not None and tie.type in ("stop", "continue"):
                        continue
                    if id(n) in slur_held or id(el) in slur_held:
                        continue
                    groups[(mi, t)].setdefault((lower_hand, n.pitch.ps), n.pitch)
    out = []
    for mi in range(n_measures):
        keys = sorted(k for k in groups if k[0] == mi)
        lines = []
        for k in keys:
            notes = [(lw, ps, p) for (lw, ps), p in groups[k].items()]
            if hands == "playable":
                notes = playable(notes)
            notes.sort(key=lambda x: (-x[1], x[0]))
            lines.append("+".join(name(p, lw) for lw, _, p in notes))
        out.append(lines or ["-"])
    return out


def playable(notes):
    """A separate, simplified implementation of the 'playable' rule (without held notes)."""
    up = {ps: p for lower, ps, p in notes if not lower}
    lo = {ps: p for lower, ps, p in notes if lower}
    for ps in sorted(set(up) & set(lo), reverse=True):
        def widen(d):
            rest = [x for x in d if x != ps]
            return 0 if not rest else max(0, ps - max(rest)) + max(0, min(rest) - ps)
        wu, wl = widen(up), widen(lo)
        if wu < wl or (wu == wl and ps >= 60):
            del lo[ps]
        else:
            del up[ps]
    if up and lo and max(lo) > min(up):
        allp = sorted(list(up.items()) + list(lo.items()), key=lambda kv: -kv[0])
        k = len(up)
        return [(i >= k, ps, p) for i, (ps, p) in enumerate(allp)]
    return [(False, ps, p) for ps, p in up.items()] + [(True, ps, p) for ps, p in lo.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--same-pitch-slur", choices=["hold", "restrike"], default="hold")
    ap.add_argument("--hands", choices=["playable", "staff"], default="playable")
    ap.add_argument("--upper", default=None)
    ap.add_argument("--lower", default=None)
    a = ap.parse_args()
    ref = music21_code(a.input, a.same_pitch_slur, a.hands, a.upper, a.lower)
    mine = nc.convert_file(Path(a.input), same_pitch_slur=a.same_pitch_slur, hands=a.hands,
                           upper=a.upper, lower=a.lower).measures
    diffs = 0
    for i in range(max(len(ref), len(mine))):
        r = ref[i] if i < len(ref) else []
        m = mine[i] if i < len(mine) else []
        if r != m:
            diffs += 1
            print(f"Measure no. {i + 1}:")
            print(f"   music21:   {r}")
            print(f"   notencode: {m}")
    total = sum(len(x) for x in mine)
    if diffs == 0:
        print(f"CROSS-CHECK OK: {len(mine)} measures, {total} lines - music21 and notencode.py are identical "
              f"(same-pitch slur: {a.same_pitch_slur}, hands: {a.hands}).")
    else:
        print(f"CROSS-CHECK: {diffs} measure(s) differ.")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
