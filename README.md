# Kriya timer

A guided Kriya meditation timer for your phone. The full session is one audio track (voice guidance, bells and timed silences), and the app shows the current step, a countdown, and the step list.

**Use it:** open the GitHub Pages link on your phone → Share → *Add to Home Screen*. It works offline after the first load and keeps playing with the screen locked.

## Session (≈37 min)
1. Butterfly – opening, then 2:00
2. Rock the Baby – left leg 2:00, right leg 2:00
3. Cat Cow – guided round, then 1:30
4. Circular Breathing – 8:00 (chime at halfway)
5. Om Chanting – 21 × your recorded Om (~11.5 s) + 2 s gap
6. Flutter Breath – 3:00
7. Bandha Locks – one guided round, then eyebrow centre; 8:00 total (chime at halfway)
8. Integration – 2:00 silence
9. Closing

## Rebuilding the audio
Voice clips live in `build/clips/` (ElevenLabs). To add or replace the Om recording, put it at `build/clips/om.m4a` (any format ffmpeg reads), then:

```
cd build && python3 build.py
```

This rewrites `audio/session.mp3` and `timeline.json`. Bump `VERSION` in `sw.js` so installed copies pick up the change.
