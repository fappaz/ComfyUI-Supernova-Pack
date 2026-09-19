import logging
from pathlib import Path

import pytest

import supernova.core.abc_score as abc_score
from supernova.core.abc_score import edit_abc_score, edit_abc_score_with_warnings

EXAMPLE = (Path(__file__).parent / "data" / "example.abc").read_text()


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"tempo": -5}, "tempo"),
        ({"default_note_length": "eighth"}, "default_note_length"),
        ({"default_note_length": "0/8"}, "default_note_length"),
        ({"keyscale": "H"}, "keyscale"),
        ({"keyscale": "#"}, "keyscale"),
        ({"time_signature": "four"}, "time_signature"),
        ({"mode": "major"}, "mode"),
        ({"chord_style": "jazzy"}, "chord_style"),
    ],
)
def test_invalid_input_is_ignored_with_warning(kwargs, name, caplog):
    with caplog.at_level(logging.WARNING):
        assert edit_abc_score(EXAMPLE, **kwargs) == EXAMPLE
    assert f"{name} " in caplog.text
    assert "ignored" in caplog.text


def test_other_inputs_still_apply():
    out = edit_abc_score(EXAMPLE, keyscale="H", tempo=90)
    assert "Q:1/4=90" in out
    assert "K:Cm" in out


def test_invalid_l_field_in_score_is_ignored(caplog):
    abc = "X:1\nL:oops\nK:C\nc2|\nL:1/0\nc2|\n"
    with caplog.at_level(logging.WARNING):
        out = edit_abc_score(abc, keyscale="D")
    assert out == "X:1\nL:oops\nK:D\nd2|\nL:1/0\nd2|\n"
    assert "L:oops in the score is invalid" in caplog.text


def test_with_warnings_returns_messages():
    out, warnings = edit_abc_score_with_warnings(EXAMPLE, keyscale="H", time_signature="3/4")
    assert "M:3/4" in out
    assert any("keyscale 'H' is invalid" in w for w in warnings)
    assert any("only the header changed" in w for w in warnings)


def test_with_warnings_is_empty_when_all_is_fine():
    assert edit_abc_score_with_warnings(EXAMPLE, tempo=90)[1] == []


def test_with_warnings_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(abc_score._Editor, "run", boom)
    out, warnings = edit_abc_score_with_warnings(EXAMPLE, tempo=90)
    assert out == EXAMPLE
    assert warnings == ["Edit ABC Score (score returned unchanged) failed: bug"]
