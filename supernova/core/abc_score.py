"""Edit ABC notation scores: tempo, unit note length, key (transposition) and meter.

Only the parts that change are rewritten; everything else is copied verbatim.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache

logger = logging.getLogger(__name__)

LETTERS = "CDEFGAB"
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTER_FIFTHS = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
SHARP_ORDER = "FCGDAEB"
# Mode -> offset in the circle of fifths relative to major, keyed by the first 3 letters of the mode name.
MODE_FIFTHS = {"maj": 0, "ion": 0, "mix": -1, "dor": -2, "min": -3, "aeo": -3, "m": -3, "phr": -4, "loc": -5, "lyd": 1}
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


@dataclass
class _Voice:
    src_key: Key | None
    out_key: Key | None
    unit: Fraction


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


def _playable(key: Key) -> Key:
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
    return _playable(Key(letter, alter, key.mode_fifths))


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
    meter = (meter or "").strip()
    meter = {"C": "4/4", "C|": "2/2"}.get(meter, meter)
    m = re.match(r"^([\d+]+)\s*/\s*(\d+)", meter)
    if not m:
        return Fraction(1, 8)
    value = Fraction(sum(int(n) for n in m.group(1).split("+") if n), int(m.group(2)))
    return Fraction(1, 16) if value < Fraction(3, 4) else Fraction(1, 8)


def _set_tempo(value: str, bpm: int) -> str:
    if re.search(r"=\s*\d+", value):
        return re.sub(r"(=\s*)\d+", rf"\g<1>{bpm}", value, count=1)
    if re.fullmatch(r"\s*\d+\s*", value):
        return str(bpm)
    return f"{value.strip()} 1/4={bpm}".strip()


class _Editor:
    def __init__(self, tempo: int, unit: Fraction | None, keyscale: str, offset: int, meter: str):
        self.tempo = tempo
        self.tgt_unit = unit
        self.offset = offset
        self.meter = meter
        self.target: tuple[Key, bool] | None = None
        if keyscale:
            parsed = parse_key(keyscale[0].upper() + keyscale[1:])
            if not parsed:
                raise ValueError(f"Invalid keyscale {keyscale!r}, expected e.g. C, Am, F#")
            self.target = (parsed[0], parsed[1].group(3) is not None)
        self._reset_tune()

    def _reset_tune(self):
        self.in_header = True
        self.seen: set[str] = set()
        self.orig_meter: str | None = None
        self.header_unit: Fraction | None = None
        self.iv: Interval | None = None
        self.default = _Voice(None, None, Fraction(1, 8))
        self.voices: dict[str, _Voice] = {}
        self.voice_id: str | None = None
        self._reset_bar()

    def _reset_bar(self):
        self.src_bar: dict[tuple[str, int], int] = {}
        self.out_bar: dict[tuple[str, int], int] = {}

    def _voice(self) -> _Voice:
        if self.voice_id is None:
            return self.default
        return self.voices.setdefault(self.voice_id, replace(self.default))

    def run(self, text: str) -> str:
        out: list[str] = []
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            out.extend(self._line(content, line[len(content) :] or "\n"))
        if out and not text.endswith(("\n", "\r")):
            out[-1] = out[-1].rstrip("\r\n")
        return "".join(out)

    def _line(self, content: str, nl: str) -> list[str]:
        field = FIELD_RE.match(content)
        if field and field.group(1) == "X":
            self._reset_tune()
            return [content + nl]
        if content.lstrip().startswith("%"):
            return [content + nl]
        if self.in_header:
            if field:
                return self._header_field(field.group(1), field.group(2), nl)
            if not content.strip():
                return [content + nl]
            return self._end_header(nl) + [self._music(content) + nl]
        if field:
            return [self._body_field(field.group(1), field.group(2)) + nl]
        return [self._music(content) + nl]

    # --- fields ---

    def _header_field(self, name: str, value: str, nl: str) -> list[str]:
        self.seen.add(name)
        if name == "M":
            self.orig_meter = value
            if self.meter:
                value = self.meter
        elif name == "L":
            self.header_unit = parse_unit(value)
            if self.tgt_unit:
                value = str(self.tgt_unit)
        elif name == "Q" and self.tempo:
            value = _set_tempo(value, self.tempo)
        elif name == "K":
            return self._end_header(nl) + ["K:" + self._key(value, header=True) + nl]
        return [f"{name}:{value}{nl}"]

    def _end_header(self, nl: str) -> list[str]:
        self.in_header = False
        added = []
        if self.meter and "M" not in self.seen:
            added.append(f"M:{self.meter}{nl}")
        unit = self.header_unit or default_unit(self.orig_meter)
        if "L" not in self.seen and (self.tgt_unit or self.meter):
            # Changing M: can change the implicit L:, so pin it to keep the rhythm.
            added.append(f"L:{self.tgt_unit or unit}{nl}")
        if self.tempo and "Q" not in self.seen:
            added.append(f"Q:1/4={self.tempo}{nl}")
        self.default.unit = unit
        if "K" not in self.seen:
            self._plan(None)
        return added

    def _body_field(self, name: str, value: str) -> str:
        if name == "K":
            return "K:" + self._key(value, header=False)
        if name == "L":
            self._voice().unit = parse_unit(value)
            return f"L:{self.tgt_unit}" if self.tgt_unit else f"L:{value}"
        if name == "V":
            self.voice_id = value.split()[0] if value.split() else None
            self._reset_bar()
        return f"{name}:{value}"

    def _plan(self, src: Key | None):
        """Work out the transposition from the tune's first key."""
        base = src or C_MAJOR
        dst, semitones = base, 0
        if self.target:
            target, mode_given = self.target
            if mode_given and target.mode_fifths != base.mode_fifths:
                logger.warning("keyscale %s: mode ignored, keeping the score's mode", target.tonic)
            dst = _playable(Key(target.letter, target.alter, base.mode_fifths))
            semitones = (dst.pitch_class - base.pitch_class + 5) % 12 - 5
        if self.offset:
            semitones += self.offset
            dst = spell_key((dst.pitch_class + self.offset) % 12, base.mode_fifths)
        if self.target or self.offset:
            self.iv = interval_to(base, dst.letter, semitones)
        out = dst if (src or self.target) else None
        self.default.src_key, self.default.out_key = src, out if self.iv else src

    def _key(self, value: str, header: bool) -> str:
        parsed = parse_key(value)
        src = parsed[0] if parsed else None
        if header:
            self._plan(src)
            out = self.default.out_key
        else:
            voice = self._voice()
            out = transpose_key(src, self.iv) if (src and self.iv) else src
            voice.src_key, voice.out_key = src, out
            self._reset_bar()
        if not self.iv or out is None:
            return value
        if parsed is None:  # K:none etc. with an explicit keyscale
            return out.tonic
        m = parsed[1]
        return value[: m.start(1)] + out.tonic + value[m.end(2) :]

    # --- music ---

    def _music(self, text: str) -> str:
        out = []
        pos = 0
        while pos < len(text):
            m = TOKEN_RE.match(text, pos)
            if not m:
                out.append(text[pos])
                pos += 1
                continue
            pos = m.end()
            if m.group("note"):
                out.append(self._note(m))
            elif m.group("rest"):
                out.append(m.group("rest") + self._length(m.group("rlen")))
            elif m.group("symbol"):
                out.append(self._chord_symbol(m.group("symbol")))
            elif m.group("field"):
                name, value = m.group("field")[1], m.group("field")[3:-1]
                out.append("[" + self._body_field(name, value) + "]")
            elif m.group("bar"):
                self._reset_bar()
                out.append(m.group("bar"))
            else:
                out.append(m.group(0))
        return "".join(out)

    def _length(self, text: str) -> str:
        if not self.tgt_unit or self._voice().unit == self.tgt_unit:
            return text
        return format_length(parse_length(text) * self._voice().unit / self.tgt_unit)

    def _note(self, m: re.Match) -> str:
        acc, letter, marks = m.group("acc") or "", m.group("letter"), m.group("octave")
        pitch = acc + letter + marks
        if self.iv:
            voice = self._voice()
            upper = letter.upper()
            octave = letter.islower() + marks.count("'") - marks.count(",")
            if acc:
                alter = self.src_bar[(upper, octave)] = ACCIDENTALS[acc]
            else:
                alter = self.src_bar.get((upper, octave), signature(voice.src_key)[upper])
            new, new_octave, new_alter = transpose(upper, octave, alter, self.iv)
            expected = self.out_bar.get((new, new_octave), signature(voice.out_key)[new])
            new_acc = ""
            if new_alter != expected:
                new_acc = ACCIDENTAL_TEXT[new_alter]
                self.out_bar[(new, new_octave)] = new_alter
            if new_octave >= 1:
                pitch = new_acc + new.lower() + "'" * (new_octave - 1)
            else:
                pitch = new_acc + new + "," * -new_octave
        return pitch + self._length(m.group("len"))

    def _chord_symbol(self, symbol: str) -> str:
        m = CHORD_RE.match(symbol[1:-1])
        if not self.iv or not m:
            return symbol

        def move(letter: str, acc: str | None) -> str:
            alter = {"#": 1, "##": 2, "b": -1, "bb": -2}.get(acc or "", 0)
            new, _, new_alter = transpose(letter, 0, alter, self.iv, simple=True)
            return Key(new, new_alter).tonic

        text = move(m.group(1), m.group(2)) + m.group(3)
        if m.group(4):
            text += "/" + move(m.group(4), m.group(5))
        return f'"{text}"'


def edit_abc_score(
    abc_score: str,
    tempo: int = 0,
    default_note_length: str = "",
    keyscale: str = "",
    semitone_offset: int = 0,
    time_signature: str = "",
) -> str:
    """Edit an ABC score. Empty / 0 arguments leave that aspect unchanged.

    - tempo: bpm for the header Q: field (beat unit kept, 1/4 if absent).
    - default_note_length: new L:; note durations are rescaled so the rhythm is unchanged.
    - keyscale: new tonic; the score's mode is kept and all notes and chord symbols are
      transposed by the nearest interval (-5..+6 semitones).
    - semitone_offset: extra transposition applied after keyscale.
    - time_signature: new header M:. Bar lines are not changed.
    """
    keyscale = keyscale.strip()
    default_note_length = default_note_length.strip()
    time_signature = time_signature.strip()
    if tempo < 0:
        raise ValueError(f"Invalid tempo {tempo}, expected a positive bpm")
    if time_signature and not METER_RE.match(time_signature):
        raise ValueError(f"Invalid time signature {time_signature!r}, expected e.g. 4/4, 6/8, C")
    unit = parse_unit(default_note_length) if default_note_length else None
    if not (tempo or unit or keyscale or semitone_offset or time_signature):
        return abc_score
    return _Editor(tempo, unit, keyscale, semitone_offset, time_signature).run(abc_score)
