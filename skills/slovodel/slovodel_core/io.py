"""Bounded, local UTF-8 input and exclusive JSON output.

No network calls. Input text is never logged or included in error messages.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

MAX_INPUT_BYTES = 1_048_576


class DataError(Exception):
    """Sanitized error code; do not attach a filename or input text."""


def read_text(path: str) -> tuple[bytes, str]:
    target = Path(path)
    try:
        if target.is_symlink():
            raise DataError("INPUT_SYMLINK")
        fd = os.open(
            target,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise DataError("INPUT_NOT_REGULAR_FILE")
            if info.st_size > MAX_INPUT_BYTES:
                raise DataError("INPUT_TOO_LARGE")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        finally:
            os.close(fd)
        if len(raw) > MAX_INPUT_BYTES:
            raise DataError("INPUT_TOO_LARGE")
        try:
            return raw, raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise DataError("INPUT_NOT_UTF8") from None
    except DataError:
        raise
    except (OSError, ValueError):
        raise DataError("INPUT_READ_FAILED") from None


def emit_json(payload: str, output: str | None) -> None:
    if output is None:
        # Always UTF-8, independent of the console code page (cp1252/cp437 on
        # Windows cannot encode Cyrillic metric ids such as letter_а_count).
        try:
            buffer = getattr(sys.stdout, "buffer", None)
            if buffer is not None:
                sys.stdout.flush()
                buffer.write((payload + "\n").encode("utf-8"))
                buffer.flush()
            else:
                sys.stdout.write(payload)
                sys.stdout.write("\n")
                sys.stdout.flush()
        except (OSError, UnicodeError):
            raise DataError("OUTPUT_WRITE_FAILED") from None
        return
    try:
        target = Path(output)
        # Exclusive creation means no overwrite and no symlink-following at the
        # final path, including when input and output names coincide.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                fd = -1
                stream.write(payload)
                stream.write("\n")
        except Exception:
            if fd >= 0:
                os.close(fd)
            try:
                target.unlink()
            except OSError:
                pass
            raise
    except (OSError, UnicodeError, ValueError):
        raise DataError("OUTPUT_WRITE_FAILED") from None
