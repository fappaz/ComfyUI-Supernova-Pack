# TODO

Pending tasks. Remove a task once it's done. IDs are never reused; a new task gets the next number.

## Get ABC Score Data (new node)

- [ ] **T10 · Get ABC Score Data.** New node that reads an ABC score and outputs its header values: `meter` (e.g. `4/4`), `default_note_length` (e.g. `1/16`), `tempo` (int, e.g. `112`), `tempo_unit` (the note value in `Q:`, e.g. `1/4`) and `key` (e.g. `F#m`).

## Preview ABC Score (new node)

- [ ] **T3 · Preview.** New node `Preview ABC Score`: an output node that renders the input score as sheet music in the node UI. Likely uses [abcjs](https://www.abcjs.net/) via a frontend extension (`WEB_DIRECTORY`).
- [ ] **T4 · Notation.** Depends on T3. New `notation` combo on `Preview ABC Score`: `standard` (default), `guitar_tab` or `both` (score with tab below).

## Audio and video

- [ ] **T6 · Video effects.** New nodes named `<Effect> Video Effect` (e.g. particles, shake, blur): each takes a video (frames) and outputs it with one effect applied, with that effect's own parameters. **Plan with the user first** (back and forth) before implementing.
- [ ] **T7 · Audio features output.** Related to T6. Add a compact `audio_features` output to `Generate Audio Spectrogram`: loudness per band per frame (kilobytes, not frames), so other nodes, e.g. T6 video effects, can react to the music without passing frames around. Design it together with T6.
- [ ] **T11 · Spectrogram live preview.** Show a one-frame preview on `Generate Audio Spectrogram` that updates as settings change, without running the workflow. Plan: a frontend extension (`WEB_DIRECTORY`) calls a small server route that draws the frame with the same Python code, from a made-up spectrum before the first run and from the last run's audio after it. **Plan with the user first**; the UI needs testing in the user's ComfyUI.
