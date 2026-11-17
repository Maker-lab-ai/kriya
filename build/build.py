#!/usr/bin/env python3
"""Assemble the Kriya session: voice clips + bells + timed silences -> one audio track.

Outputs:
  ../audio/session.mp3   the full guided session
  ../timeline.json       section / phase timings the app uses to show what's happening

Usage:  python3 build.py            (uses clips/om.* if present, else silent Om slots)
"""
import json, os, subprocess, sys
import numpy as np

SR = 44100
HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
ROOT = os.path.dirname(HERE)

# ---------- audio helpers ----------

def load(path, normalize_lufs=-18.0):
    """Decode any audio file to mono float32 at SR, loudness-normalised."""
    af = f"loudnorm=I={normalize_lufs}:TP=-2:LRA=7" if normalize_lufs is not None else "anull"
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-af", af, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()

def silence(sec):
    return np.zeros(int(round(sec * SR)), dtype=np.float32)

def bowl(f0=196.0, dur=7.0, gain=0.32, seed=0):
    """Soft singing-bowl strike: inharmonic partials, slow decay, gentle beating."""
    t = np.arange(int(dur * SR)) / SR
    partials = [(1.0, 1.0, 5.5), (2.71, 0.55, 3.6), (5.15, 0.25, 2.2), (8.40, 0.10, 1.3)]
    out = np.zeros_like(t)
    for ratio, amp, decay in partials:
        f = f0 * ratio
        beat = 1 + 0.15 * np.sin(2 * np.pi * (0.6 + 0.2 * ratio) * t)
        out += amp * beat * np.exp(-t / decay) * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t))
    attack = np.minimum(1, t / 0.008)
    out *= attack
    out /= np.abs(out).max()
    return (gain * out).astype(np.float32)

BELL = bowl(196.0, 7.0, 0.30)            # start / end of a timed section
CHIME = bowl(523.0, 4.0, 0.14)           # soft halfway chime
FINAL = bowl(174.6, 9.0, 0.30)           # closing bell

# ---------- timeline builder ----------

class Session:
    def __init__(self):
        self.parts, self.t = [], 0.0
        self.sections, self.events = [], []

    def add(self, audio):
        self.parts.append(audio)
        self.t += len(audio) / SR

    def mix_at(self, offset_sec, audio):
        """Overlay audio onto the stream at an absolute time (used for chimes inside silences)."""
        self.events.append((offset_sec, audio))

    def section(self, title, subtitle=""):
        self.sections.append({"title": title, "subtitle": subtitle, "start": round(self.t, 2), "phases": []})

    def phase(self, kind, label, fn):
        start = self.t
        self.timer_end = None
        fn()
        ph = {"kind": kind, "label": label, "start": round(start, 2), "end": round(self.t, 2)}
        if self.timer_end is not None:
            ph["timerEnd"] = round(self.timer_end, 2)   # countdown target (excludes bell ring-out)
        self.sections[-1]["phases"].append(ph)

    def render(self):
        audio = np.concatenate(self.parts)
        for off, a in self.events:
            i = int(off * SR)
            audio[i:i + len(a)] += a[: max(0, len(audio) - i)]
        return audio

def clip(name):
    return load(os.path.join(CLIPS, name))

def timed(s, seconds, halfway=False, end_bell=True):
    """A practice period: bell rings at the start, optional halfway chime, bell at the end."""
    start = s.t
    s.mix_at(start, BELL)
    if halfway:
        s.mix_at(start + seconds / 2, CHIME)
    s.add(silence(seconds))
    s.timer_end = s.t
    if end_bell:
        s.mix_at(s.t, BELL)
        s.add(silence(4.0))   # let the bell ring before the voice comes in

# ---------- Om ----------

OM_COUNT, OM_LEN, OM_GAP = 21, 10.0, 2.0

def om_track():
    om_files = [f for f in os.listdir(CLIPS) if f.startswith("om.")]
    if not om_files:
        print("  (no clips/om.* found - Om slots are silent)")
        return silence(OM_COUNT * (OM_LEN + OM_GAP)), False
    om = load(os.path.join(CLIPS, om_files[0]))
    # trim leading/trailing quiet, then fit to OM_LEN with a soft fade-out
    thr = 0.02 * np.abs(om).max()
    idx = np.where(np.abs(om) > thr)[0]
    om = om[idx[0]: idx[-1]]
    n = int(OM_LEN * SR)
    om = om[:n] if len(om) >= n else np.concatenate([om, np.zeros(n - len(om), np.float32)])
    fade = int(0.8 * SR)
    om[-fade:] *= np.linspace(1, 0, fade)
    om[:int(0.05 * SR)] *= np.linspace(0, 1, int(0.05 * SR))
    one = np.concatenate([om, silence(OM_GAP)])
    return np.tile(one, OM_COUNT), True

# ---------- the session ----------

def build():
    s = Session()
    s.add(silence(2.0))

    s.section("Butterfly", "Arriving, then gently flutter the knees")
    s.phase("voice", "Settling in", lambda: s.add(clip("c01_open_butterfly.mp3")))
    s.phase("practice", "Butterfly", lambda: timed(s, 120))

    s.section("Rock the Baby", "Left leg, then right leg")
    s.phase("voice", "Guidance", lambda: s.add(clip("c02_rock_left.mp3")))
    def left():
        s.mix_at(s.t, BELL)
        s.add(silence(120))
        s.timer_end = s.t
        s.mix_at(s.t, CHIME)
        s.add(silence(1.5))
    s.phase("practice", "Left leg", left)
    s.phase("voice", "Switch legs", lambda: s.add(clip("c03_rock_switch.mp3")))
    s.phase("practice", "Right leg", lambda: (s.add(silence(118.5)), setattr(s, "timer_end", s.t), s.mix_at(s.t, BELL), s.add(silence(4.0))))

    s.section("Cat Cow", "With knee-to-chin and leg extensions")
    s.phase("voice", "Guidance", lambda: s.add(clip("c04_catcow.mp3")))
    s.phase("practice", "Cat cow", lambda: timed(s, 90))

    s.section("Circular Breathing", "Continuous breath, no pauses")
    s.phase("voice", "Guidance", lambda: s.add(clip("c05_circular.mp3")))
    s.phase("practice", "Circular breathing", lambda: timed(s, 480, halfway=True))

    s.section("Om Chanting", "21 Oms")
    s.phase("voice", "Guidance", lambda: (s.add(clip("c06_om_intro.mp3")), s.add(silence(2.0))))
    om, has_om = om_track()
    s.phase("om", "Om", lambda: (s.add(om), setattr(s, "timer_end", s.t), s.add(silence(2.0))))

    s.section("Flutter Breath", "Light and quick")
    s.phase("voice", "Guidance", lambda: s.add(clip("c07_flutter.mp3")))
    s.phase("practice", "Flutter breath", lambda: timed(s, 180))

    s.section("Bandha Locks", "One guided round, then rest your attention at the brow")
    sec_start = s.t
    def guided():
        s.add(clip("c08a_bandha.mp3")); s.add(silence(5.0))
        s.add(clip("c08b_bandha.mp3")); s.add(silence(3.0))
        s.add(clip("c08c_bandha.mp3"))
    s.phase("voice", "Guided round", guided)
    def rest_of_bandha():
        s.mix_at(sec_start + 240, CHIME)          # halfway through the 8 minutes
        s.add(silence(sec_start + 480 - s.t))
        s.timer_end = s.t
        s.mix_at(s.t, BELL)
        s.add(silence(4.0))
    s.phase("practice", "Eyebrow centre", rest_of_bandha)

    s.section("Integration", "Silent stillness")
    s.phase("voice", "Guidance", lambda: s.add(clip("c09_rest.mp3")))
    s.phase("practice", "Stillness", lambda: (s.add(silence(120)), setattr(s, "timer_end", s.t), s.mix_at(s.t, CHIME), s.add(silence(3.0))))

    s.section("Closing", "")
    s.phase("voice", "Closing", lambda: s.add(clip("c10_closing.mp3")))
    def final():
        s.add(silence(1.5))
        for k in range(3):
            s.mix_at(s.t + k * 3.0, FINAL)
        s.add(silence(15.0))
    s.phase("end", "Complete", final)

    audio = s.render()
    peak = np.abs(audio).max()
    if peak > 0.98:
        audio *= 0.98 / peak

    out_mp3 = os.path.join(ROOT, "audio", "session.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "64k", out_mp3], input=audio.tobytes(), check=True)

    timeline = {"duration": round(len(audio) / SR, 2), "om": {"count": OM_COUNT, "len": OM_LEN, "gap": OM_GAP,
                "recorded": has_om}, "sections": s.sections}
    with open(os.path.join(ROOT, "timeline.json"), "w") as f:
        json.dump(timeline, f, indent=1)
    print(f"session: {timeline['duration']/60:.1f} min -> {out_mp3}")

if __name__ == "__main__":
    build()
