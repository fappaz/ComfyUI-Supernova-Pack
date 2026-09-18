"""Edit ABC notation scores: tempo, unit note length, key (transposition) and meter.

Only the parts that change are rewritten; everything else is copied verbatim.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from fractions import Fraction

from .abc_chords import CHORD_STYLES, style_chord
from .abc_notation import (
    ACCIDENTAL_TEXT,
    ACCIDENTALS,
    C_MAJOR,
    CHORD_RE,
    FIELD_RE,
    METER_RE,
    TOKEN_RE,
    Interval,
    Key,
    default_unit,
    format_length,
    interval_to,
    parse_key,
    parse_length,
    parse_unit,
    playable,
    signature,
    spell_key,
    transpose,
    transpose_key,
)
from .abc_rebar import rebar

logger = logging.getLogger(__name__)


@dataclass
class _Voice:
    src_key: Key | None
    out_key: Key | None
    unit: Fraction


def _set_tempo(value: str, bpm: int) -> str:
    if re.search(r"=\s*\d+", value):
        return re.sub(r"(=\s*)\d+", rf"\g<1>{bpm}", value, count=1)
    if re.fullmatch(r"\s*\d+\s*", value):
        return str(bpm)
    return f"{value.strip()} 1/4={bpm}".strip()


class _Editor:
    def __init__(self, tempo: int, unit: Fraction | None, keyscale: str, offset: int, meter: str, chord_style: str):
        self.tempo = tempo
        self.tgt_unit = unit
        self.offset = offset
        self.meter = meter
        self.chord_style = chord_style
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
        tune: list[str] = []
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            if content.startswith("X:"):
                out.extend(self._finish(tune))
                tune = []
            tune.extend(self._line(content, line[len(content) :] or "\n"))
        out.extend(self._finish(tune))
        if out and not text.endswith(("\n", "\r")):
            out[-1] = out[-1].rstrip("\r\n")
        return "".join(out)

    def _finish(self, tune: list[str]) -> list[str]:
        if self.meter and not self.in_header:
            return rebar(tune, self.orig_meter, self.meter)
        return tune

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
            dst = playable(Key(target.letter, target.alter, base.mode_fifths))
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
        text = symbol[1:-1]
        m = CHORD_RE.match(text)
        if self.iv and m:

            def move(letter: str, acc: str | None) -> str:
                alter = {"#": 1, "##": 2, "b": -1, "bb": -2}.get(acc or "", 0)
                new, _, new_alter = transpose(letter, 0, alter, self.iv, simple=True)
                return Key(new, new_alter).tonic

            text = move(m.group(1), m.group(2)) + m.group(3)
            if m.group(4):
                text += "/" + move(m.group(4), m.group(5))
        styled = style_chord(text, self._voice().out_key, self.chord_style)
        return "" if styled is None else f'"{styled}"'


def edit_abc_score(
    abc_score: str,
    tempo: int = 0,
    default_note_length: str = "",
    keyscale: str = "",
    semitone_offset: int = 0,
    time_signature: str = "",
    chord_style: str = "keep",
) -> str:
    """Edit an ABC score. Empty / 0 arguments leave that aspect unchanged.

    - tempo: bpm for the header Q: field (beat unit kept, 1/4 if absent).
    - default_note_length: new L:; note durations are rescaled so the rhythm is unchanged.
    - keyscale: new tonic; the score's mode is kept and all notes and chord symbols are
      transposed by the nearest interval (-5..+6 semitones).
    - semitone_offset: extra transposition applied after keyscale.
    - time_signature: new header M:. Bars are merged / split when the new bar length is a
      whole multiple or divisor of the old one, otherwise only the header changes.
    - chord_style: restyle chord symbols, one of CHORD_STYLES ("keep" = unchanged).
    """
    keyscale = keyscale.strip()
    default_note_length = default_note_length.strip()
    time_signature = time_signature.strip()
    if tempo < 0:
        raise ValueError(f"Invalid tempo {tempo}, expected a positive bpm")
    if time_signature and not METER_RE.match(time_signature):
        raise ValueError(f"Invalid time signature {time_signature!r}, expected e.g. 4/4, 6/8, C")
    if chord_style not in CHORD_STYLES:
        raise ValueError(f"Invalid chord style {chord_style!r}, expected one of {', '.join(CHORD_STYLES)}")
    unit = parse_unit(default_note_length) if default_note_length else None
    if not (tempo or unit or keyscale or semitone_offset or time_signature or chord_style != "keep"):
        return abc_score
    return _Editor(tempo, unit, keyscale, semitone_offset, time_signature, chord_style).run(abc_score)
