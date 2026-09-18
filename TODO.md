# TODO

Pending tasks. Remove a task once it's done. IDs are never reused; a new task gets the next number.

## Edit ABC Score

- [ ] **T2 · Mode.** New `mode` combo on `Edit ABC Score` (default `keep`), with modes in degree order: ionian, dorian, phrygian, lydian, mixolydian, aeolian, locrian. Changes `K:` and remaps scale degrees in all notes and chord symbols (e.g. C aeolian → C dorian raises every A♭ to A). Applied together with `keyscale` and `semitone_offset`.

## Preview ABC Score (new node)

- [ ] **T3 · Preview.** New node `Preview ABC Score`: an output node that renders the input score as sheet music in the node UI. Likely uses [abcjs](https://www.abcjs.net/) via a frontend extension (`WEB_DIRECTORY`).
- [ ] **T4 · Notation.** Depends on T3. New `notation` combo on `Preview ABC Score`: `standard` (default), `guitar_tab` or `both` (score with tab below).
