// Compares the JavaScript core (core.js) with the Python reference (notencode.py) on all recorded cases.
// First:  python tools/build_html/record_cases.py
// Then:   npm install   (once, inside tools/build_html)
//         node tools/build_html/compare_js_python.js
const fs = require('fs'); const zlib = require('zlib'); const path = require('path');
const { DOMParser } = require('@xmldom/xmldom');
const core = require('./core.js');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'cases.json'), 'utf8'));
const norm = (text) => text.replace(/^Converter: .*$/m, 'Converter: X');
(async () => {
  let ok = 0, bad = 0;
  for (const [i, c] of cases.entries()) {
    let xml = c.xml;
    if (c.file) xml = await core.bytesToXmlText(new Uint8Array(fs.readFileSync(c.file)), async (d) => new Uint8Array(zlib.inflateRawSync(d)));
    const doc = new DOMParser({ onError: () => {} }).parseFromString(xml, 'text/xml');
    let r, err = null;
    try { r = core.convertDocument(doc, Object.assign({ source: c.file ? path.basename(c.file) : '<xml>' }, c.opts)); }
    catch (e) { if (e instanceof core.NotencodeError) err = e.message; else throw e; }
    const fails = [];
    if (c.error !== undefined || err !== null) { if (c.error !== err) fails.push(['error', c.error, err]); }
    else {
      if (r.codeText !== c.code) fails.push(['code', c.code, r.codeText]);
      if (r.checklistText !== c.checklist) fails.push(['checklist', c.checklist, r.checklistText]);
      if (norm(r.reportText) !== norm(c.report)) fails.push(['report', c.report, r.reportText]);
      for (const k of ['warnings', 'check', 'hands', 'info'])
        if (JSON.stringify(r.report[k]) !== JSON.stringify(c[k])) fails.push([k, c[k], r.report[k]]);
    }
    if (fails.length) { bad++; console.log(`CASE ${i} ${JSON.stringify(c.opts)}`); for (const f of fails) console.log('  ', f[0], '\n   PY:', JSON.stringify(f[1]), '\n   JS:', JSON.stringify(f[2])); }
    else ok++;
  }
  console.log(`\n${ok} identical, ${bad} different (of ${cases.length})`);
  process.exit(bad ? 1 : 0);
})();
