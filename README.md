# Talking Trading Guy

An AI trading teacher that streams unattended on TikTok LIVE: live gold and Bitcoin charts drawn step by step,
lessons from a 67-lesson curriculum, a real human reference voice, live chat answers by name, a music bed,
and strict compliance rules (no signals, no predictions, no income claims, always admits it is an AI).

## Install on any Windows PC (one file)

1. Download **[TalkingGuy.exe](https://github.com/Roy-Mutwiri/TalkingGuy/releases/latest/download/TalkingGuy.exe)** and run it.
   Windows SmartScreen may warn because the file is not code-signed: choose *More info* > *Run anyway*.
2. The setup window installs everything it needs on its own: a private Python, Git, the app, its packages
   (a few hundred MB). No admin rights needed. Everything lives in `%LOCALAPPDATA%\TalkingGuy`.
3. The **launcher** opens. Go through its **Setup** tab once:
   - **Claude access**: paste an Anthropic API key (recommended; works on any PC), or sign in with your own
     Claude account on your own machine.
   - **TikTok**: your handle, so Theo can read your LIVE chat.
   - **Voice and audio**: the online voice works everywhere; on an NVIDIA GPU press *Install local AI voice*
     for the expressive Chatterbox voice (about 3 GB). Pick **CABLE Input** as the audio device and press
     *Install VB-Cable* if it is missing (that is the virtual microphone LIVE Studio listens to).
   - **Tools**: ffmpeg and the WebView2 runtime are installed automatically; *Install / repair everything* redoes it all.
4. Press **Start stream**. In TikTok LIVE Studio add a *Window Capture* of the window titled
   "Talking Trading Guy", set the microphone to *CABLE Output (VB-Audio Virtual Cable)*, portrait 9:16, go LIVE.
5. Use **Open operator console** to connect the chat, switch voice, toggle the *Popular music* bed, queue topics.

### Updates

The app folder is a git checkout of this repository. The launcher checks GitHub every 10 minutes and shows
**Update available** when there is a new commit. Press **Update now**: the stream is stopped, the new code is
pulled, changed packages are installed, and the stream restarts. Nothing is ever reinstalled, and the exe does not
change. Tick *Install updates automatically* if you prefer hands-off updates while the stream is stopped.

Each push to `main` also rebuilds `TalkingGuy.exe` (GitHub Actions) and republishes it as the *latest* release,
so a brand new PC always gets the current installer from the same link.

## For developers (run from source)

```
git clone https://github.com/Roy-Mutwiri/TalkingGuy.git
cd TalkingGuy
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt          # core (online voice)
.venv\Scripts\python -m pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python -m pip install -r requirements-gpu.txt      # optional: local GPU voices
copy .env.example .env                                           # then fill it in
.venv\Scripts\pythonw -m launcher                                # the same launcher the exe starts
start_stream.bat                                                 # or: the 24/7 supervisor directly
.venv\Scripts\python -m pytest                                   # unit tests
```

`python launcher\bootstrap.py` runs the installer logic against this checkout (no clone), and
`installer\build_exe.ps1` builds the exe locally with PyInstaller.

## Documents

- `RUNBOOK.md`: how everything works, operator guide, what to do when something breaks.
- `TIKTOK_RULES.md`: the platform rules this project is built around (music, financial content, AI disclosure).
- `app/brain/persona.md`: Theo's character sheet (edit freely).
- `app/brain/curriculum/`: the lessons.

## Claude access, honestly

Lessons and chat answers are written by Claude. For PCs you give to other people use an **Anthropic API key**
(console.anthropic.com): it is per-account, pay as you go, and permitted for third-party apps. The *Sign in with
my Claude account* option uses the Claude Code login through the Claude Agent SDK; Anthropic allows that only for
your own use on your own machines, not as the login of a product you distribute, so the launcher labels it that way.

## License and content

Music in `music/` is generated locally (original). The online music bed streams artist-uploaded tracks from the
open platform Audius through its public API; commercial songs are never fetched (see `TIKTOK_RULES.md`).
The voice reference clips in `app/voice/ref/` are public-domain LibriVox readings (CC BY 4.0, see
`ATTRIBUTION.json`). Chart rendering uses TradingView's open-source lightweight-charts (Apache-2.0).
