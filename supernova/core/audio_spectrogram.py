"""Render audio as grayscale visualizer frames: [frames, height, width] in 0-1.

Modes: bars, circular, scrolling (waterfall) and static_playhead. Loudness is measured per
frequency band in dB, normalized so the loudest moment of the track is 1.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterator

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

MODES = ("bars", "circular", "scrolling", "static_playhead")
POSITIONS = ("bottom", "center", "top")
FREQ_SCALES = ("log", "linear")
N_FFT = 4096
SILENCE_DB = -90.0
DIM_UNPLAYED = 0.35
WARN_BYTES = 2 * 1024**3
CHUNK = 16  # frames drawn at once


def to_mono(waveform: torch.Tensor) -> torch.Tensor:
    """ComfyUI AUDIO waveform ([batch, channels, samples]) -> [samples], first batch item, channels averaged."""
    w = waveform.float()
    if w.dim() == 3:
        w = w[0]
    if w.dim() == 2:
        w = w.mean(0)
    return w


def band_edges(n: int, min_freq: float, max_freq: float, scale: str) -> torch.Tensor:
    if scale == "log":
        return torch.logspace(math.log10(min_freq), math.log10(max_freq), n + 1)
    return torch.linspace(min_freq, max_freq, n + 1)


def _band_matrix(edges: torch.Tensor, sample_rate: int, n_fft: int) -> torch.Tensor:
    """[bins, bands] matrix averaging FFT bins into bands. Bands narrower than a bin use the nearest bin."""
    freqs = torch.fft.rfftfreq(n_fft, 1 / sample_rate)
    lo, hi = edges[:-1], edges[1:]
    m = ((freqs[:, None] >= lo) & (freqs[:, None] < hi)).float()
    empty = m.sum(0) == 0
    if empty.any():
        centers = (lo * hi).sqrt()
        nearest = (freqs[:, None] - centers[None]).abs().argmin(0)
        cols = empty.nonzero().squeeze(1)
        m[nearest[cols], cols] = 1
    return m / m.sum(0)


def analyze(
    x: torch.Tensor, sample_rate: int, times: torch.Tensor, edges: torch.Tensor, n_fft: int = N_FFT
) -> torch.Tensor:
    """Power per band, in dB, of a window centered at each time (seconds). Returns [len(times), bands]."""
    window = torch.hann_window(n_fft, device=x.device)
    padded = F.pad(x, (n_fft // 2, n_fft // 2))
    bands = _band_matrix(edges, sample_rate, n_fft).to(x.device)
    offsets = torch.arange(n_fft, device=x.device)
    out = []
    for chunk in (times * sample_rate).round().long().to(x.device).split(256):
        idx = (chunk[:, None] + offsets).clamp(0, padded.numel() - 1)
        power = torch.fft.rfft(padded[idx] * window).abs() ** 2
        out.append(power @ bands)
    return 10 * torch.log10(torch.cat(out) + 1e-12)


def normalize(db: torch.Tensor, db_range: float) -> torch.Tensor:
    """dB -> 0-1, where the loudest value of the track is 1 and db_range below it is 0."""
    top = db.max()
    if top < SILENCE_DB:
        return torch.zeros_like(db)
    return ((db - (top - db_range)) / db_range).clamp(0, 1)


def smooth(levels: torch.Tensor, amount: float) -> torch.Tensor:
    """Rise instantly, fall gently: amount 0 = no smoothing, close to 1 = very slow fall."""
    if amount <= 0:
        return levels
    out = levels.clone()
    for i in range(1, len(out)):
        out[i] = torch.maximum(levels[i], amount * out[i - 1] + (1 - amount) * levels[i])
    return out


def peaks(levels: torch.Tensor, fall_per_frame: float) -> torch.Tensor:
    """Peak markers that hold the highest recent level and fall at a constant speed."""
    out = levels.clone()
    for i in range(1, len(out)):
        out[i] = torch.maximum(levels[i], out[i - 1] - fall_per_frame)
    return out


def _chunks(n: int):
    for start in range(0, n, CHUNK):
        yield slice(start, min(start + CHUNK, n))


def _iter_bars(levels, peak_levels, height, width, s, device):
    n = levels.shape[1]
    margin_x, margin_y = s["margin"] * width, s["margin"] * height
    slot = ((torch.arange(width, device=device) + 0.5) - margin_x) / (width - 2 * margin_x) * n
    band = slot.floor().long()
    inside = ((band >= 0) & (band < n) & (slot - slot.floor() < 1 - s["bar_gap"])).float()
    band = band.clamp(0, n - 1)
    max_h = s["max_height"] * (height - 2 * margin_y)
    base = {"bottom": height - margin_y, "center": height / 2, "top": margin_y}[s["position"]]
    ys = torch.arange(height, device=device) + 0.5
    # Distance from the baseline in the direction the bars grow: [1, height, 1].
    dist = ((ys - base) if s["position"] == "top" else (base - ys))[None, :, None]
    cap = max(2.0, height * 0.01)
    for c in _chunks(len(levels)):
        h = (levels[c][:, band] * inside * max_h)[:, None, :]
        if s["mirror"]:
            frame = (dist.abs() < h / 2).float()
        else:
            frame = ((dist >= 0) & (dist < h)).float()
            if s["reflection"] > 0:
                fade = (1 + dist / h.clamp(min=1)).clamp(0, 1) * (dist < 0)
                frame = torch.maximum(frame, s["reflection"] * fade * (h > 0))
        if peak_levels is not None:
            p = (peak_levels[c][:, band] * inside * max_h)[:, None, :]
            d = dist.abs() - p / 2 if s["mirror"] else dist - p
            frame = torch.maximum(frame, ((d >= 0) & (d < cap) & (p > 0)).float())
        yield frame.cpu()


def _iter_circular(levels, peak_levels, height, width, s, device):
    n = levels.shape[1]
    size = min(width, height) / 2
    dx = (torch.arange(width, device=device) + 0.5 - s["center_x"] * width)[None, :]
    dy = (torch.arange(height, device=device) + 0.5 - s["center_y"] * height)[:, None]
    # Angle from the top, clockwise, as 0-1.
    turn = (torch.atan2(dx, -dy) / (2 * math.pi)) % 1
    slot = turn * n
    band = slot.floor().long().clamp(0, n - 1).flatten()
    inside = (slot - slot.floor() < 1 - s["bar_gap"]).float()
    dist = (dx**2 + dy**2).sqrt() - s["radius"] * size
    max_len = s["max_length"] * size
    cap = max(2.0, size * 0.02)
    for c in _chunks(len(levels)):
        h = levels[c][:, band].view(-1, height, width) * inside * max_len
        frame = (dist.abs() < h / 2) if s["mirror"] else ((dist >= 0) & (dist < h))
        frame = frame.float()
        if peak_levels is not None:
            p = peak_levels[c][:, band].view(-1, height, width) * inside * max_len
            d = dist.abs() - p / 2 if s["mirror"] else dist - p
            frame = torch.maximum(frame, ((d >= 0) & (d < cap) & (p > 0)).float())
        yield frame.cpu()


def _iter_scrolling(duration, frame_times, height, width, s, analysis, device):
    rows = max(1, round(s["max_height"] * height))
    col_dt = s["window_seconds"] / width
    col_times = torch.arange(math.ceil(duration / col_dt) + 1, device=device) * col_dt
    image = analysis(col_times, rows).flip(1).T  # [rows, columns], low frequencies at the bottom
    top = {"bottom": height - rows, "center": (height - rows) // 2, "top": 0}[s["position"]]
    xs = torch.arange(width, device=device)
    for c in _chunks(len(frame_times)):
        # Rightmost column shows the current time; older columns scroll to the left.
        cols = (frame_times[c].to(device) / col_dt).round().long()[:, None] - (width - 1 - xs)[None, :]
        visible = (cols >= 0).float()[:, None, :]
        out = torch.zeros(len(cols), height, width)
        out[:, top : top + rows] = (image[:, cols.clamp(0, image.shape[1] - 1)].permute(1, 0, 2) * visible).cpu()
        yield out


def _iter_static(duration, frame_times, height, width, s, analysis, device):
    col_times = (torch.arange(width, device=device) + 0.5) / width * duration
    image = analysis(col_times, height).flip(1).T  # [height, width]
    xs = torch.arange(width, device=device) + 0.5
    for c in _chunks(len(frame_times)):
        head = (frame_times[c].to(device) / duration * width)[:, None]
        frames = image[None].repeat(len(head), 1, 1)
        if s["dim_unplayed"]:
            frames *= torch.where(xs[None] > head, DIM_UNPLAYED, 1.0)[:, None, :]
        line = ((xs[None] - head).abs() < s["playhead_width"] / 2).float()[:, None, :]
        yield torch.maximum(frames, line).cpu()


def frame_count(samples: int, sample_rate: int, fps: float) -> int:
    return max(1, math.ceil(samples / sample_rate * fps))


def estimate_bytes(frames: int, height: int, width: int) -> int:
    """RAM for the frames as float32 (the IMAGE and MASK outputs share it)."""
    return frames * height * width * 4


def iter_spectrogram(
    waveform: torch.Tensor,
    sample_rate: int,
    width: int,
    height: int,
    fps: float,
    mode: str,
    settings: dict,
    freq_scale: str = "log",
    min_freq: float = 20.0,
    max_freq: float = 16000.0,
    db_range: float = 60.0,
    device: torch.device | str = "cpu",
) -> Iterator[torch.Tensor]:
    """Draw the track as chunks of [frames, height, width] grayscale frames in 0-1 (on the CPU).

    Only the analysis and one chunk are in memory at a time. settings holds the mode's options
    (see the node schema). Invalid values are fixed with a warning.
    """
    x = to_mono(waveform).to(device)
    if x.numel() == 0:
        logger.warning("audio is empty, rendering one black frame")
        yield torch.zeros(1, height, width)
        return
    max_freq = min(max_freq, sample_rate / 2)
    if min_freq >= max_freq:
        logger.warning("min_freq %.0f is not below max_freq %.0f, using 20 Hz", min_freq, max_freq)
        min_freq = min(20.0, max_freq / 2)

    def analysis(times: torch.Tensor, bands: int) -> torch.Tensor:
        edges = band_edges(bands, min_freq, max_freq, freq_scale)
        return normalize(analyze(x, sample_rate, times, edges), db_range)

    duration = x.numel() / sample_rate
    frame_times = torch.arange(frame_count(x.numel(), sample_rate, fps)) / fps
    if mode == "scrolling":
        yield from _iter_scrolling(duration, frame_times, height, width, settings, analysis, device)
    elif mode == "static_playhead":
        yield from _iter_static(duration, frame_times, height, width, settings, analysis, device)
    else:
        levels = smooth(analysis(frame_times.to(device), settings["bar_count"]), settings["smoothing"])
        peak_levels = peaks(levels, settings["peak_fall"] / fps) if settings["peak_caps"] else None
        draw = _iter_circular if mode == "circular" else _iter_bars
        yield from draw(levels, peak_levels, height, width, settings, device)


def render_spectrogram(
    waveform: torch.Tensor,
    sample_rate: int,
    width: int,
    height: int,
    fps: float,
    mode: str,
    settings: dict,
    max_bytes: int | None = None,
    **kwargs,
) -> torch.Tensor:
    """Render the whole track as one [frames, height, width] tensor (see iter_spectrogram).

    If it would need more than max_bytes of RAM, nothing is rendered: one black frame is
    returned with a warning.
    """
    count = frame_count(waveform.shape[-1], sample_rate, fps)
    needed = estimate_bytes(count, height, width)
    if max_bytes is not None and needed > max_bytes:
        logger.warning(
            "%d frames at %dx%d need about %.1f GB of RAM, over the %.1f GB budget: not rendered. "
            "Lower width, height or fps, raise max_memory_gb, or turn off render_frames (the video is streamed).",
            count,
            width,
            height,
            needed / 1024**3,
            max_bytes / 1024**3,
        )
        return torch.zeros(1, height, width)
    if needed > WARN_BYTES:
        logger.warning("%d frames at %dx%d need about %.1f GB of RAM", count, width, height, needed / 1024**3)
    out = torch.empty(count, height, width)
    pos = 0
    for chunk in iter_spectrogram(waveform, sample_rate, width, height, fps, mode, settings, **kwargs):
        out[pos : pos + len(chunk)] = chunk
        pos += len(chunk)
    return out[:pos]


class LazyFrames:
    """Looks like a [frames, height, width, 3] IMAGE tensor to code that only reads .shape and
    iterates frames (like video encoding), but draws each chunk only when it's reached."""

    def __init__(self, count: int, height: int, width: int, draw: Callable[[], Iterator[torch.Tensor]]):
        self.shape = torch.Size((count, height, width, 3))
        self._draw = draw

    def __len__(self) -> int:
        return self.shape[0]

    def __iter__(self) -> Iterator[torch.Tensor]:
        for chunk in self._draw():
            for frame in chunk:
                yield frame.unsqueeze(-1).expand(-1, -1, 3)
