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
| `keyscale` | `D`, `Am`, `F#` | Changes the key and transposes all notes and chord symbols to the nearest octave. The score's mode (major/minor) is kept, so `D` on a C minor score gives D minor. |
| `semitone_offset` | `-12` | Raises or lowers everything, including the key, by semitones. Applied after `keyscale`. |
| `time_signature` | `3/4` | Sets the header `M:` field. Bar lines are not moved. |

Chord symbols get their simplest spelling after transposing (e.g. `G#maj7` may become `Abmaj7`).

Known limits:
- `tempo` and `time_signature` change only the header. Later `Q:` / `M:` changes in the score are left as they are.
- If `keyscale` has a different mode than the score (e.g. `Emaj` on a minor score), the mode is ignored and a warning is logged.
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
