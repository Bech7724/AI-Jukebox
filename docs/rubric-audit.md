# Assignment 3 rubric audit - November 1, 2026

Reviewed against all three pages of the supplied MBAX 6418 Assignment 3 PDF and the supplied class-endpoints (2).txt (updated September 30, 2026). This is an agent verification report, not a substitute for the team's own explanation or teammate testing.

## Findings

The required AI features use only the class services. The runtime key matches the supplied endpoint file; no key is reproduced here. No app request uses port 9000. No paid AI service or external API key is needed.

| Feature | Actual destination | Model | Result |
| --- | --- | --- | --- |
| Lyrics, cover prompts, DJ scripts | http://dobolyi.com:9001/v1/chat/completions | cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit | Live generation passed |
| Cover art | http://dobolyi.com:9006/v1/images/generations | black-forest-labs/FLUX.2-klein-4B | Two new PNG covers generated |
| Music | http://dobolyi.com:9007/release_task, /query_result, audio download | Server reported acestep-v15-xl-turbo | Vocal and instrumental MP3s decoded |
| DJ speech and reference audio | http://dobolyi.com:9008/v1/audio/speech | chatterbox-v3 | Default and MP3-reference requests passed |

## Requirement-by-requirement review

| Requirement | Evidence / status |
| --- | --- |
| Style, mood, duration, vocal/instrumental controls | Present in the UI. Golden Hour: chillhop, warm sunset/easygoing, 12 seconds, vocal. Empty Streets: ambient, quiet rainfall, 10 seconds, instrumental. |
| AI-generated vocal lyrics and playable music | 101 words from Qwen; 192,812-byte vocal MP3; decoded duration exactly 12 seconds. Instrumental has no lyrics and decodes to 10 seconds. Both were saved in an isolated library. |
| A new matching FLUX cover per song | Both generated songs have valid PNG files; Golden Hour is 1024 x 1024. Prompts are derived from each song's title, genre, mood and lyrics. Human review of artistic fit remains unchecked. |
| Song-specific commentary, default voice | Two Qwen/Chatterbox intros, 157,484 and 144,812 bytes, in a four-segment show. |
| MP3/WAV reference support | UI accepts both formats. Live base64 MP3 reference produced a 195,116-byte intro with 43 words. Distinct WAV upload and perceptual voice similarity were not retested. No personal voice recording was used. |
| Sequential playback, auto-advance, no overlap | Mixer creates one continuous WAV, decoded duration 41.77 seconds. Cue times: 0.00 / 10.11 / 22.46 / 31.77 seconds, with 0.35-second gaps. Native play/pause and cue skip controls exist. Full browser listening and skip checks remain human checks. |
| Selected and shuffled queue order | Found a real bug: UI builder sorted by library recency instead of selected order. Fixed selection ordering. Regression test exercises both orders and ignores a stale ID. |
| Three bundled sample songs with titles/covers | Neon Afterglow and Morning Gold record AUTO_LYRICS; Midnight Cafe records INSTRUMENTAL. All three MP3s and covers exist in GitHub and seed a clean library. Generation script uses the same class pipeline. Historical asset provenance is recorded by metadata/script, not independently reconstructed. |
| Generation status and understandable, recoverable errors | Stage progress is wired to generation. Wrong key produced HTTP 401 with a readable invalid-key error. Restoring the correct key produced a 24,236-byte speech response. UI error wrappers and failure behavior covered in tests; browser error interaction not repeated. |
| Credentials server-side; no uploads in submission | Supplied credentials absent from tracked files, reachable Git history, and served browser configuration. No tracked data/ or samples/_stage/ files. .env is ignored and example configuration has placeholders. |
| README setup, screenshots, test evidence, design judgment | Present. Fresh evidence refreshed in scripts/evidence_output.json. README explains the continuous-mix choice and historical empty-LLM-response investigation. Port-conflict instructions corrected. |
| Independent installation from GitHub ZIP | Downloaded GitHub ZIP for 4271e0175ea87f4d933df06864873af634336e98, extracted separately, created a fresh venv and installed only requirements.txt. App booted on a free port and seeded three sample songs. This is agent testing on this Mac, not the required teammate run. |
| GitHub repository + exact commit + GitHub ZIP | Submit the reviewed final commit and a GitHub-generated ZIP for that exact commit. The locally produced make_zip.py archive is a development check; it does not replace the specifically required GitHub ZIP. |
| Issues, pull requests, teammate contributions/reviews | At inspection there were no GitHub issues or PRs. GitHub showed two contributors, which does not establish that every teammate contributed meaningfully or reviewed a teammate. Team must complete/document this itself. |
| Retained starter prompt / Hermes workflow | The original build conversation and team prompt edits were not provided; this process requirement cannot be verified from the running app. |

## Validation and practical limits

- 54 unit tests pass, including the new UI queue-order regression.
- Fresh live service results are in `scripts/evidence_output.json`. The LLM token-budget row explicitly describes a historical October 19 observation; it is not a newly reproduced failure.
- Real generated MP3s and the mixed WAV were decoded; validity is not inferred only from filename or response size.
- The live URL is temporary. It expires after about one week and depends on the host Mac and app process remaining available. A working GitHub ZIP is the grading requirement; the share URL is a convenience.
- A failed FLUX request saves the song with a warning and no cover. There is no dedicated cover-only retry; rerunning generation retries the full flow. Service load can still cause request timeouts.
- The team should listen to a two-track show, check play/pause/Next/Prev and voice similarity, review cover relevance, and have a teammate deploy the final GitHub ZIP before submission. Team explanations and peer review cannot be certified by an agent.
