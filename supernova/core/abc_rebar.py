"""Move bar lines when the new bar length is a whole multiple or divisor of the old one (e.g. 2/4 <-> 4/4).

Bars are merged or split; notes are never split. Anything that can't be re-barred cleanly
(a note or tuplet crossing a new bar line, repeat signs mid-bar, lyrics, meter changes...)
raises RebarError and the caller keeps the old bar lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from fractions import Fraction

from .abc_notation import (
    ACCIDENTAL_TEXT,
    ACCIDENTALS,
    FIELD_RE,
    TOKEN_RE,
    default_unit,
    format_length,
    meter_length,
    parse_key,
    parse_length,
    parse_unit,
    signature,
)

logger = logging.getLogger(__name__)

# Default tuplet q for (p, in simple meter. 5, 7 and 9 use 3 in compound meter.
TUPLET_Q = {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}


class RebarError(Exception):
    """The tune can't be re-barred without splitting notes or moving repeats."""


@dataclass
class _El:
    kind: str  # text, bar, note, rest, mrest, chord
    text: str = ""
    voice: str | None = None
    start: Fraction = Fraction(0)
    dur: Fraction = Fraction(0)
    breakable: bool = True  # a bar line may follow this element
    line_end: bool = False  # bars: last thing on the line
    # notes
    acc: str = ""
    pitch: str = ""
    length: str = ""
    pos: tuple[str, int] = ("C", 0)
    alter: int = 0
    sig: dict[str, int] = field(default_factory=dict)
    # chords / multi-bar rests
    children: list[_El] = field(default_factory=list)
    unit: Fraction = Fraction(1, 8)


@dataclass
class _State:
    unit: Fraction
    sig: dict[str, int]
    t: Fraction = Fraction(0)
    first_bar: Fraction | None = None
    src_bar: dict[tuple[str, int], int] = field(default_factory=dict)
    tuplet_left: int = 0
    tuplet_ratio: Fraction = Fraction(1)
    broken_next: Fraction = Fraction(1)
    last: _El | None = None


def rebar(lines: list[str], old_meter: str | None, new_meter: str) -> list[str]:
    """Re-bar one tune (lines with line endings). Returns the lines unchanged when not possible."""
    old, new = meter_length(old_meter), meter_length(new_meter)
    if not old or not new or old == new:
        return lines
    ratio = new / old
    if ratio.numerator != 1 and ratio.denominator != 1:
        logger.warning(
            "time_signature %s -> %s: bars can't be regrouped, only the header changed", old_meter, new_meter
        )
        return lines
    numerator = int(old_meter.split("/")[0]) if old_meter and old_meter.split("/")[0].isdigit() else 0
    try:
        return _Rebar(old, new, compound=numerator > 3 and numerator % 3 == 0, meter=old_meter).run(lines)
    except (RebarError, ValueError) as e:
        logger.warning("time_signature: header changed but bars kept, %s", e)
        return lines


class _Rebar:
    def __init__(self, old: Fraction, new: Fraction, compound: bool, meter: str | None):
        self.old, self.new, self.compound = old, new, compound
        self.unit = default_unit(meter)
        self.sig = signature(None)
        self.states: dict[str | None, _State] = {}
        self.voice: str | None = None
        self.out_bars: dict[str | None, dict[tuple[str, int], int]] = {}

    def _state(self) -> _State:
        if self.voice not in self.states:
            self.states[self.voice] = _State(self.unit, self.sig)
        return self.states[self.voice]

    # --- parse ---

    def run(self, lines: list[str]) -> list[str]:
        parsed: list[tuple[str, list[_El] | None, str]] = []
        in_header = True
        for line in lines:
            content = line.rstrip("\r\n")
            nl = line[len(content) :]
            m = FIELD_RE.match(content)
            if content.lstrip().startswith("%") or not content.strip():
                parsed.append((line, None, nl))
                continue
            if in_header and m:
                name, value = m.group(1), m.group(2)
                if name == "L":
                    self.unit = parse_unit(value)
                elif name == "K":
                    parsed_key = parse_key(value)
                    self.sig = signature(parsed_key[0] if parsed_key else None)
                    in_header = False
                parsed.append((line, None, nl))
                continue
            in_header = False
            if m:
                self._field(m.group(1), m.group(2))
                parsed.append((line, None, nl))
                continue
            parsed.append((content, self._parse(content), nl))

        self.pickups = {
            v: (s.first_bar if s.first_bar is not None and s.first_bar < self.old else Fraction(0))
            for v, s in self.states.items()
        }
        return [line if els is None else self._emit(els) + nl for line, els, nl in parsed]

    def _field(self, name: str, value: str):
        if name == "V":
            self.voice = value.split()[0] if value.split() else None
        elif name == "K":
            parsed_key = parse_key(value)
            state = self._state()
            state.sig = signature(parsed_key[0] if parsed_key else None)
            state.src_bar = {}
        elif name == "L":
            self._state().unit = parse_unit(value)
        elif name == "M":
            raise RebarError("the tune changes meter")
        elif name == "w":
            raise RebarError("lyrics are aligned to the bars")

    def _parse(self, content: str) -> list[_El]:
        els: list[_El] = []
        chord: _El | None = None
        chord_len: Fraction | None = None
        grace = False
        pos = 0
        while pos < len(content):
            m = TOKEN_RE.match(content, pos)
            state = self._state()
            if not m:
                el = _El("text", content[pos])
                pos += 1
            else:
                pos = m.end()
                el = self._token(m, state, grace or chord is not None)
                if m.group("chord_open"):
                    chord, chord_len = _El("chord", voice=self.voice), None
                    continue
                if m.group("chord_close") and chord is not None:
                    chord.length = m.group("clen")
                    chord.dur = (chord_len or 1) * parse_length(chord.length) * state.unit
                    self._timed(chord, state)
                    el, chord = chord, None
                elif chord is not None:
                    if el.kind == "note" and chord_len is None:
                        chord_len = parse_length(el.length)
                    chord.children.append(el)
                    continue
                grace = (grace or bool(m.group("grace_open"))) and not m.group("grace_close")
            el.voice = el.voice if el.kind == "chord" else self.voice
            els.append(el)
        if chord is not None:
            raise RebarError("a chord spans lines")
        for el in reversed(els):
            if el.kind == "bar":
                el.line_end = True
            if el.kind != "text" or not (el.text.isspace() or el.text.startswith("%")):
                break
        return els

    def _token(self, m, state: _State, zero: bool) -> _El:
        if m.group("note"):
            acc, letter, marks = m.group("acc") or "", m.group("letter"), m.group("octave")
            key = (letter.upper(), letter.islower() + marks.count("'") - marks.count(","))
            if acc:
                alter = state.src_bar[key] = ACCIDENTALS[acc]
            else:
                alter = state.src_bar.get(key, state.sig[key[0]])
            el = _El("note", acc=acc, pitch=letter + marks, length=m.group("len"), pos=key, alter=alter, sig=state.sig)
            if not zero:
                el.dur = parse_length(el.length) * state.unit
                self._timed(el, state)
            return el
        if m.group("rest") and not zero:
            el = _El("rest", m.group(0), dur=parse_length(m.group("rlen")) * state.unit, unit=state.unit)
            self._timed(el, state)
            return el
        if m.group("mrest"):
            el = _El("mrest", m.group(0), dur=int(m.group("mcount") or 1) * self.old, unit=state.unit)
            self._timed(el, state)
            return el
        if m.group("bar"):
            if state.tuplet_left:
                raise RebarError("a tuplet crosses a bar line")
            if state.first_bar is None and state.t > 0:
                state.first_bar = state.t
            state.src_bar, state.last, state.broken_next = {}, None, Fraction(1)
            return _El("bar", m.group(0), start=state.t)
        if m.group("tuplet"):
            parts = m.group(0)[1:].split(":") + ["", ""]
            p = int(parts[0])
            q = int(parts[1]) if parts[1] else TUPLET_Q.get(p, 3 if self.compound else 2)
            state.tuplet_left = int(parts[2]) if parts[2] else p
            state.tuplet_ratio = Fraction(q, p)
        elif m.group("broken"):
            self._broken(m.group(0), state)
        elif m.group("field"):
            name, value = m.group(0)[1], m.group(0)[3:-1]
            self._field(name, value)
        return _El("text", m.group(0))

    def _timed(self, el: _El, state: _State):
        el.dur *= state.broken_next
        state.broken_next = Fraction(1)
        if state.tuplet_left:
            el.dur *= state.tuplet_ratio
            state.tuplet_left -= 1
            el.breakable = state.tuplet_left == 0
        el.start = state.t
        state.t += el.dur
        state.last = el

    def _broken(self, text: str, state: _State):
        if state.last is None:
            raise RebarError("broken rhythm without a note before it")
        short = Fraction(1, 2 ** len(text))
        first, second = (2 - short, short) if text[0] == ">" else (short, 2 - short)
        delta = state.last.dur * (first - 1)
        state.last.dur += delta
        state.last.breakable = False
        state.t += delta
        state.broken_next = second

    # --- emit ---

    def _next_boundary(self, voice: str | None, t: Fraction) -> Fraction:
        """First new bar line at or after t."""
        return t + (self.pickups.get(voice, Fraction(0)) - t) % self.new

    def _is_boundary(self, voice: str | None, t: Fraction) -> bool:
        return self._next_boundary(voice, t) == t

    def _emit(self, els: list[_El]) -> str:
        out: list[str] = []
        pending: int | None = None  # where a new bar line goes, if the next element needs one
        pending_voice: str | None = None
        for el in els:
            if pending is not None:
                if el.kind == "text" and el.text in ("-", ")"):
                    out.append(el.text)
                    pending = len(out)
                    continue
                if el.kind == "text" and el.text.isspace():
                    out.append(el.text)
                    continue
                if el.kind != "bar":
                    out.insert(pending, "|")
                    self.out_bars[pending_voice] = {}
                pending = None
            if el.kind == "bar":
                if el.start == 0 or self._is_boundary(el.voice, el.start):
                    out.append(el.text)
                    self.out_bars[el.voice] = {}
                elif el.text != "|":
                    raise RebarError(f"'{el.text}' would fall mid-bar")
                elif el.line_end:
                    raise RebarError("a merged bar would span two lines")
                continue
            if el.kind in ("rest", "mrest"):
                out.append(self._rest(el))
            elif el.kind == "note":
                out.append(self._note(el))
            elif el.kind == "chord":
                inner = "".join(self._note(c) if c.kind == "note" else c.text for c in el.children)
                out.append(f"[{inner}]{el.length}")
            else:
                out.append(el.text)
            if el.dur:
                end = el.start + el.dur
                boundary = self._next_boundary(el.voice, el.start)
                if boundary == el.start:
                    boundary += self.new
                if boundary < end and el.kind not in ("rest", "mrest"):
                    raise RebarError("a note would cross a new bar line")
                if boundary < end and not el.breakable:
                    raise RebarError("a tuplet or broken rhythm would cross a new bar line")
                if self._is_boundary(el.voice, end):
                    if not el.breakable:
                        raise RebarError("a tuplet or broken rhythm would cross a new bar line")
                    pending, pending_voice = len(out), el.voice
        if pending is not None:
            out.insert(pending, "|")
        return "".join(out)

    def _note(self, el: _El) -> str:
        bar = self.out_bars.setdefault(el.voice, {})
        acc = el.acc
        if not acc and bar.get(el.pos, el.sig[el.pos[0]]) != el.alter:
            acc = ACCIDENTAL_TEXT[el.alter]
        if acc:
            bar[el.pos] = el.alter
        return acc + el.pitch + el.length

    def _rest(self, el: _El) -> str:
        """Split a rest at new bar lines. For Z / X, whole new bars stay Z / X, partial bars become z / x."""
        whole = el.kind == "mrest"
        short = el.text[0].lower()
        t, end = el.start, el.start + el.dur
        pieces: list[str] = []
        while t < end:
            boundary = self._next_boundary(el.voice, t)
            step = min(boundary if boundary > t else boundary + self.new, end) - t
            if whole and step == self.new:
                count = int(pieces.pop()[1:] or 1) + 1 if pieces and pieces[-1][0] == el.text[0] else 1
                pieces.append(el.text[0] + (str(count) if count > 1 else ""))
            else:
                pieces.append(short + format_length(step / el.unit))
            t += step
        if len(pieces) == 1 and not whole:
            return el.text
        return "|".join(pieces)
