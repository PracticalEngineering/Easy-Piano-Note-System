# -*- coding: utf-8 -*-
"""Builds index.html (the web page) from core.js + template.html + example.xml.   Run: python tools/build_html/build.py"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
template = (HERE / "template.html").read_text(encoding="utf-8")
core = (HERE / "core.js").read_text(encoding="utf-8")
example = (HERE / "example.xml").read_text(encoding="utf-8")
# punctuation timings of the example's lyrics (for the phrase breaks) - only times and marks, no text
lyrics = (HERE / "example_lyrics.json").read_text(encoding="utf-8")
assert "</script" not in example.lower() and "</script" not in core.lower()
body = template.replace("/*EXAMPLE_LYRICS*/", lyrics).replace("/*EXAMPLE*/", example).replace("/*CORE*/", core)
page = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>:root{color-scheme:light dark;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>\n' + body + '\n</body></html>\n')
(HERE.parent.parent / "index.html").write_text(page, encoding="utf-8")
print("index.html built")
