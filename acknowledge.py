"""One-time acknowledgement of DISCLAIMER.md before the tools will run.

Acceptance is stored per user (not in the repo) with a fingerprint of the disclaimer text,
so a changed disclaimer is asked for again.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DISCLAIMER = Path(__file__).resolve().parent / "DISCLAIMER.md"
PHRASE = "I UNDERSTAND"


def _record_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "emg10-ecg" / "disclaimer-accepted.json"


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _already_accepted(fp: str) -> bool:
    try:
        return json.loads(_record_path().read_text()).get("sha256") == fp
    except (OSError, ValueError):
        return False


def _record(fp: str, how: str):
    path = _record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "sha256": fp,
        "accepted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "how": how,
    }, indent=2))


def require_acknowledgement(accept_flag: bool = False):
    """Return if the current disclaimer has been accepted; otherwise ask, or exit."""
    text = DISCLAIMER.read_text()
    fp = _fingerprint(text)
    if _already_accepted(fp):
        return
    if accept_flag:
        _record(fp, "--accept-disclaimer")
        print(f"Disclaimer acceptance recorded in {_record_path()}", file=sys.stderr)
        return
    if not sys.stdin.isatty():
        sys.exit("Read DISCLAIMER.md, then run again with --accept-disclaimer to accept it.")
    print(text, file=sys.stderr)
    print(f"\nTo continue, type {PHRASE} (anything else exits): ", end="", file=sys.stderr, flush=True)
    try:
        answer = input()
    except EOFError:
        answer = ""
    if answer.strip().upper() != PHRASE:
        sys.exit("Not accepted; exiting.")
    _record(fp, "interactive prompt")
    print(f"Acceptance recorded in {_record_path()}\n", file=sys.stderr)
