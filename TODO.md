# TODO

Pending tasks. Remove a task once it's done. IDs are never reused; a new task gets the next number.

## Edit ABC Score

- [ ] **T1 · Chord styles.** New node `Edit ABC Chords` with a `chord_style` combo:
  - `keep` (default)
  - `triads`
  - `sevenths`: the 7th that fits the key (Cm → Cm7, Ab → Abmaj7, G → G7)
  - `ninths`
  - `power` (C5)
  - `sus2`, `sus4`
  - `sixths`
  - `no_bass`: drop the `/bass` note
  - `remove`: remove chord symbols

  Rewrite chord symbols only. Leave chords outside the key (e.g. `C#dim7`) unchanged.
- [ ] **T2 · Mode.** New `mode` combo on `Edit ABC Score` (default `keep`), with modes in degree order: ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian. Changes `K:` and remaps scale degrees in all notes and chord symbols (e.g. C aeolian → C dorian raises every A♭ to A). Applied together with `keyscale` and `semitone_offset`.

## Preview ABC Score (new node)

- [ ] **T3 · Preview.** New node `Preview ABC Score`: an output node that renders the input score as sheet music in the node UI. Likely uses [abcjs](https://www.abcjs.net/) via a frontend extension (`WEB_DIRECTORY`).
- [ ] **T4 · Notation.** Depends on T3. New `notation` combo on `Preview ABC Score`: `standard` (default), `guitar_tab` or `both` (score with tab below).
