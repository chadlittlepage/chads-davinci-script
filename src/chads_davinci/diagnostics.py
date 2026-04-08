"""Session-start system probe + global exception hook + screenshot helper.

Anything we want every console.log to record about the user's environment
goes here. Keep it small, fast, and side-effect-free — must NEVER trigger
a TCC permission prompt at startup.

This Script and Code created by:
Chad Littlepage
chad.littlepage@gmail.com
323.974.0444
"""

from __future__ import annotations

import locale
import platform
import subprocess
import sys
import traceback
from pathlib import Path

from rich.console import Console

from chads_davinci import __version__

console = Console()


# ----- Public API -----------------------------------------------------------


def write_session_probe() -> None:
    """Write a one-shot system probe to the console (and therefore log)."""
    try:
        lines = [""]
        lines.append("=== System probe ===")
        lines.append(f"  App version:    {__version__}")

        mac_ver = platform.mac_ver()[0] or "unknown"
        try:
            uname_release = platform.uname().release
        except Exception:
            uname_release = ""
        lines.append(
            f"  macOS:          {mac_ver}"
            + (f" (Darwin {uname_release})" if uname_release else "")
        )
        lines.append(f"  Architecture:   {platform.machine()}")
        lines.append(f"  Python:         {sys.version.split()[0]}")
        lines.append(f"  PyObjC:         {_pyobjc_version()}")
        try:
            loc = locale.getlocale()
            lines.append(f"  Locale:         {loc[0] or '?'}.{loc[1] or '?'}")
        except Exception:
            pass

        lines.append(f"  Running from:   {_running_location()}")

        # Display info — best-effort, never fail.
        try:
            from AppKit import NSScreen
            screens = NSScreen.screens() or []
            if screens:
                main = NSScreen.mainScreen()
                if main:
                    f = main.frame()
                    bsf = float(main.backingScaleFactor())
                    lines.append(
                        f"  Display:        {len(screens)} screen(s); "
                        f"primary {int(f.size.width)}x{int(f.size.height)} @{bsf:.0f}x"
                    )
        except Exception:
            pass

        # Bundled binaries
        for tool in ("mediainfo", "ffprobe"):
            lines.append(f"  bin/{tool}: {_bundled_tool_summary(tool)}")

        lines.append("")
        for line in lines:
            console.print(line)
    except Exception as e:
        # Never let the probe break the app.
        console.print(f"[dim]System probe failed: {e}[/dim]")


def install_global_exception_hook() -> None:
    """Route any unhandled exception through the rich console so the full
    traceback lands in console.log instead of being lost behind py2app's
    bare 'fatal error' dialog.

    Covers three exception sources:
      1. sys.excepthook — catches every uncaught Python exception,
         including PyObjC-wrapped NSException (PyObjC translates
         NSException → ObjCException, which is a Python exception).
      2. threading.excepthook — catches exceptions raised in
         non-main threads (Python 3.8+).
      3. asyncio handler (no-op for now; we don't use asyncio).
    """
    def _format(exc_type, exc_value, exc_tb) -> str:
        return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    prev = sys.excepthook

    def _sys_hook(exc_type, exc_value, exc_tb):
        try:
            console.print("[red bold]=== Unhandled exception (main thread) ===[/red bold]")
            console.print(_format(exc_type, exc_value, exc_tb))
        except Exception:
            pass
        try:
            prev(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _sys_hook

    # Background-thread exceptions (Python 3.8+).
    try:
        import threading

        def _thread_hook(args):
            try:
                console.print(
                    f"[red bold]=== Unhandled exception in thread "
                    f"{args.thread.name if args.thread else '?'} ===[/red bold]"
                )
                console.print(_format(args.exc_type, args.exc_value, args.exc_traceback))
            except Exception:
                pass

        threading.excepthook = _thread_hook
    except Exception:
        pass


def log_resolve_connection(ctx) -> None:
    """Log Resolve API state right after a connect()."""
    try:
        resolve = getattr(ctx, "resolve", None)
        if resolve is None:
            return
        version = "?"
        try:
            v = resolve.GetVersionString()
            if v:
                version = v
        except Exception:
            try:
                v = resolve.GetVersion()
                if v:
                    version = ".".join(str(x) for x in v)
            except Exception:
                pass
        product = "?"
        try:
            product = resolve.GetProduct()
        except Exception:
            pass
        console.print("=== Resolve API connected ===")
        console.print(f"  Product:    {product}")
        console.print(f"  Version:    {version}")
        try:
            db_count = len(ctx.project_manager.GetDatabaseList() or [])
            console.print(f"  Databases:  {db_count}")
        except Exception:
            pass
        console.print("")
    except Exception as e:
        console.print(f"[dim]Resolve probe failed: {e}[/dim]")


def log_tool_version(tool_name: str, tool_path: str | None) -> None:
    """Log the --version line of a bundled CLI tool the first time we use it."""
    if not tool_path:
        return
    flag = "-version" if tool_name == "ffprobe" else "--Version"
    try:
        out = subprocess.run(
            [tool_path, flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        first_line = (out.stdout or out.stderr or "").splitlines()
        if first_line:
            console.print(f"[dim]{tool_name}: {first_line[0].strip()}[/dim]")
    except Exception as e:
        console.print(f"[dim]{tool_name}: version check failed: {e}[/dim]")


def capture_app_screenshot(target_path: Path | str) -> Path | None:
    """Capture a PNG screenshot of the app's main window to `target_path`.
    Returns the saved Path on success, None on failure.

    Tries window-specific capture first (no chrome from other apps); falls
    back to full-screen capture if the main window can't be located.
    """
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from AppKit import NSApp
        win = None
        try:
            win = NSApp.mainWindow() or NSApp.keyWindow()
        except Exception:
            pass
        if win is not None:
            try:
                window_number = int(win.windowNumber())
                if window_number > 0:
                    # -l = capture by window ID, -o = no shadow,
                    # -x = no sound (-l implies it but be explicit)
                    result = subprocess.run(
                        ["screencapture", "-l", str(window_number), "-o", "-x", str(target)],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=10,
                    )
                    if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
                        return target
            except Exception:
                pass
        # Fallback: full-screen capture (interactive screenshot would need user action)
        result = subprocess.run(
            ["screencapture", "-x", str(target)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            return target
    except Exception as e:
        console.print(f"[dim]Screenshot failed: {e}[/dim]")
    return None


# ----- Internals ------------------------------------------------------------


def _pyobjc_version() -> str:
    try:
        import objc
        return getattr(objc, "__version__", "unknown")
    except Exception:
        return "not installed"


def _running_location() -> str:
    """Best-effort guess at where the app is being launched from."""
    try:
        from AppKit import NSBundle
        b = NSBundle.mainBundle()
        if b is not None:
            p = b.bundlePath()
            if p:
                return str(p)
    except Exception:
        pass
    return sys.executable


def _bundled_tool_summary(tool_name: str) -> str:
    """One-line summary of a bundled binary: existence, size, arch."""
    try:
        # Resolve via metadata._find_bundled_tool to use the same lookup
        # path the app uses at runtime.
        from chads_davinci.metadata import _find_bundled_tool  # type: ignore
        path = _find_bundled_tool(tool_name)
    except Exception:
        path = None
    if not path:
        return "(not found)"
    p = Path(path)
    if not p.exists():
        return f"{path} (missing)"
    size_mb = p.stat().st_size / (1024 * 1024)
    arch = "?"
    try:
        out = subprocess.run(
            ["file", str(p)], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=3,
        )
        text = out.stdout.lower()
        if "universal" in text:
            arch = "universal"
        elif "arm64" in text:
            arch = "arm64"
        elif "x86_64" in text:
            arch = "x86_64"
    except Exception:
        pass
    return f"{p} ({arch}, {size_mb:.0f} MB)"
