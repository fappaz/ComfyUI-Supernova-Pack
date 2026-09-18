import logging
from pathlib import Path

import pytest

from supernova.core.abc_chords import degree_spelling, remap_quality
from supernova.core.abc_notation import parse_key
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
        ("dorian", "K:C dor"),
        ("phrygian", "K:C phr"),
        ("lydian", "K:C lyd"),
        ("mixolydian", "K:C mix"),
        ("aeolian", "K:Cm"),
        ("locrian", "K:C loc"),
    ],
)
def test_header_gets_mode(mode, k):
    assert k_lines(edit_abc_score(tune("C", "C"), mode=mode)) == [k]


def test_diatonic_notes_keep_their_letters():
    # In C minor "E" is Eb; in C major it's E. The text stays, the key signature does the work.
    assert last(edit_abc_score(tune("CEGB"), mode="ionian")) == "CEGB"


def test_chromatic_notes_keep_their_pitch():
    # =B (raised 7th in C minor) stays B natural; B (Bb, in the scale) becomes B.
    assert last(edit_abc_score(tune("c=Bc|B"), mode="ionian")) == "cBc|B"
    # Blue note Eb in C major stays Eb, which C minor's signature already has; F# stays F#.
    # In the next bar E (in the scale) becomes Eb.
    assert last(edit_abc_score(tune("_E^F|EF", "C"), mode="aeolian")) == "E^F|EF"


def test_mode_with_keyscale_and_offset():
    out = edit_abc_score(tune("CE"), keyscale="D", mode="ionian")
    assert k_lines(out) == ["K:D"]
    assert last(out) == "DF"  # F is F# in D major
    out = edit_abc_score(tune("CE"), mode="dorian", semitone_offset=2)
    assert k_lines(out) == ["K:D dor"]


def test_mode_respells_impossible_keys():
    # G# major would need 8 sharps -> Ab major.
    assert k_lines(edit_abc_score(tune("C", "G#m"), mode="ionian")) == ["K:Ab"]


def test_mode_replaces_long_mode_names_and_keeps_extras():
    out = edit_abc_score(tune("C", "C minor clef=bass"), mode="dorian")
    assert k_lines(out) == ["K:C dor clef=bass"]


def test_mode_on_keyless_score():
    assert k_lines(edit_abc_score(tune("C", "none"), mode="dorian")) == ["K:C dor"]


def test_body_key_changes_get_the_mode():
    out = edit_abc_score(tune("C|\nK:G\nB|", "C"), mode="aeolian")
    assert k_lines(out) == ["K:Cm", "K:Gm"]
    assert last(out) == "B|"  # B -> Bb, which Gm's signature has


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


def test_example_round_trip():
    back = edit_abc_score(edit_abc_score(EXAMPLE, mode="ionian"), mode="aeolian")
    expected = (
        EXAMPLE.replace('"G#maj7"', '"Abmaj7"')
        .replace('"A#/C##"', '"Bb/D"')
        .replace('"A#maj7/C##"', '"Bbmaj7/D"')
        # =A, (A natural, outside C minor) is in C major's scale, so on the way back it becomes Ab.
        .replace("=A,", "A,")
    )
    assert back == expected
