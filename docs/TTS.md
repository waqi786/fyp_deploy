# Listen — voices, engines and licences

Resora reads papers, summaries and answers aloud (master prompt Part 12A). All speech goes through the **TTS Router**
(`apps/api/app/services/listen/tts.py`); no component calls a speech engine directly.

## Engines (priority per language)

| Tier | Engine | Where it runs | Cost to the user | Licence |
|---|---|---|---|---|
| Natural voice | Kokoro-82M via Kokoro-FastAPI (`TTS_KOKORO_URL`) | your server (`infra/docker-compose.tts.yml`) | `LISTEN_NEURAL_CREDITS_PER_MINUTE` (default 1) per started minute | Kokoro-82M weights Apache-2.0; Kokoro-FastAPI Apache-2.0 (StyleTTS2-derived code MIT) |
| Device voice | Web Speech API (`speechSynthesis`) | the user's browser / OS | free | provided by the OS / browser |

Not used, on purpose: non-commercial voices (Coqui XTTS, Meta MMS-TTS), unofficial wrappers of commercial services
(edge-tts), GPL components linked into the app, and cloud engines that may train on user text. A cloud engine can be
added later as another adapter in `tts.py` behind a config flag, for paid plans only, after checking its data terms.

## Voice registry (natural voices)

| Language | Voices (friendly name — locale) |
|---|---|
| English | Heart — en-US (female), Michael — en-US (male), Emma — en-GB (female), George — en-GB (male) |
| Spanish | Dora — es-ES (female), Alex — es-ES (male) |
| French | Siwis — fr-FR (female) |
| Hindi | Alpha — hi-IN (female), Omega — hi-IN (male) |
| Italian | Sara — it-IT (female), Nicola — it-IT (male) |
| Japanese | Hana — ja-JP (female), Kumo — ja-JP (male) |
| Portuguese | Dora — pt-BR (female), Alex — pt-BR (male) |
| Chinese | Xiaobei — zh-CN (female), Yunjian — zh-CN (male) |

Urdu, Arabic and other languages have **no natural voice yet**: Resora uses the device voice when the device has one
for that language, and otherwise says so (it never reads with a voice of another language — enforced on the server
in `TTSRouter._engine_for` and in the player's `pickDeviceVoice`). Engine names are never shown to users.

## What is read (clean listening script)

`apps/api/app/services/listen/script.py` turns PDF text into sections of sentences: ligatures and line-break
hyphenation repaired; running headers/footers, page and line numbers removed; citation markers, URLs, DOIs and e-mails
removed; the reference list skipped (toggle); figure/table captions become one short line; equation-like lines become
"Equation — see the paper."; abbreviations, Greek letters, units and comparison signs expanded per language; sentence
segmentation per script (Latin, Urdu/Arabic `۔ ؟`, CJK `。！？`, Devanagari `।`). When the paper is read in another
language, a short spoken note says it is a translated reading.

## Credits

Device voice: free. Natural voice: the player starts a session (`POST /api/v1/listen/sessions`) that reserves the
estimate; each spoken chunk is counted; `finish` commits only what was spoken and refunds the rest. A chunk that fails
on the engine is not charged and the player continues with the device voice. Audio is cached on disk
(`TTS_CACHE_DIR`, key = sha256(voice, language, text)).

## Player

Mini-player at the bottom of every page (keeps playing across tabs), full sheet with sections, sleep timer
(15/30/60 min, end of section), "Listen later" queue, listening settings, speed 0.75×–2×, voice menu, Media Session
(lock screen / headphone keys), keyboard `L`, follow-along sentence in the Reader, resume on any device
(`/api/v1/listen/progress`). Asking "read this paper aloud", "خلاصہ سناؤ", "把这篇论文读给我听" or "lee el resumen en voz
alta" in the Reader chat starts the player instead of asking the AI (`apps/web/src/listen/intent.ts`).
