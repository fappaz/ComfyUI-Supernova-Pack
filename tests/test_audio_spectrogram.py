import logging
import math

import pytest
import torch

import supernova.core.audio_spectrogram as spec
from supernova.core.audio_spectrogram import (
    LazyFrames,
    analyze,
    band_edges,
    estimate_bytes,
    frame_count,
    iter_spectrogram,
    normalize,
    peaks,
    render_spectrogram,
    smooth,
    to_mono,
)

SR = 16000
W, H, FPS = 64, 48, 10


def tone(freq: float, seconds: float = 1.0, amplitude: float = 0.5) -> torch.Tensor:
    t = torch.arange(int(SR * seconds)) / SR
    return amplitude * torch.sin(2 * math.pi * freq * t)


def audio(x: torch.Tensor) -> torch.Tensor:
    return x[None, None]  # ComfyUI AUDIO waveform: [batch, channels, samples]


BARS = dict(
    bar_count=16,
    bar_gap=0.0,
    max_height=1.0,
    position="bottom",
    margin=0.0,
    mirror=False,
    reflection=0.0,
    peak_caps=False,
    peak_fall=0.5,
    smoothing=0.0,
)
CIRCULAR = dict(
    bar_count=16,
    bar_gap=0.0,
    radius=0.4,
    max_length=0.5,
    center_x=0.5,
    center_y=0.5,
    mirror=False,
    peak_caps=False,
    peak_fall=0.5,
    smoothing=0.0,
)
SCROLLING = dict(window_seconds=1.0, position="bottom", max_height=1.0)
STATIC = dict(playhead_width=2, dim_unplayed=True)
MODES = [("bars", BARS), ("circular", CIRCULAR), ("scrolling", SCROLLING), ("static_playhead", STATIC)]


def render(x, mode, settings, **kwargs):
    return render_spectrogram(audio(x), SR, W, H, FPS, mode, settings, min_freq=50, max_freq=8000, **kwargs)


def band_of(freq: float, n: int) -> int:
    edges = band_edges(n, 50, 8000, "log")
    return int(((edges[:-1] <= freq) & (edges[1:] > freq)).nonzero()[0])


# --- analysis ---


def test_to_mono():
    stereo = torch.stack([torch.ones(10), torch.zeros(10)])[None]
    assert torch.equal(to_mono(stereo), torch.full((10,), 0.5))
    assert to_mono(torch.ones(10)).shape == (10,)


@pytest.mark.parametrize("scale", ["log", "linear"])
def test_band_edges(scale):
    edges = band_edges(8, 50, 8000, scale)
    assert len(edges) == 9
    assert edges[0] == pytest.approx(50)
    assert edges[-1] == pytest.approx(8000)
    assert (edges[1:] > edges[:-1]).all()


@pytest.mark.parametrize("freq", [100, 440, 3000])
def test_analyze_finds_the_tone(freq):
    edges = band_edges(32, 50, 8000, "log")
    db = analyze(tone(freq), SR, torch.tensor([0.5]), edges)
    assert int(db[0].argmax()) == band_of(freq, 32)


def test_normalize():
    db = torch.tensor([-10.0, -40.0, -70.0, -100.0])
    assert normalize(db, 60).tolist() == pytest.approx([1.0, 0.5, 0.0, 0.0])
    assert normalize(torch.full((4,), -120.0), 60).sum() == 0  # silence stays black


def test_smooth_rises_fast_and_falls_gently():
    levels = torch.tensor([[0.0], [1.0], [0.0], [0.0]])
    out = smooth(levels, 0.5)
    assert out[:, 0].tolist() == pytest.approx([0.0, 1.0, 0.5, 0.25])
    assert torch.equal(smooth(levels, 0), levels)


def test_peaks_fall_at_constant_speed():
    out = peaks(torch.tensor([[1.0], [0.0], [0.0], [0.9]]), 0.25)
    assert out[:, 0].tolist() == pytest.approx([1.0, 0.75, 0.5, 0.9])


# --- rendering ---


@pytest.mark.parametrize(("mode", "settings"), MODES)
def test_every_mode_renders_frames_in_range(mode, settings):
    frames = render(tone(440, 1.25), mode, settings)
    assert frames.shape == (math.ceil(1.25 * FPS), H, W)
    assert frames.min() >= 0 and frames.max() <= 1
    assert frames.max() > 0.5


@pytest.mark.parametrize(("mode", "settings"), MODES)
def test_silence_is_black(mode, settings):
    frames = render(torch.zeros(SR), mode, settings)
    if mode == "static_playhead":  # only the playhead is drawn
        head = int(frames[5].amin(0).argmax())
        frames[5, :, head - 2 : head + 3] = 0
        frames = frames[5]
    assert frames.max() == 0


def test_bars_light_the_tone_band():
    frames = render(tone(440), "bars", BARS)
    band = band_of(440, 16)
    columns = frames[5].amax(0) > 0.5
    lit = columns.nonzero().squeeze(1)
    assert lit.min() // (W // 16) <= band <= lit.max() // (W // 16)
    assert frames[5, :, band * (W // 16) + 1].sum() > frames[5, :, 0].sum()


@pytest.mark.parametrize(("position", "rows"), [("bottom", slice(0, H // 2)), ("top", slice(H // 2, H))])
def test_bars_position(position, rows):
    frames = render(tone(440), "bars", {**BARS, "position": position, "max_height": 0.4})
    assert frames[5, rows].max() == 0  # the other half stays empty
    assert frames[5].max() == 1


def test_bars_mirror_is_symmetric():
    frames = render(tone(440), "bars", {**BARS, "position": "center", "mirror": True})
    assert torch.equal(frames[5], frames[5].flip(0))


def test_bars_reflection_is_dimmer_and_below():
    settings = {**BARS, "position": "center", "max_height": 0.4, "reflection": 0.5}
    frames = render(tone(440), "bars", settings)
    below = frames[5, H // 2 :]
    assert 0 < below.max() <= 0.5
    assert render(tone(440), "bars", {**settings, "reflection": 0.0})[5, H // 2 :].max() == 0


def test_bars_peak_caps_stay_after_the_sound_stops():
    x = torch.cat([tone(440, 0.5), torch.zeros(SR // 2)])
    with_caps = render(x, "bars", {**BARS, "peak_caps": True, "peak_fall": 0.5})
    without = render(x, "bars", BARS)
    assert without[7].max() == 0
    assert with_caps[7].max() == 1


def test_circular_draws_outside_the_radius():
    frames = render(tone(440), "circular", CIRCULAR)
    ys, xs = torch.meshgrid(torch.arange(H) + 0.5, torch.arange(W) + 0.5, indexing="ij")
    r = ((xs - W / 2) ** 2 + (ys - H / 2) ** 2).sqrt()
    radius = 0.4 * min(W, H) / 2
    assert frames[5][r < radius].max() == 0
    assert frames[5][r >= radius].max() == 1


def test_circular_mirror_draws_inside_too():
    frames = render(tone(440), "circular", {**CIRCULAR, "mirror": True})
    ys, xs = torch.meshgrid(torch.arange(H) + 0.5, torch.arange(W) + 0.5, indexing="ij")
    r = ((xs - W / 2) ** 2 + (ys - H / 2) ** 2).sqrt()
    assert frames[5][r < 0.4 * min(W, H) / 2].max() == 1


def test_scrolling_starts_on_the_right():
    frames = render(tone(440), "scrolling", {**SCROLLING, "window_seconds": 2.0})
    # At 0.5 s with a 2 s window, only the rightmost quarter has sound.
    assert frames[5, :, : W // 2].max() == 0
    assert frames[5, :, -W // 8 :].max() > 0.5


def test_scrolling_tone_is_a_horizontal_line():
    frames = render(tone(440), "scrolling", SCROLLING)
    rows = frames[9].amax(1)
    assert (rows > 0.5).sum() <= H // 4
    assert frames[9].argmax(0)[-5:].unique().numel() == 1


def test_static_playhead_moves_and_dims():
    frames = render(tone(440), "static_playhead", STATIC)
    heads = [int(frames[i].amin(0).argmax()) for i in (0, 5)]
    assert heads[0] < heads[1]
    assert heads[1] == pytest.approx(W / 2, abs=2)
    image = render(tone(440), "static_playhead", {**STATIC, "dim_unplayed": False})
    assert frames[5, :, -4].max() == pytest.approx(image[5, :, -4].max() * spec.DIM_UNPLAYED)


# --- soft failures ---


def test_empty_audio_gives_one_black_frame(caplog):
    with caplog.at_level(logging.WARNING):
        frames = render(torch.zeros(0), "bars", BARS)
    assert frames.shape == (1, H, W) and frames.max() == 0
    assert "audio is empty" in caplog.text


def test_min_freq_above_max_is_fixed(caplog):
    with caplog.at_level(logging.WARNING):
        frames = render_spectrogram(audio(tone(440)), SR, W, H, FPS, "bars", BARS, min_freq=9000, max_freq=1000)
    assert frames.max() > 0
    assert "min_freq" in caplog.text


def test_max_freq_above_nyquist_is_clamped():
    frames = render_spectrogram(audio(tone(440)), SR, W, H, FPS, "bars", BARS, max_freq=48000)
    assert frames.max() > 0


def test_large_render_warns(monkeypatch, caplog):
    monkeypatch.setattr(spec, "WARN_BYTES", 1000)
    with caplog.at_level(logging.WARNING):
        render(tone(440, 0.2), "bars", BARS)
    assert "GB of RAM" in caplog.text


# --- memory ---


def test_frame_count_and_estimate():
    assert frame_count(SR * 3, SR, 16) == 48
    assert frame_count(0, SR, 16) == 1
    assert estimate_bytes(48, 360, 640) == 48 * 360 * 640 * 4


@pytest.mark.parametrize(("mode", "settings"), MODES)
def test_iter_draws_small_chunks_matching_render(mode, settings):
    x = tone(440, 3.0)
    chunks = list(iter_spectrogram(audio(x), SR, W, H, FPS, mode, settings, min_freq=50, max_freq=8000))
    assert max(len(c) for c in chunks) <= spec.CHUNK
    assert torch.equal(torch.cat(chunks), render(x, mode, settings))


def test_over_budget_renders_nothing(caplog):
    with caplog.at_level(logging.WARNING):
        frames = render(tone(440), "bars", BARS, max_bytes=1000)
    assert frames.shape == (1, H, W) and frames.max() == 0
    assert "over the" in caplog.text and "budget" in caplog.text


def test_lazy_frames_look_like_an_image_batch():
    drawn = []

    def draw():
        for i in range(3):
            drawn.append(i)
            yield torch.full((2, H, W), float(i))

    frames = LazyFrames(6, H, W, draw)
    assert frames.shape == (6, H, W, 3) and len(frames) == 6
    assert drawn == []  # nothing drawn until iterated
    it = iter(frames)
    first = next(it)
    assert first.shape == (H, W, 3) and drawn == [0]
    assert [float(f[0, 0, 0]) for f in [first, *it]] == [0, 0, 1, 1, 2, 2]
