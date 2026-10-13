# Song library

These songs appear in the **Song library** on the [website](https://practicalengineering.github.io/Easy-Piano-Note-System/). Click a song to see it in the Easy Piano Note System. Every song can be linked directly, e.g. `…/Easy-Piano-Note-System/#amazing-grace`.

| Song | Source | License |
|---|---|---|
| Silent Night | musescore.com score 2996071 | public domain |
| O Come, All Ye Faithful | CPDL #61921 (Andrew Sims) | CPDL |
| Hark! The Herald Angels Sing | CPDL #61923 (Andrew Sims) | CPDL |
| Joy to the World | CPDL #67499 (Andrew Sims) | CPDL |
| Angels We Have Heard on High | CPDL #30930 (Winfried Grünewald) | CPDL |
| O How Joyfully (O du fröhliche) | CPDL #30902 (Winfried Grünewald) | CPDL |
| O Holy Night | CPDL #20587 | public domain |
| Lift Up Your Heads, Ye Mighty Gates (Macht hoch die Tür) | CPDL #52885 (Andrew Sims) | CPDL |
| Amazing Grace | CPDL #41966 (Paul Hayward) | public domain |
| A Mighty Fortress Is Our God | CPDL #81218 (Andrew Sims) | CPDL |
| Holy God, We Praise Thy Name | CPDL #75274 (Douglas Walczak) | public domain |
| Now Thank We All Our God | CPDL #62420 (Andrew Sims) | CPDL |
| Praise to the Lord, the Almighty | CPDL #52919 (Andrew Sims) | CPDL |
| Befiehl du deine Wege | CPDL #37605 (Florian Mattersberger) | CPDL |

The files are unchanged copies of the originals. The [CPDL license](https://www.cpdl.org/wiki/index.php/ChoralWiki:CPDL) allows copying and sharing with credit to the editor; the credit line is shown under the title on the website. The page shows notes only, no lyrics.

## Adding a song

1. **Check the license.** Only music in the **public domain** (most hymns written before 1929, in an edition that is free too) or under a license that allows sharing, e.g. CPDL or CC BY. No songs from paid or "personal use only" sources, no modern worship songs unless the copyright holder allows it.
2. **Add the file** to `library/songs/` as `.mxl` or `.musicxml`, named like the song: `my-song-title.mxl`.
3. **Add an entry** to `library.json`:

```json
{
 "id": "my-song-title",
 "title": { "en": "My Song Title", "de": "Mein Liedtitel" },
 "group": "hymns",
 "file": "songs/my-song-title.mxl",
 "credit": "Melody … (year) · edition …, CPDL #12345",
 "source": "https://www.cpdl.org/wiki/index.php/…",
 "license": "CPDL"
}
```

- `group`: `hymns` or `christmas` (a new group name works too).
- If the file has more than two staves (e.g. choir + piano), add `"upper": "P5/1", "lower": "P5/2"` – which staves are the right and left hand. Run `python notencode.py library/songs/FILE.mxl` to see the staves.

4. **Run the tests**: `python -m unittest discover -s tests`. They check every song: the file exists, it converts, every note is accounted for, and the license is one of the allowed ones.
5. Open a pull request – or send the file and its source to the Discord community.
