import logging
from pathlib import Path

import pytest

from supernova.core.abc_chords import degree_spelling, remap_quality, scale
from supernova.core.abc_notation import ACCIDENTALS, MODES, NATURAL, Key, parse_key, signature
from supernova.core.abc_score import edit_abc_score

EXAMPLE = (Path(__file__).parent / "data" / "example.abc").read_text()


def key(text: str):
    return parse_key(text)[0]


def tune(body: str, k: str = "Cm") -> str:
    return f"X:1\nL:1/8\nK:{k}\n{body}\n"


def last(abc: str) -> str:
    return abc.rstrip("\n").splitlines()[-1]


def k_lines(abc: str) -> list[str]:
    return [line for line in abc.splitlines() if line.startswith("K:")]


# --- helpers ---


@pytest.mark.parametrize(
    ("pc", "old", "new", "expected"),
    [
        (8, "Cm", "C", ("A", 0)),  # Ab (bVI) -> A (VI)
        (3, "Cm", "C", ("E", 0)),
        (8, "Cm", "C loc", ("A", -1)),
        (5, "C", "C lyd", ("F", 1)),
        (1, "Cm", "C", None),  # Db isn't in C minor
    ],
)
def test_degree_spelling(pc, old, new, expected):
    assert degree_spelling(pc, key(old), key(new)) == expected


@pytest.mark.parametrize(
    ("suffix", "old_root", "new_root", "expected"),
    [
        ("m7", 5, 5, "maj7"),  # Fm7 in C minor -> Fmaj7 in C major
        ("m", 5, 5, ""),
        ("min", 5, 5, ""),
        ("", 8, 9, "m"),  # Ab -> Am
        ("maj7", 8, 9, "m7"),
        ("", 10, 11, "dim"),  # Bb -> Bdim
        ("9", 10, 11, "m7b5"),  # B has no major 9th in C major
        ("maj7", 10, 11, "maj7"),  # Bbmaj7 isn't diatonic in C minor: kept
        ("sus4", 5, 5, "sus4"),
    ],
)
def test_remap_quality(suffix, old_root, new_root, expected):
    assert remap_quality(suffix, old_root, new_root, key("Cm"), key("C")) == expected


# --- notes and header ---


def test_keep_is_unchanged():
    assert edit_abc_score(EXAMPLE, mode="keep") == EXAMPLE


def test_same_mode_is_unchanged():
    assert edit_abc_score(EXAMPLE, mode="aeolian") == EXAMPLE


@pytest.mark.parametrize(
    ("mode", "k"),
    [
        ("ionian", "K:C"),
        ("dorian", "K:Cm"),
        ("phrygian", "K:Cm"),
        ("lydian", "K:C"),
        ("mixolydian", "K:C"),
        ("aeolian", "K:Cm"),
        ("locrian", "K:Cm"),
    ],
)
def test_modes_write_major_or_minor_with_accidentals(mode, k):
    # K: is plain major/minor, and the notes still spell the mode's scale.
    out = edit_abc_score(tune("CDEFGAB", "C"), mode=mode)
    assert k_lines(out) == [k]
    assert pitches(last(out), k) == scale(Key("C", 0, MODES[mode]))


def pitches(line: str, k: str) -> list[int]:
    """Pitch classes of a one-bar line of notes under key k."""
    sig, out, acc = signature(key(k[2:])), [], ""
    for ch in line:
        if ch in "^_=":
            acc += ch
            continue
        out.append((NATURAL[ch.upper()] + (ACCIDENTALS[acc] if acc else sig[ch.upper()])) % 12)
        acc = ""
    return out


def test_melody_text_shows_the_mode():
    # Models that read the score as text (e.g. YuE) see the change in the notes, not only in K:.
    assert last(edit_abc_score(tune("c2EFAGE2"), mode="dorian", explicit_accidentals=True)) == "c2_EF=AG_E2"
    assert last(edit_abc_score(tune("c2EFAGE2"), mode="lydian", explicit_accidentals=True)) == "c2E^FAGE2"


def test_diatonic_notes_keep_their_letters():
    # In C minor "E" is Eb; in C major it's E. The text stays, the key signature does the work.
    assert last(edit_abc_score(tune("CEGB"), mode="ionian")) == "CEGB"


def test_chromatic_notes_keep_their_pitch():
    # =B (raised 7th in C minor) stays B natural; B (Bb, in the scale) becomes B.
    assert last(edit_abc_score(tune("c=Bc|B"), mode="ionian")) == "cBc|B"
    # Blue note Eb in C major stays Eb, which C minor's signature already has; F# stays F#.
    # In the next bar E (in the scale) becomes Eb.
    assert last(edit_abc_score(tune("_E^F|EF", "C"), mode="aeolian", explicit_accidentals=True)) == "_E^F|_EF"


def test_mode_with_keyscale_and_offset():
    out = edit_abc_score(tune("CE"), keyscale="D", mode="ionian", explicit_accidentals=True)
    assert k_lines(out) == ["K:D"]
    assert last(out) == "D^F"
    out = edit_abc_score(tune("CE"), mode="dorian", semitone_offset=2)
    assert k_lines(out) == ["K:Dm"]


def test_mode_respells_impossible_keys():
    # G# major would need 8 sharps -> Ab major.
    assert k_lines(edit_abc_score(tune("C", "G#m"), mode="ionian")) == ["K:Ab"]


def test_mode_replaces_long_mode_names_and_keeps_extras():
    out = edit_abc_score(tune("C", "C minor clef=bass"), mode="dorian")
    assert k_lines(out) == ["K:Cm clef=bass"]


def test_mode_on_keyless_score():
    assert k_lines(edit_abc_score(tune("C", "none"), mode="dorian")) == ["K:Cm"]


def test_body_key_changes_get_the_mode():
    out = edit_abc_score(tune("C|\nK:G\nB|", "C"), mode="aeolian", explicit_accidentals=True)
    assert k_lines(out) == ["K:Cm", "K:Gm"]
    assert last(out) == "_B|"


def test_keyscale_mode_warns(caplog):
    with caplog.at_level(logging.WARNING):
        out = edit_abc_score(tune("C"), keyscale="Em", mode="ionian")
    assert k_lines(out) == ["K:E"]
    assert "use the mode input" in caplog.text


# --- chords ---


def test_chords_change_quality():
    out = edit_abc_score(tune('"Cm7"C "Fm"F "Ab"A "Bb/D"B "G7"G'), mode="ionian")
    assert last(out) == '"Cmaj7"C "F"F "Am"A "Bdim/D"B "G7"G'


def test_loosely_spelled_chords_map_by_pitch():
    out = edit_abc_score(tune('"G#maj7"z "A#/C##"z'), mode="ionian")
    assert last(out) == '"Am7"z "Bdim/D"z'


def test_chord_style_uses_new_mode():
    assert last(edit_abc_score(tune('"Fm"F'), mode="dorian", chord_style="sevenths")) == '"F7"F'


def test_example_is_stable_after_one_mode_change():
    once = edit_abc_score(EXAMPLE, mode="ionian")
    again = edit_abc_score(edit_abc_score(once, mode="aeolian"), mode="ionian")
    assert again == once


def test_mode_spells_every_altered_note():
    # Readable without the key signature: E and A are flat in C minor, B natural is spelled out.
    assert last(edit_abc_score(tune("CDEFGAB", "C"), mode="aeolian", explicit_accidentals=True)) == "CD_EFG_A_B"
    assert last(edit_abc_score(tune("CDEFGAB"), mode="dorian", explicit_accidentals=True)) == "CD_EFG=A_B"


# --- explicit accidentals without other edits ---


def test_explicit_accidentals_alone_spells_out_the_key():
    out = edit_abc_score(EXAMPLE, explicit_accidentals=True)
    lines = out.splitlines()
    assert "K:Cm" in lines
    assert "c2_EF_AG_E2|c2_EF_AG_E2|c2_EF_AG_E2|c2_EF_AG_E2|" in lines
    assert "ddd=A,A,A,DD|DDD=A,A,A,DD|DDD=A,A,A,DD|DGcegbe'b|" not in lines  # every A, is spelled now
    assert "ddd=A,=A,=A,DD|DDD=A,=A,=A,DD|DDD=A,=A,=A,DD|DGc_eg_b_e'_b|" in lines
    assert '"G#maj7"z8|"G#maj7"z8|"G#maj7"z8|"G#maj7"z8|' in lines  # chords untouched


def test_explicit_accidentals_is_idempotent():
    once = edit_abc_score(EXAMPLE, explicit_accidentals=True)
    assert edit_abc_score(once, explicit_accidentals=True) == once


def test_explicit_then_major_changes_the_notes():
    minor = edit_abc_score(EXAMPLE, explicit_accidentals=True).splitlines()
    major = edit_abc_score(EXAMPLE, mode="ionian", explicit_accidentals=True).splitlines()
    # Every melody line with a flat (Eb, Ab, Bb in C minor) now reads differently in major.
    flats = [(a, b) for a, b in zip(minor, major, strict=True) if "_" in a and not a.startswith('"')]
    assert len(flats) >= 10
    assert all(a != b and "_" not in b for a, b in flats)
