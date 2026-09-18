import logging
from pathlib import Path

import pytest

from supernova.core.abc_score import edit_abc_score

EXAMPLE = (Path(__file__).parent / "data" / "example.abc").read_text()


def rebar(body: str, old: str, new: str, unit: str = "1/8") -> str:
    out = edit_abc_score(f"X:1\nM:{old}\nL:{unit}\nK:C\n{body}\n", time_signature=new)
    return out.split("K:C\n", 1)[1].rstrip("\n")


@pytest.mark.parametrize(
    ("body", "old", "new", "expected"),
    [
        # merge
        ("c2d2|e2f2|g4|a4|", "2/4", "4/4", "c2d2e2f2|g4a4|"),
        ("c3|d3|", "3/8", "6/8", "c3d3|"),
        ("c4|d4|", "2/2", "4/4", "c4|d4|"),  # same bar length: nothing to move
        ("c2d2|e2f2|\nc2d2|e2f2|", "2/4", "4/4", "c2d2e2f2|\nc2d2e2f2|"),
        # split
        ("c2d2e2f2|g4a4|", "4/4", "2/4", "c2d2|e2f2|g4|a4|"),
        ('"C"c2"G"d2|', "2/4", "1/4", '"C"c2|"G"d2|'),
        ("c2-c2|", "2/4", "1/4", "c2-|c2|"),
        ("[CE]2[DF]2|", "2/4", "1/4", "[CE]2|[DF]2|"),
        ("(3cde (3cde|", "2/4", "1/4", "(3cde| (3cde|"),
        ("c>d c>d|", "2/4", "1/4", "c>d| c>d|"),
        ("{g}c2 {a}d2|", "2/4", "1/4", "{g}c2| {a}d2|"),
    ],
)
def test_rebar(body, old, new, expected):
    assert rebar(body, old, new) == expected


def test_rests_are_split_and_merged():
    assert rebar("c2z6|", "4/4", "2/4") == "c2z2|z4|"
    assert rebar("Z3|", "2/4", "1/4") == "Z6|"
    assert rebar("c4|Z3|", "2/4", "4/4") == "c4z4|Z|"


def test_pickup_bar_is_kept():
    assert rebar("c|d2e2|f4|g", "2/4", "4/4") == "c|d2e2f4|g"


def test_accidentals_restated_after_merge():
    # ^F carried to the end of the old bar only; the next F was natural.
    assert rebar("^F2F2|F4|", "2/4", "4/4") == "^F2F2=F4|"


def test_accidentals_restated_after_split():
    assert rebar("^F4F4|", "4/4", "2/4") == "^F4|^F4|"


def test_accidentals_use_key_signature():
    out = edit_abc_score("X:1\nM:2/4\nL:1/8\nK:G\n=F2F2|F4|\n", time_signature="4/4")
    assert out.endswith("=F2F2^F4|\n")


def test_voices_are_rebarred_separately():
    body = "V:1\nc2d2|e2f2|\nV:2\nC4|D4|"
    assert rebar(body, "2/4", "4/4") == "V:1\nc2d2e2f2|\nV:2\nC4D4|"


def test_example_merges_to_4_4():
    lines = edit_abc_score(EXAMPLE, time_signature="4/4").splitlines()
    assert "M:4/4" in lines
    assert '"Cm7"z8"Cm7"z8|"Cm7"z8"Cm7"z8|' in lines
    assert "G2z6z8|Z|" in lines


def test_example_round_trip_keeps_music():
    back = edit_abc_score(edit_abc_score(EXAMPLE, time_signature="4/4"), time_signature="2/4")
    assert back == EXAMPLE.replace("G2z6|Z3|", "G2z6|z8|Z2|")


@pytest.mark.parametrize(
    ("body", "old", "new", "reason"),
    [
        ("c3d|", "2/4", "1/4", "a note would cross"),
        ("(4:4cdef|", "2/4", "1/4", "tuplet"),
        ("c/c>dc3/2|", "2/4", "1/4", "broken rhythm"),
        ("|:c4:|d4|", "2/4", "4/4", "':|' would fall mid-bar"),
        ("c4|\nd4|", "2/4", "4/4", "span two lines"),
        ("c4|d4|\nw: la la", "2/4", "4/4", "lyrics"),
        ("c4|\nM:3/4\nd6|", "2/4", "4/4", "changes meter"),
    ],
)
def test_complex_cases_change_header_only(body, old, new, reason, caplog):
    with caplog.at_level(logging.WARNING):
        out = rebar(body, old, new)
    assert out == body
    assert reason in caplog.text


def test_uneven_meter_change_is_header_only(caplog):
    with caplog.at_level(logging.INFO):
        out = edit_abc_score(EXAMPLE, time_signature="3/4")
    assert out == EXAMPLE.replace("M:2/4", "M:3/4")
    assert "header only" in caplog.text
