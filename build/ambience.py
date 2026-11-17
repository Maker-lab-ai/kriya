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

def thunderstorm(seconds, seed=3):
    """A proper storm: heavier, deeper downpour, slow wind gusts, and rolling thunder every 15-40 s.
    The thunder sits in the 60-700 Hz range so phone speakers can actually play it; no sharp cracks."""
    rng = np.random.default_rng(seed)
    def seg(n, rng):
        t = np.arange(n) / SR
        pour = _filtered_noise(n, rng, lo=150, hi=3500) * 0.7            # heavier, lower-pitched rain
        drum = _filtered_noise(n, rng, lo=60, hi=500) * 0.45             # rain drumming on the roof
        gust = 1 + 0.45 * np.sin(2 * np.pi * t / rng.uniform(9, 16) + rng.uniform(0, 6)) ** 2
        wind = _filtered_noise(n, rng, lo=200, hi=900) * 0.25 * gust
        return (pour + drum) * (1 + 0.25 * np.sin(2 * np.pi * t / rng.uniform(11, 19))) + wind
    bed = _chunks(seg, seconds, seed + 7)
    bed = bed / np.sqrt(np.mean(bed ** 2)) * 0.06
    n = len(bed); out = bed.copy()
    t = rng.uniform(6, 14)
    while t < seconds - 10:
        L = min(int(rng.uniform(8, 15) * SR), n - int(t * SR))
        i = int(t * SR)
        low = _filtered_noise(L, rng, lo=40, hi=220)
        mid = _filtered_noise(L, rng, lo=120, hi=700)
        k = np.arange(L) / SR
        att = rng.uniform(0.4, 1.0)
        env = np.minimum(1, k / att) ** 1.5 * np.exp(-np.maximum(0, k - att) / rng.uniform(2.5, 4.5))
        # several rolls inside one peal, like thunder travelling across the sky
        rolls = 1 + 0.6 * np.abs(np.sin(2 * np.pi * rng.uniform(0.25, 0.6) * k + rng.uniform(0, 3)))
        peal = (low / np.sqrt(np.mean(low ** 2)) + 0.8 * mid / np.sqrt(np.mean(mid ** 2))) * env * rolls
        out[i:i + L] += peal * 0.11 * rng.uniform(0.7, 1.0)
        t += rng.uniform(15, 40)
    return out
