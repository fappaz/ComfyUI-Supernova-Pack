"""Restyle chord symbols ("Cm7", "Bb/D"...): triads, diatonic sevenths/ninths, sus, power chords."""

from __future__ import annotations

import re

from .abc_notation import CHORD_RE, LETTERS, NATURAL, Key

CHORD_STYLES = ("keep", "triads", "sevenths", "ninths", "sixths", "sus2", "sus4", "power", "no_bass", "remove")

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
# Mode (as circle-of-fifths offset from major) -> scale degree of the parent major scale.
MODE_DEGREE = {0: 0, -2: 1, -4: 2, 1: 3, -1: 4, -3: 5, -5: 6}
TRIADS = {(4, 7): "maj", (3, 7): "min", (3, 6): "dim", (4, 8): "aug"}
TRIAD_SUFFIX = {"maj": "", "min": "m", "dim": "dim", "aug": "aug"}
SEVENTHS = {("maj", 11): "maj7", ("maj", 10): "7", ("min", 10): "m7", ("min", 11): "mMaj7", ("dim", 10): "m7b5"}
SEVENTHS.update({("dim", 9): "dim7", ("aug", 11): "maj7#5", ("aug", 10): "7#5"})
NINTHS = {"maj7": "maj9", "7": "9", "m7": "m9"}
ACCIDENTALS = {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}


def scale(key: Key | None) -> list[int]:
    """Pitch classes of the key's scale, starting from the tonic. No key means C major."""
    if key is None:
        return list(MAJOR_SCALE)
    degree = MODE_DEGREE[key.mode_fifths]
    parent = key.pitch_class - MAJOR_SCALE[degree]
    return [(parent + MAJOR_SCALE[(degree + i) % 7]) % 12 for i in range(7)]


def diatonic_chord(root: int, key: Key | None) -> tuple[str, str, str] | None:
    """(triad quality, seventh suffix, ninth suffix) built from the key's scale on a root pitch class."""
    notes = scale(key)
    if root not in notes:
        return None
    i = notes.index(root)

    def above(steps: int) -> int:
        return (notes[(i + steps) % 7] - root) % 12

    triad = TRIADS[(above(2), above(4))]
    seventh = SEVENTHS[(triad, above(6))]
    # Only add a 9th when it's a major 9th; b9 chords (e.g. Em7b9 in C) sound clashy.
    ninth = NINTHS.get(seventh, seventh) if above(1) == 2 else seventh
    return triad, seventh, ninth


def triad_quality(suffix: str) -> str | None:
    """Triad quality of a chord suffix ("m7" -> min). None for sus, power or unknown chords."""
    s = suffix.strip()
    if re.match(r"^(m7?(b5|-5)|ø)", s):
        return "dim"
    if re.match(r"^(maj|M|Δ)", s):
        return "maj"
    if re.match(r"^(dim|°|o)", s):
        return "dim"
    if re.match(r"^(min|m|-)", s):
        return "min"
    if re.match(r"^(aug|\+)", s) or "#5" in s:
        return "aug"
    if s == "" or re.match(r"^(\d|add)", s) and s != "5":
        return "maj"
    return None


def degree_spelling(pitch_class: int, old_key: Key | None, new_key: Key | None) -> tuple[str, int] | None:
    """The same scale degree in another key, spelled from that key: Ab in C minor -> A in C major.
    None when the pitch isn't in old_key's scale."""
    old = scale(old_key)
    if pitch_class not in old:
        return None
    degree = old.index(pitch_class)
    letter = LETTERS[(LETTERS.index(new_key.letter if new_key else "C") + degree) % 7]
    return letter, (scale(new_key)[degree] - NATURAL[letter] + 6) % 12 - 6


TRIAD_FORMS = {"maj": ("", "maj", "M"), "min": ("m", "min", "-"), "dim": ("dim", "°", "o"), "aug": ("aug", "+")}


def remap_quality(suffix: str, old_root: int, new_root: int, old_key: Key | None, new_key: Key | None) -> str:
    """Chord suffix after a mode change: diatonic chords take the new key's quality (Fm in C minor -> F
    in C major), at the same extension (triad, 7th or 9th). Other chords keep their suffix.
    """
    quality = triad_quality(suffix)
    old = diatonic_chord(old_root, old_key)
    new = diatonic_chord(new_root, new_key)
    if quality is None or old is None or new is None or old[0] != quality:
        return suffix
    if suffix == old[1]:
        return new[1]
    if suffix == old[2]:
        return new[2]
    if suffix in TRIAD_FORMS[quality]:
        return TRIAD_SUFFIX[new[0]]
    return suffix


def style_chord(text: str, key: Key | None, style: str) -> str | None:
    """Restyle one chord symbol (without quotes). None means remove it.

    Annotations ("^text") and chords that can't be restyled are returned unchanged.
    """
    if style == "keep" or text[:1] in "^_<>@":
        return text
    if style == "remove":
        return None
    m = CHORD_RE.match(text)
    if not m:
        return text
    head = m.group(1) + (m.group(2) or "")
    suffix = m.group(3)
    bass = f"/{m.group(4)}{m.group(5) or ''}" if m.group(4) else ""
    if style == "no_bass":
        return head + suffix
    if style == "power":
        return head + "5"
    if style in ("sus2", "sus4"):
        return head + style + bass
    quality = triad_quality(suffix)
    if quality is None:
        return text
    if style == "triads":
        return head + TRIAD_SUFFIX[quality] + bass
    if style == "sixths":
        return head + {"maj": "6", "min": "m6"}[quality] + bass if quality in ("maj", "min") else text
    chord = diatonic_chord((NATURAL[m.group(1)] + ACCIDENTALS[m.group(2) or ""]) % 12, key)
    if chord is None or chord[0] != quality:
        return text  # borrowed / chromatic chord: leave it alone
    return head + (chord[1] if style == "sevenths" else chord[2]) + bass
