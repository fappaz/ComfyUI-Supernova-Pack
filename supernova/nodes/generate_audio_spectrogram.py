import logging
from collections.abc import Callable
from fractions import Fraction

import comfy.model_management
import torch
from comfy_api.latest import InputImpl, Types, io, ui

from ..core.audio_spectrogram import (
    FREQ_SCALES,
    POSITIONS,
    LazyFrames,
    estimate_bytes,
    frame_count,
    iter_spectrogram,
    render_spectrogram,
)
from ..core.node_warnings import run_with_warnings
from ..core.workflow import used_outputs


def _peak_and_smoothing_inputs() -> list:
    return [
        io.Boolean.Input("peak_caps", default=False, tooltip="Show a marker at each bar's recent peak."),
        io.Float.Input(
            "peak_fall",
            default=0.5,
            min=0.05,
            max=5.0,
            step=0.05,
            tooltip="How fast peak markers fall, in full heights per second.",
        ),
        io.Float.Input(
            "smoothing",
            default=0.5,
            min=0.0,
            max=0.99,
            step=0.01,
            tooltip="0 = bars follow the sound exactly (flickery); higher = they rise fast and fall gently.",
        ),
    ]


def _bar_shape_inputs(count: int) -> list:
    return [
        io.Int.Input("bar_count", default=count, min=4, max=512, tooltip="Number of frequency bands (bars)."),
        io.Float.Input(
            "bar_gap", default=0.2, min=0.0, max=0.9, step=0.05, tooltip="Gap between bars, as a fraction of a bar."
        ),
    ]


MODE_OPTIONS = [
    io.DynamicCombo.Option(
        "bars",
        [
            *_bar_shape_inputs(64),
            io.Float.Input(
                "max_height",
                default=0.8,
                min=0.05,
                max=1.0,
                step=0.05,
                tooltip="Tallest bar, as a fraction of the frame.",
            ),
            io.Combo.Input("position", options=list(POSITIONS), default="bottom", tooltip="Where the bars' base sits."),
            io.Float.Input(
                "margin",
                default=0.05,
                min=0.0,
                max=0.45,
                step=0.01,
                tooltip="Empty border, as a fraction of the frame.",
            ),
            io.Boolean.Input("mirror", default=False, tooltip="Bars grow both ways from their base (use with center)."),
            io.Float.Input(
                "reflection",
                default=0.0,
                min=0.0,
                max=1.0,
                step=0.05,
                tooltip="Brightness of a fading reflection under the bars. 0 = off.",
            ),
            *_peak_and_smoothing_inputs(),
        ],
    ),
    io.DynamicCombo.Option(
        "circular",
        [
            *_bar_shape_inputs(96),
            io.Float.Input(
                "radius",
                default=0.4,
                min=0.0,
                max=1.0,
                step=0.05,
                tooltip="Inner circle radius, as a fraction of the frame.",
            ),
            io.Float.Input(
                "max_length",
                default=0.5,
                min=0.05,
                max=1.0,
                step=0.05,
                tooltip="Longest bar, as a fraction of the frame.",
            ),
            io.Float.Input(
                "center_x", default=0.5, min=0.0, max=1.0, step=0.01, tooltip="0 = left edge, 1 = right edge."
            ),
            io.Float.Input(
                "center_y", default=0.5, min=0.0, max=1.0, step=0.01, tooltip="0 = top edge, 1 = bottom edge."
            ),
            io.Boolean.Input("mirror", default=False, tooltip="Bars grow both outwards and inwards."),
            *_peak_and_smoothing_inputs(),
        ],
    ),
    io.DynamicCombo.Option(
        "scrolling",
        [
            io.Float.Input(
                "window_seconds", default=5.0, min=0.5, max=60.0, step=0.5, tooltip="Seconds of sound visible at once."
            ),
            io.Combo.Input("position", options=list(POSITIONS), default="center", tooltip="Where the band sits."),
            io.Float.Input(
                "max_height",
                default=1.0,
                min=0.05,
                max=1.0,
                step=0.05,
                tooltip="Band height, as a fraction of the frame.",
            ),
        ],
    ),
    io.DynamicCombo.Option(
        "static_playhead",
        [
            io.Int.Input("playhead_width", default=2, min=1, max=50, tooltip="Playhead line width, in pixels."),
            io.Boolean.Input("dim_unplayed", default=True, tooltip="Draw the part not played yet darker."),
        ],
    ),
]


logger = logging.getLogger(__name__)
FRAMES, MASK = 0, 1  # output indices


class StreamedVideo(InputImpl.VideoFromComponents):
    """A VIDEO that draws its frames while being saved, a chunk at a time, instead of keeping them
    in RAM. Nodes that ask for the frames themselves (get_components) get them rendered in full."""

    def __init__(self, frames: LazyFrames, audio: dict, frame_rate: Fraction, render: Callable[[], torch.Tensor]):
        super().__init__(Types.VideoComponents(images=frames, audio=audio, frame_rate=frame_rate))
        self._frames, self._audio, self._rate, self._render = frames, audio, frame_rate, render

    def get_components(self) -> Types.VideoComponents:
        images = self._render().unsqueeze(-1).expand(-1, -1, -1, 3)
        return Types.VideoComponents(images=images, audio=self._audio, frame_rate=self._rate)

    def get_dimensions(self) -> tuple[int, int]:
        return self._frames.shape[2], self._frames.shape[1]

    def get_frame_count(self) -> int:
        return self._frames.shape[0]

    def get_duration(self) -> float:
        return float(self._frames.shape[0] / self._rate)

    def get_frame_rate(self) -> Fraction:
        return self._rate


def _show_on_node(node_id: str | None, text: str):
    try:
        from server import PromptServer

        PromptServer.instance.send_progress_text(text, node_id)
    except Exception:
        pass  # not running inside the ComfyUI server


class SupernovaGenerateAudioSpectrogram(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SupernovaGenerateAudioSpectrogram",
            display_name="Generate Audio Spectrogram (Supernova)",
            category="Supernova/audio",
            search_aliases=["spectrogram", "audio visualizer", "equalizer", "spectrum", "music video"],
            description=(
                "Renders audio as a black & white visualizer video (bars, circle, scrolling or static spectrogram). "
                "Outputs frames, a mask to paint or composite with, and a video with the original audio. "
                "frames/mask are kept in RAM (see max_memory_gb); if only video is connected, it's drawn while "
                "saving and uses little memory."
            ),
            inputs=[
                io.Audio.Input("audio", tooltip="Audio to visualize. Stereo is mixed to mono."),
                io.Int.Input("width", default=640, min=16, max=8192, step=8, tooltip="Frame width in pixels."),
                io.Int.Input("height", default=360, min=16, max=8192, step=8, tooltip="Frame height in pixels."),
                io.Float.Input("fps", default=16.0, min=1.0, max=120.0, step=1.0, tooltip="Frames per second."),
                io.DynamicCombo.Input("mode", options=MODE_OPTIONS, tooltip="Visual style."),
                io.Combo.Input(
                    "freq_scale",
                    options=list(FREQ_SCALES),
                    default="log",
                    tooltip="log spreads frequencies like we hear them (more room for bass); linear is even in Hz.",
                ),
                io.Float.Input(
                    "min_freq", default=20.0, min=1.0, max=20000.0, step=1.0, tooltip="Lowest frequency, Hz."
                ),
                io.Float.Input(
                    "max_freq", default=16000.0, min=100.0, max=96000.0, step=100.0, tooltip="Highest frequency, Hz."
                ),
                io.Float.Input(
                    "db_range",
                    default=60.0,
                    min=10.0,
                    max=120.0,
                    step=5.0,
                    tooltip="Sensitivity: how many dB below the loudest moment still show. Lower = only loud parts.",
                ),
                io.Float.Input(
                    "max_memory_gb",
                    default=4.0,
                    min=0.1,
                    max=512.0,
                    step=0.5,
                    tooltip="RAM limit for the frames/mask outputs. Above it they aren't rendered (black frame and a "
                    "warning) instead of filling your memory. The video output is streamed and not limited.",
                ),
                io.Boolean.Input(
                    "render_frames",
                    default=True,
                    tooltip="Keep all frames in RAM for the frames/mask outputs. Turn off if you only use the video "
                    "output: it's then drawn while saving and uses little memory, and frames/mask are one black frame.",
                ),
                io.Image.Input(
                    "reference", optional=True, tooltip="If connected, its width and height are used (for compositing)."
                ),
            ],
            outputs=[
                io.Image.Output(display_name="frames", tooltip="Grayscale frames. Kept in RAM."),
                io.Mask.Output(display_name="mask", tooltip="The same frames as a mask (shares their memory)."),
                io.Video.Output(
                    display_name="video",
                    tooltip="The frames with the original audio. Drawn while saving when render_frames is off.",
                ),
                io.Float.Output(display_name="fps", tooltip="Frames per second, to wire into other nodes."),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.unique_id],
        )

    @classmethod
    def execute(
        cls,
        audio: dict,
        width: int,
        height: int,
        fps: float,
        mode: dict,
        freq_scale: str,
        min_freq: float,
        max_freq: float,
        db_range: float,
        max_memory_gb: float,
        render_frames: bool,
        reference: torch.Tensor | None = None,
    ) -> io.NodeOutput:
        if reference is not None:
            height, width = reference.shape[1], reference.shape[2]
        options = {"freq_scale": freq_scale, "min_freq": min_freq, "max_freq": max_freq, "db_range": db_range}
        options["device"] = comfy.model_management.get_torch_device()
        args = (audio["waveform"], audio["sample_rate"], width, height, fps, mode["mode"])
        settings = {k: v for k, v in mode.items() if k != "mode"}
        max_bytes = int(max_memory_gb * 1024**3)
        rate = Fraction(fps).limit_denominator(1001)
        count = frame_count(audio["waveform"].shape[-1], audio["sample_rate"], fps)
        needed = estimate_bytes(count, height, width)

        def render() -> torch.Tensor:
            return render_spectrogram(*args, settings, max_bytes=max_bytes, **options)

        streamed = StreamedVideo(
            LazyFrames(count, height, width, lambda: iter_spectrogram(*args, settings, **options)), audio, rate, render
        )
        # Which outputs are connected, for hints only: it can't decide what to render, because ComfyUI
        # would reuse cached outputs after connections change.
        used = used_outputs(cls.hidden.prompt, cls.hidden.unique_id)
        frames_connected = used is None or bool(used & {FRAMES, MASK})
        summary = f"{count:,} frames, {width}x{height} @ {fps:g} fps"
        if not render_frames:
            _show_on_node(cls.hidden.unique_id, f"{summary}. Video streamed while saving, frames not kept in RAM.")
            gray, warnings, video = torch.zeros(1, height, width), [], streamed
            if used is not None and frames_connected:
                warnings.append("render_frames is off, so frames/mask are a single black frame")
                logger.warning(warnings[-1])
        else:
            tip = "" if frames_connected else " Tip: frames/mask aren't used, turn off render_frames to save RAM."
            _show_on_node(
                cls.hidden.unique_id, f"{summary}. frames/mask need about {needed / 1024**3:.2f} GB of RAM.{tip}"
            )
            gray, warnings = run_with_warnings(
                "Generate Audio Spectrogram (black frame returned)", render, lambda: torch.zeros(1, height, width)
            )
            if len(gray) == count:
                video = InputImpl.VideoFromComponents(
                    Types.VideoComponents(images=gray.unsqueeze(-1).expand(-1, -1, -1, 3), audio=audio, frame_rate=rate)
                )
            else:  # not rendered (over budget or failed): the video can still be streamed
                video = streamed
        # IMAGE and MASK share the grayscale data instead of copying it 4 times.
        frames = gray.unsqueeze(-1).expand(-1, -1, -1, 3)
        return io.NodeOutput(frames, gray, video, fps, ui=ui.PreviewText("\n".join(warnings)) if warnings else None)
