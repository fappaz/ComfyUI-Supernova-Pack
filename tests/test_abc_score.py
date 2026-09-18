import logging
from pathlib import Path

import pytest

from supernova.core.abc_score import edit_abc_score

EXAMPLE = (Path(__file__).parent / "data" / "example.abc").read_text()


def tune(body: str, header: str = "M:2/4\nL:1/16\nQ:1/4=75\nK:Cm\n") -> str:
    return f"X:1\nT:Test\n{header}{body}\n"


def body_of(abc: str) -> str:
    return abc.rstrip("\n").splitlines()[-1]


def header_field(abc: str, name: str) -> list[str]:
    return [line for line in abc.splitlines() if line.startswith(f"{name}:")]


def test_nothing_to_change_returns_input():
    assert edit_abc_score(EXAMPLE) == EXAMPLE


# --- tempo ---


def test_tempo_replaces_bpm_keeping_beat_unit():
    assert header_field(edit_abc_score(tune("C4|"), tempo=140), "Q") == ["Q:1/4=140"]


def test_tempo_inserted_before_key_when_missing():
    out = edit_abc_score(tune("C4|", header="M:2/4\nK:C\n"), tempo=90)
    assert "Q:1/4=90\nK:C" in out


@pytest.mark.parametrize(("q", "expected"), [("120", "Q:100"), ('"Allegro"', 'Q:"Allegro" 1/4=100')])
def test_tempo_other_formats(q, expected):
    out = edit_abc_score(tune("C4|", header=f"Q:{q}\nK:C\n"), tempo=100)
    assert header_field(out, "Q") == [expected]


# --- default note length ---


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("d2B2 c4 E", "dB c2 E/"),
        ("z8|Z3|", "z4|Z3|"),
        ("[CE]2 [C2E2]", "[C/E/]2 [CE]"),
        ("(3CDE c3/2 c//", "(3C/D/E/ c3/4 c/8"),
        ("{g}c2", "{g/}c"),
    ],
)
def test_note_length_rescales_durations(body, expected):
    out = edit_abc_score(tune(body, header="L:1/16\nK:C\n"), default_note_length="1/8")
    assert body_of(out) == expected
    assert header_field(out, "L") == ["L:1/8"]


def test_note_length_handles_body_l_fields():
    out = edit_abc_score(tune("c2|\nL:1/8\nc2|[L:1/4]c|", header="L:1/16\nK:C\n"), default_note_length="1/8")
    assert out.splitlines()[-3:] == ["c|", "L:1/8", "c2|[L:1/8]c2|"]


def test_note_length_inserted_when_missing_uses_abc_default():
    # No L: and M:2/4 means the implicit unit is 1/16.
    out = edit_abc_score(tune("c2|", header="M:2/4\nK:C\n"), default_note_length="1/8")
    assert header_field(out, "L") == ["L:1/8"]
    assert body_of(out) == "c|"


def test_invalid_note_length_raises():
    with pytest.raises(ValueError, match="note length"):
        edit_abc_score(EXAMPLE, default_note_length="eighth")


# --- time signature ---


def test_time_signature_changes_header_only():
    out = edit_abc_score(tune("C4|\nM:6/8\nC4|"), time_signature="3/4")
    assert header_field(out, "M") == ["M:3/4", "M:6/8"]
    assert "C4|" in out


def test_time_signature_pins_implicit_note_length():
    # M:4/4 -> 2/4 would change the implicit L: from 1/8 to 1/16, so L:1/8 is added.
    out = edit_abc_score(tune("C4|", header="M:4/4\nK:C\n"), time_signature="2/4")
    assert header_field(out, "L") == ["L:1/8"]
    assert body_of(out) == "C4|"


@pytest.mark.parametrize("meter", ["4/4", "6/8", "C", "C|", "2+3/8", "none"])
def test_time_signature_accepts_valid(meter):
    assert header_field(edit_abc_score(tune("C4|"), time_signature=meter), "M") == [f"M:{meter}"]


def test_invalid_time_signature_raises():
    with pytest.raises(ValueError, match="time signature"):
        edit_abc_score(EXAMPLE, time_signature="four")


# --- keyscale ---


def test_keyscale_transposes_header_notes_and_chords():
    out = edit_abc_score(tune('"Cm7"d2B2|"G#maj7"c2EF|'), keyscale="D")
    assert header_field(out, "K") == ["K:Dm"]
    assert body_of(out) == '"Dm7"e2c2|"A#maj7"d2FG|'


def test_keyscale_goes_to_nearest_octave():
    # C -> A is 3 semitones down, not 9 up. C# is in A major's key signature.
    out = edit_abc_score(tune("CEG", header="K:C\n"), keyscale="A")
    assert body_of(out) == "A,CE"


def test_keyscale_handles_accidentals_and_bar_resets():
    # In Cm, =A, is A natural and stays natural (same octave) until the bar line.
    out = edit_abc_score(tune("=A,A,A^B|A,"), keyscale="Dm")
    assert body_of(out) == "=B,B,B^^c|B,"


def test_keyscale_crosses_octaves():
    # C# is in D major's key signature.
    out = edit_abc_score(tune("Bb'B,", header="K:C\n"), keyscale="D")
    assert body_of(out) == "cc''C"


def test_keyscale_keeps_score_mode(caplog):
    with caplog.at_level(logging.WARNING):
        out = edit_abc_score(tune("C"), keyscale="E")
    assert header_field(out, "K") == ["K:Em"]
    assert "mode ignored" not in caplog.text
    with caplog.at_level(logging.WARNING):
        out = edit_abc_score(tune("C"), keyscale="Emaj")
    assert header_field(out, "K") == ["K:Em"]
    assert "mode ignored" in caplog.text


@pytest.mark.parametrize(("keyscale", "expected"), [("am", "K:Am"), ("F#7", "K:F#m"), ("Bb", "K:Bbm")])
def test_keyscale_input_forms(keyscale, expected):
    assert header_field(edit_abc_score(tune("C"), keyscale=keyscale), "K") == [expected]


def test_keyscale_respells_impossible_keys():
    # G# minor is fine (5 sharps), G# major would need 8 sharps -> Ab.
    assert header_field(edit_abc_score(tune("C"), keyscale="G#"), "K") == ["K:G#m"]
    assert header_field(edit_abc_score(tune("C", header="K:C\n"), keyscale="G#"), "K") == ["K:Ab"]


def test_keyscale_keeps_mode_words_and_extras():
    out = edit_abc_score(tune("D", header="K:D dorian clef=bass\n"), keyscale="E")
    assert header_field(out, "K") == ["K:E dorian clef=bass"]
    assert body_of(out) == "E"


def test_keyscale_on_keyless_score():
    out = edit_abc_score(tune("C^F", header="K:none\n"), keyscale="D")
    assert header_field(out, "K") == ["K:D"]
    assert body_of(out) == "D^G"


def test_invalid_keyscale_raises():
    with pytest.raises(ValueError, match="keyscale"):
        edit_abc_score(EXAMPLE, keyscale="H")


def test_body_key_changes_and_voices_are_transposed():
    abc = tune("V:A\nK:G\nF|\nV:B\nF|[K:Bb]B|", header="K:C\n")
    out = edit_abc_score(abc, keyscale="D")
    assert out.splitlines()[-5:] == ["V:A", "K:A", "G|", "V:B", "G|[K:C]c|"]


# --- semitone offset ---


def test_semitone_offset_octave_keeps_key():
    out = edit_abc_score(tune("c2G,2|"), semitone_offset=-12)
    assert header_field(out, "K") == ["K:Cm"]
    assert body_of(out) == "C2G,,2|"


def test_semitone_offset_picks_simplest_key():
    # Cm + 1 -> C#m (4 sharps), not Dbm (8 flats).
    out = edit_abc_score(tune("cE"), semitone_offset=1)
    assert header_field(out, "K") == ["K:C#m"]
    assert body_of(out) == "cE"


def test_semitone_offset_applies_after_keyscale():
    out = edit_abc_score(tune("c"), keyscale="D", semitone_offset=2)
    assert header_field(out, "K") == ["K:Em"]
    assert body_of(out) == "e"


# --- untouched content ---


def test_non_music_text_is_untouched():
    body = '"^Intro"!trill!c2 %c comment\nw: la la\n%%MIDI program 1\n'
    out = edit_abc_score(tune(body, header="K:C\n"), keyscale="D", default_note_length="1/8")
    assert '"^Intro"!trill!d2 %c comment\nw: la la\n%%MIDI program 1\n' in out


def test_line_endings_preserved():
    abc = "X:1\r\nL:1/16\r\nK:C\r\nc2"
    assert edit_abc_score(abc, default_note_length="1/8", tempo=90) == "X:1\r\nL:1/8\r\nQ:1/4=90\r\nK:C\r\nc"


def test_multiple_tunes_are_edited_independently():
    abc = tune("C", header="K:C\n") + "\n" + tune("C", header="K:G\n")
    out = edit_abc_score(abc, semitone_offset=2)
    assert header_field(out, "K") == ["K:D", "K:A"]


# --- full example ---


def test_example_round_trip():
    up = edit_abc_score(EXAMPLE, keyscale="Em")
    assert header_field(up, "K") == ["K:Em"]
    down = edit_abc_score(up, keyscale="Cm")
    # Notes survive unchanged; chord symbols get their simplest spelling.
    expected = (
        EXAMPLE.replace('"G#maj7"', '"Abmaj7"').replace('"A#/C##"', '"Bb/D"').replace('"A#maj7/C##"', '"Bbmaj7/D"')
    )
    assert down == expected


def test_example_all_params():
    out = edit_abc_score(
        EXAMPLE, tempo=140, default_note_length="1/8", keyscale="Am", semitone_offset=0, time_signature="3/4"
    )
    lines = out.splitlines()
    assert lines[2:5] == ["M:3/4", "L:1/8", "Q:1/4=140"]
    assert "K:Am" in lines
    assert '"Am7"z4|"Am7"z4|"Am7"z4|"Am7"z4|' in lines
    assert "BGBG|BGBG|BGBG|BGBG|" in lines
