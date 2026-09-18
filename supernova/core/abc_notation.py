"""ABC notation primitives: tokens, keys, pitches, lengths and meters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

LETTERS = "CDEFGAB"
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTER_FIFTHS = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
SHARP_ORDER = "FCGDAEB"
# Mode -> offset in the circle of fifths relative to major, keyed by the first 3 letters of the mode name.
MODE_FIFTHS = {"maj": 0, "ion": 0, "mix": -1, "dor": -2, "min": -3, "aeo": -3, "m": -3, "phr": -4, "loc": -5, "lyd": 1}
# Modes in scale-degree order, as circle-of-fifths offset from major.
MODES = {"ionian": 0, "dorian": -2, "phrygian": -4, "lydian": 1, "mixolydian": -1, "aeolian": -3, "locrian": -5}
MODE_TEXT = {0: "", -2: " dor", -4: " phr", 1: " lyd", -1: " mix", -3: "m", -5: " loc"}
ACCIDENTALS = {"__": -2, "_": -1, "=": 0, "^": 1, "^^": 2}
ACCIDENTAL_TEXT = {v: k for k, v in ACCIDENTALS.items()}

_LEN = r"\d*(?:/+\d*)?"
FIELD_RE = re.compile(r"^([A-Za-z]):(.*)$")
KEY_RE = re.compile(r"^\s*([A-G])([#b]?)\s*((?i:(?:maj|min|ion|dor|phr|lyd|mix|aeo|loc)[a-z]*|m(?![a-z])))?")
CHORD_RE = re.compile(r"^([A-G])(##|bb|#|b)?(.*?)(?:/([A-G])(##|bb|#|b)?)?$")
METER_RE = re.compile(r"^(C\|?|none|\d+(?:\+\d+)*/\d+)$")
UNIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
TOKEN_RE = re.compile(
    rf"""
    (?P<comment>%.*)
    |(?P<symbol>"[^"]*")
    |(?P<deco>![^!]*!|\+[^+\s]*\+)
    |(?P<field>\[[A-Za-z]:[^\]]*\])
    |(?P<bar>\[\||\[\d|:*\|[|\]]*:*\d*|::+)
    |(?P<tuplet>\(\d+(?::\d*){{0,2}})
    |(?P<note>(?P<acc>\^\^|\^|__|_|=)?(?P<letter>[A-Ga-g])(?P<octave>[',]*)(?P<len>{_LEN}))
    |(?P<rest>[zx])(?P<rlen>{_LEN})
    |(?P<mrest>[ZX])(?P<mcount>\d*)
    |(?P<chord_open>\[)
    |(?P<chord_close>\])(?P<clen>{_LEN})
    |(?P<grace_open>\{{)
    |(?P<grace_close>\}})
    |(?P<broken>[<>]+)
    """,
    re.X,
)


@dataclass(frozen=True)
class Key:
    letter: str
    alter: int
    mode_fifths: int = 0

    @property
    def fifths(self) -> int:
        return LETTER_FIFTHS[self.letter] + 7 * self.alter + self.mode_fifths

    @property
    def pitch_class(self) -> int:
        return (NATURAL[self.letter] + self.alter) % 12

    @property
    def tonic(self) -> str:
        return self.letter + ("#" * self.alter if self.alter > 0 else "b" * -self.alter)


C_MAJOR = Key("C", 0)


@dataclass(frozen=True)
class Interval:
    steps: int  # letter (diatonic) steps
    semitones: int


@lru_cache
def signature(key: Key | None) -> dict[str, int]:
    """Accidental applied to each letter by the key signature."""
    sig = dict.fromkeys(LETTERS, 0)
    fifths = key.fifths if key else 0
    for i in range(abs(fifths)):
        if fifths > 0:
            sig[SHARP_ORDER[i % 7]] += 1
        else:
            sig[SHARP_ORDER[6 - i % 7]] -= 1
    return sig


def parse_key(text: str) -> tuple[Key, re.Match] | None:
    """Parse the tonic and mode at the start of a K: value. None for K:none, K:HP, etc."""
    m = KEY_RE.match(text)
    if not m:
        return None
    mode = (m.group(3) or "maj").lower()
    mode_fifths = MODE_FIFTHS["m" if mode == "m" else mode[:3]]
    return Key(m.group(1), {"#": 1, "b": -1}.get(m.group(2), 0), mode_fifths), m


def spell_key(pitch_class: int, mode_fifths: int) -> Key:
    """The spelling of a tonic with the fewest accidentals in its key signature (flats on ties)."""
    candidates = []
    for letter in LETTERS:
        alter = (pitch_class - NATURAL[letter] + 6) % 12 - 6
        if abs(alter) <= 1:
            key = Key(letter, alter, mode_fifths)
            candidates.append((abs(key.fifths), key.fifths > 0, key))
    return min(candidates, key=lambda c: c[:2])[2]


def playable(key: Key) -> Key:
    return key if abs(key.fifths) <= 7 else spell_key(key.pitch_class, key.mode_fifths)


def interval_to(src: Key, dst_letter: str, semitones: int) -> Interval:
    d = (LETTERS.index(dst_letter) - LETTERS.index(src.letter)) % 7
    return Interval(d + 7 * round((semitones * 7 / 12 - d) / 7), semitones)


def transpose(letter: str, octave: int, alter: int, iv: Interval, simple: bool = False) -> tuple[str, int, int]:
    """Transpose a pitch by an interval, keeping diatonic spelling where possible.

    simple: prefer the spelling with the fewest accidentals (for chord symbols).
    """
    max_alter = 1 if simple else 2
    midi = octave * 12 + NATURAL[letter] + alter + iv.semitones
    dia = octave * 7 + LETTERS.index(letter) + iv.steps
    options = []
    for shift in (0, -1, 1, -2, 2):
        d = dia + shift
        a = midi - (d // 7 * 12 + NATURAL[LETTERS[d % 7]])
        if abs(a) <= max_alter:
            rank = (abs(a), shift != 0) if simple else (shift != 0, abs(a))
            options.append((*rank, LETTERS[d % 7], d // 7, a))
    return min(options)[2:]


def transpose_key(key: Key, iv: Interval) -> Key:
    letter, _, alter = transpose(key.letter, 0, key.alter, iv)
    return playable(Key(letter, alter, key.mode_fifths))


def parse_length(text: str) -> Fraction:
    m = re.fullmatch(r"(\d*)(/*)(\d*)", text)
    num = int(m.group(1) or 1)
    slashes = len(m.group(2))
    if not slashes:
        return Fraction(num)
    return Fraction(num, int(m.group(3)) if m.group(3) else 2**slashes)


def format_length(value: Fraction) -> str:
    n, d = value.numerator, value.denominator
    if d == 1:
        return "" if n == 1 else str(n)
    return ("" if n == 1 else str(n)) + ("/" if d == 2 else f"/{d}")


def parse_unit(text: str) -> Fraction:
    m = UNIT_RE.match(text)
    if not m or int(m.group(1)) == 0 or int(m.group(2)) == 0:
        raise ValueError(f"Invalid note length {text!r}, expected e.g. 1/8")
    return Fraction(int(m.group(1)), int(m.group(2)))


def default_unit(meter: str | None) -> Fraction:
    """ABC's default L: when the tune has none: 1/16 if the meter is below 3/4, else 1/8."""
    length = meter_length(meter)
    return Fraction(1, 16) if length is not None and length < Fraction(3, 4) else Fraction(1, 8)


def meter_length(meter: str | None) -> Fraction | None:
    """Length of one bar as a fraction of a whole note. None for free meter (M:none)."""
    meter = {"C": "4/4", "C|": "2/2"}.get((meter or "").strip(), (meter or "").strip())
    m = re.match(r"^([\d+]+)\s*/\s*(\d+)$", meter)
    if not m:
        return None
    return Fraction(sum(int(n) for n in m.group(1).split("+") if n), int(m.group(2)))
