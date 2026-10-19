# AI Jukebox — Team Verification Checklist

This is the "grader dress rehearsal": deploy the app **from the submission ZIP**
on a machine with access to `dobolyi.com`, click through every core feature like
a grader would, and tick the boxes. Anything that fails → log it in the README's
test report as a new failure case (with input / expected / actual).

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

☐ The app starts with **no errors** and the header reads "AI Jukebox · Boulder, Colorado".
☐ The library already shows **three sample tracks** with covers (seeded on first run).
☐ `git log`-style sanity: the folder contains NO `.env` with a real key, NO `data/`.

## 1 · Core feature 1 — custom song generation (Vocal)

In *Create a song*:
☐ Title `Test Song`; genre `synthwave`; mood `hopeful`; track type **Vocal**; length 20 s.
☐ Press **Generate song + cover** → progress steps appear (Lyrics → Music → Cover art).
☐ Result: a playable MP3 in *Your song*, **AI-written lyrics** in the report, a cover in
  *Cover art* **(1024×1024, matches the vibe)**.
☐ The track appears in the Queue picker **and** the Library gallery.

## 2 · Core feature 1b — custom song generation (Instrumental + styling)

☐ Click **🎲 Surprise me** → title, genre, moods, energy, BPM, key, time signature all change.
☐ Switch track type to **Instrumental** → *Vocals style* hides itself.
☐ Generate → MP3 **with no lyrics** in the report; production log shows the prompt incl.
  energy/vocal-style words.
☐ **Rename** it in the Library row → new title appears in table + queue picker.
☐ **Delete** it → gone from table, queue picker, and covers gallery.

## 3 · Core feature 2 — cover art

☐ Every generated track (vocal + instrumental) has a cover; gallery shows "titles and
  matching cover art" as the brief requires.

## 4 · Core feature 3 — AI DJ show (default voice, no overlap, auto-advance)

☐ In *Playback queue*: pick **two tracks** (e.g. Test Song + one sample).
☐ **Build the show** → a single continuous player appears, plus a **waveform with cue
  markers** and **⏮ Prev / ⏭ Next** buttons.
☐ Play: **DJ speech first**, then song 1, then DJ speech again, then song 2 —
  sequential, **no overlap, no dead silence** (short 0.35 s gaps are by design).
☐ While playing, press **⏭ Next** → jumps to the next segment; **⏮ Prev** jumps back.
☐ Cue sheet lists every segment with its start time; covers of queued tracks show.

## 5 · Voice reference (optional but required by the brief)

☐ Upload a short MP3/WAV of a voice → Build the show again → the DJ speaks in that
  voice. (Without upload it uses Chatterbox's default voice.)

## 6 · Failure handling

☐ Stop the app (Ctrl-C), then click **Generate** in the still-open page → you get a
  clear error like *"Generation failed — nothing was saved…"* (not a crash).
☐ Restart the app → **Generate again works** (retry path). The old track was NOT saved.

## 7 · Report back

- ☐ Tell the repo owner (or open a PR) how it went: ✅ all pass, or the failures with
  input/expected/actual, so the README's "Completed vs. unchecked" list can be updated
  to reflect what the team verified.

---

*Tip: keep the app running after your pass — the README live-demo link can be refreshed
with `AIJ_SHARE=1 python app.py` (new URL printed in the log).*
