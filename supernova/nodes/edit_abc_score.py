from comfy_api.latest import io

from ..core.abc_score import edit_abc_score


class SupernovaEditABCScore(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SupernovaEditABCScore",
            display_name="Edit ABC Score (Supernova)",
            category="Supernova/music",
            search_aliases=["abc notation", "transpose", "tempo", "key", "sheet music"],
            description=(
                "Edits an ABC notation score: tempo, default note length, key and time signature. "
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
                    tooltip="New key, e.g. C, Am, F#. Transposes all notes and chord symbols to the "
                    "nearest octave. The score's mode (major/minor) is kept. Empty = unchanged.",
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
                    tooltip="New header M: field, e.g. 4/4, 3/4, 6/8. Bar lines are not moved. Empty = unchanged.",
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
        semitone_offset: int,
        time_signature: str,
    ) -> io.NodeOutput:
        return io.NodeOutput(
            edit_abc_score(
                abc_score,
                tempo=tempo,
                default_note_length=default_note_length,
                keyscale=keyscale,
                semitone_offset=semitone_offset,
                time_signature=time_signature,
            )
        )
