# AI Jukebox — Team Verification Checklist

Grader dress rehearsal. Status legend: **☑ auto-verified** (machine / agent, with
date + method) · **☐ needs human hands** (browser clicks the automation stack
cannot perform). Anything that fails → log it in the README's test report as a
new failure case (input / expected / actual).

**You'll need:** the class key (`class-endpoints.txt`), ~10-15 minutes, network
access to `http://dobolyi.com`.

---

## 0 · Fresh deploy from the ZIP (the actual grade criterion)

```bash
unzip dist/ai-jukebox-submission.zip -d /tmp/jukebox-test
cd /tmp/jukebox-test
cp .env.example .env      # put the class key in AIJ_API_KEY
bash run.sh               # macOS/Linux; run.bat on Windows
# open http://127.0.0.1:7860
```

- ☑ 2026-10-19 (agent): fresh unzip → `python3 -m venv` → `pip install -r
  requirements.txt` → app starts with **no errors** on a clean copy in `/tmp`;
  HTTP 200; header "AI Jukebox"; **zero warnings beyond Gradio 6.0 deprecation
  notices** (cosmetic, print-level).
- ☑ 2026-10-19 (agent): library shows **three sample tracks with covers**
  (Neon Afterglow, Morning Gold, Midnight Café), seeded on first run.
- ☑ 2026-10-19 (agent): ZIP audit (`make_zip.py --check`) — CLEAN: no real
  `.env`, no `data/`, no user uploads; only placeholder `.env.example`.

## 1 · Core feature 1 — custom song generation (Vocal)

- ☑ 2026-10-19 (agent, API): Generate with style inputs → **real MP3**, AI
written lyrics in the report, FLUX cover 1024×1024; track lands in Queue
picker **and** Library gallery (wiring audited via served gradio config:
create_song 15 in / 7 out, all component ids valid).
- ☑ 2026-10-19 (agent): identical flow verified earlier on the live instance
  (vocal ✅ 128-word AI lyrics / 88 BPM / E major; cover ✅ 1024×1024).

## 2 · Core feature 1b — custom song generation (Instrumental + styling)

- ☑ 2026-10-19 (agent, browser): **🎲 Surprise me** click → genre/moods/energy
  rerolled for real. Styling panel (30+ genres, moods, energy, tempo 0–220,
  12 keys, time signatures, vocal styles) present in served config with all
  values; ACE-Step knobs (`bpm`, `keyscale`, `timesignature`) honored exactly —
  verified on a live probe track.
- ☑ 2026-10-19 (agent, browser): track type → **Instrumental** hides *Vocals
  style* (`.change` event wiring audited live: component 15 → visibility).
- ☑ 2026-10-19 (agent): **Rename** persists across reloads (2 unit tests);
  **Delete** removes from table + pickers + gallery with stale-id pruning.
- ☐ (human) One manual generate of an instrumental + rename + delete pass to
  feel the flow — the clicks are exercised here, the artwork judgement is yours.

## 3 · Core feature 2 — cover art

- ☑ 2026-10-19 (agent): every generated track gets a cover (FLUX 9006, 1024²);
  cover failure is **non-fatal** (track still saved, warning shown) — covered by
  tests + earlier live run.

## 4 · Core feature 3 — AI DJ show (default voice, no overlap, auto-advance)

- ☑ 2026-10-19 (agent, API): two tracks → Build the show → real Qwen DJ
  scripts → Chatterbox speech mixed by miniaudio into **one continuous WAV**;
  cues 0.00 (DJ) / 10.63 (song 1) / 26.98 (DJ) / 39.21 (song 2) — sequential,
  **no overlap** (0.35 s gaps by design). Waveform panel with cue markers +
  Prev/Next rendered and validated.
- ☑ 2026-10-19 (agent, real handler): **⏭ Next / ⏮ Prev skip logic executed
  against the production handler**: 20.00 s → 26.98 s → 10.63 s. Cue sheet
  lists every segment + start time; queued covers show.
- ☐ (human) One *visual/audio* listen pass: pick two tracks with the mouse,
  press play, hear DJ → music → DJ → music. Everything below it is verified;
  the pleasure check is yours (10 seconds).

## 5 · Voice reference (optional but required by the brief)

- ☑ 2026-10-19 (agent): voice-ref upload path built + earlier verified live
  (uploaded ref → DJ speaks in that voice). Default voice = Chatterbox.
- ☐ (human) Optional: upload one MP3/WAV and rebuild to hear the clone.
- Note: uploads are stored under gitignored `data/`, never in the ZIP.

## 6 · Failure handling

- ☑ 2026-10-19 (agent, prior live run): a real ACE-Step timeout surfaced as
  "Generation failed … nothing was saved" — a clean `gr.Error`, not a crash;
  retry path re-verified after restart; nothing partial saved (tests).
- ☐ (human, 30 s): Ctrl-C the app, click Generate in the still-open page, see
  the friendly error, restart, Generate again.

## 7 · Report back

- ☑ This document + README "Completed vs. unchecked" updated 2026-10-19.
- ☐ (team) Tell the repo owner the human-pass outcome, or open a PR.

---

*Tip: keep the app running after your pass — the README live-demo link can be
refreshed with `AIJ_SHARE=1 python app.py` (new URL printed in the log).*
