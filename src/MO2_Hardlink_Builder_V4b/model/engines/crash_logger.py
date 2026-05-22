"""
Crash logger for worker thread unhandled exceptions.
This module must never raise its own exceptions — all operations are wrapped.
"""
import logging
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def write_crash_log(
    exc: BaseException,
    standalone_path: str = None,
    fallback_path: str = None,
    profile_name: str = "Unknown",
    build_config: dict = None,
) -> str | None:
    """
    Writes a crash_log_<timestamp>.txt file.
    Returns the path to the written log, or None if write failed.

    This function never raises. All errors are suppressed.
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"crash_log_{timestamp}.txt"

        # Choose write location: standalone root → fallback → temp
        write_dir = None
        for candidate in [standalone_path, fallback_path]:
            if candidate:
                try:
                    p = Path(candidate)
                    p.mkdir(parents=True, exist_ok=True)
                    write_dir = p
                    break
                except Exception:
                    pass

        if write_dir is None:
            import tempfile
            write_dir = Path(tempfile.gettempdir())

        log_path = write_dir / filename

        lines = [
            "=" * 80,
            "MO2 HARDLINK BUILDER — CRASH LOG",
            f"Timestamp      : {datetime.now().isoformat()}",
            f"Python Version : {sys.version}",
            f"Platform       : {platform.platform()}",
            f"MO2 Profile    : {profile_name}",
            "",
            "Build Config:",
        ]

        if build_config:
            for k, v in build_config.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append("  (not available)")

        lines += [
            "",
            "Exception Type  : " + type(exc).__name__,
            "Exception Value : " + str(exc),
            "",
            "Full Traceback:",
            "-" * 40,
            traceback.format_exc(),
            "=" * 80,
        ]

        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info("Crash log written: %s", log_path)
        return str(log_path)

    except Exception:
        return None


def crash_safe(func):
    """
    Decorator that wraps a worker run() method.
    On any unhandled exception: writes crash log and emits finished_signal(False, msg).
    The decorated method must have self.finished_signal and optionally
    self._crash_logger_kwargs() returning kwargs for write_crash_log.
    """
    import functools

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as exc:
            try:
                kw = {}
                if hasattr(self, "_crash_logger_kwargs"):
                    kw = self._crash_logger_kwargs()
                log_path = write_crash_log(exc, **kw)
                msg = f"[CRASH] {type(exc).__name__}: {exc}"
                if log_path:
                    msg += f"\nCrash log: {log_path}"
                if hasattr(self, "finished_signal"):
                    self.finished_signal.emit(False, msg)
                elif hasattr(self, "progress_signal"):
                    self.progress_signal.emit(msg)
            except Exception:
                pass

    return wrapper
