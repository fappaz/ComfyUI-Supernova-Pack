from pathlib import Path

import pytest

from supernova.core.abc_chords import CHORD_STYLES, diatonic_chord, scale, style_chord, triad_quality
from supernova.core.abc_notation import Key, parse_key
from supernova.core.abc_score import edit_abc_score

EXAMPLE = (Path(__file__).parent / "data" / "example.abc").read_text()
C_MAJOR = Key("C", 0)
C_MINOR = Key("C", 0, -3)


def key(text: str) -> Key:
    return parse_key(text)[0]


@pytest.mark.parametrize(
    ("k", "expected"),
    [
        ("C", [0, 2, 4, 5, 7, 9, 11]),
        ("Am", [9, 11, 0, 2, 4, 5, 7]),
        ("D dor", [2, 4, 5, 7, 9, 11, 0]),
        ("Cm", [0, 2, 3, 5, 7, 8, 10]),
        ("G mix", [7, 9, 11, 0, 2, 4, 5]),
    ],
)
def test_scale(k, expected):
    assert scale(key(k)) == expected


@pytest.mark.parametrize(
    ("root", "k", "expected"),
    [
        (0, "C", ("maj", "maj7", "maj9")),
        (2, "C", ("min", "m7", "m9")),
        (4, "C", ("min", "m7", "m7")),  # b9: no ninth
        (7, "C", ("maj", "7", "9")),
        (11, "C", ("dim", "m7b5", "m7b5")),
        (8, "Cm", ("maj", "maj7", "maj9")),
        (10, "Cm", ("maj", "7", "9")),
        (1, "C", None),
    ],
)
def test_diatonic_chord(root, k, expected):
    assert diatonic_chord(root, key(k)) == expected


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        ("", "maj"),
        ("7", "maj"),
        ("maj7", "maj"),
        ("M7", "maj"),
        ("add9", "maj"),
        ("m", "min"),
        ("m7", "min"),
        ("min", "min"),
        ("-7", "min"),
        ("mMaj7", "min"),
        ("dim", "dim"),
        ("°7", "dim"),
        ("m7b5", "dim"),
        ("ø", "dim"),
        ("aug", "aug"),
        ("+", "aug"),
        ("7#5", "aug"),
        ("sus4", None),
        ("5", None),
        ("(foo)", None),
    ],
)
def test_triad_quality(suffix, expected):
    assert triad_quality(suffix) == expected


@pytest.mark.parametrize(
    ("chord", "style", "expected"),
    [
        ("Cm7", "keep", "Cm7"),
        ("Cm7", "triads", "Cm"),
        ("Abmaj7/C", "triads", "Ab/C"),
        ("Bdim7", "triads", "Bdim"),
        ("Cm", "sevenths", "Cm7"),
        ("Ab", "sevenths", "Abmaj7"),
        ("G#", "sevenths", "G#maj7"),  # spelled oddly, but Ab is in the key
        ("Bb/D", "sevenths", "Bb7/D"),
        ("Cm", "ninths", "Cm9"),
        ("G", "sevenths", "G"),  # G major is borrowed (Cm has G minor): unchanged
        ("C#dim7", "sevenths", "C#dim7"),  # outside the key: unchanged
        ("Csus4", "sevenths", "Csus4"),
        ("Cm7", "sixths", "Cm6"),
        ("Ab", "sixths", "Ab6"),
        ("Bdim", "sixths", "Bdim"),
        ("Cm7/G", "sus2", "Csus2/G"),
        ("Cm7", "sus4", "Csus4"),
        ("Cm7/G", "power", "C5"),
        ("A#maj7/C##", "no_bass", "A#maj7"),
        ("Cm7", "remove", None),
        ("N.C.", "remove", None),
        ("^Intro", "remove", "^Intro"),
        ("^Intro", "triads", "^Intro"),
        ("N.C.", "triads", "N.C."),
    ],
)
def test_style_chord(chord, style, expected):
    assert style_chord(chord, C_MINOR, style) == expected


def test_style_chord_without_key_uses_c_major():
    assert style_chord("G", None, "sevenths") == "G7"


# --- through edit_abc_score ---


def test_chord_style_on_example():
    out = edit_abc_score(EXAMPLE, chord_style="sevenths")
    assert '"G#maj7"z8|"G#maj7"z8|"G#maj7"z8|"G#maj7"z8|' in out
    assert '"A#7/C##"z8|"A#7/C##"z8|"A#7/C##"z8|"A#7/C##"z8|' in out


def test_chord_style_uses_transposed_key():
    # Cm -> Em: G#maj7 (VI) -> Cmaj7, still VI in E minor.
    out = edit_abc_score(EXAMPLE, keyscale="Em", chord_style="triads")
    assert '"C"z8|"C"z8|"C"z8|"C"z8|' in out
    assert '"Em"z8|' in out


def test_chord_style_follows_key_changes():
    abc = 'X:1\nL:1/8\nK:C\n"G"c|\nK:Am\n"G"c|\n'
    assert edit_abc_score(abc, chord_style="sevenths").splitlines()[-3:] == ['"G7"c|', "K:Am", '"G7"c|']


def test_remove_chords_keeps_annotations():
    abc = 'X:1\nK:C\n"^Intro""C"c "Am"A|\n'
    assert edit_abc_score(abc, chord_style="remove").splitlines()[-1] == '"^Intro"c A|'


def test_all_styles_run_on_example():
    for style in CHORD_STYLES:
        edit_abc_score(EXAMPLE, chord_style=style)
