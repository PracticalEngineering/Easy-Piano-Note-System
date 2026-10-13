/* Notencode core (JavaScript) - an exact port of notencode.py.
   Runs in the browser (DOMParser) and in Node (with @xmldom/xmldom) - Node is only used for tests. */
(function (root) {
  'use strict';
  const VERSION = '2.1';
  const STEP_SEMITONES = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  const ALTER_TEXT = { '-2': 'bb', '-1': 'b', '0': '', '1': '#', '2': '##' };
  const ACCIDENTAL_TEXT = {
    'sharp': '#', 'flat': 'b', 'natural': 'n', 'double-sharp': '##', 'sharp-sharp': '##',
    'flat-flat': 'bb', 'double-flat': 'bb', 'natural-sharp': '#', 'natural-flat': 'b',
  };
  const UPPER = 'upper', LOWER = 'lower';
  const HAND_TEXT = { upper: 'right hand', lower: 'left hand' };

  class NotencodeError extends Error {}

  // ------------------------------------------------------------------ fractions
  function gcd(a, b) { a = Math.abs(a); b = Math.abs(b); while (b) { [a, b] = [b, a % b]; } return a || 1; }
  class Fr {
    constructor(n, d = 1) {
      if (d < 0) { n = -n; d = -d; }
      const g = gcd(n, d); this.n = n / g; this.d = d / g;
    }
    add(o) { return new Fr(this.n * o.d + o.n * this.d, this.d * o.d); }
    sub(o) { return new Fr(this.n * o.d - o.n * this.d, this.d * o.d); }
    mul(o) { return new Fr(this.n * o.n, this.d * o.d); }
    div(o) { return new Fr(this.n * o.d, this.d * o.n); }
    cmp(o) { const x = this.n * o.d - o.n * this.d; return x < 0 ? -1 : x > 0 ? 1 : 0; }
    eq(o) { return this.n === o.n && this.d === o.d; }
    lt(o) { return this.cmp(o) < 0; }
    gt(o) { return this.cmp(o) > 0; }
    isZero() { return this.n === 0; }
    key() { return this.n + '/' + this.d; }
    num() { return this.n / this.d; }
  }
  const F0 = new Fr(0);
  const fint = (i) => new Fr(i);
  const fmax = (a, b) => (a.cmp(b) >= 0 ? a : b);
  function frParse(text) {               // like Python Fraction("1.5")
    const t = String(text).trim();
    const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(t);
    if (!m || (m[2] === '' && (m[3] || '') === '')) throw new NotencodeError(`Invalid number ${JSON.stringify(t)} in the file.`);
    const frac = m[3] || '';
    let n = parseInt((m[2] || '0') + frac, 10); const d = Math.pow(10, frac.length);
    if (m[1] === '-') n = -n;
    return new Fr(n, d);
  }
  const _frac = (text) => (text && text.trim() ? frParse(text) : F0);
  const _q = (x) => (x.d === 1 ? String(x.n) : `${x.n}/${x.d}`);
  function pyRepr(s) {                      // like Python's repr() for strings (control characters as \n, \t ...)
    const ctl = (t) => t.replace(/[\x00-\x1f\x7f]/g, (c) => ({ '\n': '\\n', '\r': '\\r', '\t': '\\t' }[c] || '\\x' + c.charCodeAt(0).toString(16).padStart(2, '0')));
    if (s.includes("'") && !s.includes('"')) return '"' + ctl(s.replace(/\\/g, '\\\\')) + '"';
    return "'" + ctl(s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")) + "'";
  }
  const pyInt = (t) => (t !== null && /^\s*[+-]?\d+\s*$/.test(t) ? parseInt(t, 10) : null);

  // ------------------------------------------------------------------ DOM helpers
  const lname = (el) => el.localName || String(el.nodeName).replace(/^.*:/, '');
  function kids(el, tag) {
    const out = [];
    for (let c = el.firstChild; c; c = c.nextSibling) if (c.nodeType === 1 && (!tag || lname(c) === tag)) out.push(c);
    return out;
  }
  const kid = (el, tag) => kids(el, tag)[0] || null;
  function kidText(el, tag) { const k = kid(el, tag); return k ? (k.textContent || '') : null; }
  const path = (el, a, b) => kids(el, a).flatMap((x) => kids(x, b));
  function desc(el, tag) {                // all descendants with this name
    const out = [];
    (function walk(e) { for (let c = e.firstChild; c; c = c.nextSibling) if (c.nodeType === 1) { if (lname(c) === tag) out.push(c); walk(c); } })(el);
    return out;
  }

  // ------------------------------------------------------------------ reading the score
  function readScore(doc) {
    const rootEl = doc.documentElement;
    if (!rootEl || lname(rootEl) === 'parsererror' || doc.getElementsByTagName('parsererror').length) {
      throw new NotencodeError('The file is not valid XML.');
    }
    const kind = lname(rootEl);
    const names = new Map();
    for (const sp of path(rootEl, 'part-list', 'score-part')) names.set(sp.getAttribute('id'), (kidText(sp, 'part-name') || '').trim());
    const parts = [];
    if (kind === 'score-partwise') {
      for (const p of kids(rootEl, 'part')) {
        parts.push({ id: p.getAttribute('id') || '?', measures: kids(p, 'measure').map((m) => ({ el: m, number: m.getAttribute('number'), implicit: m.getAttribute('implicit') })) });
      }
    } else if (kind === 'score-timewise') {
      const byId = new Map();
      for (const m of kids(rootEl, 'measure')) {
        for (const p of kids(m, 'part')) {
          const pid = p.getAttribute('id') || '?';
          if (!byId.has(pid)) { byId.set(pid, { id: pid, measures: [] }); parts.push(byId.get(pid)); }
          byId.get(pid).measures.push({ el: p, number: m.getAttribute('number'), implicit: m.getAttribute('implicit') });
        }
      }
    } else {
      throw new NotencodeError(`Unknown root element <${kind}>. Expected MusicXML (score-partwise).`);
    }
    const totalNotes = desc(rootEl, 'note').length;
    return { names, parts, totalNotes };
  }

  function findStaves(score) {
    const staves = [];
    for (const part of score.parts) {
      let n = 1;
      for (const m of part.measures) {
        for (const s of desc(m.el, 'staves')) { const v = pyInt(s.textContent); if (v !== null) n = Math.max(n, v); }
        for (const s of desc(m.el, 'staff')) { const v = pyInt(s.textContent); if (v !== null) n = Math.max(n, v); }
      }
      for (let i = 1; i <= n; i++) staves.push([part.id, i, score.names.get(part.id) || '']);
    }
    return staves;
  }

  function stavesWithNotes(score) {         // staves with at least one pitched note (rests do not count)
    const used = new Set();
    for (const part of score.parts) {
      for (const m of part.measures) {
        for (const n of desc(m.el, 'note')) {
          if (!kid(n, 'pitch') && !kid(n, 'unpitched')) continue;
          const st = pyInt(kidText(n, 'staff') || '1');
          used.add(`${part.id}|${st === null ? 1 : st}`);
        }
      }
    }
    return used;
  }

  function dropEmptyStaves(score, staves, rep) {   // more than two staves, but at most two with notes: skip the empty ones
    if (staves.length <= 2) return staves;
    const used = stavesWithNotes(score);
    const keep = staves.filter(([p, s]) => used.has(`${p}|${s}`));
    if (keep.length < 1 || keep.length > 2) return staves;
    for (const [p, s, name] of staves) {
      if (!used.has(`${p}|${s}`)) rep.info.push(`Staff ${p}/${s} (${pyRepr(name)}) has no notes, only rests - skipped.`);
    }
    return keep;
  }

  function parseStaffSpec(spec, staves) {
    const out = [];
    for (const item of spec.split(',').map((s) => s.trim()).filter(Boolean)) {
      if (item.includes('/')) {
        const [pid, nr] = [item.slice(0, item.indexOf('/')), item.slice(item.indexOf('/') + 1)];
        const st = pyInt(nr);
        if (st === null || !staves.some(([p, s]) => p === pid && s === st)) throw new NotencodeError(`Staff ${item} does not exist in the file.`);
        out.push([pid, st]);
      } else {
        const keys = staves.filter(([p]) => p === item).map(([p, s]) => [p, s]);
        if (!keys.length) throw new NotencodeError(`Part ${item} does not exist in the file.`);
        out.push(...keys);
      }
    }
    return out;
  }

  function resolveHands(staves, upper, lower, rep) {
    const listing = staves.map(([p, s, name]) => `   ${p}/${s}  ${pyRepr(name)}`).join('\n');
    const hands = new Map();
    if (upper || lower) {
      if (!(upper && lower)) throw new NotencodeError('Please give both --upper AND --lower.');
      for (const [p, s] of parseStaffSpec(upper, staves)) hands.set(`${p}|${s}`, UPPER);
      for (const [p, s] of parseStaffSpec(lower, staves)) {
        if (hands.has(`${p}|${s}`)) throw new NotencodeError(`Staff ${p}/${s} is given as both upper and lower.`);
        hands.set(`${p}|${s}`, LOWER);
      }
      for (const [p, s, name] of staves) {
        if (!hands.has(`${p}|${s}`)) rep.info.push(`Staff ${p}/${s} (${pyRepr(name)}) is not assigned to a hand (as chosen) and is not written.`);
      }
      return hands;
    }
    if (staves.length === 1) {
      rep.warnings.push('The file has only one staff - everything is written as the upper staff (CAPITALS).');
      hands.set(`${staves[0][0]}|${staves[0][1]}`, UPPER);
      return hands;
    }
    if (staves.length === 2) {
      hands.set(`${staves[0][0]}|${staves[0][1]}`, UPPER);
      hands.set(`${staves[1][0]}|${staves[1][1]}`, LOWER);
      return hands;
    }
    const err = new NotencodeError(
      'The file has more than two staves. I will not guess which ones belong to the piano hands.\n' +
      `Staves found:\n${listing}\n` +
      'Please choose, e.g.:  --upper P2/1 --lower P2/2');
    err.staves = staves;
    throw err;
  }

  // ------------------------------------------------------------------ timeline
  function timeSig(attr) {
    const t = kid(attr, 'time');
    if (!t) return null;
    const bt = kidText(t, 'beats'), tt = kidText(t, 'beat-type');
    if (!bt || !tt) return null;
    const parts = bt.split('+').map(pyInt);
    const beatType = pyInt(tt);
    if (parts.some((x) => x === null) || beatType === null) return null;
    const beats = parts.reduce((a, b) => a + b, 0);
    return [new Fr(beats * 4, beatType), beatType, `${bt}/${tt}`];
  }

  function parsePart(part, hands, rep, orderStart, marks) {   // marks: fermatas, breath marks, double bars, lyrics (display only)
    const pid = part.id;
    let divisions = null, expected = null, beatType = 4, timeText = '?';
    const notes = [], measures = [];
    let absStart = F0, order = orderStart;
    part.measures.forEach((mm, midx) => {
      const measure = mm.el;
      const label = mm.number !== null && mm.number !== undefined ? mm.number : String(midx + 1);
      const implicit = mm.implicit === 'yes';
      let cursor = F0, maxCursor = F0, lastOnset = F0, hasContent = false;
      const voiceEnd = new Map();
      for (const child of kids(measure)) {
        const tag = lname(child);
        if (tag === 'note' || tag === 'backup' || tag === 'forward') hasContent = true;
        if (tag === 'attributes') {
          const d = kidText(child, 'divisions');
          if (d) divisions = _frac(d);
          const ts = timeSig(child);
          if (ts) [expected, beatType, timeText] = ts;
          if (kid(child, 'transpose')) rep.warnings.push(`Part ${pid}, measure ${label}: <transpose> found - pitches in the file may be written transposed. Please check.`);
        } else if (tag === 'backup' || tag === 'forward') {
          if (divisions === null) throw new NotencodeError(`Part ${pid}, measure ${label}: <${tag}> before <divisions>.`);
          const d = _frac(kidText(child, 'duration')).div(divisions);
          if (tag === 'backup') {
            cursor = cursor.sub(d);
            if (cursor.lt(F0)) { rep.warnings.push(`Part ${pid}, measure ${label}: <backup> jumps before the start of the measure - set to 0.`); cursor = F0; }
          } else { cursor = cursor.add(d); maxCursor = fmax(maxCursor, cursor); }
        } else if (tag === 'barline') {
          const style = (kidText(child, 'bar-style') || '').trim();
          if (marks && (kid(child, 'repeat') || ['light-light', 'light-heavy', 'heavy-light', 'heavy-heavy'].includes(style))) {
            const loc = child.getAttribute('location') || (hasContent ? 'right' : 'left');   // not given: a barline before the notes = left
            marks.push({ kind: 'barline', midx, atStart: loc === 'left' });
          }
          if (kid(child, 'repeat') || kid(child, 'ending')) rep.info.push(`Measure ${label}: repeat sign/volta - the code follows the printed score, repeats are NOT written out.`);
        } else if (tag === 'direction') {
          if (desc(child, 'octave-shift').length) rep.info.push(`Part ${pid}, measure ${label}: octave sign (8va/8vb) - the code shows the sounding octave, not the printed note position.`);
        } else if (tag === 'note') {
          order += 1;
          if (divisions === null) throw new NotencodeError(`Part ${pid}, measure ${label}: note before <divisions>.`);
          const isChord = !!kid(child, 'chord'), isGrace = !!kid(child, 'grace'), isCue = !!kid(child, 'cue'), isRest = !!kid(child, 'rest');
          const durTxt = kidText(child, 'duration');
          if (!isGrace && durTxt === null) rep.warnings.push(`Part ${pid}, measure ${label}: note without <duration> - duration 0 assumed.`);
          const dur = isGrace ? F0 : _frac(durTxt).div(divisions);
          let onset;
          if (isChord) onset = lastOnset; else { onset = cursor; lastOnset = cursor; }
          const voice = (kidText(child, 'voice') || '1').trim();
          const st = pyInt(kidText(child, 'staff') || '1');
          const staff = st === null ? 1 : st;
          if (!isChord && !isGrace) { cursor = cursor.add(dur); maxCursor = fmax(maxCursor, cursor); }
          if (!isGrace) voiceEnd.set(voice, fmax(voiceEnd.has(voice) ? voiceEnd.get(voice) : F0, onset.add(dur)));
          if (marks && !isGrace) {
            if (path(child, 'notations', 'fermata').length) marks.push({ kind: 'fermata', midx, onset: onset.num(), end: onset.add(dur).num() });
            const art = path(child, 'notations', 'articulations');
            if (art.some((a) => kid(a, 'breath-mark') || kid(a, 'caesura'))) marks.push({ kind: 'breath', midx, onset: onset.add(dur).num(), end: onset.add(dur).num() });
            if (!isRest && !isChord) {             // lyrics: punctuation at the end of a syllable marks the end of a line
              for (const ly of kids(child, 'lyric')) {
                const txt = kids(ly, 'text').map((t) => t.textContent || '').join('');
                if (txt) marks.push({ kind: 'syllable', midx, onset: onset.num(), end: onset.add(dur).num(), text: txt, staff, pid, number: ly.getAttribute('number') || '1' });
              }
            }
          }

          if (isRest) { rep.counts.rests++; continue; }
          if (isGrace) { rep.counts.grace_notes++; rep.check.push(`Measure ${label}: grace note skipped - it has no duration of its own.`); continue; }
          if (isCue) { rep.counts.cue_notes++; rep.info.push(`Measure ${label}: cue note skipped - it is not played.`); continue; }
          const pitch = kid(child, 'pitch');
          if (!pitch) { rep.counts.unpitched++; rep.warnings.push(`Part ${pid}, measure ${label}: note without pitch (e.g. percussion) skipped.`); continue; }
          const hand = hands.get(`${pid}|${staff}`);
          if (!hand) { rep.counts.unassigned++; continue; }
          if (child.getAttribute('print-object') === 'no') rep.check.push(`Measure ${label}: invisible note (print-object=no) is written - it is not in the printed score.`);

          const step = (kidText(pitch, 'step') || '').trim().toUpperCase();
          if (!(step in STEP_SEMITONES)) throw new NotencodeError(`Part ${pid}, measure ${label}: unknown note name ${pyRepr(step)}.`);
          const alter = _frac(kidText(pitch, 'alter'));
          const octave = pyInt(kidText(pitch, 'octave') || '');
          if (octave === null) throw new NotencodeError(`Part ${pid}, measure ${label}: note without a valid octave.`);
          const accEl = kid(child, 'accidental');
          const accText = accEl ? accEl.textContent : '';
          const accidental = accEl && accText ? accText.trim() : null;
          const tieTypes = new Set(kids(child, 'tie').map((t) => t.getAttribute('type')).concat(path(child, 'notations', 'tied').map((t) => t.getAttribute('type'))));
          const slurStarts = [], slurStops = [];
          for (const s of path(child, 'notations', 'slur')) {
            const num = s.getAttribute('number') || '1';
            if (s.getAttribute('type') === 'start') slurStarts.push(num); else if (s.getAttribute('type') === 'stop') slurStops.push(num);
          }
          const n = {
            partId: pid, staff, hand, measureIdx: midx, onset, duration: dur, absOnset: absStart.add(onset), voice,
            step, alter, octave, accidental,
            tieStart: tieTypes.has('start') || tieTypes.has('continue'),
            tieStop: tieTypes.has('stop') || tieTypes.has('continue'),
            slurStarts, slurStops, docOrder: order, continuation: false, heldBySlur: false, duplicateOf: null,
          };
          n.midi = fint((octave + 1) * 12 + STEP_SEMITONES[step]).add(alter);
          n.end = onset.add(dur); n.absEnd = n.absOnset.add(dur);
          notes.push(n);
        }
      }
      let length = maxCursor;
      if (length.isZero() && expected) length = expected;
      if (expected !== null) {
        for (const [v, e] of voiceEnd) {
          if (e.gt(expected)) rep.warnings.push(`Part ${pid}, measure ${label}: voice ${v} is longer than the time signature ${timeText} (${_q(e)} instead of ${_q(expected)} quarters).`);
        }
      }
      measures.push({ idx: midx, label, length, expected, beatType, timeText, implicit });
      absStart = absStart.add(length);
    });
    return [notes, measures, order];
  }

  // ------------------------------------------------------------------ names
  function plain(n) {
    const a = n.alter.d === 1 && (String(n.alter.n) in ALTER_TEXT) ? ALTER_TEXT[String(n.alter.n)] : '?';
    return `${n.step}${a}${n.octave}`;
  }
  function pyFloatG(x) { // Python f"{x:g}" for small values
    return Number(x.toPrecision(6)).toString();
  }
  function noteName(n, mode) {
    let acc;
    if (mode === 'written') {
      acc = n.accidental === null ? '' : (n.accidental in ACCIDENTAL_TEXT ? ACCIDENTAL_TEXT[n.accidental] : `[${n.accidental}]`);
    } else {
      acc = n.alter.d === 1 && (String(n.alter.n) in ALTER_TEXT) ? ALTER_TEXT[String(n.alter.n)] : `[alter=${pyFloatG(n.alter.num())}]`;
    }
    let name = n.step + acc;
    if (n.hand === LOWER) name = name.toLowerCase();
    return `${name}${n.octave}`;
  }
  function beatLabel(onset, beatType) {
    const pos = onset.div(new Fr(4, beatType)).add(fint(1));
    if (pos.d === 1) return String(pos.n);
    let d = pos.d;
    while (d % 2 === 0) d /= 2;
    while (d % 5 === 0) d /= 5;
    const whole = Math.floor(pos.n / pos.d);
    if (d === 1) {
      let rest = pos.sub(fint(whole)), digits = '';
      while (!rest.isZero()) { rest = rest.mul(fint(10)); const dg = Math.floor(rest.n / rest.d); digits += String(dg); rest = rest.sub(fint(dg)); }
      return `${whole}.${digits}`;
    }
    const rest = pos.sub(fint(whole));
    return `${whole} ${rest.n}/${rest.d}`;
  }
  const sortKey = (a, b) => (b.midi.cmp(a.midi)) || ((a.hand === UPPER ? 0 : 1) - (b.hand === UPPER ? 0 : 1)) || (a.docOrder - b.docOrder);

  // ------------------------------------------------------------------ ties & slurs
  function groupBy(arr, keyFn) { const m = new Map(); for (const x of arr) { const k = keyFn(x); if (!m.has(k)) m.set(k, []); m.get(k).push(x); } return m; }

  function resolveTies(notes, labels, rep) {
    for (const pnotes of groupBy(notes, (n) => n.partId).values()) {
      const open = new Map();   // "staff|midi" -> [notes]
      const sorted = pnotes.slice().sort((a, b) => a.absOnset.cmp(b.absOnset) || a.docOrder - b.docOrder);
      for (const n of sorted) {
        if (n.tieStop) {
          let cands = open.get(`${n.staff}|${n.midi.key()}`) || [];
          let cross = false;
          if (!cands.length) {
            for (const [k, lst] of open) { if (k.split('|')[1] === n.midi.key() && lst.length) { cands = lst; cross = true; break; } }
          }
          const exact = cands.filter((c) => c.absEnd.eq(n.absOnset));
          let start = null;
          if (exact.length) start = exact[0];
          else if (cands.length) {
            start = cands[0];
            rep.warnings.push(`Measure ${labels[n.measureIdx]}: tie on ${plain(n)} has a gap (start ends at ${_q(start.absEnd)}, continuation begins at ${_q(n.absOnset)}).`);
          }
          if (start) {
            cands.splice(cands.indexOf(start), 1);
            n.continuation = true;
            rep.counts.tie_continuations++;
            if (cross) rep.check.push(`Measure ${labels[n.measureIdx]}: tie on ${plain(n)} changes staff.`);
          } else {
            const msg = `Measure ${labels[n.measureIdx]}: tie end on ${plain(n)} without a matching start - counted as a new attack.`;
            rep.check.push(msg); addTo(rep.flags, `${n.measureIdx}|${n.onset.key()}`, msg);
          }
        }
        if (n.tieStart) {
          const k = `${n.staff}|${n.midi.key()}`;
          if (!open.has(k)) open.set(k, []);
          open.get(k).push(n);
        }
      }
      for (const lst of open.values()) for (const n of lst) rep.info.push(`Measure ${labels[n.measureIdx]}: tie on ${plain(n)} has no end in the file.`);
    }
  }

  function addTo(map, k, msg) { if (!map.has(k)) map.set(k, []); map.get(k).push(msg); }

  function checkSamePitchSlurs(notes, labels, beatTypes, mode, rep, nameMode) {
    for (const pnotes of groupBy(notes, (n) => n.partId).values()) {
      const active = [];          // [voice, number]
      const prevEvent = new Map();
      const events = new Map();
      for (const n of pnotes) {
        const k = `${n.absOnset.key()}#${n.voice}`;
        if (!events.has(k)) events.set(k, { t: n.absOnset, voice: n.voice, notes: [] });
        events.get(k).notes.push(n);
      }
      const evs = [...events.values()].sort((a, b) => a.t.cmp(b.t) || (Math.min(...a.notes.map((x) => x.docOrder)) - Math.min(...b.notes.map((x) => x.docOrder))));
      for (const ev of evs) {
        const voice = ev.voice;
        const covered = active.some(([v]) => v === voice);
        const prev = prevEvent.get(voice);
        if (covered && prev && prev.end.eq(ev.t)) {
          const prevMidis = new Set(prev.notes.map((p) => p.midi.key()));
          for (const n of ev.notes) {
            if (prevMidis.has(n.midi.key()) && !n.continuation) {
              const where = `Measure ${labels[n.measureIdx]}, beat ${beatLabel(n.onset, beatTypes[n.measureIdx])}`;
              let msg;
              if (mode === 'hold') {
                n.heldBySlur = true; rep.counts.same_pitch_slur_held++;
                msg = `${where}: ${noteName(n, nameMode)} - the slur between equal pitches is stored as a phrasing slur but looks like a tie -> held, NOT struck again.`;
              } else {
                rep.counts.same_pitch_slur_restruck++;
                msg = `${where}: ${noteName(n, nameMode)} - the slur between equal pitches is a phrasing slur in the file (not a tie) -> written as a NEW attack. In the printed score it looks like a tie.`;
              }
              rep.check.push(msg); addTo(rep.flags, `${n.measureIdx}|${n.onset.key()}`, msg);
            }
          }
        }
        for (const n of ev.notes) {
          for (const num of n.slurStops) {
            const i = active.findIndex(([v, x]) => v === voice && x === num);
            if (i >= 0) active.splice(i, 1);
            else { const j = active.findIndex(([, x]) => x === num); if (j >= 0) active.splice(j, 1); }
          }
        }
        for (const n of ev.notes) for (const num of n.slurStarts) { if (!active.some(([v, x]) => v === voice && x === num)) active.push([voice, num]); }
        let end = ev.notes[0].absEnd; for (const x of ev.notes) end = fmax(end, x.absEnd);
        prevEvent.set(voice, { end, notes: ev.notes });
      }
    }
  }

  // ------------------------------------------------------------------ hands
  function heldMidis(notes, midx, t, hand) {
    return notes.filter((n) => n.hand === hand && n.measureIdx === midx && n.duplicateOf === null &&
      ((n.onset.lt(t) && t.lt(n.end)) || ((n.continuation || n.heldBySlur) && n.onset.eq(t)))).map((n) => n.midi);
  }

  function assignPlayableHands(midx, t, uniq, allNotes, where, rep, nameMode, flagKey) {
    const byMidi = new Map();
    for (const n of uniq) { const k = n.midi.key(); if (!byMidi.has(k)) byMidi.set(k, []); byMidi.get(k).push(n); }
    const midiKeys = [...byMidi.keys()].sort((a, b) => byMidi.get(b)[0].midi.cmp(byMidi.get(a)[0].midi));
    for (const k of midiKeys) {
      const ns = byMidi.get(k);
      if (ns.length < 2) continue;
      const midi = ns[0].midi;
      const widening = (hand) => {
        const cur = uniq.filter((m) => m.hand === hand && !m.midi.eq(midi) && m.duplicateOf === null).map((m) => m.midi)
          .concat(heldMidis(allNotes, midx, t, hand));
        if (!cur.length) return F0;
        let mx = cur[0], mn = cur[0];
        for (const c of cur) { mx = fmax(mx, c); if (c.lt(mn)) mn = c; }
        return fmax(F0, midi.sub(mx)).add(fmax(F0, mn.sub(midi)));
      };
      const wu = widening(UPPER), wl = widening(LOWER);
      const hand = wu.lt(wl) ? UPPER : wl.lt(wu) ? LOWER : (midi.cmp(fint(60)) >= 0 ? UPPER : LOWER);
      const keep = ns.find((n) => n.hand === hand);
      for (const n of ns) if (n !== keep) { n.duplicateOf = keep; rep.counts.both_hands_merged++; }
      const msg = `${where}: ${noteName(keep, nameMode)} is in both staves - written once, ${HAND_TEXT[hand]} (stretch right +${_q(wu)}, left +${_q(wl)} semitones).`;
      rep.hands.push(msg); addTo(rep.infos, flagKey, msg);
    }
    const live = uniq.filter((n) => n.duplicateOf === null);
    const up = live.filter((n) => n.hand === UPPER), lo = live.filter((n) => n.hand === LOWER);
    if (up.length && lo.length) {
      let maxLo = lo[0].midi; for (const n of lo) maxLo = fmax(maxLo, n.midi);
      let minUp = up[0].midi; for (const n of up) if (n.midi.lt(minUp)) minUp = n.midi;
      if (maxLo.gt(minUp)) {
        const before = new Map(live.map((n) => [n, noteName(n, nameMode)]));
        const ordered = live.slice().sort((a, b) => b.midi.cmp(a.midi) || a.docOrder - b.docOrder);
        const changed = [];
        ordered.forEach((n, i) => {
          const nw = i < up.length ? UPPER : LOWER;
          if (n.hand !== nw) { n.hand = nw; changed.push(`${before.get(n)} → ${noteName(n, nameMode)} (${HAND_TEXT[nw]})`); }
        });
        const msg = `${where}: voices cross - so that the hands do not cross: ${changed.join(', ')}.`;
        rep.hands.push(msg); addTo(rep.infos, flagKey, msg);
      }
    }
  }

  function heldAt(notes, midx, t, nameMode) {
    const held = notes.filter((n) => n.measureIdx === midx && ((n.onset.lt(t) && t.lt(n.end)) || ((n.continuation || n.heldBySlur) && n.onset.eq(t))));
    const seen = new Set(), out = [];
    for (const n of held.slice().sort(sortKey)) { const nm = noteName(n, nameMode); if (!seen.has(nm)) { seen.add(nm); out.push(nm); } }
    return out;
  }

  // ------------------------------------------------------------------ main flow
  function convertDocument(doc, opts = {}) {
    const source = opts.source || '<xml>';
    const accidentals = opts.accidentals || 'sounding';
    const slurMode = opts.same_pitch_slur || 'hold';
    const handsMode = opts.hands || 'playable';
    const emptyMeasure = opts.empty_measure === undefined ? '-' : opts.empty_measure;
    const converterLabel = opts.converterLabel || `notencode version ${VERSION} (HTML)`;
    if (!['sounding', 'written'].includes(accidentals)) throw new NotencodeError("--accidentals must be 'sounding' or 'written'.");
    if (!['restrike', 'hold'].includes(slurMode)) throw new NotencodeError("--same-pitch-slur must be 'restrike' or 'hold'.");
    if (!['playable', 'staff'].includes(handsMode)) throw new NotencodeError("--hands must be 'playable' or 'staff'.");
    const rep = {
      warnings: [], check: [], info: [], hands: [], flags: new Map(), infos: new Map(),
      counts: {
        rests: 0, grace_notes: 0, cue_notes: 0, unpitched: 0, unassigned: 0, tie_continuations: 0,
        same_pitch_slur_held: 0, same_pitch_slur_restruck: 0, duplicates_merged: 0, both_hands_merged: 0,
      },
    };
    const score = readScore(doc);
    let staves = findStaves(score);
    if (!staves.length) throw new NotencodeError('No <part> elements found.');
    if (!(opts.upper || opts.lower)) staves = dropEmptyStaves(score, staves, rep);
    const handOf = resolveHands(staves, opts.upper, opts.lower, rep);

    const allNotes = [];
    const partMeasures = new Map();
    let order = 0;
    const marks = [];
    for (const part of score.parts) {
      const [pn, pm, o] = parsePart(part, handOf, rep, order, marks);
      order = o; allNotes.push(...pn); partMeasures.set(part.id, pm);
    }
    const counts = [...partMeasures.entries()].map(([pid, ms]) => [pid, ms.length]);
    const nMeasures = counts.length ? Math.max(...counts.map(([, c]) => c)) : 0;
    if (new Set(counts.map(([, c]) => c)).size > 1) {
      rep.warnings.push(`The parts have different numbers of measures: {${counts.map(([p, c]) => `${pyRepr(p)}: ${c}`).join(', ')}}. Matched by order.`);
    }
    const measures = [];
    for (let i = 0; i < nMeasures; i++) {
      const infos = [...partMeasures.values()].filter((ms) => i < ms.length).map((ms) => ms[i]);
      const lengths = [];
      for (const m of infos) if (!lengths.some((l) => l.eq(m.length))) lengths.push(m.length);
      if (lengths.length > 1) rep.warnings.push(`Measure ${infos[0].label}: the parts have different lengths (${lengths.slice().sort((a, b) => a.cmp(b)).map(_q).join(', ')} quarters).`);
      if (new Set(infos.map((m) => m.label)).size > 1) rep.warnings.push(`Measure no. ${i + 1}: different measure numbers in the parts: [${infos.map((m) => pyRepr(m.label)).join(', ')}].`);
      measures.push(infos[0]);
    }
    const labels = measures.map((m) => m.label), beatTypes = measures.map((m) => m.beatType);
    measures.forEach((m, i) => {
      if (m.expected !== null && m.length.lt(m.expected)) {
        if (i === 0) rep.info.push(`Measure ${m.label}: shorter than ${m.timeText} - probably a pickup.`);
        else if (i === measures.length - 1) rep.info.push(`Measure ${m.label}: shorter than ${m.timeText} - probably completes the pickup.`);
        else if (!m.implicit) rep.warnings.push(`Measure ${m.label}: shorter than the time signature ${m.timeText} (${_q(m.length)} instead of ${_q(m.expected)} quarters).`);
      }
    });

    resolveTies(allNotes, labels, rep);
    checkSamePitchSlurs(allNotes, labels, beatTypes, slurMode, rep, accidentals);

    const groups = new Map();
    for (const n of allNotes) {
      if (!n.continuation && !n.heldBySlur) {
        const k = `${n.measureIdx}|${n.onset.key()}`;
        if (!groups.has(k)) groups.set(k, { midx: n.measureIdx, t: n.onset, notes: [] });
        groups.get(k).notes.push(n);
      }
    }
    const groupList = [...groups.values()].sort((a, b) => a.midx - b.midx || a.t.cmp(b.t));
    for (const g of groupList) {
      const key = `${g.midx}|${g.t.key()}`;
      const seen = new Map();
      for (const n of g.notes.slice().sort((a, b) => a.docOrder - b.docOrder)) {
        const k = `${n.hand}|${n.midi.key()}`;
        if (seen.has(k)) {
          n.duplicateOf = seen.get(k); rep.counts.duplicates_merged++;
          rep.info.push(`Measure ${labels[g.midx]}, beat ${beatLabel(g.t, beatTypes[g.midx])}: ${noteName(n, accidentals)} is in two voices - written once.`);
        } else seen.set(k, n);
      }
      const where = `Measure ${labels[g.midx]}, beat ${beatLabel(g.t, beatTypes[g.midx])}`;
      if (handsMode === 'playable') {
        assignPlayableHands(g.midx, g.t, [...seen.values()], allNotes, where, rep, accidentals, key);
      } else {
        const byMidi = new Map();
        for (const n of seen.values()) { const k = n.midi.key(); if (!byMidi.has(k)) byMidi.set(k, new Set()); byMidi.get(k).add(n.hand); }
        for (const hs of byMidi.values()) {
          if (hs.size > 1) {
            const msg = `${where}: the same pitch in both staves at once - both written (only one key on the piano).`;
            rep.check.push(msg); addTo(rep.flags, key, msg);
          }
        }
      }
    }

    // --- lines
    const outMeasures = [], checklist = [], rows = [];
    const sounding = allNotes.filter((n) => n.duplicateOf === null);
    const mStart = []; { let acc = F0; for (const m of measures) { mStart.push(acc); acc = acc.add(m.length); } }
    const keyInfo = (n) => ({ name: noteName(n, accidentals), midi: n.midi.num(), hand: n.hand, step: n.step,
      alter: n.alter.num(), octave: n.octave, dur: n.duration.num() });
    measures.forEach((m, i) => {
      const gs = groupList.filter((g) => g.midx === i);
      const lines = [];
      let header = `Measure ${m.label}`;
      if (i === 0 || m.timeText !== measures[i - 1].timeText) header += `   (${m.timeText})`;
      checklist.push(header);
      for (const g of gs) {
        const key = `${g.midx}|${g.t.key()}`;
        const attacks = g.notes.filter((n) => n.duplicateOf === null).sort(sortKey);
        const line = attacks.map((n) => noteName(n, accidentals)).join('+');
        lines.push(line);
        const held = heldAt(sounding, i, g.t, accidentals);
        const beat = beatLabel(g.t, m.beatType);
        let row = `  beat ${beat.padEnd(7)}${line}`;
        if (held.length) row = `${row.padEnd(46)}  holds: ${held.join(', ')}`;
        checklist.push(row);
        const infos = rep.infos.get(key) || [], flags = rep.flags.get(key) || [];
        for (const msg of infos) checklist.push(`             hands: ${afterColon(msg)}`);
        for (const msg of flags) checklist.push(`             CHECK: ${afterColon(msg)}`);
        rows.push({
          measureIdx: i, label: m.label, beat, line, held, t: mStart[i].add(g.t).num(),
          keys: attacks.map(keyInfo),
          heldKeys: sounding.filter((n) => n.measureIdx === i && ((n.onset.lt(g.t) && g.t.lt(n.end)) || ((n.continuation || n.heldBySlur) && n.onset.eq(g.t))))
            .map(keyInfo),
          infos: infos.map(afterColon), flags: flags.map(afterColon),
        });
      }
      if (!gs.length) {
        lines.push(emptyMeasure);
        const held = heldAt(sounding, i, F0, accidentals);
        checklist.push(`  (no new attack)${held.length ? '  holds: ' + held.join(', ') : ''}`);
        rep.info.push(`Measure ${m.label}: no new attack - line '${emptyMeasure}' written.`);
        rows.push({ measureIdx: i, label: m.label, beat: '', line: emptyMeasure, held, t: mStart[i].num(), keys: [], heldKeys: [], infos: [], flags: [], empty: true });
      }
      outMeasures.push(lines);
      checklist.push('');
    });
    const codeText = outMeasures.map((ls) => ls.join('\n')).join('\n\n') + '\n';

    // --- note balance
    const z = rep.counts;
    const attacksTotal = allNotes.filter((n) => !n.continuation && !n.heldBySlur && n.duplicateOf === null).length;
    const accounted = attacksTotal + z.tie_continuations + z.same_pitch_slur_held + z.duplicates_merged +
      z.both_hands_merged + z.rests + z.grace_notes + z.cue_notes + z.unpitched + z.unassigned;
    const balanceOk = accounted === score.totalNotes;
    if (!balanceOk) rep.warnings.push(`NOTE BALANCE DOES NOT ADD UP: ${score.totalNotes} <note> elements, but ${accounted} accounted for.`);

    const staffLines = staves.map(([p, s, name]) => {
      const h = handOf.get(`${p}|${s}`);
      return `   ${p}/${s} ${pyRepr(name).padEnd(8)} -> ` + ({ upper: 'upper (CAPITALS, right hand)', lower: 'lower (lowercase, left hand)' }[h] || 'not written');
    });
    const nLines = outMeasures.reduce((a, ls) => a + ls.length, 0);
    const pad4 = (x) => String(x).padStart(4);
    const list = (xs) => (xs.length ? xs.map((w) => ` - ${w}`) : [' - none']);
    const report = [
      'NOTENCODE - REPORT', '='.repeat(60),
      `Input:              ${source}`,
      `Converter:          ${converterLabel}`,
      `Accidentals:        ${accidentals}` + (accidentals === 'sounding' ? '  (key signature + score = the key you press)' : '  (printed accidentals only)'),
      `Same-pitch slur:    ${slurMode}`,
      `Hands:              ${handsMode}` + (handsMode === 'playable' ? '  (same pitch once; hands never cross)' : '  (hand = staff)'),
      'Staves:', ...staffLines,
      `Measures:           ${nMeasures}  (time signature ${measures.length ? measures[0].timeText : '?'})`,
      `Attack lines:       ${nLines}`, '',
      'NOTE BALANCE (EVERY <note> ELEMENT)',
      `   ${pad4(score.totalNotes)}  <note> elements in the file`,
      `   ${pad4(attacksTotal)}  written as struck notes`,
      `   ${pad4(z.tie_continuations)}  tie continuations (keep sounding, not written)`,
      `   ${pad4(z.same_pitch_slur_held)}  slur on the same pitch treated as held`,
      `   ${pad4(z.duplicates_merged)}  same pitch in two voices (written once)`,
      `   ${pad4(z.both_hands_merged)}  same pitch in both staves (written once)`,
      `   ${pad4(z.rests)}  rests`,
      `   ${pad4(z.grace_notes)}  grace notes (skipped)`,
      `   ${pad4(z.cue_notes)}  cue notes (skipped)`,
      `   ${pad4(z.unpitched)}  unpitched notes (skipped)`,
      `   ${pad4(z.unassigned)}  notes on unassigned staves`,
      `   => balance ${balanceOk ? 'OK - every note accounted for exactly once' : 'ERROR'}`, '',
      'WARNINGS (structure of the file)', ...list(rep.warnings), '',
      'PLEASE CHECK AGAINST THE PRINTED SCORE', ...list(rep.check), '',
      handsMode === 'playable' ? 'HAND DECISIONS (rule: playable)' : 'HAND DECISIONS', ...list(rep.hands), '',
      'NOTES', ...list(rep.info), '',
      'The converter reads the file note by note with fixed rules (no guessing: same file = same output).',
      'It can only be as correct as the MusicXML file itself. Whether the file matches the printed score',
      'is not checked - that is what the checklist is for.',
    ];
    const checklistText = ['NOTENCODE - CHECKLIST', `Source: ${source}`,
      'beat = position in the measure (in 6/8 counted in eighths: 1 2 3 4 5 6; 2.5 = a sixteenth after 2).',
      "'holds' = notes that keep sounding at this moment and are therefore NOT on the line.", '']
      .concat(checklist).join('\n').replace(/\s+$/, '') + '\n';
    const spans = sounding.map((n) => [mStart[n.measureIdx].add(n.onset), mStart[n.measureIdx].add(n.onset).add(n.duration)])
      .filter(([a, b]) => b.gt(a)).sort((x, y) => x[0].cmp(y[0]));
    const total = measures.length ? mStart[measures.length - 1].add(measures[measures.length - 1].length) : F0;
    const rests = [];
    let reach = F0;
    for (const [a, b] of spans) { if (a.gt(reach)) rests.push({ t: reach.num(), dur: a.sub(reach).num() }); reach = fmax(reach, b); }
    if (total.gt(reach)) rests.push({ t: reach.num(), dur: total.sub(reach).num() });
    const timeline = {
      measures: measures.map((m, i) => ({ label: m.label, start: mStart[i].num(), length: m.length.num(), timeText: m.timeText, beatType: m.beatType,
        expected: m.expected === null ? null : m.expected.num() })),
      rests, total: total.num(),
      marks: marks.filter((m) => m.midx < measures.length).map((m) => (m.kind === 'barline'
        ? { kind: m.kind, t: mStart[m.midx].num() + (m.atStart ? 0 : measures[m.midx].length.num()) }
        : Object.assign({ kind: m.kind, t: mStart[m.midx].num() + m.onset, end: mStart[m.midx].num() + m.end }, m.kind === 'syllable' ? { text: m.text, staff: `${m.pid}/${m.staff}`, number: m.number } : {}))),
    };
    return {
      source, codeText, checklistText, timeline, reportText: report.join('\n') + '\n', measures: outMeasures, rows,
      report: { warnings: rep.warnings, check: rep.check, hands: rep.hands, info: rep.info, counts: Object.assign({}, rep.counts) },
      stats: { totalNotes: score.totalNotes, attacks: attacksTotal, balanceOk, nMeasures, nLines, timeText: measures.length ? measures[0].timeText : '?' },
      staves: staves.map(([p, s, name]) => ({ part: p, staff: s, name, hand: handOf.get(`${p}|${s}`) || null })),
    };
  }
  function afterColon(msg) { const i = msg.indexOf(': '); return i >= 0 ? msg.slice(i + 2) : msg; }

  // ------------------------------------------------------------------ files (unpacking .mxl)
  async function unzipMxl(bytes, inflateRaw) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let eocd = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new NotencodeError('The .mxl archive is damaged (no ZIP directory found).');
    const count = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const entries = new Map();
    const dec = new TextDecoder('utf-8');
    for (let i = 0; i < count; i++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new NotencodeError('The .mxl archive is damaged.');
      const method = dv.getUint16(p + 10, true), csize = dv.getUint32(p + 20, true);
      const nlen = dv.getUint16(p + 28, true), xlen = dv.getUint16(p + 30, true), clen = dv.getUint16(p + 32, true);
      const local = dv.getUint32(p + 42, true);
      const name = dec.decode(bytes.subarray(p + 46, p + 46 + nlen));
      entries.set(name, { method, csize, local });
      p += 46 + nlen + xlen + clen;
    }
    async function read(name) {
      const e = entries.get(name);
      const lnl = dv.getUint16(e.local + 26, true), lxl = dv.getUint16(e.local + 28, true);
      const data = bytes.subarray(e.local + 30 + lnl + lxl, e.local + 30 + lnl + lxl + e.csize);
      if (e.method === 0) return data;
      if (e.method === 8) return inflateRaw(data);
      throw new NotencodeError(`Unknown compression (${e.method}) in the .mxl archive.`);
    }
    let target = null;
    if (entries.has('META-INF/container.xml')) {
      const txt = dec.decode(await read('META-INF/container.xml'));
      const m = /<rootfile[^>]*full-path\s*=\s*"([^"]+)"/.exec(txt) || /<rootfile[^>]*full-path\s*=\s*'([^']+)'/.exec(txt);
      if (m) target = entries.has(m[1]) ? m[1] : ([...entries.keys()].find((n) => n.normalize('NFC') === m[1].normalize('NFC')) || null);
    }
    if (!target) {
      target = [...entries.keys()].find((n) => /\.(xml|musicxml)$/i.test(n) && !n.startsWith('META-INF')) || null;
      if (!target) throw new NotencodeError('No MusicXML file found in the .mxl archive.');
    }
    return read(target);
  }

  function decodeXmlBytes(bytes) {
    if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder('utf-16le').decode(bytes);
    if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder('utf-16be').decode(bytes);
    return new TextDecoder('utf-8').decode(bytes);
  }

  async function bytesToXmlText(bytes, inflateRaw) {
    const isZip = bytes.length > 4 && bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04;
    return decodeXmlBytes(isZip ? await unzipMxl(bytes, inflateRaw) : bytes);
  }


  // ------------------------------------------------------------------ phrase breaks (display only)
  // Finds where a musical line (usually a line of the song text) ends. Result: the moments where a new line
  // starts (always the first note of the new phrase), plus start and end.
  // Always a break: fermata, breath mark, double bar, hymnal measure split at the end of a line, silence.
  // Otherwise weighed: punctuation in the lyrics (verse 1), long melody notes, length of the line.
  const PUNCT = /([.,;:!?])["'»«“”‘’)\]]*\s*$/;
  function lyricPunctuation(r) {          // [[break, mark, syllable time]] from the lyrics - without the text itself
    const syllables = (r.timeline.marks || []).filter((m) => m.kind === 'syllable');
    if (!syllables.length) return [];
    const perStaff = new Map();
    for (const sl of syllables) { if (!perStaff.has(sl.staff)) perStaff.set(sl.staff, []); perStaff.get(sl.staff).push(sl); }
    const upperStaves = new Set((r.staves || []).filter((x) => x.hand === UPPER).map((x) => `${x.part}/${x.staff}`));
    let choice = null;
    for (const [staff, list] of perStaff) {
      const rank = (upperStaves.has(staff) ? 1e6 : 0) + list.length;
      if (!choice || rank > choice.rank) choice = { staff, list, rank };
    }
    const nr = (x) => { const v = parseInt(x.number, 10); return isNaN(v) ? 999 : v; };
    const first = Math.min(...choice.list.map(nr));
    const l = choice.list.filter((x) => nr(x) === first).sort((x, y) => x.t - y.t);
    const out = [];
    out.syllables = l.map((x) => Math.round(x.t * 1e6) / 1e6);
    l.forEach((sl, i) => {
      const m = PUNCT.exec(sl.text); if (!m) return;
      const next = i + 1 < l.length ? l[i + 1].t : r.timeline.total;
      out.push([Math.round(next * 1e6) / 1e6, m[1], Math.round(sl.t * 1e6) / 1e6]);
    });
    return out;
  }
  const WEIGHTS = { comma: 3, sentence: 5, long: 2, longNote: 3, veryLong: 4, longBefore: 1, price: 3.2, nMin: 5, nGood: 6, nMax: 16, target: 10, w1: 0.3, w2: 1 };
  function phraseBreaks(r, extra) {
    const tl = r.timeline, ms = tl.measures, total = tl.total, EPS = 1e-6;
    const result = { bounds: [0, total], reasons: [] };
    if (!ms.length || !(total > 0)) return result;
    const events = r.rows.filter((x) => !x.empty && x.keys.length);
    const times = [...new Set(events.map((x) => x.t))].sort((a, b) => a - b);
    if (times.length < 3) return result;
    const nextAttack = (T) => { for (const z of times) if (z >= T - EPS) return z; return total; };
    const mostCommon = (values) => { const c = new Map(); for (const v of values) { const k = v.toFixed(6); c.set(k, (c.get(k) || 0) + 1); } let best = null, n = 0; for (const [k, v] of c) if (v > n) { n = v; best = Number(k); } return best; };
    const nominal = mostCommon(ms.map((m) => (m.expected === null || m.expected === undefined ? m.length : m.expected))) || 4;
    const bt = ms[0].beatType || 4;
    const beat = (bt === 8 && Math.round(nominal * 2) % 3 === 0) ? 1.5 : 4 / bt;
    // melody: attacks whose highest note is not below a held note of the right hand
    const mel = [];
    for (const x of events) {
      const upper = x.keys.filter((k) => k.hand === UPPER), pool = upper.length ? upper : x.keys;
      const top = Math.max(...pool.map((k) => k.midi));
      const held = x.heldKeys.filter((k) => !upper.length || k.hand === UPPER).map((k) => k.midi);
      if (!held.length || top >= Math.max(...held) - 0.01) { if (!mel.length || x.t > mel[mel.length - 1] + EPS) mel.push(x.t); }
    }
    const durations = mel.map((t, i) => (i + 1 < mel.length ? mel[i + 1] : total) - t);
    const sorted = durations.slice(0, -1).sort((a, b) => a - b);
    const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : beat;
    const melDuration = (t) => { let d = 0; for (let i = 0; i < mel.length && mel[i] <= t + EPS; i++) d = durations[i]; return d; };
    const isLong = (d) => d >= 2 * median - EPS && d >= beat - EPS;

    const cand = new Map();
    const add = (T, score, reason, exact) => {
      const z = exact ? T : nextAttack(T);
      if (z <= times[0] + EPS || z >= total - EPS) return;
      const k = z.toFixed(6), old = cand.get(k);
      if (!old) cand.set(k, { t: z, score, reason });
      else if (score > old.score) { old.score = score; old.reason = reason; }
    };
    for (const m of tl.marks || []) {
      if (m.kind === 'fermata') add(m.end, 10, 'fermata');
      else if (m.kind === 'breath') add(m.t, 9, 'breath mark');
      else if (m.kind === 'barline') add(m.t, 8, 'double bar');
    }
    const short = (m) => m.expected !== null && m.expected !== undefined && m.length < m.expected - EPS;
    for (let i = 1; i < ms.length - 1; i++) {
      if (!short(ms[i])) continue;
      add(ms[i].start + ms[i].length, 8, 'split measure');
      if (short(ms[i + 1]) && Math.abs(ms[i].length + ms[i + 1].length - ms[i].expected) < EPS) i++;   // 3 + 1: the second part is a pickup
    }
    for (const rs of tl.rests) if (rs.dur >= beat - EPS && rs.t > times[0] + EPS) add(rs.t, 7, 'rest');
    const longCands = [];
    const onBarline = (T) => ms.some((m) => Math.abs(m.start - T) < EPS);
    for (let i = 0; i + 1 < mel.length; i++) {
      if (!isLong(durations[i])) continue;
      // several long notes in a row: break at the barline, otherwise after the last one
      let j = i; while (j + 2 < mel.length && isLong(durations[j + 1])) j++;
      const run = []; for (let k = i; k <= j; k++) run.push({ t: nextAttack(mel[k] + durations[k]), d: durations[k] });
      const atBar = run.findIndex((x) => onBarline(x.t));
      const main = atBar >= 0 ? atBar : run.length - 1;
      run.forEach((x, k) => longCands.push({ t: x.t, score: k !== main ? WEIGHTS.longBefore : (x.d >= 3 * median - EPS ? WEIGHTS.veryLong : WEIGHTS.longNote), bar: onBarline(x.t) }));
      i = j;
    }
    const melIndex = (T) => { let k = -1; for (let i = 0; i < mel.length && mel[i] <= T + EPS; i++) k = i; return k; };
    const ownPunct = lyricPunctuation(r);
    const punct = ownPunct.length ? ownPunct : ((extra && extra.punctuation) || []);
    const syllableTimes = ownPunct.length ? ownPunct.syllables : ((extra && extra.syllables) || null);
    for (const [brk, mark, tSyl] of punct) {
      // "feminine" line endings (a-DO-re him,): the long note lies up to two melody notes before the punctuation
      const iB = melIndex(brk - EPS);
      let bonus = isLong(melDuration(tSyl)) ? WEIGHTS.long : 0;
      for (const lc of longCands) if (!lc.used && lc.t <= brk + EPS && melIndex(lc.t) >= iB - 2) { bonus = WEIGHTS.long; lc.used = true; }
      add(brk, (mark === ',' ? WEIGHTS.comma : WEIGHTS.sentence) + bonus, mark === ',' ? 'comma' : 'sentence end', true);
    }
    // instrumental piece (no lyrics, fast melody): prefer lines at the barline, of equal length, usually 4 short or 2 long measures
    const instrumental = !syllableTimes && median < 0.75 - EPS;
    for (const lc of longCands) if (!lc.used) add(lc.t, instrumental && !lc.bar ? 0 : lc.score, 'long note', true);
    for (const m of ms) add(m.start, 0.5, 'barline');

    // choice: lowest "cost" - every break costs something, its sign earns something; lines that are too short or too long cost a lot
    const P = [{ t: 0, score: 0, fixed: true }, ...[...cand.values()].sort((a, b) => a.t - b.t).map((k) => Object.assign(k, { fixed: k.score >= 7.5 && /fermata|breath|double|split|rest/.test(k.reason) })), { t: total, score: 0, fixed: true }];
    const LMIN = 3.5, LMAX = Math.max(24, 3 * nominal), PRICE = instrumental ? 1.5 : WEIGHTS.price;
    const countable = syllableTimes && syllableTimes.length >= 0.5 * mel.length ? syllableTimes : mel;   // syllables, otherwise melody notes
    const notesIn = (a, b) => { let n = 0; for (const t of countable) if (t >= a - EPS && t < b - EPS) n++; return n; };
    const choose = (target, w) => {
      const cost = (L, a, b) => {
        if (instrumental) {
          const targetI = (nominal <= 3 + EPS ? 4 : 2) * nominal;
          return (L < 2 * nominal - EPS ? 6 : 0) + (L > 2 * targetI + EPS ? 2 + 4 * (L - 2 * targetI) / targetI : 0) + 1.5 * ((L - targetI) / targetI) ** 2;
        }
        const n = notesIn(a, b);
        const nMin = countable === mel ? WEIGHTS.nMin : WEIGHTS.nMin - 1, nGood = countable === mel ? WEIGHTS.nGood : WEIGHTS.nGood - 1;
        let k = n < nMin ? 6 + 2 * (nMin - n) : (n < nGood ? 1.5 : (n > WEIGHTS.nMax ? 1 + 0.5 * (n - WEIGHTS.nMax) : 0));
        if (L < LMIN - EPS) k += 8; else if (L > LMAX + EPS) k += 2 + 8 * (L - LMAX) / LMAX;
        return k + w * ((L - target) / target) ** 2;
      };
      const best = [0], prev = [-1];
      for (let i = 1; i < P.length; i++) {
        best[i] = Infinity; prev[i] = -1;
        for (let j = i - 1; j >= 0; j--) {
          const c = best[j] + cost(P[i].t - P[j].t, P[j].t, P[i].t) + (i < P.length - 1 ? PRICE - P[i].score : 0);
          if (c < best[i]) { best[i] = c; prev[i] = j; }
          if (P[j].fixed) break;                     // fixed breaks must not be skipped
        }
      }
      const way = []; for (let i = prev[P.length - 1]; i > 0; i = prev[i]) way.push(P[i]);
      return way.reverse();
    };
    // pass 1: usual line length; pass 2: lines as even as the ones found in pass 1
    let way = choose(WEIGHTS.target, WEIGHTS.w1);
    if (WEIGHTS.w2 > 0) {
      const g = [0, ...way.map((k) => k.t), total], l = [];
      for (let i = 1; i < g.length; i++) l.push(g[i] - g[i - 1]);
      l.sort((a, b) => a - b);
      const m = l[Math.floor(l.length / 2)];
      if (m > 0) way = choose(m, WEIGHTS.w2);
    }
    result.bounds = [0, ...way.map((k) => k.t), total];
    result.reasons = way.map((k) => ({ t: k.t, reason: k.reason }));
    return result;
  }

  const api = { VERSION, NotencodeError, convertDocument, bytesToXmlText, noteName, beatLabel, Fr, phraseBreaks, lyricPunctuation, WEIGHTS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.NotencodeCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
