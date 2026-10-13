# Easy Piano Note System – Specification (version 2)

The system has two layers: **Notencode**, a plain-text form of the music, and the **colored sheet** drawn from it.

This document defines the rules. `notencode.py` (Python) and `tools/build_html/core.js` (JavaScript) both follow it, and the test suite checks that they produce identical output.

## Notencode – basic rules

| Rule | Example |
|---|---|
| Upper staff (right hand): note name in CAPITALS | `F4`, `Bb4`, `F#5` |
| Lower staff (left hand): everything lowercase | `bb3`, `f#2`, `c4` |
| Case depends on the staff, never on the octave. Exceptions only by the hand rules below (same pitch, voice crossing). | bass C4 → `c4`; alto B♭3 → `Bb3` |
| Always give the octave (C4 = middle C) | `D4`, `bb2` |
| Notes struck together are joined with `+` | `F4+D4+bb3+bb2` |
| Order on a line: highest note first, by sound | `F4+E4` (not alphabetical) |
| Every new moment of attack = a new line | |
| Exactly one blank line between two measures | |

## Accidentals

Default **sounding**: the accidental of the key you press. The key signature counts (in B♭ major every B is `Bb`).

| MusicXML `<alter>` | Sign |
|---|---|
| -2 | `bb` |
| -1 | `b` |
| 0 / missing | – |
| 1 | `#` |
| 2 | `##` |

How to read it: the first letter is always the note name, then the accidental, then the octave. `bb3` = note B, accidental b, octave 3 (B♭3). `Bbb4` would be B double flat.

Alternative `--accidentals written`: only accidentals printed directly before the note. A natural sign is written as `n` (`Bn4`).

## Timeline

- The time of every note is computed from `<duration>`, `<backup>`, `<forward>` and `<chord/>`, with exact fractions (no rounding). The screen position (`default-x`) is **not** used.
- `<chord/>`: same moment as the previous note; the cursor does not move.
- Changing `<divisions>` are taken into account.
- Notes from both staves are only joined if they start **exactly** at the same moment in the same measure.

## Ties

- `<tie>` or `<notations><tied>` of type `stop`/`continue` = continuation → **no** new line, no note.
- The state is kept across measure boundaries, also for chains over several measures.
- Matched by staff + pitch (enharmonic: G♯ to A♭ works).
- A tie end without a start → written as an attack and reported.

## Decisions

| Case | Rule |
|---|---|
| Slur (`<slur>`) between **different** pitches | normal attack (phrasing) |
| Slur (`<slur>`) between two directly consecutive **equal** pitches in the same voice | **hold** (default): like a tie, no new attack – that is how the printed score reads. Reported. Alternative: `--same-pitch-slur restrike`. |
| Same pitch in two voices of the **same** staff at the same time (unison, shared note head) | written once |
| Same pitch in **both** staves at the same time | written **once**, given to the hand whose stretch grows the least (held notes count); tie: from C4 up the right hand, below the left hand. Reported. `--hands staff`: both written. |
| Voice crossing (a lower-staff note sounds higher than an upper-staff note) | **shared out playably**: the right hand takes the upper notes, the left hand the lower ones, as many as before. Example: `G4+Eb4+bb3+g3` instead of `G4+eb4+Bb3+g3`. Reported. `--hands staff`: hand = staff. |
| Measure without a new attack (only rests or held notes) | line `-` (otherwise counting measures by blank lines would break) |
| Rests | no line; their duration moves the following notes |
| Grace notes, cue notes | not written, counted in the report |
| Chord symbols (B♭, F7 …), lyrics, dynamics | ignored |
| Order of measures | order in the file (= order in the printed score); repeats are not written out |

## Staves → hands

- Exactly two staves in the file: the first is upper, the second lower. It does not matter whether these are two parts (P1, P2) or one piano part with `<staff>` 1/2.
- The hand follows the staff the note is written on (`<staff>`), not the voice.
- After that, the hand rules "playable" apply (see Decisions). With `--hands staff` only the staff counts.
- More than two staves, but only one or two of them with notes: the empty staves (rests only) are skipped and listed under "Notes" (common in hymnal files with an empty text staff).
- Otherwise, with more than two staves, the converter stops and asks for `--upper` / `--lower` instead of guessing. Several staves per hand are separated by commas: `--upper P1,P2 --lower P3`. Staves that are not chosen are listed under "Notes"; their notes count as "unassigned" in the note balance.

## Self-check on every run

- **Note balance**: every `<note>` element of the file must fall into exactly one category: struck, tie continuation, unison, rest, grace note, etc. Otherwise a warning.
- Measure lengths are checked against the time signature (pickup and final measure only as a note).

## Output files

| File | Content |
|---|---|
| `NAME_notencode.txt` | the Notencode |
| `NAME_notencode.checklist.txt` | the same code with measure number, beat and the notes that keep sounding – for comparing with the printed score |
| `NAME_notencode.report.txt` | note balance, warnings, places to check in the score, hand decisions |

Beats are written in the unit of the time signature (6/8: eighths 1–6; 4/4: quarters 1–4). `2.5` = halfway between beat 2 and 3; triplets are written as fractions (`1 1/3`).

## Colored sheet (display)

The goal of the project is music in its own notation. Notencode is the tested intermediate step.

| Rule | Value |
|---|---|
| Lines | 3 per octave, one block per octave, highest octave on top |
| Places in a block (in line spaces from the top line) | B 0 (top line) · A 0.5 · G 1 (middle line) · F 1.5 · E 2 (bottom line) · D 2.5 · C 3 |
| Block spacing | 4 line spaces block + 3 spaces gap = 7 spaces per octave |
| Colors | C #FFD400 yellow · D #1976D2 blue · E #2E7D32 green · F #8E24AA purple · G #6D4C41 brown · A #D32F2F red · B #F57C00 orange |
| Note head | ellipse 9 × 7 at a line space of 14 |
| Accidentals | to the left of every note (`b`, `#`, `bb`, `##`), because there is no key signature; the place follows the note name (C♭4 sits on C4) |
| Time | "compact" (default): every doubling of a duration gets one unit more space, so long notes do not waste room. "exact": distance strictly proportional to time (at least 60 px per quarter). In both cases wide enough that heads and accidentals never collide. |
| Octaves | No octave labels. The block from C4 (middle of the keyboard) has thicker, stronger lines and appears on every row as an anchor; count up and down from it. "used only" (default): above and below only as many blocks as these measures need. "all": the whole range of the piece. |
| Rest | thin vertical stroke from the top to the bottom line – only where nothing sounds at all |
| Measures | faint dashed barline without a number (minimal style); a little room before each measure so accidentals do not touch the line |
| Held notes | not drawn again (as in Notencode) |
| Left hand | option "darker" (color × 0.6); default: same color |
| Second in the same block | the second head sits right next to the first so they do not cover each other |
| Rows | "by phrase" (default): every musical line starts a new row, even in the middle of a measure. Fixed breaks: fermata, breath mark, double/repeat barline, a hymnal measure split at the end of a line, silence of at least one beat. Weighed: punctuation of verse 1 (end of sentence stronger than a comma), long melody notes (at least twice as long as usual), line length (5–16 syllables or melody notes). Rows that are too wide wrap at the barline. Other settings: auto, 2 or 4 measures per row. By hand (right-click on a note, long press on a phone): to the next / previous row, new row from here, automatic again – remembered per piece in the browser. Without lyrics and with a fast melody: breaks preferably at the barline, target 4 measures (from 4/4: 2 measures). Display only – the Notencode does not change. |
| Fullscreen | only title, colors and sheet over the whole screen; "− / +" note size (0.75× to 2.5×), ← → next/previous note, Esc closes |
