# -*- coding: utf-8 -*-
"""
Automated tests for notencode.py

Run (inside the project folder):
    python -m unittest discover -s tests -v
"""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import notencode as nc  # noqa: E402


# --------------------------------------------------------------------------- small XML building blocks

def note(step, octave, dur, alter=None, voice="1", staff=None, chord=False, tie=None, tied=None,
         slur=None, rest=False, grace=False, x=None, accidental=None, cue=False):
    attrs = f' default-x="{x}"' if x is not None else ""
    parts = [f"<note{attrs}>"]
    if grace:
        parts.append("<grace/>")
    if cue:
        parts.append("<cue/>")
    if chord:
        parts.append("<chord/>")
    if rest:
        parts.append("<rest/>")
    else:
        alt = f"<alter>{alter}</alter>" if alter is not None else ""
        parts.append(f"<pitch><step>{step}</step>{alt}<octave>{octave}</octave></pitch>")
    if not grace:
        parts.append(f"<duration>{dur}</duration>")
    for t in ([tie] if isinstance(tie, str) else (tie or [])):
        parts.append(f'<tie type="{t}"/>')
    parts.append(f"<voice>{voice}</voice>")
    if accidental:
        parts.append(f"<accidental>{accidental}</accidental>")
    if staff is not None:
        parts.append(f"<staff>{staff}</staff>")
    notations = []
    for t in ([tied] if isinstance(tied, str) else (tied or [])):
        notations.append(f'<tied type="{t}"/>')
    for s in ([slur] if isinstance(slur, tuple) else (slur or [])):
        notations.append(f'<slur type="{s[0]}" number="{s[1]}"/>')
    if notations:
        parts.append("<notations>" + "".join(notations) + "</notations>")
    parts.append("</note>")
    return "".join(parts)


def rest(dur, voice="1", staff=None):
    return note("C", 4, dur, rest=True, voice=voice, staff=staff)


def backup(d):
    return f"<backup><duration>{d}</duration></backup>"


def forward(d):
    return f"<forward><duration>{d}</duration></forward>"


def attributes(divisions=4, beats=4, beat_type=4, fifths=0, staves=None):
    st = f"<staves>{staves}</staves>" if staves else ""
    return (f"<attributes><divisions>{divisions}</divisions><key><fifths>{fifths}</fifths></key>"
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>{st}</attributes>")


def measure(number, *items, implicit=False):
    imp = ' implicit="yes"' if implicit else ""
    return f'<measure number="{number}"{imp}>' + "".join(items) + "</measure>"


def score(*parts):
    """parts: (part_id, [measure-xml, ...])"""
    plist = "".join(f'<score-part id="{pid}"><part-name>{pid}</part-name></score-part>' for pid, _ in parts)
    body = "".join(f'<part id="{pid}">' + "".join(ms) + "</part>" for pid, ms in parts)
    return f'<?xml version="1.0" encoding="UTF-8"?><score-partwise><part-list>{plist}</part-list>{body}</score-partwise>'


def code(xml, **opts):
    return nc.convert_xml_text(xml, **opts)


def lines(xml, **opts):
    return code(xml, **opts).code_text.rstrip("\n").split("\n")


A = attributes  # short form


# --------------------------------------------------------------------------- timing

class Timing(unittest.TestCase):

    def test_01_simultaneous_notes_of_both_parts_on_one_line(self):
        xml = score(("P1", [measure(1, A(), note("A", 4, 16))]),
                    ("P2", [measure(1, A(), note("D", 3, 16))]))
        self.assertEqual(lines(xml), ["A4+d3"])

    def test_02_different_moments_never_joined_even_with_same_default_x(self):
        # Same screen position (default-x), but a different musical time
        xml = score(("P1", [measure(1, A(), note("A", 4, 4, x=50), note("B", 4, 12, x=90))]),
                    ("P2", [measure(1, A(), note("D", 3, 8, x=90), note("E", 3, 8, x=50))]))
        self.assertEqual(lines(xml), ["A4+d3", "B4", "e3"])

    def test_05_backup_layers_voices(self):
        xml = score(("P1", [measure(1, A(),
                                    note("C", 5, 8), note("D", 5, 8),            # voice 1: half, half
                                    backup(16),
                                    note("E", 4, 4, voice="2"), note("F", 4, 4, voice="2"),
                                    note("G", 4, 8, voice="2"))]))
        self.assertEqual(lines(xml), ["C5+E4", "F4", "D5+G4"])

    def test_06_forward_skips_time(self):
        xml = score(("P1", [measure(1, A(),
                                    note("C", 5, 16),
                                    backup(16),
                                    forward(8), note("G", 4, 8, voice="2"))]))
        self.assertEqual(lines(xml), ["C5", "G4"])

    def test_07_chord_does_not_move_the_cursor(self):
        # An early prototype shifted chord notes back by the duration of the previous note.
        xml = score(("P1", [measure(1, A(),
                                    note("C", 4, 4), note("E", 4, 4, chord=True), note("G", 4, 4, chord=True),
                                    note("D", 4, 12))]))
        self.assertEqual(lines(xml), ["G4+E4+C4", "D4"])

    def test_triplets_not_wrongly_merged(self):
        # Upper: eighth-note triplet (divisions=6: triplet eighth = 2), lower: normal eighths (= 3)
        xml = score(("P1", [measure(1, A(divisions=6), note("C", 5, 2), note("D", 5, 2), note("E", 5, 2),
                                    note("F", 5, 18))]),
                    ("P2", [measure(1, A(divisions=6), note("C", 3, 3), note("G", 3, 3), note("C", 3, 18))]))
        self.assertEqual(lines(xml), ["C5+c3", "D5", "g3", "E5", "F5+c3"])

    def test_divisions_change_between_measures(self):
        xml = score(("P1", [measure(1, A(divisions=2), note("C", 4, 2), note("D", 4, 6)),
                            measure(2, "<attributes><divisions>8</divisions></attributes>",
                                    note("E", 4, 8), note("F", 4, 24))]),
                    ("P2", [measure(1, A(divisions=4), note("C", 3, 4), note("D", 3, 12)),
                            measure(2, note("E", 3, 4), note("F", 3, 12))]))
        self.assertEqual(lines(xml), ["C4+c3", "D4+d3", "", "E4+e3", "F4+f3"])

    def test_beat_labels(self):
        self.assertEqual(nc.beat_label(nc.Fraction(0), 4), "1")
        self.assertEqual(nc.beat_label(nc.Fraction(3, 2), 8), "4")
        self.assertEqual(nc.beat_label(nc.Fraction(3, 4), 8), "2.5")
        self.assertEqual(nc.beat_label(nc.Fraction(1, 3), 4), "1 1/3")


class NoteNames(unittest.TestCase):

    def test_03_accidentals_are_kept(self):
        xml = score(("P1", [measure(1, A(fifths=-2), note("B", 4, 16, alter=-1))]),
                    ("P2", [measure(1, A(fifths=-2), note("B", 3, 16, alter=-1))]))
        self.assertEqual(lines(xml), ["Bb4+bb3"])

    def test_sharps_and_double_accidentals(self):
        xml = score(("P1", [measure(1, A(), note("F", 5, 4, alter=1), note("C", 5, 4, alter=2),
                                    note("E", 4, 4, alter=-2), note("G", 4, 4))]),
                    ("P2", [measure(1, A(), note("F", 2, 16, alter=1))]))
        self.assertEqual(lines(xml), ["F#5+f#2", "C##5", "Ebb4", "G4"])

    def test_04_octaves_unchanged(self):
        xml = score(("P1", [measure(1, A(), note("C", 6, 16))]),
                    ("P2", [measure(1, A(), note("C", 1, 16))]))
        self.assertEqual(lines(xml), ["C6+c1"])

    def test_case_depends_on_staff_not_on_octave(self):
        # Old bug: a bass C4 was written in capitals because octave >= 4
        xml = score(("P1", [measure(1, A(), note("E", 3, 16))]),
                    ("P2", [measure(1, A(), note("C", 4, 16))]))
        self.assertEqual(lines(xml, hands="staff"), ["c4+E3"])
        self.assertEqual(lines(xml), ["C4+e3"])          # playable: hands do not cross

    def test_sorted_by_pitch_not_alphabetically(self):
        # E4/F4: alphabetically E would come first, but F4 sounds higher. Cb4 sounds like B3.
        xml = score(("P1", [measure(1, A(), note("E", 4, 4), note("F", 4, 4, chord=True),
                                    note("C", 4, 4, alter=-1, chord=True), note("D", 4, 12))]),
                    ("P2", [measure(1, A(), note("C", 4, 16))]))
        self.assertEqual(lines(xml, hands="staff")[0], "F4+E4+c4+Cb4")

    def test_written_mode_only_printed_accidentals(self):
        xml = score(("P1", [measure(1, A(fifths=-2),
                                    note("B", 4, 4, alter=-1),                       # flat from the key, not printed
                                    note("B", 4, 4, accidental="natural"),           # natural sign
                                    note("F", 4, 4, alter=1, accidental="sharp"),
                                    note("E", 4, 4, alter=-1))]))
        self.assertEqual(lines(xml, accidentals="written"), ["B4", "Bn4", "F#4", "E4"])
        self.assertEqual(lines(xml, accidentals="sounding"), ["Bb4", "B4", "F#4", "Eb4"])


class Ties(unittest.TestCase):

    def test_08_tie_continuation_is_not_an_attack(self):
        xml = score(("P1", [measure(1, A(), note("G", 4, 8, tie="start", tied="start"),
                                    note("G", 4, 8, tie="stop", tied="stop"))]),
                    ("P2", [measure(1, A(), note("C", 3, 8), note("E", 3, 8))]))
        self.assertEqual(lines(xml), ["G4+c3", "e3"])

    def test_tie_across_barline(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8), note("G", 4, 8, tie="start")),
                            measure(2, note("G", 4, 8, tie="stop"), note("A", 4, 8))]))
        self.assertEqual(lines(xml), ["C5", "G4", "", "A4"])

    def test_tie_chain_over_three_measures(self):
        # Early prototype: the last link was written as an attack again
        xml = score(("P1", [measure(1, A(), note("C", 5, 16, tie="start")),
                            measure(2, note("C", 5, 16, tie=["stop", "start"])),
                            measure(3, note("C", 5, 8, tie="stop"), note("D", 5, 8))]))
        self.assertEqual(lines(xml), ["C5", "", "-", "", "D5"])

    def test_tie_only_as_tied_element(self):
        xml = score(("P1", [measure(1, A(), note("E", 4, 8, tied="start"), note("E", 4, 8, tied="stop"))]))
        self.assertEqual(lines(xml), ["E4"])

    def test_tie_enharmonic(self):
        xml = score(("P1", [measure(1, A(), note("G", 4, 8, alter=1, tie="start"),
                                    note("A", 4, 8, alter=-1, tie="stop"))]))
        self.assertEqual(lines(xml), ["G#4"])

    def test_tie_in_one_voice_other_voice_strikes(self):
        xml = score(("P1", [measure(1, A(),
                                    note("C", 5, 8, tie="start"), note("C", 5, 8, tie="stop"),
                                    backup(16),
                                    note("E", 4, 8, voice="2"), note("F", 4, 8, voice="2"))]))
        self.assertEqual(lines(xml), ["C5+E4", "F4"])
        res = code(xml)
        self.assertIn("holds: C5", res.checklist_text)

    def test_tie_stop_without_start_stays_attack_and_is_reported(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8), note("C", 5, 8, tie="stop"))]))
        res = code(xml)
        self.assertEqual(res.code_text.split(), ["C5", "C5"])
        self.assertTrue(any("without a matching start" in p for p in res.report.check))


class Slurs(unittest.TestCase):

    def test_09_slurs_do_not_change_attacks(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 4, slur=("start", 1)), note("D", 5, 4),
                                    note("E", 5, 8, slur=("stop", 1)))]))
        self.assertEqual(lines(xml), ["C5", "D5", "E5"])
        self.assertEqual(code(xml).report.check, [])

    def test_same_pitch_slur_default_is_hold_and_is_reported(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8, slur=("start", 1)),
                                    note("C", 5, 8, slur=("stop", 1)))]))
        res = code(xml)
        self.assertEqual(res.code_text.split(), ["C5"])
        self.assertEqual(len(res.report.check), 1)
        self.assertIn("phrasing slur", res.report.check[0])

    def test_same_pitch_slur_restrike(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8, slur=("start", 1)),
                                    note("C", 5, 8, slur=("stop", 1)))]))
        res = code(xml, same_pitch_slur="restrike")
        self.assertEqual(res.code_text.split(), ["C5", "C5"])
        self.assertEqual(len(res.report.check), 1)

    def test_same_pitch_slur_hold(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8, slur=("start", 1)),
                                    note("C", 5, 8, slur=("stop", 1)))]))
        self.assertEqual(lines(xml, same_pitch_slur="hold"), ["C5"])

    def test_same_pitch_slur_hold_leaves_other_notes_alone(self):
        # Under the slur: C5 -> C5 (equal), E4 -> F4 (different)
        xml = score(("P1", [measure(1, A(),
                                    note("C", 5, 8, slur=("start", 1)), note("E", 4, 8, chord=True),
                                    note("C", 5, 8, slur=("stop", 1)), note("F", 4, 8, chord=True))]))
        self.assertEqual(lines(xml, same_pitch_slur="hold"), ["C5+E4", "F4"])

    def test_same_slur_number_in_two_voices(self):
        # MuseScore numbers slurs per voice from 1 - they must not end each other
        xml = score(("P1", [measure(1, A(),
                                    note("G", 3, 8, slur=("start", 1)), note("A", 3, 8, slur=("stop", 1)),
                                    backup(16),
                                    note("E", 3, 8, voice="2", slur=("start", 1)),
                                    note("E", 3, 8, voice="2", slur=("stop", 1)))]))
        self.assertEqual(lines(xml, same_pitch_slur="hold"), ["G3+E3", "A3"])


class RestsMeasuresFormat(unittest.TestCase):

    def test_10_rests_skipped_duration_counts(self):
        xml = score(("P1", [measure(1, A(), rest(4), note("D", 5, 12))]),
                    ("P2", [measure(1, A(), note("C", 3, 8), note("G", 2, 8))]))
        self.assertEqual(lines(xml), ["c3", "D5", "g2"])

    def test_11_measures_in_order_with_one_blank_line(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 16)), measure(2, note("D", 5, 16)),
                            measure(3, note("E", 5, 16))]))
        self.assertEqual(code(xml).code_text, "C5\n\nD5\n\nE5\n")

    def test_empty_measure_gets_dash(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 16)), measure(2, rest(16)), measure(3, note("E", 5, 16))]))
        self.assertEqual(code(xml).code_text, "C5\n\n-\n\nE5\n")

    def test_pickup(self):
        xml = score(("P1", [measure(0, A(beats=3), note("G", 4, 4), implicit=True),
                            measure(1, note("C", 5, 12))]))
        res = code(xml)
        self.assertEqual(res.code_text, "G4\n\nC5\n")
        self.assertFalse(any("shorter" in w for w in res.report.warnings))
        self.assertTrue(any("pickup" in h for h in res.report.info))

    def test_same_pitch_in_two_voices_once(self):
        xml = score(("P1", [measure(1, A(), note("B", 3, 16, alter=-1), backup(16),
                                    note("B", 3, 16, alter=-1, voice="2"))]))
        self.assertEqual(lines(xml), ["Bb3"])

    def test_grace_and_cue_notes_not_written(self):
        xml = score(("P1", [measure(1, A(), note("D", 5, 0, grace=True), note("C", 5, 8),
                                    note("A", 4, 8, cue=True))]))
        res = code(xml)
        self.assertEqual(res.code_text, "C5\n")
        self.assertEqual(res.report.counts["grace_notes"], 1)
        self.assertEqual(res.report.counts["cue_notes"], 1)

    def test_output_is_reproducible(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 8), note("D", 5, 8))]),
                    ("P2", [measure(1, A(), note("C", 3, 16))]))
        self.assertEqual(code(xml).code_text, code(xml).code_text)

    def test_balance_every_note_accounted_for(self):
        xml = score(("P1", [measure(1, A(), rest(4), note("C", 5, 4, tie="start"), note("C", 5, 4, tie="stop"),
                                    note("D", 5, 0, grace=True), note("E", 5, 4), backup(4),
                                    note("E", 5, 4, voice="2"))]))
        self.assertIn("balance OK", code(xml).report_text)


class HandRules(unittest.TestCase):
    """Rule 'playable' (default) and 'staff'."""

    def test_same_pitch_both_staves_once_right_hand(self):
        # Eb4 in alto (upper) and tenor (lower): right G4-Eb4 = +4, left Bb3-Eb4 = +5 -> right hand
        xml = score(("P1", [measure(1, A(), note("G", 4, 16), backup(16), note("E", 4, 16, alter=-1, voice="2"))]),
                    ("P2", [measure(1, A(), note("E", 4, 16, alter=-1), backup(16),
                                    note("B", 3, 16, alter=-1, voice="2"))]))
        self.assertEqual(lines(xml), ["G4+Eb4+bb3"])
        self.assertIn("balance OK", code(xml).report_text)

    def test_same_pitch_both_staves_left_hand(self):
        xml = score(("P1", [measure(1, A(), note("E", 4, 16), backup(16), note("G", 3, 16, voice="2"))]),
                    ("P2", [measure(1, A(), note("G", 3, 16), backup(16), note("F", 3, 16, voice="2"))]))
        self.assertEqual(lines(xml), ["E4+g3+f3"])

    def test_tie_break_from_c4_right_hand(self):
        xml = score(("P1", [measure(1, A(), note("E", 4, 16), backup(16), note("C", 4, 16, voice="2"))]),
                    ("P2", [measure(1, A(), note("C", 4, 16), backup(16), note("G", 3, 16, alter=1, voice="2"))]))
        self.assertEqual(lines(xml), ["E4+C4+g#3"])

    def test_held_notes_count_for_the_stretch(self):
        # D5 keeps sounding on the right -> G4 on the right would widen the stretch by 7, on the left (D4) only by 5
        xml = score(("P1", [measure(1, A(), note("D", 5, 16), backup(16), rest(8, voice="2"),
                                    note("G", 4, 8, voice="2"))]),
                    ("P2", [measure(1, A(), rest(8), note("G", 4, 8), note("D", 4, 8, chord=True))]))
        self.assertEqual(lines(xml), ["D5", "g4+d4"])

    def test_voice_crossing_is_shared_out_playably(self):
        # Tenor Eb4 above alto Bb3 (Silent Night m. 7): right hand the upper two, left hand the lower two
        xml = score(("P1", [measure(1, A(), note("G", 4, 16), backup(16), note("B", 3, 16, alter=-1, voice="2"))]),
                    ("P2", [measure(1, A(), note("E", 4, 16, alter=-1), backup(16), note("G", 3, 16, voice="2"))]))
        self.assertEqual(lines(xml), ["G4+Eb4+bb3+g3"])
        self.assertEqual(len(code(xml).report.hands), 1)

    def test_staff_mode_follows_the_staves_strictly(self):
        crossing = score(("P1", [measure(1, A(), note("G", 4, 16), backup(16), note("B", 3, 16, alter=-1, voice="2"))]),
                         ("P2", [measure(1, A(), note("E", 4, 16, alter=-1), backup(16), note("G", 3, 16, voice="2"))]))
        self.assertEqual(lines(crossing, hands="staff"), ["G4+eb4+Bb3+g3"])
        same = score(("P1", [measure(1, A(), note("G", 4, 16), backup(16), note("E", 4, 16, alter=-1, voice="2"))]),
                     ("P2", [measure(1, A(), note("E", 4, 16, alter=-1), backup(16),
                                     note("B", 3, 16, alter=-1, voice="2"))]))
        res = code(same, hands="staff")
        self.assertEqual(res.code_text, "G4+Eb4+eb4+bb3\n")
        self.assertEqual(len(res.report.check), 1)


class StaffAssignment(unittest.TestCase):

    def test_one_part_with_two_staves(self):
        xml = score(("P1", [measure(1, A(staves=2),
                                    note("A", 4, 16, staff=1), backup(16),
                                    note("B", 2, 16, alter=-1, voice="5", staff=2))]))
        self.assertEqual(lines(xml), ["A4+bb2"])

    def test_voice_moves_to_the_other_staff(self):
        # Hand = staff, even if the voice is the same
        xml = score(("P1", [measure(1, A(staves=2),
                                    note("C", 4, 8, staff=1), note("C", 4, 8, staff=2))]))
        self.assertEqual(lines(xml), ["C4", "c4"])

    def test_more_than_two_staves_without_choice_is_an_error(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 16))]),
                    ("P2", [measure(1, A(staves=2), note("E", 4, 16, staff=1), backup(16),
                                    note("C", 3, 16, staff=2))]))
        with self.assertRaises(nc.NotencodeError):
            code(xml)
        self.assertEqual(lines(xml, upper="P2/1", lower="P2/2"), ["E4+c3"])

    def test_empty_staff_is_skipped(self):
        # Hymnal files: an empty staff (rests only), below it soprano/alto and tenor/bass
        xml = score(("P1", [measure(1, A(), rest(16)), measure(2, rest(16))]),
                    ("P2", [measure(1, A(), note("E", 4, 16)), measure(2, note("F", 4, 16))]),
                    ("P3", [measure(1, A(), note("C", 3, 16)), measure(2, note("A", 2, 16))]))
        r = code(xml)
        self.assertEqual(r.code_text.rstrip("\n").split("\n"), ["E4+c3", "", "F4+a2"])
        self.assertTrue(any("P1/1" in h and "no notes" in h for h in r.report.info))
        self.assertIn("balance OK", r.report_text)

    def test_three_staves_with_notes_stay_an_error(self):
        xml = score(("P1", [measure(1, A(), rest(8), note("G", 5, 8))]),
                    ("P2", [measure(1, A(), note("E", 4, 16))]),
                    ("P3", [measure(1, A(), note("C", 3, 16))]))
        with self.assertRaises(nc.NotencodeError):
            code(xml)

    def test_mxl_archive(self):
        xml = score(("P1", [measure(1, A(), note("C", 5, 16))]))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("META-INF/container.xml",
                       '<container><rootfiles><rootfile full-path="music.xml"/></rootfiles></container>')
            z.writestr("music.xml", xml)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "test.mxl"
            tmp.write_bytes(buf.getvalue())
            self.assertEqual(nc.convert_file(tmp).code_text, "C5\n")

    def test_mxl_umlaut_in_file_name_without_utf8_flag(self):
        # Some programs store "fröhliche.xml" as UTF-8 without flagging it in the archive
        xml = score(("P1", [measure(1, A(), note("C", 5, 16))]))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("META-INF/container.xml",
                       '<?xml version="1.0" encoding="UTF-8"?><container><rootfiles>'
                       '<rootfile full-path="fröhliche.xml"/></rootfiles></container>'.encode("utf-8"))
            z.writestr("froehliche.xml", xml)   # same length as "fröhliche.xml" in UTF-8
        raw = buf.getvalue().replace(b"froehliche.xml", "fröhliche.xml".encode("utf-8"))
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "test.mxl"
            tmp.write_bytes(raw)
            with zipfile.ZipFile(tmp) as z:
                self.assertFalse(z.infolist()[1].flag_bits & 0x800)
            self.assertEqual(nc.convert_file(tmp).code_text, "C5\n")


# --------------------------------------------------------------------------- Silent Night (a real file)

class SilentNight(unittest.TestCase):
    SOURCE = ROOT / "examples" / "silent_night.mxl"

    def setUp(self):
        if not self.SOURCE.exists():
            self.skipTest("source file not in examples/")

    def test_12_first_group(self):
        res = nc.convert_file(self.SOURCE)
        self.assertEqual(res.measures[0][0], "F4+D4+bb3+bb2")

    def test_measures_1_to_4_as_read_from_the_printed_score(self):
        # Read independently from the printed score
        res = nc.convert_file(self.SOURCE, same_pitch_slur="hold")
        self.assertEqual(res.measures[:4], [
            ["F4+D4+bb3+bb2", "G4+Eb4", "F4+D4+bb3+bb2", "D4+Bb3+f3+bb2"],
            ["F4+D4+bb3+bb2", "G4+Eb4", "F4+D4+bb3+bb2", "D4+Bb3+f3+bb2"],
            ["C5+Eb4+a3+f3", "C5+Eb4+a3+f3", "A4+Eb4+c4+f3"],
            ["Bb4+D4+bb3+bb2", "Bb4+D4+f3+bb2", "F4+D4+bb3+bb2"],
        ])

    def test_whole_output_unchanged(self):
        for mode in ("hold", "restrike"):
            expected = (HERE / f"expected_silent_night_{mode}.txt")
            if not expected.exists():
                self.skipTest("reference output missing")
            res = nc.convert_file(self.SOURCE, same_pitch_slur=mode)
            self.assertEqual(res.code_text, expected.read_text(encoding="utf-8"), mode)
            self.assertIn("balance OK", res.report_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
