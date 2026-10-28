# Chart Room: run book

An AI trading teacher that streams unattended through TikTok LIVE Studio.
Everything runs on this PC; only lesson writing and chat answers call the Claude API.

## One-time setup

1. **Keys**: copy `.env.example` to `.env` and fill in
   - `ANTHROPIC_API_KEY` (console.anthropic.com). Without it the stream runs in OFFLINE mode: template lessons from real data, canned chat replies.
   - `TIKTOK_UNIQUE_ID` = your TikTok handle without the `@` (needed to read LIVE chat).
   - `TWELVEDATA_KEY` optional (free key at twelvedata.com) for forex/stock candles. Without it the app uses Yahoo Finance data (delayed, fine for lessons).
2. **Check the machine**: `.venv\Scripts\python scripts\check_env.py` must print OK for GPU, Kokoro, audio device, chart library, Binance.
   The first run downloads the Kokoro voice model (about 330 MB).
3. **Hear the voice**: `.venv\Scripts\python scripts\test_voice.py --device Speakers` plays through your speakers. Change the voice with `TTS_VOICE` in `.env` (`am_michael`, `af_heart`, `bm_george`, `bf_emma` ...).
4. **TikTok LIVE Studio** (do once):
   - Add a source: **Window Capture** of the window titled "Chart Room stage" (started by `start_stream.bat`). Set the LIVE layout to portrait 9:16.
   - Audio: set the microphone to **CABLE Output (VB-Audio Virtual Cable)**. Mute any other mic. The teacher's voice is written to "CABLE Input" by the app, so it arrives in LIVE Studio as if it were a microphone.
   - Turn on TikTok's AI-generated content disclosure where LIVE Studio offers it, and keep the on-screen banner (it is always shown).

## Every stream (24/7)

1. Double-click `start_stream.bat`. It runs the supervisor (`supervise.ps1`), which starts the teacher and the stage window and restarts either one if it dies, rotates logs, and relaunches the window if the stage disconnects. Leave it running; it is designed for 24 hours a day, 7 days a week. Supervisor log: `logs/supervisor.log`.
2. In LIVE Studio, check the preview: chart moving, captions, character, ticker at the bottom. Press Go LIVE.
3. In the console (`open_console.bat`), type the TikTok username whose LIVE chat Haddan should answer and press Connect chat; it is remembered across restarts. The console shows the chat connection state. Comments are triaged like a human host would: urgent questions get answered at the next beat, on-topic remarks every third beat, idle chatter only between lessons, spam never. "Teach me X" requests become the next lesson automatically.
4. Optional: the operator page also offers: pause, skip beat, skip lesson, force a market tour, mute, inject a topic, simulate a viewer question.
4. To stop: close the console window of `start_stream.bat` (Ctrl+C) and end the LIVE in LIVE Studio.

## Personality, memory, voice

- **Persona**: `app/brain/persona.md` is the character sheet (name Haddan, backstory, speaking style, rituals). Edit it freely; it is read into every prompt. Haddan always admits to being an AI when asked.
- **Memory**: with `SUPERMEMORY_API_KEY` in `.env` the teacher remembers lessons taught, every viewer question and answer, and notable market events across restarts (Supermemory namespace `chartroom`). A local SQLite copy (`data_cache/memory.db`) is always kept, so memory works offline too. Regular viewers get greeted as regulars; lessons taught before are re-explained from a fresh angle.
- **Community mentions**: the free Telegram discussion group (link in the bio) is mentioned between lessons and in newcomer hooks on cooldowns, from a bank of 100 wordings that never repeat within a day (`app/brain/community.py`); every line states it is discussion only, no signals. `COMMUNITY_MENTIONS=0` disables.
- **No repetition**: lessons rotate with a 72-hour cooldown and never two from the same module in a row; every scripted line (greetings, bridges, recaps, market commentary, mistakes of the day) comes from phrase banks with a no-repeat picker whose history survives restarts; Claude lessons are told what was said last time and ordered to open differently.
- **Chart of the hour**: gold (XAU/USD) whenever the forex market is open (Sunday 23:00 UTC to Friday 22:00 UTC, daily break 22:00-23:00 UTC), Bitcoin otherwise. Lessons and the live market tour follow this rule automatically (`app/data/market_hours.py`).
- **Voice**: `TTS_ENGINE=edge` uses Microsoft's free online neural voices (default `en-US-AndrewMultilingualNeural`); if the online voice fails the local Kokoro voice takes over automatically and the online one is retried later. Tickers, jargon and numbers are rewritten for natural pronunciation (`app/voice/pronounce.py`): BTCUSDT becomes "Bitcoin", XAUUSD "gold", RSI "R S I", 79961 "79,961".

## The 3D room and the body

The lower part of the stage is a real-time 3D room (three.js, `app/stage/static/room3d.js`): a rigged human sits at the desk, posed and animated procedurally (breathing, head tracking the monitors, typing with both hands by inverse kinematics, mouse drift, coffee sips, leaning in on big moves, chair reclining with the body, foot taps). The four monitors are real screens fed by the live quote service, and they light the room.

**Changing the body**: drop a rigged humanoid into `app/stage/static/assets/room/` as `avatar.glb` or `avatar.fbx` and reload the stage window. Mixamo-rigged characters (any Mixamo character FBX, free with an Adobe account) and Quaternius rigs are supported. The current default is the CC0 hoodie character; `soldier.glb` and `xbot.glb` are fallbacks.

## Music, intonation, streamer behaviour

- **Music bed**: drop files you own or have a LIVE license for into `music/`; they loop quietly under the voice and duck when Haddan speaks (`MUSIC_LEVEL` in `.env`). While the stream runs, the **live music maker** (`app/voice/music_maker.py`, started by the supervisor, CPU only, below-normal priority) adds a new original 30 s beat every few minutes and retires the oldest generated ones past `MUSIC_MAKER_MAX`, so the bed never loops the same handful; the bed rescans the folder every 30 s and nothing repeats until every track has played. `MUSIC_MAKER=0` turns the maker off; your own files (any name not starting with `beat_`) are never touched. The console's **Skip track** button skips to the next folder track. Generate original beats locally with `scripts\make_music.py` (MusicGen on the GPU). Commercial songs, remixed or not, get LIVEs muted or ended: see `TIKTOK_RULES.md`.
- **Intonation**: the online voice gets a per-sentence rate and pitch from the current mood (teach, hype, calm, serious, warm) plus cues in the text (questions, exclamations, "watch this", numbers, short punchy lines) and a small per-sentence variation, so delivery never flattens into monotone.
- **Streamer behaviour**: welcomes joiners by name (batched), thanks follows, gifts and shares, nudges likes occasionally, re-orients newcomers with a hook every ~2.5 minutes, gives the chat an easy prompt every ~4 minutes, counts down into live market tours. The playbook is in `app/brain/persona.md`.
- **The room**: the real-person reference photo is the default stage (breathing, head motion while talking, live screens, real clock, slow live-camera drift, no chair motion). There is no lip-sync or rendered face: the voice plays the moment it is synthesised. The experimental 3D room is still available at `/stage?room=3d`.

## Draft-book analysis, real-time prices, human voice

- **Draft book**: `app/data/analysis.py` turns any loaded chart into a trader's markup, drawn step by step with a pen animation and narrated: swing labels (HH/HL/LH/LL), structure zig-zag, trendline and channel, support/resistance zones with touch counts, Fibonacci on the last impulse, equal highs/lows (liquidity), fair value gaps, order block, EMA 20/50, day high/low, measured move, written notes including the invalidation. It runs once near the end of every lesson and on every live market tour.
- **TradingView look**: the chart area is a TradingView-style window built on TradingView's own open-source renderer (lightweight-charts, Apache-2.0, attribution logo kept) plus their official plugin primitives (trend line, rectangle, session highlighting, volume profile) bundled from the cloned repo into `app/stage/static/vendor/lwc-plugins/`. Toolbar, timeframe buttons, left drawing bar, legend with O/H/L/C, footer ranges and UTC clock, and TradingView's dark palette. To rebuild the plugins after updating the repo: `npx esbuild <plugin>.ts --bundle --format=esm --external:lightweight-charts --alias:@tradingview/lwc-toolkit=<repo>/packages/lwc-toolkit/src --alias:fancy-canvas=<build>/node_modules/fancy-canvas` (see data_cache/lwc-build). Polish pass: TradingView default candle colors (#089981/#f23645), symbol watermark, bar-close countdown chip on the price axis, day separators, right sidebar and bottom tabs, second legend row (Vol, EMA 20), crosshair ping when a marker/note lands, live readout bottom-left. Every loaded chart is extended to the bar in progress from the live 1-minute tick candles (`Director._extend_with_live`), so the last bar is never older than one timeframe step.

- **Interacting with the chart (operator)**: the TradingView chrome in the stage window is live. Mouse wheel zooms, drag pans, drag the price axis or the time axis to stretch it, double-click an axis to reset it. Timeframe buttons (1m…W) ask the teacher to reload the live chart in that timeframe and keep it as the preferred timeframe for later live charts. Footer 1D/5D/1M… buttons set the visible range; `%`, `log`, `auto` switch the price scale. Left bar: Trend line (2 clicks), Horizontal line (1 click), Fib (2 clicks), Rectangle (2 clicks), Text, Measure (2 clicks, shows % and points); Esc returns to the cursor; the trash button removes your hand-drawn items. While you are touching the chart the teacher's automatic fit/scroll/zoom stay out of the way for 2 minutes (double-click to release early). Use the real 1080x1920 stage window for this, not the `?fit=1` preview (CSS scaling offsets the mouse). Candles keep their shape when you zoom out because every chart is loaded with up to 400 real bars behind the 90-bar analysis window, and scrolling to the left edge pages in another 400 (stage sends `chart_more`, director answers with `prepend`) until the source has no more. Minimum bar spacing is 0.5 px, the TradingView value.
- **Live charts only**: the big chart is always the real live chart. Lessons load the last ~90 real bars ending now (gold or Bitcoin by the market-hours rule, 15m/1h/4h), the example pattern is the most recent instance on that live chart, and the current bar keeps updating from the tick feed while Haddan talks. The chart label reads "live · tf"; the price readout shows the live price at all times.
- **Real-time prices**: crypto ticks from Binance; gold and forex from Swissquote's public bank feed every two seconds (bid/ask mid), with one-minute candles built from the ticks. Yahoo is only used once at startup for history. The live market tour uses those one-minute live candles for the chart of the hour.
- **Human voice layer**: per-sentence mic chain (high-pass, presence, compression), synthesized breaths before some sentences, varying gaps, a faint room tone instead of digital silence, plus text-level fillers, tag questions and thinking pauses (`app/voice/humanize_audio.py`, `app/voice/disfluency.py`). Serious lines (disclaimers) are left clean.

## What the teacher does on its own

- Plays lessons from the curriculum (`app/brain/curriculum/*.md`, 67 lessons in 10 modules), rotating so nothing repeats within 48 hours, two lessons always pre-generated.
- Every ~25 minutes: a live "market tour" on the chart of the hour (gold or Bitcoin) with candles updating in real time and purely descriptive commentary; every ~40 minutes a small ritual (mistake of the day, honesty line).
- Reads the LIVE chat, moderates it, and answers one question every third beat and up to three between lessons, by name.
- Refuses signals, predictions, targets and income claims (system prompt + regex filter), and states it is an AI when asked.
- Logs to `logs/stream.log`. Lesson history in `data_cache/lesson_history.json`. Candle cache in `data_cache/candles.db`.

## Testing without TikTok

- `.venv\Scripts\python -m app.run --offline` then open http://127.0.0.1:8000/stage?fit=1 in any browser (fit mode scales the vertical stage to your window).
- `.venv\Scripts\python scripts\dry_run_lesson.py tests\fixtures\sample_lesson.json --voice` plays a fixed lesson with synthetic candles (hub must be running).
- `.venv\Scripts\python -m pytest` runs the unit tests (schema, compliance filter, scanners, curriculum).

## If something breaks

| Symptom | What to do |
|---|---|
| No sound in LIVE Studio | Check `.env` `AUDIO_DEVICE=CABLE Input`, run `scripts\test_voice.py --device list`, confirm LIVE Studio mic = CABLE Output |
| "Invalid sample rate" in log | Fixed in code (audio is resampled to the device rate); if it returns, pick the MME device: `AUDIO_DEVICE=CABLE Input (VB-Audio Virtual C` |
| Lessons say "planner failed ... using template" | API key missing/invalid or network; stream continues with template lessons |
| Chat never answers | `TIKTOK_UNIQUE_ID` missing, or you are not live yet; the reader retries every 30 s |
| Chart empty | Data source down; check Binance reachability with `scripts\check_env.py` |

## Compliance reminders

Unattended AI streams can still be flagged as unoriginal/low-interaction by TikTok. The design keeps real-time chat answers, moving charts, a visible character and an always-on disclosure banner, and never gives signals. If LIVE access gets restricted, use the recorded clips (Phase 8, `app/clips`) for the feed with the AI label turned on.

## Streamer training pack (host behaviour)

The Trade Fix streamer training starter lives in `training/streamer_pack/` (48 synthetic scenarios, 8 skills, respond/commentate/wait targets, 12 preference pairs, rubric). It is wired into the runtime, not just stored:

- `app/brain/host_policy.py`: the respond / commentate / wait decision. Waits when speech is playing, when a question is still collecting answers, when a comment is a near-duplicate of something answered in the last 10 minutes, or when chat text looks like an instruction. Orients newcomers, slows down for struggling viewers, deflects predictions, says when the quote is missing, never treats a chat claim as a verified result, strips emoji from speech. Used directly in offline mode and as the safety layer in front of Claude.
- `app/brain/host_demos.py`: retrieves 4 relevant demonstrations from the pack's *train* split for every Claude chat reply (validation/test never reach a prompt). `PROPERTIES` (the 7 host properties + hard failures) is in the responder's system prompt and in `persona.md`.
- Runtime: `Director.ask_audience()` asks one answerable question, opens a 20 s answer window (chat answers bypass moderation while it is open), then `_callback_line()` refers back to real names only. Quizzes and the chat prompts use it. Claude replies carry `delivery` (mapped to voice mood) and `follow_up`; follow-ups go to a promise ledger and are paid off by `deliver_promises()` after the lesson block (dropped silently after 30 min, never claimed).
- Evaluate: `python scripts/eval_host.py --split validation|test` (offline policy; add `--claude` with a key). Reports action agreement per skill, reply-target agreement and the rubric's hard failures. Current: 8/8 validation, 8/8 test, 0 hard failures.
- Fine-tune later (needs 2,000-5,000 reviewed moments first): `python scripts/train_host_lora.py` (TRL SFT, QLoRA on a 3B instruct model, then `--dpo`). Not run yet; smoke pipeline only.
- Growing the corpus: log real moments from your own streams (`data_cache/segments.jsonl` boundaries + stream.log) and review them with `evaluation_rubric.md` before adding to `annotated_examples.jsonl` (keep whole sessions in one split).

## Haddan's energy profile (cheerful host that drives the show)

- Baseline upbeat (7/10): the Edge voice "teach" mood is now +6% rate / +2 Hz; `cheerful` (+8/+5), `excited` (+14/+9, brief, only when something real happens), `curious` (+3/+5), `considerate` (-7/-3, when someone describes a loss). Every delivery label from the brain maps to one of these, so the label changes the audio. Hear them: `python scripts/voice_sample.py` writes `data_cache/voice_samples/<mood>.wav`.
- Initiative: when nothing is queued and chat is quiet, Haddan starts something after `QUIET_INITIATIVE_S` (12 s, in `app/brain/host_policy.py`, tune it): a live-quote observation (real number only), a mini challenge with a 20 s answer window and a hint at 9 s, a continuation, or the disclaimer, rotating.
- Participation: quizzes and challenges collect real answers; a correct answer is celebrated by name ("Sam, you spotted it!"), otherwise real answers are acknowledged, and if nobody answers the reveal happens naturally. Never invented participation.
- Chat reactions: observations ("it closed above on the second attempt") are celebrated; losses get a considerate, focused reply; stale comments are dropped by priority (high 10 min, medium 4 min, low 90 s) instead of being answered late; after a good exchange Haddan sometimes bridges into the next activity.
- Movement (photo room): `gesture` (hand lift on cheerful/excited lines), `celebrate` (double nod + lean), `attentive` (leans in for the answer window), `considerate` (slow nod, slight lean), `glance` (turns to the chart for an observation).

## Showman layer (energy for TikTok LIVE)

`ENERGY=0.85` in `.env` (0.5 = calm teacher). At 0.7+ Haddan runs as a show host (`app/brain/showman.py`, hooked into `app/director.py`):

- **Live move reactions**: a real move of 0.12% (gold) / 0.35% (BTC) / 0.06% (EUR/USD) inside 60 s fires once per 150 s. The stage shows a "+0.31% in the last minute" pop and the trader reacts instantly; Haddan reacts out loud at the next beat boundary in the excited mood, with the real price. No predictions, only "watch the level".
- **Fast welcomes**: joiners are welcomed by name every 20 s (was 60) with energetic lines; viewer milestones every +25 viewers; gifts and shares get hype lines with a celebrate reaction.
- **Like goal**: real like counts from TikTok events drive a goal bar on the room (100, 250, 500, 1k, 2.5k...). Haddan calls the goal every ~3 min while climbing and celebrates when it is hit.
- **Cliffhangers**: before the last two beats of a lesson he teases what is actually queued next. Hooks for newcomers every 90 s (was 150).
- **Voice**: base mood `show` (+10% rate, +4 Hz), `excited` (+17%, +10 Hz) with exclamation lift; `energize()` turns short flat openers into exclamations on show moods only. Music lifts by 60% during answer windows and excited lines.
- **Audition voices**: `python scripts/voice_sample.py --voices` writes `data_cache/voice_samples/voice_<name>.wav` for six energetic Edge voices (Andrew, Brian, Guy, Christopher, Ryan, William) saying the same show line. Pick the liveliest in the console voice selector.

## Standalone windows (no browser)

The stage and the console open in our own windows: `python -m app.stage_window` (frameless 1080x1920 stage, title "Talking Trading Guy", captured by LIVE Studio as a window) and `python -m app.stage_window --console` (`open_console.bat`). `open_stage_preview.bat` opens a half-size preview. The window hosts the Windows WebView2 runtime (part of Windows 11) through pywebview; it waits for the hub, loads the page, and reloads by itself if the hub restarts. `supervise.ps1` launches and watches `app.stage_window` instead of Chrome. Add `--framed` for a normal title bar.

**Full resolution.** By default the stage window is a true 1080x1920 at device scale 1, even on a 1440 px screen: the launcher lifts the WinForms maximum size and places the window with SetWindowPos, so the bottom 480 px sit below the screen edge but are still rendered. LIVE Studio's window capture takes the whole window, so the stream gets every pixel at native resolution. The hub logs `stage ready: 1080x1920 css px, dpr 1`. If LIVE Studio's preview ever shows the bottom cut off, start the window with `--fit-screen` (or set `STAGE_FIT_SCREEN=1` in the environment of `supervise.ps1`): then the window is the largest 9:16 that fits the screen and the page renders at a matching device scale factor (layout still 1080x1920 CSS px, mouse interaction still exact). In LIVE Studio add a **Window capture** of "Talking Trading Guy" and stretch it to the full canvas (right-click the source, Fit to screen).

**Chart theme.** The chart window uses TradingView's light theme (white background, #131722 text, 18 px axis labels, 30 px live price) for legibility on phones. Session shading and day separators are off.

## Disappearing chart: root causes (fixed 2026-10-26)

Stage-side errors now land in `logs/stream.log` as `stage error: ...`. Two causes were found in the browser console:
1. `Value is null` in the candlestick series: a history bar with a null open/high/low reached `setData`, the library dropped the whole series. Now the director validates every bar it sends and `chart.js` cleans data (finite OHLC, ascending unique times) before any `setData`.
2. `Cannot update oldest data`: a live bar update arrived while the draw-in replay was still running, so every later replay step threw and the chart stayed half-drawn. Updates during a replay are now merged into the pending data instead of hitting the series; a failing replay step finishes with the full data set.
Also guarded: `resize()` ignores 0x0 (hidden window), a `load` without candles keeps the current chart.

## On-stage operator dock

Move the mouse over the stage window and a small dock appears at the top right (it fades out 2.5 s after the mouse stops, so it is not part of the broadcast): **Pause / Resume**, **Mute / Unmute** (stops the voice immediately), **Skip** (skip the current beat). Keyboard: `P`, `M`, `S` work any time the stage window has focus. The teacher reports its state back, so the buttons and the "Paused" / "Muted" pills in the header always show the truth, even after a reconnect. The console window has the same controls plus topic injection and voice selection.

## Voice: broadcast microphone chain

`app/voice/humanize_audio.py` is the chain a streaming engineer puts after a studio microphone: 24 dB/oct high-pass at 80 Hz, mud cut at 240 Hz, presence at 2.8 kHz, air shelf at 9.5 kHz, an aural exciter that adds real sparkle above the TTS codec's cut-off, a relative de-esser (only acts when an "s" stands out), a soft-knee 3.2:1 compressor, loudness normalisation to -17 dBFS on the loud frames, and a look-ahead limiter at -1 dBFS (never clips). Breaths are quiet and natural; the old room-tone hiss is gone (studio silence at -72 dBFS, inaudible) and the player's idle noise floor is effectively off.

Measure and listen: `python scripts/voice_check.py` writes `data_cache/voice_samples/chain_raw.wav`, `chain_old.wav`, `chain_new.wav` and prints loud-frame RMS, peak, crest, level steadiness, noise floor, spectral balance, sibilance and clipping. Reference run (2026-10-27): floor -64 -> -85 dBFS, steadiness ±3.9 -> ±1.8 dB, presence +4.5 dB, air +5 dB, 0 clipped samples. Tuning lives at the top of `mic_chain()`.

## Teaching flow (how lessons are built)

`app/brain/teaching.md` is the doctrine, distilled from Rosenshine's principles, Feynman/3Blue1Brown, Mind Math Money, Al Brooks, Adam Khoo, Rayner Teo, Mark Douglas, Wyckoff, Brian Shannon, signposting research and live educators. Every lesson follows one arc: hook, plain words + analogy, point at it on the live chart, the story (who's in control, who's trapped), what confirms it and where it's wrong (invalidation line on the chart), the beginner mistake, one check question to the chat (answer window, real names called back), recap in one breath (takeaway, invalidation, what to watch next).

- `app/brain/teaching.py` holds the library: plain definition, analogy, story, confirmation, mistake, check question and hint for 35 concepts (wicks, engulfing, structure, liquidity, order blocks, fair value gaps, VWAP, RSI, risk, psychology, Wyckoff, absorption, delta, drawdowns...). `notes_for(title, body)` matches 67 of the 68 curriculum lessons to a specific note; the rest get a sound default.
- Offline (`TemplatePlanner.build`) produces the arc from a real example window: 10-12 beats, exactly one `ask` beat, the invalidation hline, a recap with "what to watch next".
- Claude (`LessonPlanner`) gets the doctrine in its system prompt plus the arc and the concept's notes in the user prompt, and must put the check question in a beat's `ask` field.
- The director opens a 20 s answer window on an `ask` beat, celebrates a correct answer by name, otherwise calls back real answers.

## Claude models, credits and spend

- `CLAUDE_MODEL` (lessons, default `claude-opus-5-5`) and `CLAUDE_CHAT_MODEL` (chat replies + comment triage, default `claude-sonnet-5`) in `.env`. The persona/doctrine system prompt is prompt-cached on every call.
- The hub log prints a running meter: `Claude spend today $x.xx over N calls` on every call and on every lesson line. Prices are the public list prices (estimates).
- If the account has no credits the API answers "credit balance is too low"; the brain then pauses itself for 30 minutes and the stream keeps running on template lessons and the offline host policy (no errors every call). Add credits at console.anthropic.com, Billing; it picks the brain back up automatically.
- Rough cost at 24/7 (lessons every ~6 min, ~600 chat replies/day): Opus 5.5 lessons + Sonnet 5 chat about $20-30/day; Sonnet 5 for lessons too about $12-18/day. Less with fewer lessons per hour or quieter chat.

## Running the brain on the Claude Max subscription (no API credits)

`BRAIN_BACKEND=claude_code` in `.env` makes every structured call go through Claude Code's harness (the Claude Agent SDK) using the claude.ai login on this machine: run `claude` once in a terminal and `/login` with the Max account; `claude auth status` must show `loggedIn: true`, `subscriptionType: max`. Each call spawns the CLI with no tools, one turn and a JSON schema; ANTHROPIC_API_KEY is removed from that process's environment so the login authenticates.

Facts to know:
- Anthropic's Agent SDK docs say products built on the SDK must use API keys and that claude.ai logins are not offered for third-party products unless approved. This setup uses only the owner's own login on the owner's own machine. It is your call; the API-key backend (`BRAIN_BACKEND=api`) is one line away.
- Subscription usage windows (5-hour and weekly) apply. When a call comes back limited, the brain pauses for 10 minutes and the stream runs on template lessons and the offline host policy; it resumes by itself. Sonnet is the default for everything to stretch the window (`CLAUDE_MODEL=claude-opus-5-5` for Opus lessons if the window allows).
- Latency is about 7-8 s per call (CLI start-up), fine for pre-generated lessons; chat replies arrive a beat later than with the API.
- The log line `LessonScript claude-sonnet-5 via claude.ai login: ...` confirms the path; the meter shows plan usage at list price for reference only (nothing is billed).

## Host-technique study (streamer_style)

`scripts/style_from_streams.py --urls training/streamer_style/urls.txt` downloads audio only from the reference host's streams, transcribes on the GPU (faster-whisper large-v3-turbo), measures cadence (talk share, words per minute, questions per 10 min, greetings, chat addresses, hype lines, laughs, silences) into `training/streamer_style/style_profile.json` + `style_report.md`, then has Claude write ORIGINAL demonstrations of each technique in Haddan's voice (`demos.jsonl`, same schema as the starter pack). Those demos join the retrieval set the chat brain sees (`host_demos.load_train`). Nothing from the host is copied: no voice, no catchphrases, no name, no trades. Progress: `training/streamer_style/pipeline.log`; the stages are resumable (`--stage transcribe|analyze|demos`).

Language switching in the voice: multilingual Edge voices (Andrew/Brian/Ava/Emma "Multilingual") auto-detect language per sentence and drift on names and symbols. Default is now `en-US-GuyNeural` (English-only) and all speech text is folded to ASCII before synthesis.

## Expressive voice (laughs, sighs) with Chatterbox-Turbo

`TTS_ENGINE=chatterbox` (default now). Chatterbox-Turbo (Resemble AI, MIT) runs on the GPU and performs non-verbal tags inline: `[laugh] [chuckle] [sigh] [clear throat] [gasp] [groan] [sniff] [cough]`. The brain writes them sparingly in replies and lessons (one per reply, two or three per lesson); the pronunciation pass keeps them, captions strip them, and if the voice falls back to Edge the tags are removed so nothing reads "laughs" aloud. The timbre comes from `app/voice/ref/theo_ref.wav`, a synthetic clip rendered from an Edge voice (no real person cloned); drop another 10 s+ WAV in `app/voice/ref/` and pick it in the console to change the voice. Speed on the RTX 5060 Ti: about 0.45x real time, first audio after ~2 s. Edge is the automatic fallback. Listen: `data_cache/voice_samples/chatterbox_tags.wav`.

Install notes: chatterbox-tts pins old torch/transformers; it is installed with `--no-deps` on the project's torch 2.11 and works; `app/voice/chatterbox_voice.py` patches two float64/float32 mismatches at load time.

Reference voices on disk (`app/voice/ref/`): `theo_ref.wav` (synthetic), `libritts_3752.wav` and `libritts_2803.wav` (real human readers from LibriTTS-R, LibriVox public-domain readings, CC BY 4.0; attribution in `ATTRIBUTION.json`). Default is `libritts_3752` for testing; change in the console (Voice) or with `TTS_REF` in `.env`. `python scripts/fetch_public_voices.py` fetches fresh candidates and renders a comparison line for each into `data_cache/voice_samples/ref_<speaker>.wav`.

## Non-verbal sounds (laughs, sighs, chuckles, gasps, groans, throat-clears, sniffs)

Three layers decide them. (1) The brain writes tags where a person would make the sound (one per reply, two or three per lesson, never near numbers or in the recap). (2) The phrase banks and live-move reactions carry them where they are always right (a laugh on a nailed answer, a gasp on a real move, a chuckle on a self-deprecating line). (3) `app/voice/nonverbal.py` adds one where neither did, with discipline: cue words (a loss earns a sigh, "you spotted it" earns a laugh, a chased trade earns a groan, "whoa" earns a gasp), mood palettes (excited and cheerful laugh more, considerate sighs, serious never), a 35 s minimum gap, never on disclaimers, recaps or numbers-only lines, placed at sentence boundaries. `ENERGY` scales the frequency. Every tagged utterance is logged as `nonverbal: ...`.

Hear every sound on the current voice: `data_cache/voice_samples/tags_board.wav` (plain, laugh, chuckle, sigh, gasp, groan, clear throat, sniff, cough). Each adds 0.4-1.2 s of real sound.

## No AI traces in speech (Wikipedia: Signs of AI writing)

Three defences. (1) `HUMAN_RULES` in `app/brain/deai.py` is appended to the persona on every Claude call: the banned vocabulary (delve, tapestry, testament, crucial, pivotal, underscore, landscape, vibrant, robust, seamless, utilize, foster, showcase, enhance, navigate, journey, embark, unlock, realm, elevate, empower, intricate, meticulous, interplay, boasts, additionally, furthermore, moreover...), "is" instead of "serves as / represents / refers to", no negative parallelism, no groups of three, no summary endings or filler, no sycophancy or chatbot talk, no em dashes, hedge once at most. (2) `deai.clean()` scrubs every utterance before speech and every brain output before memory: vocabulary rewritten to plain speech, artifact sentences dropped whole, "not only X but also Y" and "it's not about X, it's about Y" flattened, em dashes and curly quotes removed. Trading terms are preserved (leverage, key level, highlight on a chart). Each scrub is logged as `deai:`, every utterance as `say:`. (3) `python scripts/ai_tells_audit.py` checks all static phrase banks (must be zero) and reports how often the brain still produced a tell, from the log.

## Progress board and the slow link

`open_progress.bat` (or `python -m app.stage_window --progress`) opens a live board: stream study per file, model downloads with percentages, GPU, and Haddan on air. The machine's internet is a 10 Mbps line, and LIVE Studio's upload competes with every download, so big models arrive one at a time.
