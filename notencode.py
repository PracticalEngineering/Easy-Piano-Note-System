#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notencode.py  -  MusicXML  ->  Notencode

Notencode is a plain-text piano notation: one line per moment a key is struck,
right hand in CAPITALS, left hand in lowercase, simultaneous notes joined with "+".

    F4+D4+bb3+bb2
    G4+Eb4

Usage (inside the project folder):
    python notencode.py examples/silent_night.mxl
    python notencode.py input/song.musicxml -o output/song.txt
    python notencode.py input/*.mxl                     (several files)
    python notencode.py                                 (every file in input/)

Options:
    --accidentals sounding   (default) accidentals from key signature AND score -> the key you press
    --accidentals written    only accidentals printed directly before the note (natural sign = n)
    --same-pitch-slur hold      (default) a slur between two equal pitches is read like a tie: not struck again
    --same-pitch-slur restrike  read such slurs as phrasing: the note is struck again
    --hands playable         (default) the same pitch in both hands is written once (hand with the smaller
                             stretch); if voices cross, the right hand takes the upper notes
    --hands staff            hand = staff, no exceptions
    --upper P1 --lower P2    force which staves belong to which hand ("P1" or "P1/2" for staff 2 of P1)
    --empty-measure "-"      line written for a measure without a new attack

Three files are written per input file:
    <name>_notencode.txt             the Notencode
    <name>_notencode.checklist.txt   the same code with measure, beat, held notes and things to check
    <name>_notencode.report.txt      report: note balance, warnings, places to check in the score

Python standard library only (Python 3.8+).
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VERSION = "2.1"

STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ALTER_TEXT = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "##"}
ACCIDENTAL_TEXT = {
    "sharp": "#", "flat": "b", "natural": "n",
    "double-sharp": "##", "sharp-sharp": "##",
    "flat-flat": "bb", "double-flat": "bb",
    "natural-sharp": "#", "natural-flat": "b",
}

UPPER, LOWER = "upper", "lower"
HAND_TEXT = {UPPER: "right hand", LOWER: "left hand"}


class NotencodeError(Exception):
    """An error after which no reliable output is possible."""


# --------------------------------------------------------------------------- data model

@dataclass
class Note:
    part_id: str
    staff: int
    hand: str                  # "upper" (CAPITALS) or "lower" (lowercase)
    measure_idx: int           # 0-based, order in the document
    onset: Fraction            # in quarter notes from the start of the measure
    duration: Fraction         # in quarter notes
    abs_onset: Fraction        # in quarter notes from the start of the piece (within the part)
    voice: str
    step: str
    alter: Fraction
    octave: int
    accidental: Optional[str]  # printed accidental (<accidental>), if any
    tie_start: bool
    tie_stop: bool
    slur_starts: List[str]
    slur_stops: List[str]
    doc_order: int
    continuation: bool = False         # continuation of a tie -> not struck
    held_by_slur: bool = False         # only with --same-pitch-slur hold
    duplicate_of: Optional["Note"] = None

    @property
    def midi(self) -> Fraction:
        return (self.octave + 1) * 12 + STEP_SEMITONES[self.step] + self.alter

    @property
    def end(self) -> Fraction:
        return self.onset + self.duration

    @property
    def abs_end(self) -> Fraction:
        return self.abs_onset + self.duration

    @property
    def is_attack(self) -> bool:
        return not self.continuation and not self.held_by_slur and self.duplicate_of is None


@dataclass
class MeasureInfo:
    idx: int
    label: str
    length: Fraction           # actual length in quarter notes (longest voice)
    expected: Optional[Fraction]
    beat_type: int
    time_text: str
    implicit: bool


@dataclass
class Report:
    warnings: List[str] = field(default_factory=list)   # structural problems in the file
    check: List[str] = field(default_factory=list)      # please compare with the printed score
    info: List[str] = field(default_factory=list)       # for information
    flags: Dict[Tuple[int, Fraction], List[str]] = field(default_factory=lambda: defaultdict(list))
    hands: List[str] = field(default_factory=list)      # hand decisions (rule "playable")
    infos: Dict[Tuple[int, Fraction], List[str]] = field(default_factory=lambda: defaultdict(list))
    counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class Result:
    source: str
    code_text: str
    checklist_text: str
    report_text: str
    measures: List[List[str]]   # the code lines of each measure
    report: Report


# --------------------------------------------------------------------------- reading

def _zip_entry(z: zipfile.ZipFile, wanted: str) -> Optional[str]:
    """Find the archive entry for a name from container.xml - even if the archive stores
    UTF-8 names without the UTF-8 flag (e.g. "fröhliche" in some .mxl files)."""
    if wanted in z.namelist():
        return wanted
    nfc = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731
    for info in z.infolist():
        variants = {info.filename}
        if not info.flag_bits & 0x800:
            try:
                variants.add(info.filename.encode("cp437").decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        if any(nfc(v) == nfc(wanted) for v in variants):
            return info.filename
    return None


def load_root(path: Path) -> ET.Element:
    """Read .musicxml/.xml or compressed .mxl and return the root element."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            target = None
            if "META-INF/container.xml" in names:
                container = ET.fromstring(z.read("META-INF/container.xml"))
                for el in container.iter():
                    if str(el.tag).endswith("rootfile") and el.get("full-path"):
                        target = _zip_entry(z, el.get("full-path"))
                        break
            if target is None:
                candidates = [n for n in names
                              if n.lower().endswith((".xml", ".musicxml")) and not n.startswith("META-INF")]
                if not candidates:
                    raise NotencodeError("No MusicXML file found in the .mxl archive.")
                target = candidates[0]
            data = z.read(target)
    else:
        data = path.read_bytes()
    return parse_xml_bytes(data)


def parse_xml_bytes(data: bytes) -> ET.Element:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise NotencodeError(f"The file is not valid XML: {e}")
    for el in root.iter():                     # drop namespaces, if any
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    if root.tag == "score-timewise":
        root = timewise_to_partwise(root)
    if root.tag != "score-partwise":
        raise NotencodeError(f"Unknown root element <{root.tag}>. Expected MusicXML (score-partwise).")
    return root


def timewise_to_partwise(root: ET.Element) -> ET.Element:
    new = ET.Element("score-partwise", root.attrib)
    for child in root:
        if child.tag != "measure":
            new.append(child)
    parts: Dict[str, ET.Element] = {}
    for m in root.findall("measure"):
        for p in m.findall("part"):
            pid = p.get("id", "?")
            if pid not in parts:
                parts[pid] = ET.SubElement(new, "part", {"id": pid})
            nm = ET.SubElement(parts[pid], "measure", m.attrib)
            for c in p:
                nm.append(c)
    return new


# --------------------------------------------------------------------------- staves -> hands

def find_staves(root: ET.Element) -> List[Tuple[str, int, str]]:
    """All staves in score order: (part_id, staff_number, part_name)."""
    names = {}
    for sp in root.findall("part-list/score-part"):
        names[sp.get("id")] = (sp.findtext("part-name") or "").strip()
    staves = []
    for part in root.findall("part"):
        pid = part.get("id", "?")
        n = 1
        for s in part.iter("staves"):
            try:
                n = max(n, int(s.text))
            except (TypeError, ValueError):
                pass
        for s in part.iter("staff"):
            try:
                n = max(n, int(s.text))
            except (TypeError, ValueError):
                pass
        for i in range(1, n + 1):
            staves.append((pid, i, names.get(pid, "")))
    return staves


def staves_with_notes(root: ET.Element) -> set:
    """Staves that contain at least one pitched note (rests do not count)."""
    used = set()
    for part in root.findall("part"):
        pid = part.get("id", "?")
        for note in part.iter("note"):
            if note.find("pitch") is None and note.find("unpitched") is None:
                continue
            try:
                staff = int((note.findtext("staff") or "1").strip())
            except ValueError:
                staff = 1
            used.add((pid, staff))
    return used


def drop_empty_staves(root: ET.Element, staves, rep: Report):
    """More than two staves, but at most two of them with notes: skip the empty ones (rests only).
    Common in hymnal files with an empty text or chord staff."""
    if len(staves) <= 2:
        return staves
    used = staves_with_notes(root)
    keep = [s for s in staves if (s[0], s[1]) in used]
    if not 1 <= len(keep) <= 2:
        return staves
    for p, s, name in staves:
        if (p, s) not in used:
            rep.info.append(f"Staff {p}/{s} ({name!r}) has no notes, only rests - skipped.")
    return keep


def parse_staff_spec(spec: str, staves) -> List[Tuple[str, int]]:
    out = []
    for item in [s.strip() for s in spec.split(",") if s.strip()]:
        if "/" in item:
            pid, nr = item.split("/", 1)
            key = (pid, int(nr))
            if key not in [(p, s) for p, s, _ in staves]:
                raise NotencodeError(f"Staff {item} does not exist in the file.")
            out.append(key)
        else:
            keys = [(p, s) for p, s, _ in staves if p == item]
            if not keys:
                raise NotencodeError(f"Part {item} does not exist in the file.")
            out.extend(keys)
    return out


def resolve_hands(staves, upper: Optional[str], lower: Optional[str], rep: Report) -> Dict[Tuple[str, int], str]:
    listing = "\n".join(f"   {p}/{s}  {name!r}" for p, s, name in staves)
    if upper or lower:
        if not (upper and lower):
            raise NotencodeError("Please give both --upper AND --lower.")
        hands = {}
        for key in parse_staff_spec(upper, staves):
            hands[key] = UPPER
        for key in parse_staff_spec(lower, staves):
            if key in hands:
                raise NotencodeError(f"Staff {key[0]}/{key[1]} is given as both upper and lower.")
            hands[key] = LOWER
        for p, s, name in staves:
            if (p, s) not in hands:
                rep.info.append(f"Staff {p}/{s} ({name!r}) is not assigned to a hand (as chosen) and is not written.")
        return hands
    if len(staves) == 1:
        rep.warnings.append("The file has only one staff - everything is written as the upper staff (CAPITALS).")
        return {(staves[0][0], staves[0][1]): UPPER}
    if len(staves) == 2:
        return {(staves[0][0], staves[0][1]): UPPER, (staves[1][0], staves[1][1]): LOWER}
    raise NotencodeError(
        "The file has more than two staves. I will not guess which ones belong to the piano hands.\n"
        f"Staves found:\n{listing}\n"
        "Please choose, e.g.:  --upper P2/1 --lower P2/2")


# --------------------------------------------------------------------------- timeline

def _frac(text: Optional[str]) -> Fraction:
    return Fraction(text.strip()) if text and text.strip() else Fraction(0)


def _time_sig(attr: ET.Element) -> Optional[Tuple[Fraction, int, str]]:
    t = attr.find("time")
    if t is None:
        return None
    beats_txt, type_txt = t.findtext("beats"), t.findtext("beat-type")
    if not beats_txt or not type_txt:
        return None
    try:
        beats = sum(int(b) for b in beats_txt.split("+"))
        beat_type = int(type_txt)
    except ValueError:
        return None
    return Fraction(beats * 4, beat_type), beat_type, f"{beats_txt}/{type_txt}"


def parse_part(part: ET.Element, hands: Dict[Tuple[str, int], str], rep: Report, order_start: int):
    pid = part.get("id", "?")
    divisions: Optional[Fraction] = None
    expected: Optional[Fraction] = None
    beat_type, time_text = 4, "?"
    notes: List[Note] = []
    measures: List[MeasureInfo] = []
    abs_start = Fraction(0)
    order = order_start

    for midx, measure in enumerate(part.findall("measure")):
        label = measure.get("number", str(midx + 1))
        implicit = measure.get("implicit") == "yes"
        cursor = Fraction(0)
        max_cursor = Fraction(0)
        last_onset = Fraction(0)
        voice_end: Dict[str, Fraction] = defaultdict(Fraction)

        for child in measure:
            tag = child.tag
            if tag == "attributes":
                d = child.findtext("divisions")
                if d:
                    divisions = _frac(d)
                ts = _time_sig(child)
                if ts:
                    expected, beat_type, time_text = ts
                if child.find("transpose") is not None:
                    rep.warnings.append(f"Part {pid}, measure {label}: <transpose> found - pitches in the file may be "
                                        "written transposed. Please check.")
            elif tag in ("backup", "forward"):
                if divisions is None:
                    raise NotencodeError(f"Part {pid}, measure {label}: <{tag}> before <divisions>.")
                d = _frac(child.findtext("duration")) / divisions
                if tag == "backup":
                    cursor -= d
                    if cursor < 0:
                        rep.warnings.append(f"Part {pid}, measure {label}: <backup> jumps before the start of the "
                                            "measure - set to 0.")
                        cursor = Fraction(0)
                else:
                    cursor += d
                    max_cursor = max(max_cursor, cursor)
            elif tag == "barline":
                if child.find("repeat") is not None or child.find("ending") is not None:
                    rep.info.append(f"Measure {label}: repeat sign/volta - the code follows the printed score, "
                                    "repeats are NOT written out.")
            elif tag == "direction":
                if child.find(".//octave-shift") is not None:
                    rep.info.append(f"Part {pid}, measure {label}: octave sign (8va/8vb) - the code shows the "
                                    "sounding octave, not the printed note position.")
            elif tag == "note":
                order += 1
                if divisions is None:
                    raise NotencodeError(f"Part {pid}, measure {label}: note before <divisions>.")
                is_chord = child.find("chord") is not None
                is_grace = child.find("grace") is not None
                is_cue = child.find("cue") is not None
                is_rest = child.find("rest") is not None
                dur_txt = child.findtext("duration")
                if not is_grace and dur_txt is None:
                    rep.warnings.append(f"Part {pid}, measure {label}: note without <duration> - duration 0 assumed.")
                dur = Fraction(0) if is_grace else _frac(dur_txt) / divisions
                if is_chord:
                    onset = last_onset
                else:
                    onset = cursor
                    last_onset = cursor
                voice = (child.findtext("voice") or "1").strip()
                try:
                    staff = int((child.findtext("staff") or "1").strip())
                except ValueError:
                    staff = 1
                if not is_chord and not is_grace:
                    cursor += dur
                    max_cursor = max(max_cursor, cursor)
                if not is_grace:
                    voice_end[voice] = max(voice_end[voice], onset + dur)

                # --- whatever is not written is counted (note balance)
                if is_rest:
                    rep.counts["rests"] += 1
                    continue
                if is_grace:
                    rep.counts["grace_notes"] += 1
                    rep.check.append(f"Measure {label}: grace note skipped - it has no duration of its own.")
                    continue
                if is_cue:
                    rep.counts["cue_notes"] += 1
                    rep.info.append(f"Measure {label}: cue note skipped - it is not played.")
                    continue
                pitch = child.find("pitch")
                if pitch is None:
                    rep.counts["unpitched"] += 1
                    rep.warnings.append(f"Part {pid}, measure {label}: note without pitch (e.g. percussion) skipped.")
                    continue
                hand = hands.get((pid, staff))
                if hand is None:
                    rep.counts["unassigned"] += 1
                    continue
                if child.get("print-object") == "no":
                    rep.check.append(f"Measure {label}: invisible note (print-object=no) is written - "
                                     "it is not in the printed score.")

                step = (pitch.findtext("step") or "").strip().upper()
                if step not in STEP_SEMITONES:
                    raise NotencodeError(f"Part {pid}, measure {label}: unknown note name {step!r}.")
                alter = _frac(pitch.findtext("alter"))
                try:
                    octave = int((pitch.findtext("octave") or "").strip())
                except ValueError:
                    raise NotencodeError(f"Part {pid}, measure {label}: note without a valid octave.")
                acc_el = child.find("accidental")
                accidental = acc_el.text.strip() if acc_el is not None and acc_el.text else None

                tie_types = {t.get("type") for t in child.findall("tie")}
                tie_types |= {t.get("type") for t in child.findall("notations/tied")}
                slur_starts, slur_stops = [], []
                for s in child.findall("notations/slur"):
                    num = s.get("number", "1")
                    if s.get("type") == "start":
                        slur_starts.append(num)
                    elif s.get("type") == "stop":
                        slur_stops.append(num)

                notes.append(Note(
                    part_id=pid, staff=staff, hand=hand, measure_idx=midx, onset=onset, duration=dur,
                    abs_onset=abs_start + onset, voice=voice, step=step, alter=alter, octave=octave,
                    accidental=accidental,
                    tie_start="start" in tie_types or "continue" in tie_types,
                    tie_stop="stop" in tie_types or "continue" in tie_types,
                    slur_starts=slur_starts, slur_stops=slur_stops, doc_order=order))

        length = max_cursor
        if length == 0 and expected:
            length = expected
        if expected is not None:
            for v, e in voice_end.items():
                if e > expected:
                    rep.warnings.append(f"Part {pid}, measure {label}: voice {v} is longer than the time signature "
                                        f"{time_text} ({_q(e)} instead of {_q(expected)} quarters).")
        measures.append(MeasureInfo(midx, label, length, expected, beat_type, time_text, implicit))
        abs_start += length

    return notes, measures, order


def _q(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


# --------------------------------------------------------------------------- ties & slurs

def resolve_ties(notes: List[Note], labels: List[str], rep: Report):
    """Mark tie continuations. The state is kept across measure boundaries."""
    by_part: Dict[str, List[Note]] = defaultdict(list)
    for n in notes:
        by_part[n.part_id].append(n)
    for pid, pnotes in by_part.items():
        open_ties: Dict[Tuple[int, Fraction], List[Note]] = defaultdict(list)
        for n in sorted(pnotes, key=lambda x: (x.abs_onset, x.doc_order)):
            if n.tie_stop:
                cands = open_ties.get((n.staff, n.midi), [])
                cross_staff = False
                if not cands:
                    for (st, m), lst in open_ties.items():
                        if m == n.midi and lst:
                            cands, cross_staff = lst, True
                            break
                exact = [c for c in cands if c.abs_end == n.abs_onset]
                if exact:
                    start = exact[0]
                elif cands:
                    start = cands[0]
                    rep.warnings.append(f"Measure {labels[n.measure_idx]}: tie on {_plain(n)} has a gap "
                                        f"(start ends at {_q(start.abs_end)}, continuation begins at {_q(n.abs_onset)}).")
                else:
                    start = None
                if start is not None:
                    cands.remove(start)
                    n.continuation = True
                    rep.counts["tie_continuations"] += 1
                    if cross_staff:
                        rep.check.append(f"Measure {labels[n.measure_idx]}: tie on {_plain(n)} changes staff.")
                else:
                    msg = (f"Measure {labels[n.measure_idx]}: tie end on {_plain(n)} without a matching start - "
                           "counted as a new attack.")
                    rep.check.append(msg)
                    rep.flags[(n.measure_idx, n.onset)].append(msg)
            if n.tie_start:
                open_ties[(n.staff, n.midi)].append(n)
        for lst in open_ties.values():
            for n in lst:
                rep.info.append(f"Measure {labels[n.measure_idx]}: tie on {_plain(n)} has no end in the file.")


def check_same_pitch_slurs(notes: List[Note], labels: List[str], beat_types: List[int], mode: str, rep: Report):
    """
    A slur between two directly consecutive notes of the same pitch looks exactly like a tie
    in the printed score. In MusicXML, however, it is a <slur> (phrasing slur).
    Default "hold": treat it like a tie.  With --same-pitch-slur restrike: new attack.
    Both are reported.
    """
    by_part: Dict[str, List[Note]] = defaultdict(list)
    for n in notes:
        by_part[n.part_id].append(n)
    for pid, pnotes in by_part.items():
        active: set = set()                            # open slurs: (voice, slur number)
        prev_event: Dict[str, Tuple[Fraction, List[Note]]] = {}
        events: Dict[Tuple[Fraction, str], List[Note]] = defaultdict(list)
        for n in pnotes:
            events[(n.abs_onset, n.voice)].append(n)
        for (t, voice) in sorted(events, key=lambda k: (k[0], min(x.doc_order for x in events[k]))):
            ev = events[(t, voice)]
            covered = any(v == voice for v, _ in active)
            prev = prev_event.get(voice)
            if covered and prev is not None and prev[0] == t:
                prev_midis = {p.midi for p in prev[1]}
                for n in ev:
                    if n.midi in prev_midis and not n.continuation:
                        where = f"Measure {labels[n.measure_idx]}, beat {beat_label(n.onset, beat_types[n.measure_idx])}"
                        if mode == "hold":
                            n.held_by_slur = True
                            rep.counts["same_pitch_slur_held"] += 1
                            msg = (f"{where}: {_name(n)} - the slur between equal pitches is stored as a phrasing "
                                   "slur but looks like a tie -> held, NOT struck again.")
                        else:
                            rep.counts["same_pitch_slur_restruck"] += 1
                            msg = (f"{where}: {_name(n)} - the slur between equal pitches is a phrasing slur in "
                                   "the file (not a tie) -> written as a NEW attack. In the printed score it looks "
                                   "like a tie.")
                        rep.check.append(msg)
                        rep.flags[(n.measure_idx, n.onset)].append(msg)
            for n in ev:
                for num in n.slur_stops:
                    if (voice, num) in active:
                        active.discard((voice, num))
                    else:                              # slur across voices
                        for entry in [a for a in active if a[1] == num][:1]:
                            active.discard(entry)
            for n in ev:
                for num in n.slur_starts:
                    active.add((voice, num))
            prev_event[voice] = (max(x.abs_end for x in ev), ev)


# --------------------------------------------------------------------------- output helpers

def _plain(n: Note) -> str:
    return f"{n.step}{ALTER_TEXT.get(int(n.alter), '?') if n.alter.denominator == 1 else '?'}{n.octave}"


_NAME_MODE = {"mode": "sounding"}


def _name(n: Note) -> str:
    return note_name(n, _NAME_MODE["mode"])


def note_name(n: Note, mode: str = "sounding") -> str:
    if mode == "written":
        if n.accidental is None:
            acc = ""
        else:
            acc = ACCIDENTAL_TEXT.get(n.accidental, f"[{n.accidental}]")
    else:
        if n.alter.denominator == 1 and int(n.alter) in ALTER_TEXT:
            acc = ALTER_TEXT[int(n.alter)]
        else:
            acc = f"[alter={float(n.alter):g}]"
    name = n.step + acc
    if n.hand == LOWER:
        name = name.lower()
    return f"{name}{n.octave}"


def beat_label(onset: Fraction, beat_type: int) -> str:
    """Position in the measure as a beat of the time signature (6/8: eighths 1..6; 4/4: quarters 1..4)."""
    pos = onset / Fraction(4, beat_type) + 1
    if pos.denominator == 1:
        return str(pos.numerator)
    d = pos.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    whole = pos.numerator // pos.denominator
    if d == 1:                                   # finite decimal: exact, no rounding
        rest, digits = pos - whole, ""
        while rest:
            rest *= 10
            digit = rest.numerator // rest.denominator
            digits += str(digit)
            rest -= digit
        return f"{whole}.{digits}"
    rest = pos - whole
    return f"{whole} {rest.numerator}/{rest.denominator}"


def _sort_key(n: Note):
    return (-n.midi, 0 if n.hand == UPPER else 1, n.doc_order)


# --------------------------------------------------------------------------- main flow

def convert_root(root: ET.Element, source: str = "<xml>", accidentals: str = "sounding",
                 same_pitch_slur: str = "hold", upper: Optional[str] = None,
                 lower: Optional[str] = None, empty_measure: str = "-", hands: str = "playable") -> Result:
    if hands not in ("playable", "staff"):
        raise NotencodeError("--hands must be 'playable' or 'staff'.")
    if accidentals not in ("sounding", "written"):
        raise NotencodeError("--accidentals must be 'sounding' or 'written'.")
    if same_pitch_slur not in ("restrike", "hold"):
        raise NotencodeError("--same-pitch-slur must be 'restrike' or 'hold'.")
    _NAME_MODE["mode"] = accidentals
    rep = Report()
    total_note_elements = sum(1 for _ in root.iter("note"))

    staves = find_staves(root)
    if not staves:
        raise NotencodeError("No <part> elements found.")
    if not (upper or lower):
        staves = drop_empty_staves(root, staves, rep)
    hand_of = resolve_hands(staves, upper, lower, rep)

    all_notes: List[Note] = []
    part_measures: Dict[str, List[MeasureInfo]] = {}
    order = 0
    for part in root.findall("part"):
        pnotes, pmeasures, order = parse_part(part, hand_of, rep, order)
        all_notes.extend(pnotes)
        part_measures[part.get("id", "?")] = pmeasures

    # --- line up the measures of all parts
    counts = {pid: len(ms) for pid, ms in part_measures.items()}
    n_measures = max(counts.values()) if counts else 0
    if len(set(counts.values())) > 1:
        rep.warnings.append(f"The parts have different numbers of measures: {counts}. Matched by order.")
    measures: List[MeasureInfo] = []
    for i in range(n_measures):
        infos = [ms[i] for ms in part_measures.values() if i < len(ms)]
        lengths = {m.length for m in infos}
        if len(lengths) > 1:
            rep.warnings.append(f"Measure {infos[0].label}: the parts have different lengths "
                                f"({', '.join(_q(x) for x in sorted(lengths))} quarters).")
        if len({m.label for m in infos}) > 1:
            rep.warnings.append(f"Measure no. {i + 1}: different measure numbers in the parts: {[m.label for m in infos]}.")
        measures.append(infos[0])
    labels = [m.label for m in measures]
    beat_types = [m.beat_type for m in measures]
    for i, m in enumerate(measures):
        if m.expected is not None and m.length < m.expected:
            if i == 0:
                rep.info.append(f"Measure {m.label}: shorter than {m.time_text} - probably a pickup.")
            elif i == len(measures) - 1:
                rep.info.append(f"Measure {m.label}: shorter than {m.time_text} - probably completes the pickup.")
            elif not m.implicit:
                rep.warnings.append(f"Measure {m.label}: shorter than the time signature {m.time_text} "
                                    f"({_q(m.length)} instead of {_q(m.expected)} quarters).")

    # --- ties, slurs on equal pitches
    resolve_ties(all_notes, labels, rep)
    check_same_pitch_slurs(all_notes, labels, beat_types, same_pitch_slur, rep)

    # --- groups: same measure + exactly the same moment
    groups: Dict[Tuple[int, Fraction], List[Note]] = defaultdict(list)
    for n in all_notes:
        if not n.continuation and not n.held_by_slur:
            groups[(n.measure_idx, n.onset)].append(n)
    for key in sorted(groups):
        grp = groups[key]
        seen: Dict[Tuple[str, Fraction], Note] = {}
        for n in sorted(grp, key=lambda x: x.doc_order):
            k = (n.hand, n.midi)
            if k in seen:
                n.duplicate_of = seen[k]
                rep.counts["duplicates_merged"] += 1
                rep.info.append(f"Measure {labels[key[0]]}, beat {beat_label(key[1], beat_types[key[0]])}: "
                                f"{_name(n)} is in two voices - written once.")
            else:
                seen[k] = n
        where = f"Measure {labels[key[0]]}, beat {beat_label(key[1], beat_types[key[0]])}"
        if hands == "playable":
            assign_playable_hands(key, list(seen.values()), all_notes, where, rep)
        else:
            by_midi = defaultdict(set)
            for (hand, midi) in seen:
                by_midi[midi].add(hand)
            for midi, hs in by_midi.items():
                if len(hs) > 1:
                    msg = (f"{where}: the same pitch in both staves at once - both written "
                           "(only one key on the piano).")
                    rep.check.append(msg)
                    rep.flags[key].append(msg)

    # --- build the lines
    out_measures: List[List[str]] = []
    checklist: List[str] = []
    sounding = [n for n in all_notes if n.duplicate_of is None]
    for i, m in enumerate(measures):
        keys = sorted(k for k in groups if k[0] == i)
        lines = []
        header = f"Measure {m.label}"
        if i == 0 or m.time_text != measures[i - 1].time_text:
            header += f"   ({m.time_text})"
        checklist.append(header)
        for k in keys:
            attacks = sorted([n for n in groups[k] if n.duplicate_of is None], key=_sort_key)
            line = "+".join(note_name(n, accidentals) for n in attacks)
            lines.append(line)
            held = _held_at(sounding, i, k[1])
            beat = beat_label(k[1], m.beat_type)
            row = f"  beat {beat:<7}{line}"
            if held:
                row = f"{row:<46}  holds: {', '.join(held)}"
            checklist.append(row)
            for msg in rep.infos.get(k, []):
                checklist.append(f"             hands: {msg.split(': ', 1)[-1]}")
            for msg in rep.flags.get(k, []):
                checklist.append(f"             CHECK: {msg.split(': ', 1)[-1]}")
        if not keys:
            lines.append(empty_measure)
            held = _held_at(sounding, i, Fraction(0))
            checklist.append(f"  (no new attack){'  holds: ' + ', '.join(held) if held else ''}")
            rep.info.append(f"Measure {m.label}: no new attack - line '{empty_measure}' written.")
        out_measures.append(lines)
        checklist.append("")

    code_text = "\n\n".join("\n".join(ls) for ls in out_measures) + "\n"

    # --- note balance: every <note> element must fall into exactly one category
    z = rep.counts
    attacks_total = sum(1 for n in all_notes if n.is_attack)
    accounted = (attacks_total + z["tie_continuations"] + z["same_pitch_slur_held"]
                 + z["duplicates_merged"] + z["both_hands_merged"] + z["rests"] + z["grace_notes"] + z["cue_notes"]
                 + z["unpitched"] + z["unassigned"])
    balance_ok = accounted == total_note_elements
    if not balance_ok:
        rep.warnings.append(f"NOTE BALANCE DOES NOT ADD UP: {total_note_elements} <note> elements, "
                            f"but {accounted} accounted for.")

    staff_lines = []
    for p, s, name in staves:
        h = hand_of.get((p, s))
        staff_lines.append(f"   {p}/{s} {name!r:<8} -> " + ({UPPER: "upper (CAPITALS, right hand)",
                                                              LOWER: "lower (lowercase, left hand)"}.get(h, "not written")))
    n_lines = sum(len(ls) for ls in out_measures)
    report = [
        "NOTENCODE - REPORT",
        "=" * 60,
        f"Input:              {source}",
        f"Converter:          notencode.py version {VERSION}",
        f"Accidentals:        {accidentals}" + ("  (key signature + score = the key you press)"
                                                if accidentals == "sounding" else "  (printed accidentals only)"),
        f"Same-pitch slur:    {same_pitch_slur}",
        f"Hands:              {hands}" + ("  (same pitch once; hands never cross)" if hands == "playable"
                                          else "  (hand = staff)"),
        "Staves:",
        *staff_lines,
        f"Measures:           {n_measures}  (time signature {measures[0].time_text if measures else '?'})",
        f"Attack lines:       {n_lines}",
        "",
        "NOTE BALANCE (EVERY <note> ELEMENT)",
        f"   {total_note_elements:4d}  <note> elements in the file",
        f"   {attacks_total:4d}  written as struck notes",
        f"   {z['tie_continuations']:4d}  tie continuations (keep sounding, not written)",
        f"   {z['same_pitch_slur_held']:4d}  slur on the same pitch treated as held",
        f"   {z['duplicates_merged']:4d}  same pitch in two voices (written once)",
        f"   {z['both_hands_merged']:4d}  same pitch in both staves (written once)",
        f"   {z['rests']:4d}  rests",
        f"   {z['grace_notes']:4d}  grace notes (skipped)",
        f"   {z['cue_notes']:4d}  cue notes (skipped)",
        f"   {z['unpitched']:4d}  unpitched notes (skipped)",
        f"   {z['unassigned']:4d}  notes on unassigned staves",
        f"   => balance {'OK - every note accounted for exactly once' if balance_ok else 'ERROR'}",
        "",
        "WARNINGS (structure of the file)",
        *([f" - {w}" for w in rep.warnings] or [" - none"]),
        "",
        "PLEASE CHECK AGAINST THE PRINTED SCORE",
        *([f" - {w}" for w in rep.check] or [" - none"]),
        "",
        "HAND DECISIONS (rule: playable)" if hands == "playable" else "HAND DECISIONS",
        *([f" - {w}" for w in rep.hands] or [" - none"]),
        "",
        "NOTES",
        *([f" - {w}" for w in rep.info] or [" - none"]),
        "",
        "The converter reads the file note by note with fixed rules (no guessing: same file = same output).",
        "It can only be as correct as the MusicXML file itself. Whether the file matches the printed score",
        "is not checked - that is what the checklist is for.",
    ]
    checklist_text = "\n".join([
        "NOTENCODE - CHECKLIST",
        f"Source: {source}",
        "beat = position in the measure (in 6/8 counted in eighths: 1 2 3 4 5 6; 2.5 = a sixteenth after 2).",
        "'holds' = notes that keep sounding at this moment and are therefore NOT on the line.",
        "",
    ] + checklist).rstrip() + "\n"
    return Result(source, code_text, checklist_text, "\n".join(report) + "\n", out_measures, rep)


def _held_midis(notes: List[Note], midx: int, t: Fraction, hand: str) -> List[Fraction]:
    return [n.midi for n in notes if n.hand == hand and n.measure_idx == midx and n.duplicate_of is None and (
        (n.onset < t < n.end) or ((n.continuation or n.held_by_slur) and n.onset == t))]


def assign_playable_hands(key, uniq: List[Note], all_notes: List[Note], where: str, rep: Report):
    """
    Rule "playable":
    1. Same pitch in both staves -> written once, given to the hand whose stretch grows the least
       (held notes count). Tie: from C4 up the right hand, below C4 the left hand.
    2. If a left-hand note is higher than a right-hand note (voice crossing), the notes are shared out
       by pitch: the right hand takes the upper ones, the left hand the lower ones - as many as before.
    """
    midx, t = key
    by_midi: Dict[Fraction, List[Note]] = defaultdict(list)
    for n in uniq:
        by_midi[n.midi].append(n)
    for midi in sorted(by_midi, reverse=True):
        ns = by_midi[midi]
        if len(ns) < 2:
            continue

        def widening(hand):
            cur = [m.midi for m in uniq if m.hand == hand and m.midi != midi and m.duplicate_of is None]
            cur += _held_midis(all_notes, midx, t, hand)
            if not cur:
                return 0
            return max(0, midi - max(cur)) + max(0, min(cur) - midi)
        wu, wl = widening(UPPER), widening(LOWER)
        hand = UPPER if wu < wl else LOWER if wl < wu else (UPPER if midi >= 60 else LOWER)
        keep = next(n for n in ns if n.hand == hand)
        for n in ns:
            if n is not keep:
                n.duplicate_of = keep
                rep.counts["both_hands_merged"] += 1
        msg = (f"{where}: {_name(keep)} is in both staves - written once, {HAND_TEXT[hand]} "
               f"(stretch right +{_q(wu)}, left +{_q(wl)} semitones).")
        rep.hands.append(msg)
        rep.infos[key].append(msg)

    live = [n for n in uniq if n.duplicate_of is None]
    up = [n for n in live if n.hand == UPPER]
    lo = [n for n in live if n.hand == LOWER]
    if up and lo and max(n.midi for n in lo) > min(n.midi for n in up):
        before = {id(n): _name(n) for n in live}
        ordered = sorted(live, key=lambda n: (-n.midi, n.doc_order))
        changed = []
        for i, n in enumerate(ordered):
            new = UPPER if i < len(up) else LOWER
            if n.hand != new:
                n.hand = new
                changed.append(f"{before[id(n)]} → {_name(n)} ({HAND_TEXT[new]})")
        msg = (f"{where}: voices cross - so that the hands do not cross: "
               + ", ".join(changed) + ".")
        rep.hands.append(msg)
        rep.infos[key].append(msg)


def _held_at(notes: List[Note], midx: int, t: Fraction) -> List[str]:
    held = [n for n in notes if n.measure_idx == midx and (
        (n.onset < t < n.end) or ((n.continuation or n.held_by_slur) and n.onset == t))]
    seen, out = set(), []
    for n in sorted(held, key=_sort_key):
        nm = note_name(n, _NAME_MODE["mode"])
        if nm not in seen:
            seen.add(nm)
            out.append(nm)
    return out


def convert_file(path: Path, **opts) -> Result:
    return convert_root(load_root(Path(path)), source=Path(path).name, **opts)


def convert_xml_text(text: str, **opts) -> Result:
    return convert_root(parse_xml_bytes(text.encode("utf-8")), **opts)


# --------------------------------------------------------------------------- command line

def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")   # Windows console
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="MusicXML -> Notencode (version %s)" % VERSION)
    ap.add_argument("inputs", nargs="*",
                    help=".musicxml, .xml or .mxl (none given: every file in the input/ folder)")
    ap.add_argument("-o", "--output", help="output file (only with a single input file)")
    ap.add_argument("--accidentals", choices=["sounding", "written"], default="sounding")
    ap.add_argument("--same-pitch-slur", choices=["hold", "restrike"], default="hold")
    ap.add_argument("--upper", help="staff/staves for the right hand, e.g. P1 or P1/1")
    ap.add_argument("--lower", help="staff/staves for the left hand, e.g. P2 or P1/2")
    ap.add_argument("--hands", choices=["playable", "staff"], default="playable",
                    help="playable: same pitch once, hands never cross; staff: hand = staff")
    ap.add_argument("--empty-measure", default="-", help="line for a measure without a new attack (default: -)")
    args = ap.parse_args(argv)
    here = Path(__file__).resolve().parent
    inputs: List[Path] = []
    for item in args.inputs:                        # Windows does not expand *.mxl itself
        if any(ch in item for ch in "*?"):
            inputs.extend(sorted(Path(".").glob(item)))
        else:
            inputs.append(Path(item))
    if not args.inputs:
        inputs = sorted(p for p in (here / "input").glob("*")
                        if p.suffix.lower() in (".mxl", ".musicxml", ".xml"))
        if not inputs:
            print(f"No MusicXML file (.mxl, .musicxml, .xml) found in {here / 'input'}.")
            return 1
    if args.output and len(inputs) > 1:
        ap.error("-o/--output only works with a single input file.")

    rc = 0
    for inp in inputs:
        try:
            res = convert_file(inp, accidentals=args.accidentals, same_pitch_slur=args.same_pitch_slur,
                               upper=args.upper, lower=args.lower, empty_measure=args.empty_measure,
                               hands=args.hands)
        except (NotencodeError, OSError) as e:
            print(f"ERROR in {inp.name}: {e}")
            rc = 2
            continue
        if args.output:
            out = Path(args.output)
        else:
            out = here / "output" / f"{inp.stem}_notencode.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        stem = out.with_suffix("")
        checklist_path = Path(f"{stem}.checklist.txt")
        report_path = Path(f"{stem}.report.txt")
        out.write_text(res.code_text, encoding="utf-8")
        checklist_path.write_text(res.checklist_text, encoding="utf-8")
        report_path.write_text(res.report_text, encoding="utf-8")
        r = res.report
        print(f"{inp.name}: {len(res.measures)} measures, {sum(len(m) for m in res.measures)} lines")
        print(f"   Notencode:  {out}")
        print(f"   Checklist:  {checklist_path}")
        print(f"   Report:     {report_path}")
        print(f"   {len(r.warnings)} warning(s), {len(r.check)} place(s) to check in the printed score")
    return rc


if __name__ == "__main__":
    sys.exit(main())
