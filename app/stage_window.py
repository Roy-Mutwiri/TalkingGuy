"""Standalone window for the stage (and the operator console). No browser involved.

    python -m app.stage_window                 # the stage window LIVE Studio captures: a true 1080x1920, full resolution
    python -m app.stage_window --fit-screen    # fallback: largest 9:16 that fits the screen, page scaled to match
    python -m app.stage_window --console       # the operator console window
    python -m app.stage_window --fit           # half-size framed preview
    python -m app.stage_window --framed        # with a normal title bar (default: frameless, clean capture)

The window is a native Win32 window hosting the Windows WebView2 runtime (ships with Windows 11),
driven by pywebview.

Full resolution: Windows normally clamps a window to the screen height. We lift the WinForms maximum
size on the UI thread and position the window with SetWindowPos(SWP_NOSENDCHANGING), which gives a
real 1080x1920 window at device scale 1 even on a 1440 px screen; the part below the screen edge is
still rendered and LIVE Studio's window capture picks up the whole window. If that ever fails, the
process relaunches itself with --fit-screen (scaled, always visible).

A watcher waits for the hub to answer on /health, then loads the page, and reloads it if the hub goes
away and comes back. Window titles: "Talking Trading Guy" / "Talking Trading Guy Console".
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time
import urllib.request

STAGE_TITLE = "Talking Trading Guy"
CONSOLE_TITLE = "Talking Trading Guy Console"
STAGE_W, STAGE_H = 1080, 1920

BOOT_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>html,body{{margin:0;height:100%;background:#0b0e14;color:#9aa3b2;font:500 15px "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif}}
.c{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}}
.m{{width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,#2962ff,#089981);display:grid;place-items:center;font-weight:800;color:#fff;letter-spacing:.5px}}
.d{{width:8px;height:8px;border-radius:50%;background:#2962ff;animation:p 1.2s infinite}}@keyframes p{{50%{{opacity:.25}}}}</style></head>
<body><div class="c"><div class="m">TTG</div><div id="s">Starting the chart room…</div><div class="d"></div></div></body></html>"""


def hub_ok(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def stage_geometry(screen_w: int, screen_h: int, margin: int = 0) -> tuple[int, int, float]:
    """Largest 9:16 window that fits the screen, and the device scale that maps 1080x1920 onto it."""
    h = min(STAGE_H, screen_h - margin)
    scale = h / STAGE_H
    w = round(STAGE_W * scale)
    if w > screen_w:
        w = screen_w
        scale = w / STAGE_W
        h = round(STAGE_H * scale)
    return w, h, scale


def force_window_size(window, w: int, h: int, x: int, y: int) -> bool:
    """Make the native window exactly w x h even if that is taller than the screen."""
    try:
        import clr  # noqa: F401  (pythonnet, present with pywebview on Windows)
        from System import Action
        from System.Drawing import Size

        form = window.native
        hwnd = int(form.Handle.ToInt64())

        def on_ui() -> None:
            form.MaximumSize = Size(32000, 32000)
            form.MinimumSize = Size(0, 0)

        form.Invoke(Action(on_ui))
        swp_nozorder, swp_noactivate, swp_nosendchanging = 0x0004, 0x0010, 0x0400
        ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, w, h, swp_nozorder | swp_noactivate | swp_nosendchanging)
        time.sleep(0.8)
        rc = wt.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rc))
        return (rc.right - rc.left) == w and (rc.bottom - rc.top) == h
    except Exception:  # noqa: BLE001
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Talking Trading Guy standalone window")
    ap.add_argument("--console", action="store_true", help="open the operator console instead of the stage")
    ap.add_argument("--progress", action="store_true", help="open the live build-progress board")
    ap.add_argument("--fit-screen", action="store_true", help="scale the stage to the screen instead of a true 1080x1920 window")
    ap.add_argument("--fit", action="store_true", help="half-size framed preview of the stage")
    ap.add_argument("--framed", action="store_true", help="normal window frame (default is frameless for a clean capture)")
    ap.add_argument("--port", type=int, default=int(os.getenv("HUB_PORT", "8000")))
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    a = ap.parse_args()

    try:
        import webview
    except ImportError:
        sys.exit("pywebview is not installed: .venv\\Scripts\\python -m pip install pywebview")

    base = f"http://127.0.0.1:{a.port}"
    full = False
    if a.progress:
        url, title, w, h, frameless, scale = f"{base}/progress", "Talking Trading Guy Progress", 1000, 900, False, 1.0
        a.console = True       # same window behaviour as the console (framed, resizable, no fit logic)
    elif a.console:
        url, title, w, h, frameless, scale = f"{base}/console", CONSOLE_TITLE, 560, 860, False, 1.0
    else:
        screen = webview.screens[0]
        url, title, frameless = f"{base}/stage", STAGE_TITLE, not a.framed
        if a.fit:
            w, h, scale = stage_geometry(screen.width, screen.height, margin=56)
            frameless, w, h, scale = False, round(w / 2), round(h / 2), scale / 2
        elif a.fit_screen or os.getenv("STAGE_FIT_SCREEN"):
            w, h, scale = stage_geometry(screen.width, screen.height, margin=56)
        else:
            w, h, scale, full = STAGE_W, STAGE_H, 1.0, True
    if scale != 1.0:
        # WebView2 honours this; the page keeps its 1080x1920 CSS layout and renders at `scale` physical px per CSS px
        extra = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (extra + f" --force-device-scale-factor={scale:.5f}").strip()
    window = webview.create_window(title, html=BOOT_HTML.format(title=title), width=w, height=h, x=a.x, y=a.y,
                                   resizable=True, frameless=frameless, easy_drag=False,
                                   background_color="#0b0e14", text_select=False)

    def fit_viewport() -> None:
        """Scaled mode: Windows trims a few pixels from the window we asked for; grow it so the page is exactly 1080x1920 CSS px."""
        for _ in range(10):
            time.sleep(1.5)
            try:
                vw, vh = window.evaluate_js("[window.innerWidth, window.innerHeight]")
            except Exception:  # noqa: BLE001
                continue
            if vw and vh:
                if abs(vw - STAGE_W) <= 1 and abs(vh - STAGE_H) <= 1:
                    return
                try:   # resize() sets the client size directly; create_window() had subtracted an invisible frame
                    window.resize(round(window.width + (STAGE_W - vw) * scale), round(window.height + (STAGE_H - vh) * scale))
                except Exception:  # noqa: BLE001
                    return
                time.sleep(1.0)

    def follow_resize() -> None:
        """The window may be resized by hand: keep the 1080x1920 page whole by zooming the browser to fit the client area."""
        try:
            import clr  # noqa: F401
            from System import EventHandler

            form = window.native
            browser = getattr(form, "browser", None)
            control = getattr(browser, "webview", None)
            if control is None:
                return
            # a frameless window has no edges to grab: give it a sizing border (invisible on Windows 11) so it can be
            # resized by dragging any edge or corner, while staying borderless for LIVE Studio
            try:
                from System import Action

                def add_sizing_border() -> None:
                    u = ctypes.windll.user32
                    hwnd = wt.HWND(int(form.Handle.ToInt64()))
                    u.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
                    u.GetWindowLongPtrW.restype = ctypes.c_longlong
                    u.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_longlong]
                    u.SetWindowLongPtrW.restype = ctypes.c_longlong
                    gwl_style, ws_thickframe = -16, 0x00040000
                    style = u.GetWindowLongPtrW(hwnd, gwl_style)
                    u.SetWindowLongPtrW(hwnd, gwl_style, style | ws_thickframe)
                    swp = 0x0001 | 0x0002 | 0x0004 | 0x0020      # nosize | nomove | nozorder | framechanged
                    u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp)

                form.Invoke(Action(add_sizing_border))
            except Exception:  # noqa: BLE001
                pass

            def on_resize(sender, args) -> None:
                try:
                    cw, ch = form.ClientSize.Width, form.ClientSize.Height
                    if cw < 50 or ch < 50:
                        return
                    dpr = float(ctypes.windll.user32.GetDpiForWindow(int(form.Handle.ToInt64()))) / 96.0
                    z = min(cw / dpr / STAGE_W, ch / dpr / STAGE_H) / max(scale, 1e-6)
                    control.ZoomFactor = max(0.2, min(2.0, z))
                except Exception:  # noqa: BLE001
                    pass

            form.Resize += EventHandler(on_resize)
        except Exception:  # noqa: BLE001
            pass

    def watcher() -> None:
        """Runs after the GUI is up: size the window, load the page once the hub answers, reload after a hub restart."""
        if not a.console:
            time.sleep(1.2)
            follow_resize()
        if full:
            time.sleep(1.0)
            if not force_window_size(window, STAGE_W, STAGE_H, a.x, a.y):
                # cannot get a true 1080x1920 here: relaunch in scaled mode so the stream is never cut off
                subprocess.Popen([sys.executable, "-m", "app.stage_window", "--fit-screen", *(["--framed"] if a.framed else [])],
                                 cwd=os.getcwd(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                window.destroy()
                return
        loaded, down = False, 0
        while True:
            ok = hub_ok(base)
            if ok and (not loaded or down >= 2):
                try:
                    window.load_url(url)
                    if not loaded and not full and not a.console and not a.fit:
                        fit_viewport()
                    loaded = True
                except Exception:  # noqa: BLE001
                    pass
                down = 0
            elif not ok:
                down += 1
            time.sleep(1.0 if not loaded else 5.0)

    webview.start(watcher, gui="edgechromium", private_mode=False, debug=bool(os.getenv("STAGE_DEBUG")))


if __name__ == "__main__":
    main()
