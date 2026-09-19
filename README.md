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
| Generate Audio Spectrogram (Supernova) | Supernova/audio | Turn audio into a black & white visualizer video. |

### Edit ABC Score

Takes an ABC score string and returns it edited. Parameters left empty / 0 are unchanged. Invalid values (e.g. `keyscale` = `H`) are ignored: the node still runs, and a warning is printed in the ComfyUI console and attached to the node's output.

| Parameter | Example | Effect |
|---|---|---|
| `tempo` | `140` | Sets the bpm in the header `Q:` field. |
| `default_note_length` | `1/8` | Sets `L:` and rewrites note durations so the rhythm stays the same. |
| `keyscale` | `D`, `Eb`, `F#` | Changes the key tonic and transposes all notes and chord symbols by at most 6 semitones. The score's mode is kept, so `D` on a C minor score gives D minor. Mode suffixes (`m`, `min`, `maj`, `dor`, `phr`, `lyd`, `mix`, `aeo`, `loc`) and chord suffixes (`7`, `maj7`) are accepted but don't change the mode; use `mode` for that. |
| `mode` | `ionian`, `dorian` | Changes the mode, keeping the tonic: `ionian` (major), `dorian`, `phrygian`, `lydian`, `mixolydian`, `aeolian` (natural minor), `locrian`. Each note keeps its scale degree (C minor → C major turns E♭, A♭, B♭ into E, A, B); notes outside the scale keep their pitch. Chords in the key change quality (Fm7 → Fmaj7). Works with `keyscale` and `semitone_offset`. `K:` is written as plain major or minor (C dorian → `K:Cm`) with explicit accidentals (`=A`), so players and music models that don't know mode names, such as YuE, still get the right notes. |
| `chord_style` | `sevenths` | Restyles chord symbols: `triads` (Cm7 → Cm), `sevenths` / `ninths` (adds the 7th / 9th that fits the key: Cm → Cm7, Ab → Abmaj7, G → G7), `sixths`, `sus2`, `sus4`, `power` (C5), `no_bass` (Bb/D → Bb) or `remove`. Chords outside the key are left unchanged by `sevenths` / `ninths`. Applied in the new key after `keyscale`. |
| `semitone_offset` | `-12` | Raises or lowers everything, including the key, by semitones. Applied after `keyscale`. |
| `time_signature` | `4/4` | Sets the header `M:` field. If the new bar is a whole multiple or divisor of the old one (2/4 ↔ 4/4, 3/8 ↔ 6/8), bars are merged or split. Otherwise only the header changes. |

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

### Generate Audio Spectrogram

Renders audio as a black & white visualizer, one frame per `1 / fps` seconds of the whole track. While it runs, the node shows the frame count and the RAM it needs.

Outputs `frames` (IMAGE), the same frames as a `mask` (to paint, colour or composite with), a `video` with the original audio attached, and `fps`.

| Parameter | Effect |
|---|---|
| `width`, `height`, `fps` | Frame size and rate. Connect a `reference` image to use its size instead. |
| `mode` | `bars` (equalizer), `circular` (bars around a circle), `scrolling` (spectrogram scrolling right to left) or `static_playhead` (whole track, with a moving line). Each mode shows its own options below it. |
| `freq_scale` | `log` spreads frequencies like we hear them; `linear` is even in Hz. |
| `min_freq`, `max_freq` | Frequency range shown. |
| `db_range` | Sensitivity: how far below the loudest moment still shows. |
| `max_memory_gb` | RAM limit for `frames`/`mask` (default 4). Above it they aren't rendered: you get a black frame and a warning instead of running out of memory. |
| `render_frames` | On (default): `frames`/`mask` are kept in RAM. Off: they're a single black frame and the `video` is drawn while it's saved, using little memory at any length. Turn it off when you only save the video. |

Mode options:
- `bars`: `bar_count`, `bar_gap`, `max_height`, `position` (bottom / center / top), `margin`, `mirror` (grow both ways), `reflection`, `peak_caps` + `peak_fall`, `smoothing`.
- `circular`: `bar_count`, `bar_gap`, `radius`, `max_length`, `center_x`, `center_y`, `mirror` (grow inwards too), `peak_caps` + `peak_fall`, `smoothing`.
- `scrolling`: `window_seconds` (time visible), `position`, `max_height`.
- `static_playhead`: `playhead_width`, `dim_unplayed`.

Known limits:
- `frames`/`mask` are kept in RAM, like all ComfyUI images: at the default 640×360, 16 fps that's about 15 MB per second (a 3-minute song: about 2.6 GB). A warning is logged above 2 GB, and `max_memory_gb` stops runaway renders. To save a long track, turn off `render_frames`: the video is then streamed.
- With `render_frames` off, nodes that read the video's frames (e.g. to edit them) still render them all into RAM, within `max_memory_gb`.
- Stereo is mixed to mono. Loudness is normalized to the loudest moment of the track.
- `frames` and `mask` share memory. Nodes that edit images in place (rare) may fail on them.

## Development

Requires [uv](https://docs.astral.sh/uv/) (Windows: `winget install astral-sh.uv`).

```
uv sync          # dev env: Python, pytest, ruff, CPU torch
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

See [AGENTS.md](AGENTS.md) for conventions.
