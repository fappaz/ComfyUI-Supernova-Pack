# ComfyUI-Supernova-Pack
Pack of nodes with useful features not available natively in ComfyUI

## Install

Clone into `ComfyUI/custom_nodes/` and restart ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/fappaz/ComfyUI-Supernova-Pack.git
```

## Nodes

| Node | Category | Purpose |
|---|---|---|
| Edit ABC Score (Supernova) | Supernova/music | Edit an [ABC notation](https://abcnotation.com/) score. |

### Edit ABC Score

Takes an ABC score string and returns it edited. Parameters left empty / 0 are unchanged.

| Parameter | Example | Effect |
|---|---|---|
| `tempo` | `140` | Sets the bpm in the header `Q:` field. |
| `default_note_length` | `1/8` | Sets `L:` and rewrites note durations so the rhythm stays the same. |
| `keyscale` | `D`, `Eb`, `F#` | Changes the key tonic and transposes all notes and chord symbols by at most 6 semitones. The score's mode is kept, so `D` on a C minor score gives D minor. Mode suffixes (`m`, `min`, `maj`, `dor`, `phr`, `lyd`, `mix`, `aeo`, `loc`) and chord suffixes (`7`, `maj7`) are accepted but don't change the mode; use `mode` for that. |
| `mode` | `ionian`, `dorian` | Changes the mode, keeping the tonic: `ionian` (major), `dorian`, `phrygian`, `lydian`, `mixolydian`, `aeolian` (natural minor), `locrian`. Each note keeps its scale degree (C minor → C major turns E♭, A♭, B♭ into E, A, B); notes outside the scale keep their pitch. Chords in the key change quality (Fm7 → Fmaj7). Works with `keyscale` and `semitone_offset`. |
| `semitone_offset` | `-12` | Raises or lowers everything, including the key, by semitones. Applied after `keyscale`. |
| `time_signature` | `4/4` | Sets the header `M:` field. If the new bar is a whole multiple or divisor of the old one (2/4 ↔ 4/4, 3/8 ↔ 6/8), bars are merged or split. Otherwise only the header changes. |
| `chord_style` | `sevenths` | Restyles chord symbols: `triads` (Cm7 → Cm), `sevenths` / `ninths` (adds the 7th / 9th that fits the key: Cm → Cm7, Ab → Abmaj7, G → G7), `sixths`, `sus2`, `sus4`, `power` (C5), `no_bass` (Bb/D → Bb) or `remove`. Chords outside the key are left unchanged by `sevenths` / `ninths`. Applied in the new key after `keyscale`. |

Chord symbols get their simplest spelling after transposing (e.g. `G#maj7` may become `Abmaj7`).

Known limits:
- `tempo` changes only the header. Later `Q:` changes in the score are left as they are.
- Re-barring never splits notes. In these cases `time_signature` changes only the header, and a warning is logged: a note, tuplet or `>`/`<` pair would cross a new bar line, a repeat sign or ending would land mid-bar, a merged bar would span two lines, or the tune has lyrics (`w:`) or meter changes.
- After merging bars, a `Z3`-style multi-bar rest may be written as `z8|Z2`. It's the same length.
- A mode typed into `keyscale` (e.g. `Emaj`) is ignored and a warning is logged; use `mode` instead.
- `mode` changes every key in the tune, including mid-tune key changes, to the chosen mode.
- Changing mode and back isn't always lossless: a note outside the old scale keeps its pitch, and may be inside the new scale (e.g. C minor's raised A natural), so it moves on the way back.
- Blank lines don't end a tune; only `X:` starts a new one. Free text between tunes would be treated as music.
- Microtonal accidentals (e.g. `^/`) aren't supported.

## Development

Requires [uv](https://docs.astral.sh/uv/) (Windows: `winget install astral-sh.uv`).

```
uv sync          # dev env: Python, pytest, ruff, CPU torch
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

See [AGENTS.md](AGENTS.md) for conventions.
