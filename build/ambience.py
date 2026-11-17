#!/usr/bin/env python3
"""Synthesise gentle, non-repeating rain and ocean-wave beds (mono float32, 44.1 kHz).
Procedural so they loop-free for any length and cost nothing to regenerate."""
import numpy as np
SR = 44100

def _filtered_noise(n, rng, lo=None, hi=None):
    """White noise band-limited in the frequency domain."""
    x = rng.standard_normal(n).astype(np.float32)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = np.ones_like(f)
    if hi: g *= 1 / np.sqrt(1 + (f / hi) ** 4)
    if lo: g *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(X * g, n).astype(np.float32)

def _chunks(fn, seconds, seed, chunk=60.0, xf=2.0):
    """Build long beds from overlapping chunks (keeps FFT sizes small), cross-faded."""
    rng = np.random.default_rng(seed)
    total = int(seconds * SR); c = int(chunk * SR); x = int(xf * SR)
    out = np.zeros(total + c + x, np.float32); pos = 0
    ramp = np.sin(np.linspace(0, np.pi / 2, x)) ** 2
    while pos < total:
        seg = fn(c + x, rng)
        seg[:x] *= ramp
        seg[-x:] *= ramp[::-1]
        out[pos:pos + len(seg)] += seg
        pos += c
    return out[:total]

def rain(seconds, seed=1):
    def seg(n, rng):
        t = np.arange(n) / SR
        bed = _filtered_noise(n, rng, lo=300, hi=6000) * 0.5          # steady hiss of rainfall
        body = _filtered_noise(n, rng, lo=80, hi=900) * 0.35            # low rumble on the roof
        swell = 1 + 0.18 * np.sin(2 * np.pi * t / rng.uniform(17, 29) + rng.uniform(0, 6))
        out = (bed + body) * swell
        # scattered soft droplets
        for _ in range(int(n / SR * 9)):
            i = rng.integers(0, n - 2000); L = rng.integers(300, 1400)
            d = rng.standard_normal(L).astype(np.float32) * np.exp(-np.arange(L) / (L / 5))
            out[i:i + L] += d * rng.uniform(0.15, 0.5)
        return out
    a = _chunks(seg, seconds, seed)
    return a / np.sqrt(np.mean(a ** 2)) * 0.06       # quiet bed (about -24 dBFS RMS)

def waves(seconds, seed=2):
    def seg(n, rng):
        t = np.arange(n) / SR
        wash = _filtered_noise(n, rng, lo=60, hi=1800)
        foam = _filtered_noise(n, rng, lo=900, hi=5000) * 0.35
        # irregular swell: each wave 7-12 s, slow rise, longer fall
        env = np.zeros(n, np.float32); p = 0
        while p < n:
            L = int(rng.uniform(7, 12) * SR); a = rng.uniform(0.55, 1.0)
            k = np.arange(L) / L
            shape = np.where(k < 0.35, np.sin(np.pi / 2 * k / 0.35) ** 2, np.exp(-(k - 0.35) * 4.0))
            end = min(n, p + L); env[p:end] = np.maximum(env[p:end], a * shape[:end - p]); p += int(L * 0.8)
        env = 0.18 + env
        return wash * env + foam * env ** 2
    a = _chunks(seg, seconds, seed)
    return a / np.sqrt(np.mean(a ** 2)) * 0.06
