from comfy_api.latest import io, ui

from ..core.abc_chords import CHORD_STYLES
from ..core.abc_notation import MODES
from ..core.abc_score import edit_abc_score_with_warnings


class SupernovaEditABCScore(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SupernovaEditABCScore",
            display_name="Edit ABC Score (Supernova)",
            category="Supernova/music",
            search_aliases=["abc notation", "transpose", "tempo", "key", "mode", "chords", "sheet music"],
            description=(
                "Edits an ABC notation score: tempo, default note length, key, mode, time signature and chord style. "
                "Empty / 0 parameters leave that part unchanged."
            ),
            inputs=[
                io.String.Input("abc_score", force_input=True, tooltip="Score in ABC notation."),
                io.Int.Input(
                    "tempo",
                    default=0,
                    min=0,
                    max=1000,
                    tooltip="Beats per minute, e.g. 80, 140. Sets the header Q: field. 0 = unchanged.",
                ),
                io.String.Input(
                    "default_note_length",
                    default="",
                    tooltip="New L: field, e.g. 1/8, 1/16. Note durations are rewritten so the rhythm "
                    "stays the same. Empty = unchanged.",
                ),
                io.String.Input(
                    "keyscale",
                    default="",
                    tooltip="New key tonic: C, D, Eb, F#, Bb... Transposes all notes and chord symbols to the "
                    "nearest octave (at most 6 semitones). The score keeps its own mode: D on a C minor score "
                    "gives D minor. Mode suffixes (m, min, maj, dor, phr, lyd, mix, aeo, loc) and chord "
                    "suffixes (7, maj7) are accepted but don't change the mode; use the mode input for that. "
                    "Empty = unchanged.",
                ),
                io.Combo.Input(
                    "mode",
                    options=["keep", *MODES],
                    default="keep",
                    tooltip="Change the mode, keeping the tonic. ionian = major, aeolian = natural minor; dorian, "
                    "phrygian, lydian, mixolydian and locrian are in between. Each note keeps its scale degree "
                    "(C minor -> C major turns every Eb, Ab and Bb into E, A and B); notes outside the scale keep "
                    "their pitch. Chords in the key change quality (Fm7 -> Fmaj7). keep = unchanged.",
                ),
                io.Int.Input(
                    "semitone_offset",
                    default=0,
                    min=-48,
                    max=48,
                    tooltip="Raise (+) or lower (-) all notes, chords and the key by this many semitones "
                    "(12 = one octave). Applied after keyscale. 0 = unchanged.",
                ),
                io.String.Input(
                    "time_signature",
                    default="",
                    tooltip="New header M: field, e.g. 4/4, 3/4, 6/8, C. When the new bar is a whole multiple "
                    "or divisor of the old one (2/4 <-> 4/4, 3/8 <-> 6/8), bars are merged or split. Otherwise, "
                    "or if a note would cross a new bar line, only the header changes. Empty = unchanged.",
                ),
                io.Combo.Input(
                    "chord_style",
                    options=list(CHORD_STYLES),
                    default="keep",
                    tooltip="Restyle chord symbols. triads: Cm7 -> Cm. sevenths / ninths: the 7th / 9th that fits "
                    "the key (Cm -> Cm7, Ab -> Abmaj7, G -> G7); chords outside the key are left unchanged. "
                    "sixths: C6 / Cm6. sus2 / sus4: Csus2. power: C5. no_bass: Bb/D -> Bb. remove: delete "
                    "chord symbols.",
                ),
            ],
            outputs=[
                io.String.Output(display_name="abc_score", tooltip="The edited score."),
            ],
        )

    @classmethod
    def execute(
        cls,
        abc_score: str,
        tempo: int,
        default_note_length: str,
        keyscale: str,
        mode: str,
        semitone_offset: int,
        time_signature: str,
        chord_style: str,
    ) -> io.NodeOutput:
        score, warnings = edit_abc_score_with_warnings(
            abc_score,
            tempo=tempo,
            default_note_length=default_note_length,
            keyscale=keyscale,
            mode=mode,
            semitone_offset=semitone_offset,
            time_signature=time_signature,
            chord_style=chord_style,
        )
        # Invalid inputs don't fail the node: they're ignored, logged, and shown on the node.
        return io.NodeOutput(score, ui=ui.PreviewText("\n".join(warnings)) if warnings else None)
