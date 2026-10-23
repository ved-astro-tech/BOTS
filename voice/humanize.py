"""Make TTS audio sound less robotic.

TTS output is very even: same loudness, same speed, same pitch range, same
pause lengths, and a perfectly silent background. Real speech drifts on all of
these. This script adds small, smooth, random variation on top of a TTS file:

1. Speed + pitch drift: a slow random time warp (resampling), so some phrases
   come out a little faster and higher, others slower and lower, the way
   people speed up and lift their voice when they are engaged.
2. Pause jitter: silent gaps between phrases get longer or shorter at random.
3. Energy drift: a slow loudness curve across the whole clip, plus a separate
   gain for every phrase, so the energy bands in the mel spectrogram are no
   longer flat.
4. Room: a faint room-tone noise floor and a short, quiet reverb so it does
   not sound like it came from a vacuum.

Usage:
    python voice/humanize.py in.mp3 out.wav [--seed 7] [--strength 1.0] [--plot mel.png]

--strength scales every effect (0 = unchanged, 1 = default, 2 = strong).
"""

import argparse

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from scipy.signal import fftconvolve


def smooth_noise(rng, n, sr, period_s):
    """Random curve with values around [-1, 1] that changes every ~period_s seconds."""
    hop = max(1, int(sr * period_s / 4))
    pts = rng.standard_normal(n // hop + 2)
    pts = gaussian_filter1d(pts, sigma=2)
    pts /= np.max(np.abs(pts)) + 1e-9
    return np.interp(np.arange(n), np.arange(len(pts)) * hop, pts)


def time_warp(y, sr, rng, depth):
    """Vary playback rate smoothly by about +/- depth (0.03 = 3%)."""
    rate = 1.0 + depth * smooth_noise(rng, len(y), sr, period_s=1.8)
    read_pos = np.cumsum(rate)
    read_pos = read_pos[read_pos < len(y) - 1]
    return np.interp(read_pos, np.arange(len(y)), y)


def phrases(y, sr, top_db=35, min_gap_s=0.12):
    """Return [start, end) sample ranges of voiced phrases."""
    iv = librosa.effects.split(y, top_db=top_db, frame_length=1024, hop_length=256)
    merged = []
    for s, e in iv:
        if merged and s - merged[-1][1] < min_gap_s * sr:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return merged


def rebuild(y, sr, rng, pause_jitter, phrase_gain_db):
    """Re-join phrases with jittered pauses and a random gain per phrase."""
    iv = phrases(y, sr)
    if not iv:
        return y
    fade = int(0.01 * sr)
    out = [y[: iv[0][0]]]
    for i, (s, e) in enumerate(iv):
        seg = y[s:e].copy()
        gain = 10 ** (rng.uniform(-phrase_gain_db, phrase_gain_db) / 20)
        # ramp the gain in and out so phrase edges do not click
        env = np.full(len(seg), gain)
        r = min(fade, len(seg) // 2)
        env[:r] = np.linspace(1, gain, r)
        env[len(seg) - r :] = np.linspace(gain, 1, r)
        out.append(seg * env)
        gap_end = iv[i + 1][0] if i + 1 < len(iv) else len(y)
        gap = y[e:gap_end]
        if i + 1 < len(iv) and len(gap) > 0:
            factor = np.clip(rng.normal(1.0, pause_jitter), 0.6, 1.8)
            n = max(int(0.06 * sr), int(len(gap) * factor))
            gap = np.resize(gap, n) if n > len(gap) else gap[:n]
        out.append(gap)
    return np.concatenate(out)


def energy_drift(y, sr, rng, depth_db):
    """Slow loudness curve (+/- depth_db) plus a faster, smaller wobble."""
    slow = depth_db * smooth_noise(rng, len(y), sr, period_s=3.0)
    fast = 0.35 * depth_db * smooth_noise(rng, len(y), sr, period_s=0.5)
    return y * 10 ** ((slow + fast) / 20)


def room(y, sr, rng, noise_db, wet):
    """Add a faint pink-ish room tone and a short synthetic reverb."""
    n = int(0.35 * sr)
    t = np.arange(n) / sr
    ir = rng.standard_normal(n) * np.exp(-t / 0.07)
    ir = gaussian_filter1d(ir, 2)
    ir /= np.sqrt(np.sum(ir**2)) + 1e-9
    rev = fftconvolve(y, ir)[: len(y)]
    y = (1 - wet) * y + wet * rev

    white = rng.standard_normal(len(y))
    pink = np.cumsum(white)
    pink -= gaussian_filter1d(pink, sr // 50)  # remove DC drift
    pink /= np.std(pink) + 1e-9
    peak = np.max(np.abs(y)) + 1e-9
    return y + pink * peak * 10 ** (noise_db / 20)


def plot_mels(before, after, sr, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa.display

    fig, axes = plt.subplots(3, 1, figsize=(12, 9))
    for ax, y, title in ((axes[0], before, "Original TTS"), (axes[1], after, "Humanized")):
        m = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=sr, n_mels=80), ref=np.max)
        librosa.display.specshow(m, sr=sr, x_axis="time", y_axis="mel", ax=ax)
        ax.set_title(title)
    for y, label in ((before, "Original"), (after, "Humanized")):
        rms = librosa.feature.rms(y=y)[0]
        db = librosa.amplitude_to_db(rms, ref=1.0)
        axes[2].plot(librosa.times_like(rms, sr=sr), db, label=label, lw=0.8)
    axes[2].set_title("Energy (RMS, dB)")
    axes[2].set_ylim(-70, 0)
    axes[2].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def humanize(y, sr, seed=None, strength=1.0):
    rng = np.random.default_rng(seed)
    y = time_warp(y, sr, rng, depth=0.035 * strength)
    y = rebuild(y, sr, rng, pause_jitter=0.25 * strength, phrase_gain_db=2.0 * strength)
    y = energy_drift(y, sr, rng, depth_db=2.5 * strength)
    y = room(y, sr, rng, noise_db=-52 + 4 * (strength - 1), wet=min(0.25, 0.08 * strength))
    return y / (np.max(np.abs(y)) + 1e-9) * 0.89  # about -1 dBFS peak


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--plot", help="save before/after mel spectrogram PNG here")
    a = p.parse_args()

    y, sr = librosa.load(a.input, sr=None, mono=True)
    out = humanize(y, sr, seed=a.seed, strength=a.strength)
    sf.write(a.output, out, sr)
    print(f"{a.input}: {len(y) / sr:.1f}s -> {a.output}: {len(out) / sr:.1f}s")
    if a.plot:
        plot_mels(y, out, sr, a.plot)
        print(f"mel spectrograms -> {a.plot}")


if __name__ == "__main__":
    main()
