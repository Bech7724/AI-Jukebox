# Assignment 3 rubric audit - November 1, 2026

Reviewed against all three pages of the supplied Assignment 3 PDF and the supplied class endpoint file. This is an agent review; it does not substitute for the team's explanation or a teammate's independent test.

## Required class services

The configured key matches the supplied file. It is not included in this report.

| Purpose | Class destination | Model |
| --- | --- | --- |
| Lyrics, artwork prompts, DJ scripts | http://dobolyi.com:9001/v1/chat/completions | cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit |
| Cover art | http://dobolyi.com:9006/v1/images/generations | black-forest-labs/FLUX.2-klein-4B |
| Music | http://dobolyi.com:9007/release_task and /query_result | ACE-Step/acestep-v15-xl-turbo |
| DJ voice/reference audio | http://dobolyi.com:9008/v1/audio/speech | chatterbox-v3 |

Live requests passed for all four services. No paid AI service is used. Port 9000 is rejected by the URL builder.

## Rubric findings

| Requirement | Finding |
| --- | --- |
| Custom vocal and instrumental songs | Genre, mood, duration and vocal controls are wired to the pipeline. Fresh real MP3s were decoded and checked against requested 12- and 10-second durations. Vocal lyrics came from Qwen; instrumental lyrics were empty. |
| New matching FLUX cover per song | Both new songs received valid 1024 x 1024 PNGs. Artwork prompts use the song's theme and mood. Artistic relevance remains a human judgment. |
| Integrated DJ, default and reference voice | Real Qwen scripts and Chatterbox audio were mixed between songs. The MP3 reference request produced a decoded speech file. Perceived voice similarity and a distinct WAV upload remain unchecked. |
| Queue sequencing and controls | A single WAV contains intro/song/intro/song with short gaps and no overlapping segments. Selected order is preserved. The final browser skip check is recorded below. |
| Three sample songs with titles and covers | All audio files and covers are present. Two samples record AUTO_LYRICS; the third is instrumental. The generation script uses the class pipeline; historical provenance was not independently reconstructed. |
| New tracks remain playable in the session | Local JSON-indexed library persists generated assets. Gallery, queue and table update after generation. |
| Status, errors and recovery | Stage progress and error wrappers exist. Live invalid-key requests returned 401; restoring a correct key succeeded in the earlier same-day recovery check. |
| Credentials and uploads excluded | No tracked runtime library or reference recordings. Supplied key values absent from tracked files and browser configuration at the initial scan. Final archive is scanned again before delivery. |
| Setup, screenshots, test evidence, design judgment | README now uses actual section names and measured evidence, with older screenshots labeled as such. Design discussion explains the continuous-mix tradeoff. The historical token-budget failure is identified as historical. |
| Independent ZIP deployment | Initial and subsequent GitHub ZIPs booted from extracted source. Dependencies were installed in a fresh virtual environment on this Mac. A teammate still needs to repeat the installation independently. |
| Exact repository, commit and matching GitHub ZIP | Final handoff supplies the repository commit and an archive downloaded from GitHub for that commit. |
| Meaningful teammate contributions and reviews | Two contributor accounts were observed; no issues or PRs existed at the initial audit. That does not establish every teammate's contribution or review. Team must complete/document it. |
| Retained starter prompt/Hermes build record | Original build conversation and prompt edits were unavailable; this requirement cannot be certified from the app. |

## Verified fixes

- Preserved selected queue order rather than library recency.
- Updated the library table immediately after generation.
- Fixed empty AIJ_DATA_DIR so generated files stay under the gitignored data directory.
- Fixed waveform amplitude calculations and scaled cue markers to the actual show duration; escaped track labels for valid SVG.
- Fixed skip-button targeting: Gradio's unused light-DOM audio element was being selected instead of the active player in its shadow DOM.
- Rejected the example credential placeholder and reserved agent port before requests.
- Clarified labels and planning behavior, removed duplicated genre-entry paths, and removed stale or unsupported README claims.
- Strengthened the live evidence runner so missing audio, missing covers, wrong duration or accepted bad credentials fail assertions rather than being marked PASS.

59 unit tests pass. The live evidence runner also completed successfully with its new assertions; measured results are in scripts/evidence_output.json and summarized in README.md.

## Remaining limits

A human should judge the music, pronunciation, artwork relevance and cloned voice, test a WAV reference, and perform the required teammate installation and peer review. Long-duration availability and Windows launch were not retested. Public visitors share one library. Share links are temporary and require the host to stay running.

## Final browser check

A two-track default-voice show was built through the live UI. With cues 0.00 / 12.23 / 28.58 / 39.49 seconds, clicking Next changed the visible player from 0:03 to 0:12; the active audio element reported 12.59 seconds and a 55.49-second duration. This confirms the fixed handler targeted the actual player. A full Previous-button recheck was interrupted when the browser tab became unavailable. Full listening, voice similarity and teammate checks remain unchecked.

## Display cleanup

Matched dark-theme colors to the light palette to keep labels readable, constrained the page width, and added stacked controls below 600 pixels. A browser check at a 644-pixel viewport measured a 644-pixel page with readable controls and no page overflow. The saved reviewed screenshot shows this view.
