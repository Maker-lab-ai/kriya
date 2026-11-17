# Meditations (Kriya timer)

A home screen lists the meditations; each opens its own player. Currently: **Kriya** and **Sleep Manifestation**.

A guided Kriya meditation timer for your phone. The full session is one audio track (voice guidance, bells and timed silences), and the app shows the current step, a countdown, and the step list.

**Use it:** open the GitHub Pages link on your phone → Share → *Add to Home Screen*. It works offline after the first load and keeps playing with the screen locked.

## Session (≈35 min)
0. Preparation – opening script with breath pauses, then a short chant (~26 s)
1. Butterfly – pose guidance, then 2:00
2. Rock the Baby – left leg 2:00, right leg 2:00
3. Cat Cow – guided round, then 1:30
4. Circular Breathing – 8:00 (chime at halfway)
5. Om Chanting – 21 × your recorded Om (~11.5 s) + 2 s gap
6. Flutter Breath – 3:00
7. Bandha Locks – one guided round, then eyebrow centre; chanting over the last 2:00; 8:00 total (chime at halfway)
8. Closing

## Voices
Two guidance voices, switchable in the app: **Original** and **Proctor** (an original ElevenLabs designed voice). Each has its own track: `audio/session-<voice>.mp3`. Proctor's lines are recorded as separate phrases in `build/clips/proctor/` so pauses are set exactly.

## Rebuilding the audio
Voice clips live in `build/clips/` (ElevenLabs). To add or replace the Om recording, put it at `build/clips/om.m4a` (any format ffmpeg reads), then:

```
cd build && python3 build.py
```

This rewrites `audio/session.mp3` and `timeline.json` (which carries a content-hashed audio URL), so installed copies pick up the change automatically.

## Sleep Manifestation
Script in `build/sleep_script.json` (line id, text, pause after). Recorded phrase by phrase in Proctor's voice (`build/clips/sleep-proctor/`). Three tracks are rendered with different background sounds — rain, waves, silence — from `build/ambience.py` (procedural, no samples). After "Sleep well" the sound holds 2 minutes, then fades to silence over 3.

Build just one meditation: `python3 build.py sleep` or `python3 build.py kriya`.
