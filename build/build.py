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
    """Soft singing-bowl strike: mostly the warm fundamental, quiet overtones, padded attack."""
    t = np.arange(int(dur * SR)) / SR
    partials = [(1.0, 1.0, 6.0), (2.71, 0.30, 3.2), (5.15, 0.06, 1.8)]
    out = np.zeros_like(t)
    for ratio, amp, decay in partials:
        f = f0 * ratio
        beat = 1 + 0.15 * np.sin(2 * np.pi * (0.6 + 0.2 * ratio) * t)
        out += amp * beat * np.exp(-t / decay) * (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.003 * t))
    attack = np.sin(0.5 * np.pi * np.minimum(1, t / 0.06))   # soft mallet, no click
    out *= attack
    out /= np.abs(out).max()
    return (gain * out).astype(np.float32)

BELL = bowl(196.0, 7.0, 0.11)            # start / end of a timed section
CHIME = bowl(330.0, 4.5, 0.06)           # soft halfway chime
FINAL = bowl(174.6, 9.0, 0.12)           # closing bell

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
        if getattr(self, "cues", None):
            ph["cues"] = self.cues                       # label changes within a phase
            self.cues = None
        self.sections[-1]["phases"].append(ph)

    def render(self):
        audio = np.concatenate(self.parts)
        for off, a in self.events:
            i = int(off * SR)
            audio[i:i + len(a)] += a[: max(0, len(audio) - i)]
        return audio

def clip(name):
    return load(os.path.join(CLIPS, name))

def clip_with_pauses(name, at, extra):
    """Insert `extra` seconds of silence at each time in `at` (mid-pause points in the clip)."""
    a, out, prev = clip(name), [], 0
    for t in sorted(at):
        i = int(t * SR)
        out += [a[prev:i], silence(extra)]
        prev = i
    out.append(a[prev:])
    return np.concatenate(out)

# Mid-points of the pauses after "breath in…", "let your body relax", "another deep breath in…",
# "relax even more" in the opening clip: 3 s more time for each breath.
OPENING_BREATH_PAUSES = [8.93, 12.88, 15.45, 19.35]
OPENING_SPLIT = 26.93   # mid-pause between "...in this moment." and "We'll begin with butterfly pose"
# Cat cow: 2 s more after each movement ("lift your gaze", "right knee to your chin",
# "right leg ... towards the sky", "left knee to your chin", "left leg to the sky", "left leg down").
CATCOW_MOVE_PAUSES = [12.745, 17.30, 21.58, 26.365, 29.805, 32.59]

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
    """Returns (track, recorded, om_len). Uses the natural length of the recorded Om."""
    global OM_LEN
    om_files = [f for f in os.listdir(CLIPS) if f.startswith("om.")]
    if not om_files:
        print("  (no clips/om.* found - Om slots are silent)")
        return silence(OM_COUNT * (OM_LEN + OM_GAP)), False
    om = load(os.path.join(CLIPS, om_files[0]), normalize_lufs=-20.0)
    thr = 0.02 * np.abs(om).max()
    idx = np.where(np.abs(om) > thr)[0]
    om = om[max(0, idx[0] - int(0.05 * SR)): idx[-1] + int(0.15 * SR)]
    fi, fo = int(0.04 * SR), int(0.6 * SR)
    om[:fi] *= np.linspace(0, 1, fi)
    om[-fo:] *= np.linspace(1, 0, fo)
    OM_LEN = round(len(om) / SR, 3)
    pad = int(round((OM_LEN + OM_GAP) * SR)) - len(om)
    one = np.concatenate([om, np.zeros(pad, np.float32)])
    print(f"  Om recording: {OM_LEN:.2f}s x {OM_COUNT}")
    return np.tile(one, OM_COUNT), True

# ---------- voices ----------
# Each voice supplies the same guidance pieces; everything else (bells, Om, chants, timings) is shared.

def trimmed(path, pad=0.12):
    """Load a clip and trim leading/trailing quiet, leaving a small pad."""
    a = load(path)
    thr = 0.01 * np.abs(a).max()
    idx = np.where(np.abs(a) > thr)[0]
    return a[max(0, idx[0] - int(pad * SR)): idx[-1] + int(pad * SR)]

def joined(paths, gap):
    parts = []
    for i, pth in enumerate(paths):
        if i: parts.append(silence(gap))
        parts.append(trimmed(pth))
    return np.concatenate(parts)

def voice_original():
    opening = clip_with_pauses("c01_open_butterfly.mp3", OPENING_BREATH_PAUSES, 3.0)
    split = int((OPENING_SPLIT + 3.0 * len(OPENING_BREATH_PAUSES)) * SR)
    return {
        "prep": opening[:split], "butterfly": opening[split:],
        "rock_left": clip("c02_rock_left.mp3"), "rock_switch": clip("c03_rock_switch.mp3"),
        "catcow": clip_with_pauses("c04_catcow.mp3", CATCOW_MOVE_PAUSES, 2.0),
        "circular": clip("c05_circular.mp3"), "om_intro": clip("c06_om_intro.mp3"),
        "flutter": clip("c07_flutter.mp3"),
        "bandha_a": clip("c08a_bandha.mp3"), "bandha_b": clip("c08b_bandha.mp3"), "bandha_c": clip("c08c_bandha.mp3"),
        "closing": clip("c10_closing.mp3"),
    }

def voice_split(folder):
    """A voice recorded as separate phrases, so the breathing / movement gaps are set exactly."""
    P = lambda n: os.path.join(CLIPS, folder, n + ".mp3")
    lead = silence(0.3)
    return {
        # ~3.9 s between breath cues, matching the original voice's pauses
        "prep": np.concatenate([lead, joined([P("p01a"), P("p01b"), P("p01c"), P("p01d"), P("p01e")], 3.6)]),
        "butterfly": trimmed(P("p01f")),
        "rock_left": trimmed(P("p02")), "rock_switch": trimmed(P("p03")),
        # ~2.5 s after each movement cue
        "catcow": joined([P("p04a"), P("p04b"), P("p04c"), P("p04d"), P("p04e"), P("p04f"), P("p04g")], 2.3),
        "circular": trimmed(P("p05")), "om_intro": trimmed(P("p06")), "flutter": trimmed(P("p07")),
        "bandha_a": trimmed(P("p08a")), "bandha_b": trimmed(P("p08b")), "bandha_c": trimmed(P("p08c")),
        "closing": trimmed(P("p10")),
    }

VOICES = [
    {"id": "original", "name": "Original", "pieces": voice_original},
    {"id": "proctor", "name": "Proctor", "pieces": lambda: voice_split("proctor")},
]

# ---------- the session ----------

def build_session(V, om, has_om):
    s = Session()
    s.add(silence(2.0))

    s.section("Preparation", "Arriving, breathing, chanting")
    s.phase("voice", "Settling in", lambda: (s.add(V["prep"]), s.add(silence(3.5))))
    def prep_chant():
        s.add(load(os.path.join(CLIPS, "chant_prep.m4a"), normalize_lufs=-21.0))
        s.timer_end = s.t
        s.add(silence(2.5))
    s.phase("practice", "Chanting", prep_chant)

    s.section("Butterfly", "Gently flutter the knees")
    s.phase("voice", "Guidance", lambda: s.add(V["butterfly"]))
    s.phase("practice", "Butterfly", lambda: timed(s, 120))

    s.section("Rock the Baby", "Left leg, then right leg")
    s.phase("voice", "Guidance", lambda: s.add(V["rock_left"]))
    def left():
        s.mix_at(s.t, BELL)
        s.add(silence(120))
        s.timer_end = s.t
        s.mix_at(s.t, CHIME)
        s.add(silence(1.5))
    s.phase("practice", "Left leg", left)
    s.phase("voice", "Switch legs", lambda: s.add(V["rock_switch"]))
    s.phase("practice", "Right leg", lambda: (s.add(silence(118.5)), setattr(s, "timer_end", s.t), s.mix_at(s.t, BELL), s.add(silence(4.0))))

    s.section("Cat Cow", "With knee-to-chin and leg extensions")
    s.phase("voice", "Guidance", lambda: s.add(V["catcow"]))
    s.phase("practice", "Cat cow", lambda: timed(s, 90))

    s.section("Circular Breathing", "Continuous breath, no pauses")
    s.phase("voice", "Guidance", lambda: s.add(V["circular"]))
    s.phase("practice", "Circular breathing", lambda: timed(s, 480, halfway=True))

    s.section("Om Chanting", "21 Oms")
    s.phase("voice", "Guidance", lambda: (s.add(V["om_intro"]), s.add(silence(2.0))))
    s.phase("om", "Om", lambda: (s.add(om), setattr(s, "timer_end", s.t), s.add(silence(2.0))))

    s.section("Flutter Breath", "Light and quick")
    s.phase("voice", "Guidance", lambda: s.add(V["flutter"]))
    s.phase("practice", "Flutter breath", lambda: timed(s, 180))

    s.section("Bandha Locks", "One guided round, then rest your attention at the brow")
    sec_start = s.t
    def guided():
        s.add(V["bandha_a"]); s.add(silence(5.0))
        s.add(V["bandha_b"]); s.add(silence(3.0))
        s.add(V["bandha_c"])
    s.phase("voice", "Guided round", guided)
    def rest_of_bandha():
        s.mix_at(sec_start + 240, CHIME)          # halfway through the 8 minutes
        chant_at = sec_start + 360                # chanting over the last 2 minutes
        s.mix_at(chant_at, load(os.path.join(CLIPS, "chant.m4a"), normalize_lufs=-21.0))
        s.cues = [{"at": round(chant_at, 2), "label": "Chanting"}]
        s.add(silence(sec_start + 480 - s.t))
        s.timer_end = s.t
        s.mix_at(s.t, BELL)
        s.add(silence(4.0))
    s.phase("practice", "Eyebrow centre", rest_of_bandha)

    s.section("Closing", "")
    s.phase("voice", "Closing", lambda: s.add(V["closing"]))
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
    return audio, s.sections

# ---------- sleep meditation ----------

def build_sleep_voice(folder):
    """Speech + timed silences for the sleep script. Returns (voice_track, sections)."""
    import ambience  # noqa: F401  (imported here so the Kriya build doesn't need it)
    script = json.load(open(os.path.join(HERE, "sleep_script.json")))
    parts, t, sections = [silence(6.0)], 6.0, []          # 6 s for the ambience to fade in first
    for sec in script["sections"]:
        start = t
        for line_id, _text, pause in sec["lines"]:
            a = trimmed(os.path.join(CLIPS, folder, line_id + ".mp3"))
            a = a * (10 ** (-2 / 20))                      # a touch softer than Kriya guidance
            parts += [a.astype(np.float32), silence(pause)]
            t += len(a) / SR + pause
        sections.append({"title": sec["title"], "subtitle": "", "start": round(start, 2),
                         "phases": [{"kind": "sleep", "label": sec["title"], "start": round(start, 2), "end": round(t, 2)}]})
    voice_end = t
    tail = script["tail_seconds"]
    parts.append(silence(tail))
    t += tail
    sections[-1]["phases"][0]["end"] = round(voice_end, 2)
    sections[-1]["phases"].append({"kind": "fade", "label": "Fading out", "start": round(voice_end, 2), "end": round(t, 2)})
    return np.concatenate(parts), sections, voice_end

def ambience_bed(kind, n, voice_end):
    import ambience
    if kind == "silence":
        return np.zeros(n, np.float32)
    bed = getattr(ambience, kind)(n / SR + 1)[:n].astype(np.float32) * (10 ** ({"rain": -6, "waves": -9, "thunderstorm": -6}[kind] / 20)) * 0.1   # 10% of the original level (Bex, 17 Nov)
    fi = int(6 * SR); bed[:fi] *= np.linspace(0, 1, fi) ** 2
    # hold through the voice and the first part of the tail, then fade slowly to silence
    fo_start = int((voice_end + 120) * SR)
    if fo_start < n:
        k = np.linspace(1, 0, n - fo_start)
        bed[fo_start:] *= k ** 2
    return bed

SLEEP_VOICES = [{"id": "proctor", "name": "Proctor", "folder": "sleep-proctor"}]
SLEEP_AMBIENTS = [{"id": "rain", "name": "Rain"}, {"id": "thunderstorm", "name": "Thunderstorm"}, {"id": "waves", "name": "Waves"}, {"id": "silence", "name": "Silence"}]

def encode(audio, rel):
    import hashlib
    path = os.path.join(ROOT, rel)
    peak = np.abs(audio).max()
    if peak > 0.98: audio = audio * (0.98 / peak)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-c:a", "libmp3lame", "-b:a", "64k", path], input=audio.astype(np.float32).tobytes(), check=True)
    return f"{rel}?v={hashlib.md5(open(path, 'rb').read()).hexdigest()[:10]}"

def build_sleep():
    voices = []
    for v in SLEEP_VOICES:
        voice, sections, voice_end = build_sleep_voice(v["folder"])
        audio = {}
        for amb in SLEEP_AMBIENTS:
            mix = voice + ambience_bed(amb["id"], len(voice), voice_end)
            audio[amb["id"]] = encode(mix, f"audio/sleep-{v['id']}-{amb['id']}.mp3")
        voices.append({"id": v["id"], "name": v["name"], "audio": audio,
                       "duration": round(len(voice) / SR, 2), "sections": sections})
        print(f"Sleep / {v['name']}: {len(voice)/SR/60:.1f} min (voice ends {voice_end/60:.1f} min)")
    return {"id": "sleep", "title": "Sleep Manifestation", "style": "sleep",
            "blurb": "Wind down, see the life you're creating, drift off with abundance affirmations.",
            "ambients": SLEEP_AMBIENTS, "voices": voices}

def build_kriya(om, has_om):
    out = []
    for v in VOICES:
        audio, sections = build_session(v["pieces"](), om, has_om)
        out.append({"id": v["id"], "name": v["name"], "audio": encode(audio, f"audio/session-{v['id']}.mp3"),
                    "duration": round(len(audio) / SR, 2), "sections": sections})
        print(f"Kriya / {v['name']}: {len(audio)/SR/60:.1f} min")
    return {"id": "kriya", "title": "Kriya", "style": "kriya",
            "blurb": "Guided kriya: preparation, movement, breathwork, Om and bandhas.",
            "om": {"count": OM_COUNT, "len": OM_LEN, "gap": OM_GAP, "recorded": has_om}, "voices": out}

def build(only=None):
    import datetime
    path = os.path.join(ROOT, "timeline.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    meds = {m["id"]: m for m in old.get("meditations", [])}
    if only in (None, "kriya"):
        om, has_om = om_track()
        meds["kriya"] = build_kriya(om, has_om)
    if only in (None, "sleep"):
        meds["sleep"] = build_sleep()
    order = ["kriya", "sleep"]
    k = meds["kriya"]
    timeline = {"built": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%d %b %Y, %H:%M"),
                "meditations": [meds[i] for i in order if i in meds],
                # Kriya also at top level, for older copies of the app
                "om": k["om"], "voices": k["voices"], "audio": k["voices"][0]["audio"],
                "duration": k["voices"][0]["duration"], "sections": k["voices"][0]["sections"]}
    with open(path, "w") as f:
        json.dump(timeline, f, indent=1)

if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
