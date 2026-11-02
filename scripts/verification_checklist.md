# AI Jukebox team verification

Agent checks and team checks are separate. Record the tester, date, inputs and actual result; check a box only after doing it. Do not interpret a previous agent run as a teammate's test.

## Automated evidence, November 1, 2026

- [x] Class configuration matches the supplied endpoint file; no port 9000 app route.
- [x] Vocal/instrumental generation, FLUX artwork, default DJ speech and MP3 reference requests succeeded in the live evidence run.
- [x] Generated audio decoded; two-track show is a single sequential mix.
- [x] Wrong-key request rejected; correct-key retry succeeded.
- [x] GitHub ZIP installed in a fresh virtual environment and seeded three sample songs.
- [x] 59 unit tests pass, including queue order, library refresh, blank storage default and waveform timing/amplitude.

The live API run is recorded in `scripts/evidence_output.json`; manual items below remain unchecked. The final Next-button browser check moved the visible player to its cue; the complete Previous-button recheck was interrupted when the tab became unavailable.

## Teammate installation and listening pass

- [ ] Download the ZIP for the exact submitted GitHub commit and extract it into a new folder.
- [ ] Follow only README.md and the supplied class credentials to install and launch it. Use a free AIJ_PORT if the default is occupied.
- [ ] Confirm three sample titles, audio files and covers are included.
- [ ] Generate a vocal song with chosen genre/mood/duration and AI lyrics; play it and inspect its cover.
- [ ] Generate an instrumental; confirm it has no sung lyrics and that the library table, gallery and queue update.
- [ ] Select two tracks in a deliberate order; build a default-voice show and hear DJ, song, DJ, song without overlap.
- [ ] Check play/pause, seek bar and Prev/Next segment buttons. Rebuild after shuffling and confirm the new order.
- [ ] Upload an MP3 reference, rebuild and judge voice similarity; repeat with a WAV reference.
- [ ] Rename a track, refresh, and confirm the title persists. Delete only a disposable test track and confirm it is removed.
- [ ] Check a failed request produces an understandable error and that retry works after correcting the cause.
- [ ] Judge cover relevance, sung pronunciation and overall listening quality.

## Team report and submission

- [ ] Record each teammate's meaningful contribution and review through GitHub issues/PRs.
- [ ] Explain the team's findings in its own words and retain the required starter-prompt language in the build record.
- [ ] Submit the repository URL, exact commit ID and matching GitHub ZIP. Verify grader access.
- [ ] Exclude credentials, uploaded recordings and runtime data from submission.
