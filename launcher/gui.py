"""Talking Trading Guy launcher window (tkinter, ships with Python; nothing to install).

Tabs: Stream (start/stop, console, update), Setup (Claude access, TikTok, voice, audio, tools), Settings (.env),
Logs. Long jobs run in a worker thread and print into the activity box; the UI never blocks.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk

from . import process, setup_steps, updater
from .common import ENV_FILE, LOGS, ROOT, TOOLS, audio_outputs, gpu_name, gpu_voice_installed, has_ffmpeg, has_vbcable, has_webview2, read_env, write_env

TITLE = "Talking Trading Guy"
POLL_STATUS_S = 5
POLL_UPDATES_S = 10 * 60
SETTINGS_KEYS = [
    ("TIKTOK_UNIQUE_ID", "TikTok handle (without @)"),
    ("AUDIO_DEVICE", "Audio output device (name contains)"),
    ("TTS_ENGINE", "Voice engine: edge | chatterbox | kokoro"),
    ("TTS_VOICE", "Edge voice id (edge engine)"),
    ("ENERGY", "Show energy 0..1"),
    ("MUSIC_LEVEL", "Music bed level 0..0.5"),
    ("CLAUDE_MODEL", "Lesson model"),
    ("CLAUDE_CHAT_MODEL", "Chat model"),
    ("TWELVEDATA_KEY", "TwelveData key (optional)"),
    ("SUPERMEMORY_API_KEY", "Supermemory key (optional)"),
]


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.geometry("860x640")
        self.root.minsize(760, 560)
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        self.update_state: updater.UpdateState | None = None
        self._build()
        self.root.after(200, self._pump)
        self.root.after(500, self._poll_status)
        self.root.after(3000, self._poll_updates)
        if not ENV_FILE.exists() or not read_env().get("TIKTOK_UNIQUE_ID"):
            self.nb.select(self.tab_setup)
            self.log("Welcome. Go through the Setup tab once: Claude access, your TikTok handle, voice and audio. Then press Start stream.")

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text=TITLE, font=("Segoe UI", 15, "bold")).pack(side="left")
        self.lbl_version = ttk.Label(top, text=updater.current_version(), foreground="#667")
        self.lbl_version.pack(side="right")

        bar = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        bar.pack(fill="x")
        self.lbl_status = ttk.Label(bar, text="Stream: checking...", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side="left")
        self.lbl_update = ttk.Label(bar, text="", foreground="#b8860b")
        self.lbl_update.pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.tab_stream = ttk.Frame(self.nb, padding=10)
        self.tab_setup = ttk.Frame(self.nb, padding=10)
        self.tab_settings = ttk.Frame(self.nb, padding=10)
        self.tab_logs = ttk.Frame(self.nb, padding=10)
        for tab, name in ((self.tab_stream, "Stream"), (self.tab_setup, "Setup"), (self.tab_settings, "Settings"), (self.tab_logs, "Logs")):
            self.nb.add(tab, text=name)
        self._build_stream()
        self._build_setup()
        self._build_settings()
        self._build_logs()

        box = ttk.LabelFrame(self.root, text="Activity", padding=6)
        box.pack(fill="both", expand=False, padx=12, pady=(0, 10))
        self.out = scrolledtext.ScrolledText(box, height=9, font=("Consolas", 9), state="disabled", wrap="word")
        self.out.pack(fill="both", expand=True)

    def _build_stream(self) -> None:
        f = self.tab_stream
        row = ttk.Frame(f); row.pack(fill="x", pady=4)
        ttk.Button(row, text="Start stream", command=self.start).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Stop stream", command=self.stop).pack(side="left", padx=6)
        ttk.Button(row, text="Open operator console", command=process.open_console).pack(side="left", padx=6)
        ttk.Button(row, text="Stage preview", command=process.open_stage_preview).pack(side="left", padx=6)
        row2 = ttk.Frame(f); row2.pack(fill="x", pady=4)
        self.btn_update = ttk.Button(row2, text="Update now", command=self.do_update)
        self.btn_update.pack(side="left", padx=(0, 6))
        ttk.Button(row2, text="Check for updates", command=lambda: self._poll_updates(manual=True)).pack(side="left", padx=6)
        self.var_auto = tk.BooleanVar(value=read_env().get("AUTO_UPDATE", "0") == "1")
        ttk.Checkbutton(row2, text="Install updates automatically when the stream is stopped", variable=self.var_auto,
                        command=lambda: write_env({"AUTO_UPDATE": "1" if self.var_auto.get() else "0"})).pack(side="left", padx=12)
        ttk.Separator(f).pack(fill="x", pady=10)
        txt = ("How a stream day works:\n"
               "1. Start stream. The stage window opens (that is what TikTok LIVE Studio captures: Window Capture of \"Talking Trading Guy\").\n"
               "2. In LIVE Studio set the microphone to CABLE Output (VB-Audio) and go LIVE in portrait 9:16.\n"
               "3. Open the operator console to connect the LIVE chat, switch voice, queue topics.\n"
               "4. Leave it running. The supervisor restarts anything that dies, 24/7. Updates: press Update now when the badge shows.")
        ttk.Label(f, text=txt, justify="left", wraplength=780).pack(anchor="w")
        row3 = ttk.Frame(f); row3.pack(fill="x", pady=(14, 0))
        ttk.Button(row3, text="Open app folder", command=lambda: process.open_folder(ROOT)).pack(side="left", padx=(0, 6))
        ttk.Button(row3, text="Open logs folder", command=lambda: process.open_folder(LOGS)).pack(side="left", padx=6)
        ttk.Button(row3, text="Run environment check", command=lambda: self.job(setup_steps.check_environment)).pack(side="left", padx=6)

    def _build_setup(self) -> None:
        f = self.tab_setup
        env = read_env()
        # Claude
        g = ttk.LabelFrame(f, text="1. Claude access (the brain)", padding=8); g.pack(fill="x", pady=4)
        self.var_brain = tk.StringVar(value="login" if env.get("BRAIN_BACKEND") == "claude_code" else "api")
        ttk.Radiobutton(g, text="Anthropic API key (works on any PC; pay as you go)", variable=self.var_brain, value="api").grid(row=0, column=0, sticky="w", columnspan=3)
        ttk.Label(g, text="Key:").grid(row=1, column=0, sticky="e")
        self.ent_key = ttk.Entry(g, width=58, show="*")
        self.ent_key.insert(0, env.get("ANTHROPIC_API_KEY", ""))
        self.ent_key.grid(row=1, column=1, sticky="w", padx=4)
        kb = ttk.Frame(g); kb.grid(row=1, column=2, sticky="w")
        ttk.Button(kb, text="Save & test", command=lambda: self.job(lambda log: setup_steps.set_api_key(self.ent_key.get(), log))).pack(side="left")
        ttk.Button(kb, text="Get a key", command=lambda: webbrowser.open("https://console.anthropic.com/settings/keys")).pack(side="left", padx=4)
        ttk.Radiobutton(g, text="Sign in with my Claude account (claude.ai subscription; for your own machines only)", variable=self.var_brain, value="login").grid(row=2, column=0, sticky="w", columnspan=3, pady=(6, 0))
        lb = ttk.Frame(g); lb.grid(row=3, column=1, sticky="w", pady=2)
        ttk.Button(lb, text="Sign in", command=lambda: self.job(setup_steps.claude_login)).pack(side="left")
        ttk.Button(lb, text="Check sign-in", command=lambda: self.job(setup_steps.claude_status)).pack(side="left", padx=4)
        self.lbl_brain = ttk.Label(g, text="Status: " + setup_steps.brain_summary(), foreground="#667"); self.lbl_brain.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        # TikTok
        g2 = ttk.LabelFrame(f, text="2. TikTok", padding=8); g2.pack(fill="x", pady=4)
        ttk.Label(g2, text="Your handle (without @):").pack(side="left")
        self.ent_tiktok = ttk.Entry(g2, width=28); self.ent_tiktok.insert(0, env.get("TIKTOK_UNIQUE_ID", "")); self.ent_tiktok.pack(side="left", padx=6)
        ttk.Button(g2, text="Save", command=self._save_tiktok).pack(side="left")
        # Voice + audio
        g3 = ttk.LabelFrame(f, text="3. Voice and audio", padding=8); g3.pack(fill="x", pady=4)
        gpu = gpu_name()
        ttk.Label(g3, text=f"GPU: {gpu or 'none detected'}   |   local AI voice: {'installed' if gpu_voice_installed() else 'not installed'}").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Button(g3, text="Install local AI voice (NVIDIA GPU, ~3 GB)", command=lambda: self.job(setup_steps.install_gpu_voice)).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Button(g3, text="Use online voice (no GPU)", command=lambda: (write_env({"TTS_ENGINE": "edge"}), self.log("Voice: online (Edge)."))).grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(g3, text="Audio output (pick CABLE Input for LIVE Studio):").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.cmb_audio = ttk.Combobox(g3, width=48, values=audio_outputs()); self.cmb_audio.set(env.get("AUDIO_DEVICE", "CABLE Input"))
        self.cmb_audio.grid(row=3, column=0, columnspan=2, sticky="w")
        ab = ttk.Frame(g3); ab.grid(row=3, column=2, sticky="w", padx=6)
        ttk.Button(ab, text="Save", command=lambda: (write_env({"AUDIO_DEVICE": self.cmb_audio.get()}), self.log(f"Audio device: {self.cmb_audio.get()}"))).pack(side="left")
        ttk.Button(ab, text="Refresh", command=lambda: self.cmb_audio.configure(values=audio_outputs())).pack(side="left", padx=4)
        ttk.Button(g3, text=("VB-Cable: installed" if has_vbcable() else "Install VB-Cable (virtual mic for LIVE Studio)"), command=lambda: self.job(setup_steps.install_vbcable)).grid(row=4, column=0, sticky="w", pady=(6, 0))
        # Tools
        g4 = ttk.LabelFrame(f, text="4. Tools", padding=8); g4.pack(fill="x", pady=4)
        ttk.Label(g4, text=f"ffmpeg: {'ok' if has_ffmpeg() else 'missing'}   |   WebView2: {'ok' if has_webview2() else 'missing'}   |   tools folder: {TOOLS}").pack(side="left")
        ttk.Button(g4, text="Install / repair everything", command=lambda: self.job(lambda log: setup_steps.first_run_setup(log, want_gpu_voice=False))).pack(side="right")

    def _build_settings(self) -> None:
        f = self.tab_settings
        ttk.Label(f, text="Saved to .env in the app folder. Restart the stream for changes to apply.").pack(anchor="w")
        grid = ttk.Frame(f); grid.pack(fill="x", pady=6)
        env = read_env()
        self.setting_entries: dict[str, ttk.Entry] = {}
        for i, (key, label) in enumerate(SETTINGS_KEYS):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="e", padx=(0, 8), pady=2)
            e = ttk.Entry(grid, width=60, show="*" if "KEY" in key else "")
            e.insert(0, env.get(key, ""))
            e.grid(row=i, column=1, sticky="w", pady=2)
            self.setting_entries[key] = e
        ttk.Button(f, text="Save settings", command=self._save_settings).pack(anchor="w", pady=6)
        ttk.Button(f, text="Edit persona (Haddan's character sheet)", command=lambda: process.open_folder(ROOT / "app" / "brain" / "persona.md")).pack(anchor="w")

    def _build_logs(self) -> None:
        f = self.tab_logs
        self.txt_log = scrolledtext.ScrolledText(f, font=("Consolas", 9), state="disabled", wrap="none")
        self.txt_log.pack(fill="both", expand=True)
        self._refresh_log()

    # ------------------------------------------------------------------ actions
    def _save_tiktok(self) -> None:
        h = self.ent_tiktok.get().strip().lstrip("@")
        write_env({"TIKTOK_UNIQUE_ID": h})
        self.log(f"TikTok handle saved: @{h}. Connect the chat from the operator console once you are LIVE.")

    def _save_settings(self) -> None:
        write_env({k: e.get().strip() for k, e in self.setting_entries.items()})
        self.log("Settings saved.")

    def start(self) -> None:
        if not process.venv_ready():
            messagebox.showerror(TITLE, "The Python environment is missing. Press 'Install / repair everything' in Setup.")
            return
        if process.teacher_running():
            self.log("The stream is already running.")
            return
        process.start_stream()
        self.log("Stream starting (hub, teacher, stage window). First start downloads the voice model; give it a minute.")

    def stop(self) -> None:
        n = process.stop_stream()
        self.log(f"Stopped {n} process(es)." if n else "Nothing was running.")

    def do_update(self) -> None:
        if self.busy:
            return
        self.job(updater.update, after=self._after_update)

    def _after_update(self, ok: bool) -> None:
        self.lbl_version.configure(text=updater.current_version())
        self.lbl_update.configure(text="")
        self.update_state = None
        if ok:
            self.log("Update applied. If the launcher itself changed, close and reopen it to pick that up.")

    # ------------------------------------------------------------------ background jobs
    def job(self, fn, after=None) -> None:
        if self.busy:
            self.log("Another task is still running; wait for it to finish.")
            return
        self.busy = True

        def work():
            ok = False
            try:
                ok = bool(fn(self.log))
            except Exception as exc:  # noqa: BLE001
                self.log(f"error: {exc}")
            finally:
                self.busy = False
                self.q.put(("done", (after, ok)))
        threading.Thread(target=work, daemon=True).start()

    def log(self, line: str) -> None:
        self.q.put(("log", line))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.out.configure(state="normal")
                    self.out.insert("end", time.strftime("%H:%M:%S ") + str(payload) + "\n")
                    self.out.see("end")
                    self.out.configure(state="disabled")
                elif kind == "done":
                    after, ok = payload
                    self.lbl_brain.configure(text="Status: " + setup_steps.brain_summary())
                    if after:
                        after(ok)
        except queue.Empty:
            pass
        self.root.after(200, self._pump)

    # ------------------------------------------------------------------ polling
    def _poll_status(self) -> None:
        running = process.teacher_running()
        h = process.hub_health() if running else None
        if running and h:
            self.lbl_status.configure(text=f"Stream: RUNNING   (stage windows {h.get('stages', 0)}, controllers {h.get('controllers', 0)})", foreground="#1a7f37")
        elif running:
            self.lbl_status.configure(text="Stream: starting...", foreground="#b8860b")
        else:
            self.lbl_status.configure(text="Stream: stopped", foreground="#a40000")
        if self.nb.index(self.nb.select()) == 3:
            self._refresh_log()
        self.root.after(POLL_STATUS_S * 1000, self._poll_status)

    def _refresh_log(self) -> None:
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("end", process.tail_log(80))
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _poll_updates(self, manual: bool = False) -> None:
        def work():
            st = updater.check()
            self.update_state = st
            if manual or st.behind:
                self.log(f"Updates: {st.message}" + (f"   you: {st.local}   latest: {st.remote}" if st.ok and st.behind else ""))
            self.root.after(0, self._show_update_badge)
        threading.Thread(target=work, daemon=True).start()
        if not manual:
            self.root.after(POLL_UPDATES_S * 1000, self._poll_updates)

    def _show_update_badge(self) -> None:
        st = self.update_state
        if st and st.ok and st.behind:
            self.lbl_update.configure(text=f"Update available: {st.behind} new change(s)  ->  press Update now")
            if self.var_auto.get() and not process.teacher_running() and not self.busy:
                self.log("Auto-update: installing now (stream is stopped).")
                self.do_update()
        else:
            self.lbl_update.configure(text="")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    App().run()
