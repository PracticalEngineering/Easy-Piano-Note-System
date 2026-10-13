# Contributing

Thank you for helping! Bug reports, test files, translations and code are all welcome.

## Reporting a wrong note

If a piece comes out wrong, please open an issue with:

1. the MusicXML file (only if you are allowed to share it – public-domain music is ideal),
2. the measure and beat (shown in the checklist and on the page),
3. what you expected and what you got.

## Changing the rules

The rules live in [SPEC.md](SPEC.md). A change of rules needs:

- the SPEC updated,
- the change in **both** `notencode.py` and `tools/build_html/core.js`,
- a test in `tests/test_notencode.py`,
- all tests passing and JavaScript and Python identical:

```
python -m unittest discover -s tests
python tools/build_html/record_cases.py
cd tools/build_html && npm install && node compare_js_python.js
```

Then rebuild the page: `python tools/build_html/build.py`.

## Translations

The page text is in `tools/build_html/template.html`, object `T`. Copy the `en` block, translate the values, add the language to `LANGS`, rebuild. The check report itself comes from the converter and stays in English.

## Sheet music

Do not add copyrighted scores to the repository. Files in `examples/` must be in the public domain or under a license that allows redistribution; name the source and license in `examples/README.md`.
