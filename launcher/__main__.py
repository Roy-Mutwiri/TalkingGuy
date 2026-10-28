from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _main() -> None:
    try:
        from launcher.gui import main
        main()
    except Exception:  # noqa: BLE001
        (ROOT / "logs").mkdir(exist_ok=True)
        (ROOT / "logs" / "launcher.err").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            import tkinter.messagebox as mb
            mb.showerror("Talking Trading Guy", "The launcher crashed. Details: logs\\launcher.err")
        except Exception:  # noqa: BLE001
            pass
        raise


if __name__ == "__main__":
    _main()
